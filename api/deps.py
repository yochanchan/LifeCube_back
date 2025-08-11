# backend/api/deps.py
from __future__ import annotations

from dataclasses import dataclass
from fastapi import Depends, HTTPException, Request, status

from auth.session import get_session  # Cookieからセッションを取り出す

@dataclass
class CurrentUser:
    account_id: int
    role: str  # "admin" or "user"

def get_current_user(request: Request) -> CurrentUser:
    """
    クッキーセッション必須。未ログインなら 401。
    ログイン済みなら account_id / role を返す。
    """
    s = get_session(request)
    if not s:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return CurrentUser(account_id=s.account_id, role=s.role)
