from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from db_control.mymodels import Account, Trip, Picture, PictureData

# アプリ標準タイムゾーン（JST）
JST = timezone(timedelta(hours=9))

def _now_jst() -> datetime:
    return datetime.now(JST)

def _to_jst_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(JST).replace(tzinfo=None)

def _day_bounds(d: date | str) -> tuple[datetime, datetime]:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    start = datetime(d.year, d.month, d.day)
    end = start + timedelta(days=1)
    return start, end

def _picture_to_dict(p: Picture, thumb_w: int | None = None) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "picture_id": p.picture_id,
        "account_id": p.account_id,
        "trip_id": p.trip_id,
        "pictured_at": p.pictured_at.isoformat(sep=" "),
        "gps_lat": float(p.gps_lat) if p.gps_lat is not None else None,
        "gps_lng": float(p.gps_lng) if p.gps_lng is not None else None,
        "device_id": p.device_id,
        "speech": p.speech,
        "situation_for_quiz": p.situation_for_quiz,
        "user_comment": p.user_comment,
        "content_type": p.content_type,
        "image_size": p.image_size,
        "sha256_hex": p.sha256.hex() if p.sha256 else None,
        "created_at": p.created_at.isoformat(sep=" "),
    }
    if thumb_w:
        d["thumbnail_path"] = f"/api/pictures/{p.picture_id}/thumbnail?w={thumb_w}"
    return d

# 1) picture が存在する日付（JST）
def list_picture_dates(
    db: Session,
    account_id: Optional[int] = None,
    trip_id: Optional[int] = None,
) -> List[str]:
    day_expr = func.date(Picture.pictured_at)
    stmt = select(day_expr)
    if account_id is not None:
        stmt = stmt.where(Picture.account_id == account_id)
    if trip_id is not None:
        stmt = stmt.where(Picture.trip_id == trip_id)
    stmt = stmt.group_by(day_expr).order_by(day_expr.asc())
    rows = db.execute(stmt).all()
    return [r[0].isoformat() if isinstance(r[0], date) else str(r[0]) for r in rows]

# 2) 指定1日分の picture 一覧（メタ＋サムネURLヒント）
def list_pictures_by_date(
    db: Session,
    account_id: Optional[int],
    target_date: date | str,
    trip_id: Optional[int] = None,
    order_desc: bool = False,
    thumb_w: int = 256,
) -> List[Dict[str, Any]]:
    start, end = _day_bounds(target_date)
    stmt = select(Picture).where(
        Picture.pictured_at >= start,
        Picture.pictured_at < end,
    )
    if account_id is not None:
        stmt = stmt.where(Picture.account_id == account_id)
    if trip_id is not None:
        stmt = stmt.where(Picture.trip_id == trip_id)
    stmt = stmt.order_by(Picture.pictured_at.desc() if order_desc else Picture.pictured_at.asc())
    pics = db.scalars(stmt).all()
    return [_picture_to_dict(p, thumb_w=thumb_w) for p in pics]

def delete_picture_one(db: Session, picture_id: int, owner_account_id: Optional[int] = None) -> bool:
    # 書き込み系は明示トランザクション
    with db.begin():
        pic = db.get(Picture, picture_id)
        if not pic:
            return False
        if owner_account_id is not None and pic.account_id != owner_account_id:
            return False
        db.delete(pic)
    return True

def create_trip(db: Session, account_id: int, started_at: Optional[datetime] = None) -> int:
    started_at = started_at or _now_jst()
    with db.begin():
        if not db.get(Account, account_id):
            raise ValueError(f"account not found: {account_id}")
        trip = Trip(account_id=account_id, trip_started_at=_to_jst_naive(started_at))
        db.add(trip)
        db.flush()
        return trip.trip_id

def create_picture_with_data(
    db: Session,
    *,
    account_id: int,
    trip_id: Optional[int],
    device_id: Optional[str],
    image_binary: bytes,
    content_type: str,
    pictured_at: Optional[datetime] = None,
    gps_lat: Optional[float] = None,
    gps_lng: Optional[float] = None,
    speech: Optional[str] = None,
    situation_for_quiz: Optional[str] = None,
    user_comment: Optional[str] = None,
    max_bytes: int = 16 * 1024 * 1024,
) -> int:
    if not image_binary:
        raise ValueError("image_binary is empty")
    if len(image_binary) > max_bytes:
        raise ValueError(f"image size exceeds limit: {len(image_binary)} > {max_bytes}")
    if not content_type:
        raise ValueError("content_type is required")

    pictured_at = pictured_at or _now_jst()
    digest = sha256(image_binary).digest()
    size = len(image_binary)

    with db.begin():
        if not db.get(Account, account_id):
            raise ValueError(f"account not found: {account_id}")
        if trip_id is not None:
            t = db.get(Trip, trip_id)
            if not t:
                raise ValueError(f"trip not found: {trip_id}")
            if t.account_id != account_id:
                raise ValueError("trip does not belong to the account")

        pic = Picture(
            account_id=account_id,
            trip_id=trip_id,
            pictured_at=_to_jst_naive(pictured_at),
            gps_lat=gps_lat,
            gps_lng=gps_lng,
            device_id=device_id,
            speech=speech,
            situation_for_quiz=situation_for_quiz,
            user_comment=user_comment,
            content_type=content_type,
            image_size=size,
            sha256=digest,
        )
        db.add(pic)
        db.flush()  # picture_id 採番

        pdata = PictureData(picture_id=pic.picture_id, image_binary=image_binary)
        db.add(pdata)

        return pic.picture_id

def get_picture_image(db: Session, picture_id: int) -> Optional[Tuple[str, bytes]]:
    pic = db.get(Picture, picture_id)
    if not pic:
        return None
    data = db.get(PictureData, picture_id)
    if not data:
        return None
    return (pic.content_type, data.image_binary)

def get_picture_thumbnail(
    db: Session,
    picture_id: int,
    max_px: int = 256,
    prefer_webp: bool = True,
) -> Optional[Tuple[str, bytes]]:
    data = db.get(PictureData, picture_id)
    if not data:
        return None
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError("Pillow が必要です。pip install Pillow を実行してください。")
    with Image.open(BytesIO(data.image_binary)) as im:
        im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        out = BytesIO()
        if prefer_webp:
            im.save(out, format="WEBP", quality=80, method=6)
            return ("image/webp", out.getvalue())
        else:
            im.save(out, format="JPEG", quality=80, optimize=True, progressive=True)
            return ("image/jpeg", out.getvalue())

def count_pictures_by_date(
    db: Session,
    account_id: Optional[int] = None,
    trip_id: Optional[int] = None,
) -> Dict[str, int]:
    day_expr = func.date(Picture.pictured_at)
    stmt = select(day_expr, func.count())
    if account_id is not None:
        stmt = stmt.where(Picture.account_id == account_id)
    if trip_id is not None:
        stmt = stmt.where(Picture.trip_id == trip_id)
    stmt = stmt.group_by(day_expr).order_by(day_expr.asc())
    rows = db.execute(stmt).all()
    return {(d.isoformat() if isinstance(d, date) else str(d)): c for d, c in rows}
