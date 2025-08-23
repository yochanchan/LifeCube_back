# backend/auth/routes.py
from __future__ import annotations

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from db_control.connect import get_db
from db_control.mymodels import Account
from auth.security import create_access_token, new_refresh_record, hash_refresh
from api.deps import get_current_user, CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])

# ─────────────────────────────────────────
# DTO（PoC最小：重複メール以外の厳格チェックなし）
# ─────────────────────────────────────────
class SignupIn(BaseModel):
    email: str
    password: str

class LoginIn(BaseModel):
    email: str
    password: str

class RefreshIn(BaseModel):
    refresh_token: str

class LogoutIn(BaseModel):
    jti: str

class MeOut(BaseModel):
    account_id: int
    email: str
    role: str

# ─────────────────────────────────────────
# /auth/signup  …メール重複のみチェック、作成後すぐトークン返却
# ─────────────────────────────────────────
@router.post("/signup")
def signup(body: SignupIn, db: Session = Depends(get_db)):
    email_norm = body.email.strip().lower()
    exists = db.execute(select(Account).where(Account.email == email_norm)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="email already registered")

    pw_hash: bytes = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt())

    # INSERT 群 → commit
    acc = Account(email=email_norm, password_hash=pw_hash, role="user")
    db.add(acc)
    db.flush()  # id 採番

    rec, refresh_raw = new_refresh_record(account_id=acc.id)
    db.execute(text(
        "INSERT INTO refresh_tokens (jti, account_id, token_hash, issued_at, expires_at) "
        "VALUES (:jti, :account_id, :token_hash, :issued_at, :expires_at)"
    ), rec)
    db.commit()

    access = create_access_token(sub=acc.id, role=acc.role)
    return {  # /login と同じ形式
        "token_type": "Bearer",
        "access_token": access,
        "expires_in": 60 * 15,
        "refresh_token": refresh_raw,
        "jti": rec["jti"],
    }

# ─────────────────────────────────────────
# /auth/login  …JWTを返す（access + refresh）
# ─────────────────────────────────────────
@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    email_norm = body.email.strip().lower()

    acc = db.execute(select(Account).where(Account.email == email_norm)).scalar_one_or_none()
    if not acc or not acc.password_hash:
        raise HTTPException(status_code=401, detail="invalid credentials")

    if not bcrypt.checkpw(body.password.encode("utf-8"), acc.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")

    access = create_access_token(sub=acc.id, role=acc.role)
    rec, refresh_raw = new_refresh_record(account_id=acc.id)

    db.execute(
        text("""INSERT INTO refresh_tokens
                (jti, account_id, token_hash, issued_at, expires_at)
                VALUES (:jti, :account_id, :token_hash, :issued_at, :expires_at)"""),
        rec,
    )
    db.commit()

    return {
        "token_type": "Bearer",
        "access_token": access,
        "expires_in": 60 * 15,  # 必要なら auth.security.ACCESS_MIN を返却してもOK
        "refresh_token": refresh_raw,
        "jti": rec["jti"],
    }

# ─────────────────────────────────────────
# /auth/refresh  …refresh_token から新しい access を返す
# ─────────────────────────────────────────
@router.post("/refresh")
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    if not body.refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token required")

    # 有効なrefreshのみをサーバ時刻で抽出（UTC_TIMESTAMP(6)）
    row = db.execute(
        text("""SELECT jti, account_id
                FROM refresh_tokens
                WHERE token_hash=:h
                  AND revoked_at IS NULL
                  AND expires_at > UTC_TIMESTAMP(6)
                LIMIT 1"""),
        {"h": hash_refresh(body.refresh_token)},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=401, detail="invalid or expired refresh")

    # last_used_at を更新 → commit
    db.execute(
        text("UPDATE refresh_tokens SET last_used_at=UTC_TIMESTAMP(6) WHERE jti=:j"),
        {"j": row["jti"]},
    )
    db.commit()

    # role を取り直す（権限変更を反映）
    acc = db.get(Account, row["account_id"])
    role = acc.role if acc else "user"

    access = create_access_token(sub=row["account_id"], role=role)
    return {"token_type": "Bearer", "access_token": access, "expires_in": 60 * 15}

# ─────────────────────────────────────────
# /auth/logout  …対象の refresh を失効させる
# ─────────────────────────────────────────
@router.post("/logout")
def logout(body: LogoutIn, db: Session = Depends(get_db)):
    if not body.jti:
        raise HTTPException(status_code=400, detail="jti required")

    db.execute(
        text("""UPDATE refresh_tokens
                SET revoked_at=UTC_TIMESTAMP(6), revoked_reason='logout'
                WHERE jti=:j"""),
        {"j": body.jti},
    )
    db.commit()
    return {"ok": True}

# ─────────────────────────────────────────
# /auth/me  …JWTからユーザを特定し、DBのemailを返す（互換用）
# ─────────────────────────────────────────
@router.get("/me", response_model=MeOut)
def me(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = db.get(Account, user.account_id)            # ← 属性アクセスに修正
    if not acc:
        raise HTTPException(status_code=401, detail="account not found")
    return MeOut(account_id=acc.id, email=acc.email, role=acc.role)
