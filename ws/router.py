# backend/ws/router.py
from __future__ import annotations

import json
import logging
from typing import Optional, Any, cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from starlette.websockets import WebSocketState

from .manager import manager, TTL_SECONDS
from .schemas import (
    WsInMsg,
    MsgTakePhoto,
    MsgPhotoUploadedIn,
    MsgJoinIn,
)

router = APIRouter()
log = logging.getLogger("app.ws")

def _is_valid_room(r: Optional[str]) -> bool:
    return bool(r and r.strip().lower().startswith("acc:"))

async def _broadcast_roster(room: str):
    roster = await manager.get_roster(room)
    await manager.broadcast_json(room, {
        "type": "roster_update",
        **roster,
    })

@router.websocket("/ws")
async def room_ws(
    ws: WebSocket,
    room: Optional[str] = Query(default=None),
    device_id: Optional[str] = Query(default=None),
):
    await ws.accept()

    # 監視タスクを起動（多重起動は内部で抑止）
    manager.ensure_monitor_task()

    room_final = (room or "").strip()
    device_final = (device_id or "").strip()

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

    if not _is_valid_room(room_final) or not device_final:
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
    log.info("ws connected: room=%s device=%s", room_final, device_final)

    joined = False
    my_role: Optional[str] = None

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
                continue

            if typ == "join":
                # --- JOIN HANDLER ---
                try:
                    j = cast(MsgJoinIn, msg)
                    role = j.get("role")
                    log.info("join requested: room=%s dev=%s role=%s", room_final, device_final, role)
                    ok, reason, limits = await manager.join_role(room_final, device_final, str(role))
                    if ok:
                        joined = True
                        my_role = str(role)
                        await ws.send_json({"type": "join_ok", "role": my_role, "limits": limits})
                        log.info("join ok: room=%s dev=%s role=%s", room_final, device_final, my_role)
                        await _broadcast_roster(room_final)
                    else:
                        await ws.send_json({"type": "join_denied", "reason": reason or "invalid_role"})
                        log.info("join denied: room=%s dev=%s role=%s reason=%s", room_final, device_final, role, reason)
                        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
                        break
                except Exception:
                    log.exception("join handler failed: room=%s dev=%s", room_final, device_final)
                    try:
                        await ws.send_json({"type": "join_denied", "reason": "server_error"})
                    except Exception:
                        pass
                    await ws.close(code=status.WS_1011_INTERNAL_ERROR)
                    break
                continue

            # join 必須
            if not joined:
                continue

            if typ == "recorder_acquire":
                # recorderページ以外は拒否（shooterからの誤送を抑止）
                if my_role != "recorder":
                    await ws.send_json({"type": "recorder_denied", "holder_device_id": None})
                    continue
                granted, holder, deadline = await manager.recorder_acquire(room_final, device_final, TTL_SECONDS)
                if granted:
                    await ws.send_json({"type": "recorder_granted", "device_id": device_final, "ttl": TTL_SECONDS, "deadline": deadline})
                    await _broadcast_roster(room_final)
                else:
                    await ws.send_json({"type": "recorder_denied", "holder_device_id": holder})
                continue

            if typ == "recorder_heartbeat":
                # 保持者のみ延長、応答は不要
                await manager.recorder_heartbeat(room_final, device_final, TTL_SECONDS)
                continue

            if typ == "recorder_release":
                # 保持者のみ解放
                released = await manager.recorder_release(room_final, device_final)
                if released:
                    await manager.broadcast_json(room_final, {
                        "type": "recorder_revoked",
                        "device_id": device_final,
                        "reason": "released",
                    })
                    await _broadcast_roster(room_final)
                continue

            if typ == "take_photo":
                take = cast(MsgTakePhoto, msg)
                await manager.broadcast_json(room_final, take, exclude_device_id=device_final)

            elif typ == "photo_uploaded":
                up = cast(MsgPhotoUploadedIn, msg)
                device = device_final
                picture_id = int(up["picture_id"])
                image_url = up.get("image_url") or f"/api/pictures/{picture_id}/image"
                pictured_at = up.get("pictured_at")
                seq = await manager.next_seq(room_final)
                out = {
                    "type": "photo_uploaded",
                    "seq": seq,
                    "picture_id": picture_id,
                    "device_id": device,
                    "image_url": image_url,
                }
                if pictured_at:
                    out["pictured_at"] = pictured_at
                await manager.broadcast_json(room_final, out)

            else:
                # 未知メッセージは無視
                pass

    except WebSocketDisconnect:
        log.info("ws disconnected: room=%s device=%s", room_final, device_final)
    finally:
        # 切断前に自分が保持者か確認してからremove
        was_holder = await manager.is_recorder(room_final, device_final)
        await manager.remove(room_final, device_final)
        if _is_valid_room(room_final):
            if was_holder:
                await manager.broadcast_json(room_final, {
                    "type": "recorder_revoked",
                    "device_id": device_final,
                    "reason": "disconnected",
                })
            await _broadcast_roster(room_final)

@router.get("/ws/roster")
async def ws_roster(room: Optional[str] = Query(default=None)):
    if not _is_valid_room(room):
        return {"recorder": None, "shooters": [], "counts": {"recorder": 0, "shooter": 0}}
    # ここで型を厳密化（Pylanceの型ナローイング）
    assert room is not None
    return await manager.get_roster(room)

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
