# backend/ws/manager.py
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Mapping, Any

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
    photo_seq: int = 0  # 1..N

class RoomManager:
    """room=acc:<account_id> 単位で WS を管理。"""
    def __init__(self) -> None:
        self._rooms: Dict[str, RoomState] = {}
        self._lock = asyncio.Lock()

    async def _get_or_create(self, room: str) -> RoomState:
        async with self._lock:
            rs = self._rooms.get(room)
            if not rs:
                rs = RoomState()
                self._rooms[room] = rs
            return rs

    async def add(self, room: str, device_id: str, ws: WebSocket) -> None:
        rs = await self._get_or_create(room)
        async with self._lock:
            rs.connections[device_id] = Client(ws=ws, device_id=device_id)

    async def remove(self, room: str, device_id: str) -> None:
        async with self._lock:
            rs = self._rooms.get(room)
            if not rs:
                return
            rs.connections.pop(device_id, None)
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

    async def next_seq(self, room: str) -> int:
        """photo_seq をインクリメントして返す。"""
        async with self._lock:
            rs = self._rooms.get(room)
            if not rs:
                rs = RoomState()
                self._rooms[room] = rs
            rs.photo_seq += 1
            return rs.photo_seq

    async def broadcast_json(
        self,
        room: str,
        payload: Mapping[str, Any],
        exclude_device_id: Optional[str] = None,
    ) -> int:
        """room 内の全クライアントに送信（exclude は除外）。戻り値は送信数。"""
        async with self._lock:
            rs = self._rooms.get(room)
            targets = list(rs.connections.values()) if rs else []

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
