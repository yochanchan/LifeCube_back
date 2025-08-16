# backend/ws/manager.py
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Mapping, Any, Set, Tuple, List

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
    """room=acc:<account_id> 単位で WS を管理。Phase2: 役割・上限制御つき。
    送信I/Oはロック外で行い、送信失敗の掃除は remove() に委ねる。
    """

    def __init__(self) -> None:
        self._rooms: Dict[str, RoomState] = {}
        self._lock = asyncio.Lock()
        # RECORDERのTTL（秒）。touch() 更新がこの秒数を超えると剥奪。
        self._ttl_seconds = 20
        # TTLスイーパ（2秒毎）
        asyncio.create_task(self._sweeper())

    # ───────── 低レベル: 接続の追加/削除/タッチ ─────────

    async def add(self, room: str, device_id: str, ws: WebSocket) -> None:
        """接続を登録。既存deviceがあれば置き換える。
        古い接続の close() はロック外で実行してデッドロックを避ける。
        """
        old_ws: Optional[WebSocket] = None
        async with self._lock:
            rs = self._rooms.setdefault(room, RoomState())
            old = rs.connections.get(device_id)
            if old:
                old_ws = old.ws  # ロック解除後にclose
            rs.connections[device_id] = Client(ws=ws, device_id=device_id)

        if old_ws:
            try:
                await old_ws.close()
            except Exception:
                pass

    async def remove(self, room: str, device_id: str) -> None:
        """接続を削除し、役割からも外す。部屋が空になればルーム自体を破棄。"""
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
        """心拍（ping）による最終時刻更新。TTL監視で利用。"""
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
        """room 内の全クライアントに送信（exclude は除外）。戻り値は送信数。
        送信ターゲットのスナップショット取得のみロック内、実送信はロック外。
        """
        async with self._lock:
            rs = self._rooms.get(room)
            if not rs:
                return 0
            # (device_id, WebSocket) のスナップショットを作る
            targets: List[Tuple[str, WebSocket]] = [
                (dev_id, cli.ws)
                for dev_id, cli in rs.connections.items()
                if not (exclude_device_id and dev_id == exclude_device_id)
            ]

        dead: List[str] = []
        sent = 0
        for dev_id, ws in targets:
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:
                dead.append(dev_id)

        # 失敗クライアントの掃除（ロックは remove 側で取得）
        for dev_id in dead:
            try:
                await self.remove(room, dev_id)
            except Exception:
                pass

        return sent

    # ───────── TTLスイーパ ─────────

    async def _sweeper(self) -> None:
        """2秒毎にRECORDERのTTLを監視し、期限切れなら剥奪して通知する。"""
        while True:
            await asyncio.sleep(2)
            now = time.time()
            # 剥奪対象の room をロック内で抽出
            to_revoke: List[str] = []
            async with self._lock:
                for room, rs in list(self._rooms.items()):
                    rec = rs.recorder
                    if not rec:
                        continue
                    cli = rs.connections.get(rec)
                    if (not cli) or (now - cli.last_seen > self._ttl_seconds):
                        # RECORDERを空に
                        rs.recorder = None
                        to_revoke.append(room)

            # ロック外で通知（revoked → roster_update）
            for room in to_revoke:
                try:
                    await self.broadcast_json(room, {"type": "recorder_revoked"})
                    roster = await self.get_roster(room)
                    await self.broadcast_json(room, {"type": "roster_update", **roster})
                except Exception:
                    # 通知失敗は次ループで再評価されるので握りつぶし
                    pass


# 明示注釈でPylanceに型を伝える（broadcast_json 未検出エラー回避）
manager: RoomManager = RoomManager()

__all__ = ["Client", "RoomState", "RoomManager", "manager"]
