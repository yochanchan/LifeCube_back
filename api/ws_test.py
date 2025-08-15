from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from uuid import uuid4
from typing import Dict, List
import json

router = APIRouter(prefix="/ws_test", tags=["websocket_test"])

class ConnectionManager:
    def __init__(self):
        self.rooms: Dict[str, List[WebSocket]] = {}

    async def connect(self, room_id: str, ws: WebSocket):
        await ws.accept()
        if room_id not in self.rooms:
            self.rooms[room_id] = []
        self.rooms[room_id].append(ws)
        print(f"🔗 クライアントがルーム {room_id} に接続しました")

    def disconnect(self, room_id: str, ws: WebSocket):
        if room_id in self.rooms:
            if ws in self.rooms[room_id]:
                self.rooms[room_id].remove(ws)
            if not self.rooms[room_id]:
                del self.rooms[room_id]
        print(f"🔌 クライアントがルーム {room_id} から切断されました")

    async def broadcast_to_room(self, room_id: str, msg: dict):
        if room_id in self.rooms:
            dead_connections = []
            for ws in self.rooms[room_id]:
                try:
                    await ws.send_json(msg)
                except WebSocketDisconnect:
                    dead_connections.append(ws)
            
            # 切断された接続をクリーンアップ
            for ws in dead_connections:
                self.disconnect(room_id, ws)

manager = ConnectionManager()
history: Dict[str, List[dict]] = {}

@router.websocket("/ws/{room_id}")
async def socket(ws: WebSocket, room_id: str):
    await manager.connect(room_id, ws)

    # ルームの履歴を初期化
    if room_id not in history:
        history[room_id] = []

    # 既存履歴を新規クライアントへ送信
    for msg in history[room_id]:
        try:
            await ws.send_json(msg)
        except WebSocketDisconnect:
            break

    try:
        while True:
            msg = await ws.receive_json()

            # ★ delete 以外は必ず id を補完
            if msg["type"] != "delete":
                msg.setdefault("id", str(uuid4()))

            if msg["type"] == "chat":
                history[room_id].append(msg)
            elif msg["type"] == "photo":
                # 写真メッセージを履歴に保存
                history[room_id].append(msg)
<<<<<<< HEAD
                print(f"📸 ルーム {room_id} で写真メッセージを受信: データ長 {len(msg.get('data', ''))}")
            elif msg["type"] == "notification":
                # 通知メッセージを履歴に保存
                history[room_id].append(msg)
                print(f"📢 ルーム {room_id} で通知メッセージを受信: {msg.get('data', '')}")
=======
                print(f"�� ルーム {room_id} で写真メッセージを受信: データ長 {len(msg.get('data', ''))}")
            elif msg["type"] == "notification":
                # 通知メッセージを履歴に保存
                history[room_id].append(msg)
                print(f"�� ルーム {room_id} で通知メッセージを受信: {msg.get('data', '')}")
>>>>>>> 9a0962863c4740792446c397e39bfc302e1fa613
            elif msg["type"] == "delete":
                history[room_id] = [m for m in history[room_id] if m["id"] != msg["id"]]

            # 同じルーム内の全クライアントにブロードキャスト
            await manager.broadcast_to_room(room_id, msg)

    except WebSocketDisconnect:
        manager.disconnect(room_id, ws)

@router.get("/")
async def root():
<<<<<<< HEAD
    return {"status": "ok", "message": "WebSocket server running"}
=======
    return {"status": "ok", "message": "WebSocket server running"}  
>>>>>>> 9a0962863c4740792446c397e39bfc302e1fa613
