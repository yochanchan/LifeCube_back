# backend/app.py
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.pictures import router as pictures_router
from auth.routes import router as auth_router
from ws.router import router as ws_router                # /ws（WebSocket）
from api.azure_speech import router as azure_speech_router
from ws.manager import manager                           # ← lifecycle で start/stop を呼ぶ

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # アプリ起動時（イベントループ確立後）
    manager.start()
    try:
        yield
    finally:
        # アプリ終了時
        await manager.stop()

app = FastAPI(lifespan=lifespan)

# CORS の設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://app-002-gen10-step3-2-node-oshima10.azurewebsites.net",
        "https://app-lifecube-frontend.azurewebsites.net",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def hello():
    return {"message": "hello!"}

app.include_router(pictures_router)
app.include_router(auth_router)
app.include_router(ws_router)
app.include_router(azure_speech_router)
