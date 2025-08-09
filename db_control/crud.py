# backend/db_control/crud.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.orm import sessionmaker

from db_control.connect import engine
from db_control.mymodels import Account, Trip, Picture, PictureData

# ─────────────────────────────────────────────────────────────
# アプリ標準タイムゾーン：東京 (JST, UTC+9)
# DBはDATETIME(6)（タイムゾーン情報なし）だが、「JSTの値が入る」前提で統一運用
# ─────────────────────────────────────────────────────────────
JST = timezone(timedelta(hours=9))

# セッションファクトリ
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


# ─────────────────────────────────────────────────────────────
# 内部ユーティリティ
# ─────────────────────────────────────────────────────────────
def _now_jst() -> datetime:
    """JSTの現在時刻（tz-aware）"""
    return datetime.now(JST)


def _to_jst_naive(dt: datetime) -> datetime:
    """timezone付→JSTに変換してnaive化 / naiveはそのまま返す（既にJST想定）"""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(JST).replace(tzinfo=None)


def _day_bounds(d: date | str) -> tuple[datetime, datetime]:
    """
    指定日（JST）1日分の範囲を返す。
    [その日 00:00:00, 翌日 00:00:00)  ※JST naive
    """
    if isinstance(d, str):
        d = date.fromisoformat(d)  # "YYYY-MM-DD"
    start = datetime(d.year, d.month, d.day)           # JST naive
    end = start + timedelta(days=1)                    # 翌日 00:00
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
    # サムネイル取得用のヒントURL（実際のルート名はアプリに合わせてください）
    if thumb_w:
        d["thumbnail_path"] = f"/api/pictures/{p.picture_id}/thumbnail?w={thumb_w}"
    return d


# ─────────────────────────────────────────────────────────────
# 1) pictureが存在する日付をselect（JST基準）
#    返り値: "YYYY-MM-DD" の文字列リスト
# ─────────────────────────────────────────────────────────────
def list_picture_dates(
    account_id: int,
    trip_id: Optional[int] = None,
) -> List[str]:
    with SessionLocal() as session:
        day_expr = func.date(Picture.pictured_at)  # JST格納前提なのでそのまま日付抽出
        stmt = select(day_expr).where(Picture.account_id == account_id)
        if trip_id is not None:
            stmt = stmt.where(Picture.trip_id == trip_id)
        stmt = stmt.group_by(day_expr).order_by(day_expr.asc())

        rows = session.execute(stmt).all()
        return [r[0].isoformat() if isinstance(r[0], date) else str(r[0]) for r in rows]


# ─────────────────────────────────────────────────────────────
# 2) 指定「1日間」のpictureを全てselect（メタ＋サムネイルURLのヒント）
#    - 入力日付のJST 00:00〜翌日00:00の範囲で抽出
#    - 画像BLOBは含めない（一覧を軽量化）
#    - サムネイルは別エンドポイントでオンザフライ生成（DB変更は不要）
# ─────────────────────────────────────────────────────────────
def list_pictures_by_date(
    account_id: int,
    target_date: date | str,
    trip_id: Optional[int] = None,
    order_desc: bool = False,
    thumb_w: int = 256,
) -> List[Dict[str, Any]]:
    start, end = _day_bounds(target_date)

    with SessionLocal() as session:
        stmt = (
            select(Picture)
            .where(
                Picture.account_id == account_id,
                Picture.pictured_at >= start,
                Picture.pictured_at < end,
            )
        )
        if trip_id is not None:
            stmt = stmt.where(Picture.trip_id == trip_id)
        stmt = stmt.order_by(Picture.pictured_at.desc() if order_desc else Picture.pictured_at.asc())

        pics = session.scalars(stmt).all()
        return [_picture_to_dict(p, thumb_w=thumb_w) for p in pics]


# ─────────────────────────────────────────────────────────────
# 3) 指定pictureを1点delete（CASCADEでpicture_dataも削除）
# ─────────────────────────────────────────────────────────────
def delete_picture_one(picture_id: int, owner_account_id: Optional[int] = None) -> bool:
    with SessionLocal() as session, session.begin():
        pic = session.get(Picture, picture_id)
        if not pic:
            return False
        if owner_account_id is not None and pic.account_id != owner_account_id:
            return False
        session.delete(pic)
        return True


# ─────────────────────────────────────────────────────────────
# 4) account_idでtripを1件追加（JST現在時刻を記録）
#    返り値: 新規 trip_id
# ─────────────────────────────────────────────────────────────
def create_trip(account_id: int, started_at: Optional[datetime] = None) -> int:
    started_at = started_at or _now_jst()
    with SessionLocal() as session, session.begin():
        if not session.get(Account, account_id):
            raise ValueError(f"account not found: {account_id}")

        trip = Trip(
            account_id=account_id,
            trip_started_at=_to_jst_naive(started_at),
        )
        session.add(trip)
        session.flush()
        return trip.trip_id


# ─────────────────────────────────────────────────────────────
# 5) tripに紐づくpictureを1点追加 + picture_data保存（同一Tx）
#    pictured_at はJST現在時刻（未指定時）
#    返り値: 新規 picture_id
# ─────────────────────────────────────────────────────────────
def create_picture_with_data(
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
    max_bytes: int = 16 * 1024 * 1024,  # MEDIUMBLOBの安全ライン
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

    with SessionLocal() as session, session.begin():
        if not session.get(Account, account_id):
            raise ValueError(f"account not found: {account_id}")
        if trip_id is not None:
            t = session.get(Trip, trip_id)
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
        session.add(pic)
        session.flush()  # picture_id 採番

        pdata = PictureData(
            picture_id=pic.picture_id,
            image_binary=image_binary,
        )
        session.add(pdata)

        return pic.picture_id


# ─────────────────────────────────────────────────────────────
# 追加：フル画像の取得（content_type, bytes）
# ─────────────────────────────────────────────────────────────
def get_picture_image(picture_id: int) -> Optional[Tuple[str, bytes]]:
    with SessionLocal() as session:
        pic = session.get(Picture, picture_id)
        if not pic:
            return None
        data = session.get(PictureData, picture_id)
        if not data:
            return None
        return (pic.content_type, data.image_binary)


# ─────────────────────────────────────────────────────────────
# 追加：サムネイル生成（オンザフライ、DB変更不要）
# 返り値: (content_type, bytes) 例: image/webp or image/jpeg
# ─────────────────────────────────────────────────────────────
def get_picture_thumbnail(
    picture_id: int,
    max_px: int = 256,
    prefer_webp: bool = True,
) -> Optional[Tuple[str, bytes]]:
    with SessionLocal() as session:
        data = session.get(PictureData, picture_id)
        if not data:
            return None

        try:
            from PIL import Image
        except ImportError:
            raise RuntimeError("Pillow が必要です。`pip install Pillow` を実行してください。")

        with Image.open(BytesIO(data.image_binary)) as im:
            im = im.convert("RGB")
            im.thumbnail((max_px, max_px))  # アスペクト比維持、長辺max_px

            out = BytesIO()
            if prefer_webp:
                im.save(out, format="WEBP", quality=80, method=6)
                return ("image/webp", out.getvalue())
            else:
                im.save(out, format="JPEG", quality=80, optimize=True, progressive=True)
                return ("image/jpeg", out.getvalue())


# ─────────────────────────────────────────────────────────────
# 追加：日付別件数（JST基準） { "YYYY-MM-DD": count, ... }
# ─────────────────────────────────────────────────────────────
def count_pictures_by_date(
    account_id: int,
    trip_id: Optional[int] = None,
) -> Dict[str, int]:
    with SessionLocal() as session:
        day_expr = func.date(Picture.pictured_at)
        stmt = select(day_expr, func.count()).where(Picture.account_id == account_id)
        if trip_id is not None:
            stmt = stmt.where(Picture.trip_id == trip_id)
        stmt = stmt.group_by(day_expr).order_by(day_expr.asc())
        rows = session.execute(stmt).all()
        return {(d.isoformat() if isinstance(d, date) else str(d)): c for d, c in rows}
