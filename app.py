from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# apiルーター（フォルダ）が増えたら行追加する
from api.common import router as common_router
from api.openai import router as openai_router
from api.ws_test import router as ws_test_router
from api.speech_test import router as speech_test_router
from api.pictures import router as pictures_router
from api.auth import router as auth_router
from api.camera_ws import router as camera_ws_router
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
    return {"message": "FastAPI hello!"}

# apiルーター（フォルダ）が増えたら行追加する
app.include_router(common_router)
app.include_router(openai_router)
app.include_router(ws_test_router)
app.include_router(speech_test_router)
app.include_router(pictures_router)
app.include_router(auth_router)
app.include_router(camera_ws_router)
app.include_router(azure_speech_router)