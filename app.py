# backend/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.pictures import router as pictures_router
from api.auth import router as auth_router
from ws.router import router as ws_router                # /ws（WebSocket）
from api.azure_speech import router as azure_speech_router


app = FastAPI()

# CORSの設定 フロントエンドからの接続を許可する部分
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://app-002-gen10-step3-2-node-oshima10.azurewebsites.net"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/")
def hello():
    return {"message": "hello!"}

app.include_router(pictures_router)
app.include_router(auth_router)
app.include_router(ws_router)
app.include_router(azure_speech_router)
