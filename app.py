from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# apiルーター（フォルダ）が増えたら行追加する
from api.common import router as common_router
from api.openai import router as openai_router
from api.apitest_eiko import router as apitest_eiko_router
from api.apitest_hama import router as apitest_hama_router
from api.apitest_yuka import router as apitest_yuka_router
from api.apitest_yoch import router as apitest_yoch_router
from api.ws_test import router as wb_test_router


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
app.include_router(apitest_hama_router)
app.include_router(apitest_yuka_router)
app.include_router(apitest_eiko_router)
app.include_router(apitest_yoch_router)
app.include_router(wb_test_router)