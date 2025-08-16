# backend/ws/schemas.py
from __future__ import annotations
from typing import Literal, TypedDict, NotRequired

class MsgBase(TypedDict):
    type: str

class MsgTakePhoto(MsgBase):
    type: Literal["take_photo"]
    origin_device_id: str
    ts: NotRequired[int]

class MsgPing(MsgBase):
    type: Literal["ping"]

class MsgPong(MsgBase):
    type: Literal["pong"]

WsInMsg = MsgTakePhoto | MsgPing
WsOutMsg = MsgTakePhoto | MsgPong
