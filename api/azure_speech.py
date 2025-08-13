# backend/api/azure_speech.py
from __future__ import annotations

import os
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import get_current_user, CurrentUser  # 認証必須

# ほかで /speech を使用中のため、ここは /azurespeech
router = APIRouter(prefix="/azurespeech", tags=["azure_speech"])

# 環境変数:
#   AZURE_SPEECH_REGION (例: "japaneast")
#   AZURE_SPEECH_KEY or (AZURE_SPEECH_KEY1 / AZURE_SPEECH_KEY2)
REGION_DEFAULT = os.getenv("AZURE_SPEECH_REGION", "japaneast")

def _pick_key() -> str:
    k = os.getenv("AZURE_SPEECH_KEY")
    if k:
        return k
    k1 = os.getenv("AZURE_SPEECH_KEY1")
    k2 = os.getenv("AZURE_SPEECH_KEY2")
    if k1:
        return k1
    if k2:
        return k2
    raise RuntimeError("Azure Speech key not configured")

async def _issue_token(region: str, api_key: str) -> str:
    # Azure STS: https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken
    url = f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    async with httpx.AsyncClient(timeout=8) as cx:
        r = await cx.post(url, headers=headers)
    if r.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"token issue failed ({r.status_code})",
        )
    return r.text

@router.post("/token")
async def issue_speech_token(
    current: CurrentUser = Depends(get_current_user),  # ← ログイン必須
    region: Optional[str] = None,
):
    # リージョンはクエリで上書き可（将来の多リージョン対応）
    region_final = (region or REGION_DEFAULT).strip().lower()
    api_key = _pick_key()
    token = await _issue_token(region_final, api_key)

    # Azureの発行トークンは通常 ~10分有効。
    # クライアントでは “安全側” に 55秒で更新する運用とし、expires_at も短く返す。
    now = int(time.time())
    return {
        "token": token,
        "region": region_final,
        "expires_at": now + 55,  # 55秒後に再取得を推奨
    }
