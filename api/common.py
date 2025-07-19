from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/common", tags=["starter"])

# データのスキーマを定義するためのクラス
class EchoMessage(BaseModel):
    message: str | None = None

@router.get("/hello")
def hello_world():
    return {"message": "Hello World by FastAPI"}

@router.get("/multiply/{id}")
def multiply(id: int):
    print("multiply")
    doubled_value = id * 2
    return {"doubled_value": doubled_value}

@router.post("/echo")
def echo(message: EchoMessage):
    print("echo")
    if not message:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    echo_message = message.message if message.message else "No message provided"
    return {"message": f"echo: {echo_message}"}