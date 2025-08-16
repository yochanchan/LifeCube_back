# backend/ws/manager.py
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Mapping, Any, Set, Tuple

from starlette.websockets import WebSocket

# ─────────────────────────────────────────────────────────────
# Phase3: RECORDER リース / TTL
# ─────────────────────────────────────────────────────────────
TTL_SECONDS = 20          # 既定TTL（DoD: 20s±で自動解放）
MONITOR_INTERVAL = 2.0    # 監視タスク周期（秒）


@dataclass
class Client:
    ws: WebSocket
    device_id: str
    joined_at: float = field(default_factory=lambda: time.time())
    last_seen: float = field(default_factory=lambda: time.time())


@dataclass
class RoomState:
    # 接続
    connections: Dict[str, Client] = field(default_factory=dict)

    # 役割（join）
    recorder_role: Optional[str] = None          # join(recorder) したデバイス（最大1）
    shooters: Set[str] = field(default_factory=set)

    # 上限
    recorder_max: int = 1
    shooter_max: int = 4

    # リース（録音ON中のみ保持）
    recorder_holder: Optional[str] = None        # 現在の保持者（録音ON中のみ）
    recorder_deadline: Optional[float] = None    # 期限（epoch秒）

    # “最新”採番
    photo_seq: int = 0


class RoomManager:
    """room=acc:<account_id> 単位で WS を管理。Phase3: リース＋TTL対応。"""

    def __init__(self) -> None:
        self._rooms: Dict[str, RoomState] = {}
        self._lock = asyncio.Lock()
        self._monitor_task: Optional[asyncio.Task] = None

    # ───────── 低レベル: 接続の追加/削除/タッチ ─────────

    async def add(self, room: str, device_id: str, ws: WebSocket) -> None:
        async with self._lock:
            rs = self._rooms.setdefault(room, RoomState())
            # 同一 device_id は置き換える（多重接続防止）
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

            # 役割から外す
            if rs.recorder_role == device_id:
                rs.recorder_role = None
            if device_id in rs.shooters:
                rs.shooters.discard(device_id)

            # 保持者ならリース解放
            if rs.recorder_holder == device_id:
                rs.recorder_holder = None
                rs.recorder_deadline = None

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

    # ───────── 役割/人数（join） ─────────

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
                # 既に自分が recorder_role を持っていればOK
                if rs.recorder_role == device_id:
                    return (True, None, limits)
                # 他の誰かが recorder_role を保持中
                if rs.recorder_role and rs.recorder_role != device_id:
                    return (False, "recorder_full", limits)
                # 取得
                rs.recorder_role = device_id
                return (True, None, limits)

            # shooter
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
            # counts.recorder は role の有無、recorder はリース保持者を返す
            return {
                "recorder": rs.recorder_holder,
                "shooters": sorted(rs.shooters),
                "counts": {
                    "recorder": 1 if rs.recorder_role else 0,
                    "shooter": len(rs.shooters),
                },
            }

    async def next_seq(self, room: str) -> int:
        async with self._lock:
            rs = self._rooms.setdefault(room, RoomState())
            rs.photo_seq += 1
            return rs.photo_seq

    # ───────── リース操作（Phase3） ─────────

    async def recorder_acquire(self, room: str, device_id: str, ttl_seconds: int) -> Tuple[bool, Optional[str], Optional[float]]:
        """録音ON: リース取得。成功時 (True, None, deadline)。失敗時 (False, holder_device_id, None)。"""
        now = time.time()
        async with self._lock:
            rs = self._rooms.setdefault(room, RoomState())

            # 既に自分が保持者なら延長だけしてOKを返す
            if rs.recorder_holder == device_id:
                rs.recorder_deadline = now + ttl_seconds
                return True, None, rs.recorder_deadline

            # 空いているなら取得
            if not rs.recorder_holder:
                rs.recorder_holder = device_id
                rs.recorder_deadline = now + ttl_seconds
                return True, None, rs.recorder_deadline

            # 他者が保持中
            return False, rs.recorder_holder, None

    async def recorder_heartbeat(self, room: str, device_id: str, ttl_seconds: int) -> None:
        """保持者のみ延長。非保持者なら無視。"""
        now = time.time()
        async with self._lock:
            rs = self._rooms.get(room)
            if not rs:
                return
            if rs.recorder_holder == device_id:
                rs.recorder_deadline = now + ttl_seconds

    async def recorder_release(self, room: str, device_id: str) -> bool:
        """自発的解放。保持者なら True。"""
        async with self._lock:
            rs = self._rooms.get(room)
            if not rs:
                return False
            if rs.recorder_holder == device_id:
                rs.recorder_holder = None
                rs.recorder_deadline = None
                return True
            return False

    async def is_recorder(self, room: str, device_id: str) -> bool:
        async with self._lock:
            rs = self._rooms.get(room)
            if not rs:
                return False
            return rs.recorder_holder == device_id

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

    # ───────── 監視タスク（TTL） ─────────

    def ensure_monitor_task(self) -> None:
        """2秒間隔で期限切れを剥奪するバックグラウンドタスクを起動。多重起動は抑止。"""
        if self._monitor_task and not self._monitor_task.done():
            return
        self._monitor_task = asyncio.create_task(self._monitor_loop(), name="recorder-ttl-monitor")

    async def _monitor_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(MONITOR_INTERVAL)
                await self._sweep_expired()
            except asyncio.CancelledError:
                break
            except Exception:
                # 監視は止めない
                continue

    async def _sweep_expired(self) -> None:
        now = time.time()
        # スナップショット→ロック最小化
        async with self._lock:
            items = list(self._rooms.items())

        for room, rs in items:
            expired_device: Optional[str] = None
            async with self._lock:
                rs2 = self._rooms.get(room)
                if not rs2:
                    continue
                if rs2.recorder_holder and rs2.recorder_deadline and now > rs2.recorder_deadline:
                    expired_device = rs2.recorder_holder
                    rs2.recorder_holder = None
                    rs2.recorder_deadline = None

            if expired_device:
                # 剥奪通知
                await self.broadcast_json(room, {
                    "type": "recorder_revoked",
                    "device_id": expired_device,
                    "reason": "expired",
                })
                # roster 更新
                roster = await self.get_roster(room)
                await self.broadcast_json(room, {"type": "roster_update", **roster})


manager = RoomManager()
