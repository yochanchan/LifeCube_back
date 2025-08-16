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

class RoomManager:
    """room=acc:<account_id> 単位で WS を管理。"""
    def __init__(self) -> None:
        self._rooms: Dict[str, Dict[str, Client]] = {}
        self._lock = asyncio.Lock()

    async def add(self, room: str, device_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._rooms.setdefault(room, {})
            self._rooms[room][device_id] = Client(ws=ws, device_id=device_id)

    async def remove(self, room: str, device_id: str) -> None:
        async with self._lock:
            m = self._rooms.get(room)
            if not m:
                return
            m.pop(device_id, None)
            if not m:
                self._rooms.pop(room, None)

    async def touch(self, room: str, device_id: str) -> None:
        async with self._lock:
            c = self._rooms.get(room, {}).get(device_id)
            if c:
                c.last_seen = time.time()

    async def broadcast_json(
        self,
        room: str,
        payload: Mapping[str, Any],                 # ★ 明示化：Mapping[str, Any]
        exclude_device_id: Optional[str] = None,
    ) -> int:
        """room 内の全クライアントに送信（exclude は除外）。戻り値は送信数。"""
        async with self._lock:
            targets = list(self._rooms.get(room, {}).values())

        sent = 0
        for cli in targets:
            if exclude_device_id and cli.device_id == exclude_device_id:
                continue
            try:
                await cli.ws.send_json(payload)     # Mapping なら OK
                sent += 1
            except Exception:
                try:
                    await cli.ws.close()
                except Exception:
                    pass
                await self.remove(room, cli.device_id)
        return sent

manager = RoomManager()
