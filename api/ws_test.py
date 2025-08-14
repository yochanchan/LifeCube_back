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

# @router.websocket("/ws/{client_id}")
# async def socket(ws: WebSocket, client_id: str):
#     await manager.connect(client_id, ws)

#     # 既存履歴を新規クライアントへ送信
#     for msg in history:
#         await ws.send_json(msg)

#     try:
#         while True:
#             msg = await ws.receive_json()

#             # ★ delete 以外は必ず id を補完
#             if msg["type"] != "delete":
#                 msg.setdefault("id", str(uuid4()))

#             if msg["type"] == "chat":
#                 history.append(msg)
#             elif msg["type"] == "delete":
#                 history[:] = [m for m in history if m["id"] != msg["id"]]

#             await manager.broadcast(msg)

#     except WebSocketDisconnect:
#         manager.disconnect(client_id)



#沢田つけたし
class Room:
    def __init__(self):
        self.clients: List[WebSocket] = set()
        self.latest_image_base64: str | None = None

rooms: Dict[str, Room] = {}

async def get_room(room_id: str) -> Room:
    if room_id not in rooms:
        rooms[room_id] = Room()
    return rooms[room_id]

@router.get("/")
async def root():
    return {"status": "ok", "message": "WebSocket server running"}

@router.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    room = await get_room(room_id)
    await websocket.accept()
    room.clients.add(websocket)

    # 接続直後、最新画像があればすぐ送る（途中参加のdisplayにも表示される）
    if room.latest_image_base64:
        await websocket.send_text(json.dumps({
            "type": "image",
            "data": room.latest_image_base64
        }))

    try:
        while True:
            message = await websocket.receive_text()
            payload = json.loads(message)

            if payload.get("type") == "image":
                dataurl = payload.get("data")  # 例: "data:image/jpeg;base64,...."
                room.latest_image_base64 = dataurl
                # 他のクライアントへブロードキャスト
                dead_clients = []
                for client in room.clients:
                    try:
                        if client is not websocket:  # 送信者以外にも送る（同じ端末で確認したいならこのifを外す）
                            await client.send_text(json.dumps({"type": "image", "data": dataurl}))
                    except Exception:
                        dead_clients.append(client)
                for dc in dead_clients:
                    room.clients.discard(dc)
            else:
                # 任意のメッセージ種別に拡張可能
                pass

    except WebSocketDisconnect:
        room.clients.discard(websocket)
    except Exception:
        room.clients.discard(websocket)
        # 本番ではログ出力など
