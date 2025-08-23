# backend/auth/security.py
from __future__ import annotations
import os, time, uuid, secrets, hmac, hashlib
from datetime import datetime, timedelta, timezone
from typing import Final, Tuple
from jose import jwt

SECRET: Final[str] = os.environ["JWT_SECRET"]  # 未設定なら起動時エラーに
ALG: Final[str] = "HS256"
ACCESS_MIN: Final[int] = int(os.getenv("ACCESS_TOKEN_EXPIRES_MIN", "15"))
REFRESH_DAYS: Final[int] = int(os.getenv("REFRESH_TOKEN_EXPIRES_DAYS", "14"))
PEPPER: Final[str] = os.getenv("REFRESH_PEPPER", "dev-pepper")  # PoC可

def create_access_token(sub: int, role) -> str:
    now = int(time.time())
    payload = {"sub": str(sub), "role": role, "iat": now, "exp": now + ACCESS_MIN * 60}
    return jwt.encode(payload, SECRET, algorithm=ALG)

def _hmac_sha256(raw: str) -> bytes:
    return hmac.new(PEPPER.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).digest()

def new_refresh_record(account_id: int) -> Tuple[dict, str]:
    """
    戻り値: (DBにINSERTするdict, クライアントへ返すrefreshの生値)
    """
    raw = secrets.token_urlsafe(48)
    rec = {
        "jti": str(uuid.uuid4()),
        "account_id": account_id,
        "token_hash": _hmac_sha256(raw),
        "issued_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=REFRESH_DAYS),
    }
    return rec, raw

def hash_refresh(raw: str) -> bytes:
    return _hmac_sha256(raw)
