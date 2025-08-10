# backend/api/auth.py
from __future__ import annotations

from dataclasses import asdict
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from db_control.connect import engine
from db_control.mymodels import Account
from auth.session import (
    create_session,
    set_session_cookie,
    clear_session_cookie,
    destroy_session,
    get_session,
    require_session,
    rotate_session,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# ─────────────────────────────────────────
# DB セッション
# ─────────────────────────────────────────
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ─────────────────────────────────────────
# 入出力スキーマ
# ─────────────────────────────────────────
class SignupBody(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def check_pw_len(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError("password must be at least 3 chars")
        return v

class LoginBody(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

class MeOut(BaseModel):
    account_id: int
    email: str
    role: str

# ─────────────────────────────────────────
# ユーティリティ
# ─────────────────────────────────────────
def _hash_password(raw: str) -> bytes:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt(rounds=12))

def _verify_password(raw: str, hashed: bytes) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed)
    except Exception:
        return False

# ─────────────────────────────────────────
# /auth/signup
# ─────────────────────────────────────────
@router.post("/signup", response_model=MeOut, status_code=201)
def signup(body: SignupBody, response: Response, db: Session = Depends(get_db)):
    # 既存メール重複チェック（emailは小文字一意運用）
    exists = db.execute(select(Account).where(Account.email == body.email)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="email already registered")

    pw_hash = _hash_password(body.password)

    acc = Account(email=body.email, password_hash=pw_hash, role="user")
    db.add(acc)
    db.flush()  # id 採番

    # ログイン状態にして返す（セッション発行）
    sess = create_session(account_id=acc.id, role=acc.role)
    set_session_cookie(response, sess)

    return MeOut(account_id=acc.id, email=acc.email, role=acc.role)

# ─────────────────────────────────────────
# /auth/login
# ─────────────────────────────────────────
@router.post("/login", response_model=MeOut)
def login(body: LoginBody, response: Response, db: Session = Depends(get_db)):
    acc = db.execute(select(Account).where(Account.email == body.email)).scalar_one_or_none()
    if not acc or not acc.password_hash:
        raise HTTPException(status_code=401, detail="invalid credentials")

    if not _verify_password(body.password, acc.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")

    # 既存セッションがあればローテーション、なければ新規
    new_sess = create_session(account_id=acc.id, role=acc.role)
    set_session_cookie(response, new_sess)

    return MeOut(account_id=acc.id, email=acc.email, role=acc.role)

# ─────────────────────────────────────────
# /auth/logout
# ─────────────────────────────────────────
@router.post("/logout")
def logout(request: Request, response: Response):
    s = get_session(request, touch=False)
    if s:
        destroy_session(s.session_id)
    clear_session_cookie(response)
    return {"ok": True}

# ─────────────────────────────────────────
# /auth/me
# ─────────────────────────────────────────
@router.get("/me", response_model=MeOut)
def me(request: Request, db: Session = Depends(get_db)):
    s = require_session(request)
    # email は DB から取得（セッションには持っていない方針のため）
    acc = db.get(Account, s.account_id)
    if not acc:
        # アカウントが消されていた等
        raise HTTPException(status_code=401, detail="account not found")
    return MeOut(account_id=acc.id, email=acc.email, role=acc.role)
