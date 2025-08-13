# backend/api/camera_ws.py
from __future__ import annotations

from typing import Dict, Optional, Tuple
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from auth.session import get_session_from_id, COOKIE_NAME

router = APIRouter(prefix="/camera", tags=["camera-ws"])

# ルームはアカウント単位: "acc:<account_id>"
Room = str
DeviceId = str

class ConnectionManager:
    """
    rooms: 各 room (acc:<id>) に対して、device_id -> WebSocket を保持
    例: {"acc:123": {"dev_xxx": <WebSocket>, "dev_yyy": <WebSocket>}, ...}
    """
    def __init__(self) -> None:
        self.rooms: Dict[Room, Dict[DeviceId, WebSocket]] = {}

    async def connect(self, room: Room, device_id: DeviceId, ws: WebSocket) -> None:
        await ws.accept()
        self.rooms.setdefault(room, {})[device_id] = ws

    def disconnect(self, room: Room, device_id: DeviceId) -> None:
        room_map = self.rooms.get(room)
        if not room_map:
            return
        room_map.pop(device_id, None)
        if not room_map:
            self.rooms.pop(room, None)

    async def broadcast_take_photo(self, room: Room, origin_device_id: DeviceId, ts: int) -> None:
        """
        同じ room の他端末へ撮影命令を送る（自分発は除外）
        """
        room_map = self.rooms.get(room)
        if not room_map:
            return

        dead: list[Tuple[DeviceId, WebSocket]] = []
        for dev, ws in room_map.items():
            if dev == origin_device_id:
                continue
            try:
                await ws.send_json({"type": "take_photo", "from_device_id": origin_device_id, "ts": ts})
            except WebSocketDisconnect:
                dead.append((dev, ws))
            except Exception:
                dead.append((dev, ws))

        # 切断ソケットの掃除
        for dev, _ in dead:
            room_map.pop(dev, None)
        if not room_map:
            self.rooms.pop(room, None)


manager = ConnectionManager()


def _require_param_str(value: Optional[str], name: str) -> str:
    """
    Optional[str] を strict な str に絞るヘルパ。
    None/空文字なら ValueError。
    """
    if value is None or value == "":
        raise ValueError(f"missing query param: {name}")
    return value


def _verify_room_with_session(room: str, ws: WebSocket) -> None:
    """
    セッションCookieからアカウントIDを取得し、room=acc:<id> であることを検証
    不一致/未ログインなら 1008(close) で弾く。
    """
    sid = ws.cookies.get(COOKIE_NAME)
    sess = get_session_from_id(sid, touch=True)
    if not sess:
        # 未ログイン
        # RFC: 1008 Policy Violation
        raise PermissionError("unauthorized (no valid session)")
    expected = f"acc:{sess.account_id}"
    if room != expected:
        raise PermissionError(f"room mismatch: expected={expected}, got={room}")


@router.websocket("/ws")
async def camera_ws(ws: WebSocket):
    # 1) Query の取り出し（None を str に絞る）
    try:
        room = _require_param_str(ws.query_params.get("room"), "room")
        device_id = _require_param_str(ws.query_params.get("device_id"), "device_id")
    except ValueError as e:
        # クエリ不足 → 1008 で閉じる（Policy violation）
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2) room とログインセッションの整合を検証
    try:
        _verify_room_with_session(room, ws)
    except PermissionError:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 3) 接続登録
    await manager.connect(room, device_id, ws)

    try:
        while True:
            # {"type": "take_photo", "origin_device_id": "<dev_xxx>", "ts": 1234567890}
            msg = await ws.receive_json()
            if not isinstance(msg, dict):
                continue

            mtype = msg.get("type")
            if mtype == "ping":
                # 簡易ヘルスチェック（任意）
                await ws.send_json({"type": "pong"})
                continue

            if mtype == "take_photo":
                origin = msg.get("origin_device_id")
                ts = msg.get("ts")
                # 送信者のdevice_id偽装を避けたい場合は origin==device_id を強制
                if origin != device_id:
                    # 不正な送信 → 1008 で閉じる or 無視
                    # ここでは無視に留める
                    continue
                if not isinstance(ts, int):
                    # ts 無し/不正でも既定値で送れるようにする
                    ts = 0

                # 同 room へブロードキャスト（自分発は除外）
                await manager.broadcast_take_photo(room, origin_device_id=device_id, ts=ts)
                continue

            # 既知でない type は無視
    except WebSocketDisconnect:
        # 4) 切断
        manager.disconnect(room, device_id)
    except Exception:
        # 予期せぬ例外でもクリーンアップ
        manager.disconnect(room, device_id)
        try:
            await ws.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
