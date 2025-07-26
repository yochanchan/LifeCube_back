from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from uuid import uuid4
from typing import Dict, List
import json

router = APIRouter(prefix="/ws_test", tags=["websocket_test"])

class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, WebSocket] = {}

    async def connect(self, cid: str, ws: WebSocket):
        await ws.accept()
        self.active[cid] = ws

    def disconnect(self, cid: str):
        self.active.pop(cid, None)

    async def broadcast(self, msg: dict):
        dead = []
        for cid, ws in self.active.items():
            try:
                await ws.send_json(msg)          # ← 辞書は send_json で送信
            except WebSocketDisconnect:
                dead.append(cid)
        for cid in dead:                         # ← 切断済みをクリーンアップ
            self.disconnect(cid)

manager = ConnectionManager()
history: List[dict] = []

@router.websocket("/ws/{client_id}")
async def socket(ws: WebSocket, client_id: str):
    await manager.connect(client_id, ws)

    # 既存履歴を新規クライアントへ送信
    for msg in history:
        await ws.send_json(msg)

    try:
        while True:
            msg = await ws.receive_json()

            # ★ delete 以外は必ず id を補完
            if msg["type"] != "delete":
                msg.setdefault("id", str(uuid4()))

            if msg["type"] == "chat":
                history.append(msg)
            elif msg["type"] == "delete":
                history[:] = [m for m in history if m["id"] != msg["id"]]

            await manager.broadcast(msg)

    except WebSocketDisconnect:
        manager.disconnect(client_id)
