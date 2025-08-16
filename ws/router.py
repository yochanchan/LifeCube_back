# backend/ws/router.py
from __future__ import annotations

import json
from typing import Optional, Any, cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from starlette.websockets import WebSocketState

from .manager import manager
from .schemas import WsInMsg, MsgTakePhoto

router = APIRouter()

@router.websocket("/ws")
async def room_ws(
    ws: WebSocket,
    room: Optional[str] = Query(default=None),
    device_id: Optional[str] = Query(default=None),
):
    # まず受け入れ（403のまま潰れるのを避け、デバッグしやすくする）
    await ws.accept()

    room_final = (room or "").strip()
    device_final = (device_id or "").strip()

    # 接続メタのエコー（Origin/Hostを確認）
    try:
        await ws.send_json({
            "type": "hello",
            "room": room_final,
            "device_id": device_final,
            "origin": ws.headers.get("origin"),
            "host": ws.headers.get("host"),
        })
    except Exception:
        pass

    # PoC：roomは acc: から始まる前提
    if not room_final or not device_final or not room_final.lower().startswith("acc:"):
        try:
            await ws.send_json({
                "type": "error",
                "reason": "invalid_params",
                "room": room_final,
                "device_id": device_final,
                "hint": 'expect room like "acc:<id>" and non-empty device_id',
            })
        except Exception:
            pass
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.add(room_final, device_final, ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg_any: Any = json.loads(raw)
                if not isinstance(msg_any, dict):
                    continue
                msg: WsInMsg = cast(WsInMsg, msg_any)
            except Exception:
                continue

            typ = msg.get("type")
            if typ == "ping":
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json({"type": "pong"})
                await manager.touch(room_final, device_final)

            elif typ == "take_photo":
                take = cast(MsgTakePhoto, msg)
                await manager.broadcast_json(room_final, take, exclude_device_id=device_final)

            else:
                # 未知メッセージは無視
                pass

    except WebSocketDisconnect:
        pass
    finally:
        await manager.remove(room_final, device_final)

# 🔎 room 正規化をHTTPで確認する補助エンドポイント（開発時のみ使う）
@router.get("/ws-debug")
def ws_debug(room: Optional[str] = None, device_id: Optional[str] = None):
    rf = (room or "")
    df = (device_id or "")
    return {
        "room_raw": room,
        "room_stripped": rf.strip(),
        "room_lower": rf.strip().lower(),
        "room_is_acc": rf.strip().lower().startswith("acc:"),
        "device_id_raw": device_id,
        "device_id_stripped": df.strip(),
    }
