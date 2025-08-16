from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Mapping, Any, Set, Tuple

from starlette.websockets import WebSocket


@dataclass
class Client:
    ws: WebSocket
    device_id: str
    joined_at: float = field(default_factory=lambda: time.time())
    last_seen: float = field(default_factory=lambda: time.time())


@dataclass
class RoomState:
    connections: Dict[str, Client] = field(default_factory=dict)
    # 役割と上限
    recorder: Optional[str] = None
    shooters: Set[str] = field(default_factory=set)
    recorder_max: int = 1
    shooter_max: int = 4
    # “最新”採番
    photo_seq: int = 0


class RoomManager:
    """room=acc:<account_id> 単位で WS を管理。Phase2: 役割・上限制御つき。"""

    def __init__(self) -> None:
        self._rooms: Dict[str, RoomState] = {}
        self._lock = asyncio.Lock()

    # ───────── 低レベル: 接続の追加/削除/タッチ ─────────

    async def add(self, room: str, device_id: str, ws: WebSocket) -> None:
        async with self._lock:
            rs = self._rooms.setdefault(room, RoomState())
            # 同一 device_id の既存接続があるなら閉じて置き換える（多重防止）
            old = rs.connections.get(device_id)
            if old:
                try:
                    await old.ws.close()
                except Exception:
                    pass
            rs.connections[device_id] = Client(ws=ws, device_id=device_id)

    async def remove(self, room: str, device_id: str) -> None:
        async with self._lock:
            rs = self._rooms.get(room)
            if not rs:
                return
            rs.connections.pop(device_id, None)
            # 役割からも外す
            if rs.recorder == device_id:
                rs.recorder = None
            if device_id in rs.shooters:
                rs.shooters.discard(device_id)
            # 誰もいなければ room を掃除
            if not rs.connections:
                self._rooms.pop(room, None)

    async def touch(self, room: str, device_id: str) -> None:
        async with self._lock:
            rs = self._rooms.get(room)
            if not rs:
                return
            c = rs.connections.get(device_id)
            if c:
                c.last_seen = time.time()

    # ───────── 役割/人数 ─────────

    async def join_role(self, room: str, device_id: str, role: str) -> Tuple[bool, Optional[str], Dict[str, int]]:
        """
        役割の取得を試みる。
        戻り値: (ok, reason, limits)
          - ok=True なら取得成功
          - ok=False の reason は 'invalid_role' / 'recorder_full' / 'shooter_full'
        """
        async with self._lock:
            rs = self._rooms.setdefault(room, RoomState())

            limits = {"recorder_max": rs.recorder_max, "shooter_max": rs.shooter_max}

            if role not in ("recorder", "shooter"):
                return (False, "invalid_role", limits)

            if role == "recorder":
                # すでに自分が保持しているならOK
                if rs.recorder == device_id:
                    return (True, None, limits)
                # 他人が保持 → 上限
                if rs.recorder and rs.recorder != device_id:
                    return (False, "recorder_full", limits)
                # 取得
                rs.recorder = device_id
                # shooters 側にも入っていれば維持して良い（仕様次第だがここでは放置）
                return (True, None, limits)

            # role == "shooter"
            if device_id in rs.shooters:
                return (True, None, limits)
            if len(rs.shooters) >= rs.shooter_max:
                return (False, "shooter_full", limits)
            rs.shooters.add(device_id)
            return (True, None, limits)

    async def get_roster(self, room: str) -> Dict[str, Any]:
        async with self._lock:
            rs = self._rooms.get(room)
            if not rs:
                return {"recorder": None, "shooters": [], "counts": {"recorder": 0, "shooter": 0}}
            return {
                "recorder": rs.recorder,
                "shooters": sorted(rs.shooters),
                "counts": {
                    "recorder": 1 if rs.recorder else 0,
                    "shooter": len(rs.shooters),
                },
            }

    async def next_seq(self, room: str) -> int:
        async with self._lock:
            rs = self._rooms.setdefault(room, RoomState())
            rs.photo_seq += 1
            return rs.photo_seq

    # ───────── ブロードキャスト ─────────

    async def broadcast_json(
        self,
        room: str,
        payload: Mapping[str, Any],
        exclude_device_id: Optional[str] = None,
    ) -> int:
        """room 内の全クライアントに送信（exclude は除外）。戻り値は送信数。"""
        async with self._lock:
            rs = self._rooms.get(room)
            if not rs:
                return 0
            targets = list(rs.connections.values())

        sent = 0
        for cli in targets:
            if exclude_device_id and cli.device_id == exclude_device_id:
                continue
            try:
                await cli.ws.send_json(payload)
                sent += 1
            except Exception:
                try:
                    await cli.ws.close()
                except Exception:
                    pass
                await self.remove(room, cli.device_id)
        return sent


manager = RoomManager()
