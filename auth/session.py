# backend/auth/session.py
from __future__ import annotations

import os
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Literal, cast

from fastapi import Request, Response, HTTPException

# ─────────────────────────────────────────────────────────────
# 設定（env が無ければ安全なデフォルト）
# ─────────────────────────────────────────────────────────────
COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "lc_session")

IDLE_TIMEOUT = int(os.getenv("SESSION_IDLE_TIMEOUT_SECONDS", str(24 * 3600)))  # 24h
MAX_AGE = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(7 * 24 * 3600)))        # 7d

# Cookie属性
COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "lax").lower()  # lax / strict / none
COOKIE_DOMAIN = os.getenv("SESSION_COOKIE_DOMAIN")  # 通常は None（同一オリジン）。別ドメインで配るなら設定
COOKIE_PATH = "/"

# タイムゾーンはUTCで持つ（アプリはJST運用でも、期限計算はUTCが楽）
UTC = timezone.utc


@dataclass
class SessionData:
    session_id: str
    account_id: int
    role: str                 # 'admin' or 'user'
    created_at: datetime      # セッション作成時刻（UTC）
    last_access_at: datetime  # 最終アクセス時刻（UTC）


# ─────────────────────────────────────────────────────────────
# メモリストア（PoC用）＋スレッドロック
# ─────────────────────────────────────────────────────────────
_STORE: Dict[str, SessionData] = {}
_LOCK = threading.Lock()


def _now() -> datetime:
    return datetime.now(UTC)


# 追加：型安全な SameSite 取得関数
def _samesite_value() -> Optional[Literal['lax', 'strict', 'none']]:
    v = COOKIE_SAMESITE
    if v in ("lax", "strict", "none"):
        # v は実行時は str だが、ここで Literal 型として扱うことを Pylance に明示
        return cast(Literal['lax', 'strict', 'none'], v)
    return None  # 無効値は None として扱う（＝ブラウザ既定）


def _is_expired(s: SessionData) -> bool:
    """アイドル24h または 最大7d を超えたら期限切れ"""
    if (_now() - s.last_access_at).total_seconds() > IDLE_TIMEOUT:
        return True
    if (_now() - s.created_at).total_seconds() > MAX_AGE:
        return True
    return False


def _sweep(probability: float = 0.02) -> None:
    """確率的に期限切れを掃除（アクセス時にたまに呼ぶ）"""
    if secrets.randbelow(100) >= int(probability * 100):
        return
    with _LOCK:
        expired = [k for k, v in _STORE.items() if _is_expired(v)]
        for k in expired:
            _STORE.pop(k, None)


# ─────────────────────────────────────────────────────────────
# セッション操作：作成 / 取得 / タッチ / 再発行 / 破棄
# ─────────────────────────────────────────────────────────────
def create_session(account_id: int, role: str, email: Optional[str] = None) -> SessionData:
    """新しいセッションを作り、メモリに保存して返す。"""
    sid = secrets.token_urlsafe(32)  # 43文字程度のURL安全ランダム
    now = _now()
    s = SessionData(
        session_id=sid,
        account_id=account_id,
        role=role,
        created_at=now,
        last_access_at=now,
    )
    with _LOCK:
        _STORE[sid] = s
    _sweep()
    return s


def get_session_from_id(session_id: Optional[str], *, touch: bool = True) -> Optional[SessionData]:
    """セッションIDから取得。期限切れなら破棄して None を返す。"""
    if not session_id:
        return None
    with _LOCK:
        s = _STORE.get(session_id)
        if not s:
            return None
        if _is_expired(s):
            _STORE.pop(session_id, None)
            return None
        if touch:
            s.last_access_at = _now()
    _sweep()
    return s


def get_session(request: Request, *, touch: bool = True) -> Optional[SessionData]:
    """リクエストの Cookie からセッションを取得。"""
    sid = request.cookies.get(COOKIE_NAME)
    return get_session_from_id(sid, touch=touch)


def require_session(request: Request, *, touch: bool = True) -> SessionData:
    """未ログインなら 401 を投げる依存関数イメージ（手動呼び出し用）。"""
    s = get_session(request, touch=touch)
    if not s:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return s


def rotate_session(old_session: SessionData) -> SessionData:
    """セッション固定化対策：新しいIDを発行し、古いIDを無効にする。"""
    with _LOCK:
        # 古いIDを消して、新IDで保存。created_at は“再ログイン相当”として今にしておく
        _STORE.pop(old_session.session_id, None)
    new = create_session(old_session.account_id, old_session.role)
    return new


def destroy_session(session_id: str) -> None:
    """セッションを破棄（ログアウト）。"""
    with _LOCK:
        _STORE.pop(session_id, None)


# ─────────────────────────────────────────────────────────────
# Cookie ヘルパ
# ─────────────────────────────────────────────────────────────
def set_session_cookie(response: Response, session: SessionData) -> None:
    """レスポンスに Set-Cookie を付与。"""
    # RFC 的には Max-Age だけでOKだが、互換のため Expires も付ける
    expires = session.created_at + timedelta(seconds=MAX_AGE)
    response.set_cookie(
        key=COOKIE_NAME,
        value=session.session_id,
        max_age=MAX_AGE,
        expires=expires,        # datetime 可
        path=COOKIE_PATH,
        domain=COOKIE_DOMAIN,   # 通常 None
        secure=COOKIE_SECURE,
        httponly=True,          # JavaScript から読めない
        samesite=_samesite_value(),  # Literal['lax','strict','none'] | None
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        path=COOKIE_PATH,
        domain=COOKIE_DOMAIN,
    )
