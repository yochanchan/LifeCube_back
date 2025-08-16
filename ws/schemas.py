# backend/ws/schemas.py
from __future__ import annotations
from typing import Literal, TypedDict, NotRequired

# ---- Inbound ----

class MsgBase(TypedDict):
    type: str

class MsgJoinIn(MsgBase):
    type: Literal["join"]
    role: Literal["recorder", "shooter"]
    device_id: NotRequired[str]  # クライアントから来てもサーバ側で上書き

class MsgTakePhoto(MsgBase):
    type: Literal["take_photo"]
    origin_device_id: str
    ts: NotRequired[int]

class MsgPhotoUploadedIn(MsgBase):
    type: Literal["photo_uploaded"]
    picture_id: int
    image_url: NotRequired[str]
    pictured_at: NotRequired[str]
    device_id: NotRequired[str]  # クライアントから来てもサーバ側で上書き

# Phase3: recorder lease
class MsgRecorderAcquire(MsgBase):
    type: Literal["recorder_acquire"]

class MsgRecorderHeartbeat(MsgBase):
    type: Literal["recorder_heartbeat"]

class MsgRecorderRelease(MsgBase):
    type: Literal["recorder_release"]

class MsgPing(MsgBase):
    type: Literal["ping"]

WsInMsg = (
    MsgJoinIn |
    MsgTakePhoto |
    MsgPhotoUploadedIn |
    MsgRecorderAcquire |
    MsgRecorderHeartbeat |
    MsgRecorderRelease |
    MsgPing
)

# ---- Outbound ----

class MsgPong(MsgBase):
    type: Literal["pong"]

class MsgJoinOk(TypedDict):
    type: Literal["join_ok"]
    role: Literal["recorder", "shooter"]
    limits: dict  # {"recorder_max":1, "shooter_max":4}

class MsgJoinDenied(TypedDict):
    type: Literal["join_denied"]
    reason: Literal["invalid_role", "recorder_full", "shooter_full", "server_error"]

class MsgRosterUpdate(TypedDict):
    type: Literal["roster_update"]
    recorder: str | None             # ← リース保持者
    shooters: list[str]
    counts: dict                     # {"recorder":0|1 (role), "shooter":n}

class MsgPhotoUploadedOut(TypedDict):
    type: Literal["photo_uploaded"]
    seq: int
    picture_id: int
    device_id: str
    image_url: str
    pictured_at: NotRequired[str]

# Phase3: recorder lease responses
class MsgRecorderGranted(TypedDict):
    type: Literal["recorder_granted"]
    device_id: str
    ttl: int
    deadline: float

class MsgRecorderDenied(TypedDict):
    type: Literal["recorder_denied"]
    holder_device_id: str | None

class MsgRecorderRevoked(TypedDict):
    type: Literal["recorder_revoked"]
    device_id: str
    reason: Literal["expired", "released", "disconnected"]

WsOutMsg = (
    MsgPong | MsgJoinOk | MsgJoinDenied |
    MsgRosterUpdate | MsgPhotoUploadedOut | MsgTakePhoto |
    MsgRecorderGranted | MsgRecorderDenied | MsgRecorderRevoked
)
