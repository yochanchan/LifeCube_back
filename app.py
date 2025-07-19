from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# apiルーター（フォルダ）が増えたら行追加する
from api.common import router as common_router
from api.openai import router as openai_router
from api.apitest import router as apitest_router

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
app.include_router(apitest_router)