# backend/ws/schemas.py
from __future__ import annotations
from typing import Literal, TypedDict, NotRequired

class MsgBase(TypedDict):
    type: str

# --- ping/pong ---
class MsgPing(MsgBase):
    type: Literal["ping"]

class MsgPong(MsgBase):
    type: Literal["pong"]

# --- take_photo ---
class MsgTakePhoto(MsgBase):
    type: Literal["take_photo"]
    origin_device_id: str
    ts: NotRequired[int]

# --- photo_uploaded ---
# Inbound from client (sender). device_id はサーバで上書きするので任意扱い
class MsgPhotoUploadedIn(MsgBase):
    type: Literal["photo_uploaded"]
    picture_id: int
    image_url: str                 # フル画像URL（相対可）
    pictured_at: NotRequired[str]  # ISO8601 文字列
    device_id: NotRequired[str]    # ← クライアントから来ても無視/上書き

# Outbound broadcast (server → clients)
class MsgPhotoUploadedOut(MsgBase):
    type: Literal["photo_uploaded"]
    seq: int
    picture_id: int
    device_id: str
    image_url: str
    pictured_at: NotRequired[str]

WsInMsg = MsgTakePhoto | MsgPing | MsgPhotoUploadedIn
WsOutMsg = MsgTakePhoto | MsgPong | MsgPhotoUploadedOut
