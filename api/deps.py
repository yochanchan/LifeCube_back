# backend/api/deps.py
from __future__ import annotations

import os
from typing import Final
from pydantic import BaseModel

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
from jose.exceptions import JWTError

class CurrentUser(BaseModel):
    account_id: int
    role: str | None = None

bearer = HTTPBearer(auto_error=True)

_secret = os.getenv("JWT_SECRET")
if not _secret:
    raise RuntimeError("JWT_SECRET is not set")
SECRET: Final[str] = _secret
ALG: Final[str] = "HS256"

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> CurrentUser:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALG])
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=401, detail="invalid token (no sub)")
        return CurrentUser(account_id=int(sub), role=payload.get("role"))
    except JWTError:
        raise HTTPException(status_code=401, detail="invalid token")
