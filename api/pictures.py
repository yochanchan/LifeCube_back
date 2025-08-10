from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile, File, Form

from db_control import crud

router = APIRouter(prefix="/api/pictures", tags=["pictures"])

# ---------------------------
# Create (upload)
# ---------------------------
@router.post("", status_code=201)
async def create_picture(
    # ファイル本体（必須）
    file: UploadFile = File(..., description="Captured image file"),
    # メタ（PoCの既定値をサーバ側でも持つ）
    account_id: int = Form(1, description="Fixed for PoC: 1"),
    trip_id: Optional[int] = Form(None),
    device_id: Optional[str] = Form("yochan"),
    pictured_at: Optional[datetime] = Form(
        None,
        description="ISO8601. Omit to use server-side JST now.",
    ),
):
    """
    画像を1件登録して picture_id を返す。
    multipart/form-data でファイルを送ること。
    """
    try:
        image_binary = await file.read()
        content_type = file.content_type or "application/octet-stream"

        pic_id = crud.create_picture_with_data(
            account_id=account_id,
            trip_id=trip_id,
            device_id=device_id,
            image_binary=image_binary,
            content_type=content_type,
            pictured_at=pictured_at,  # NoneならサーバがJST現在時刻を入れる
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"picture_id": pic_id, "thumbnail_path": f"/api/pictures/{pic_id}/thumbnail?w=256"}

# ---------------------------
# Read (dates)
# ---------------------------
@router.get("/dates", response_model=List[str])
def get_dates(
    account_id: Optional[int] = Query(None, ge=1),
    trip_id: Optional[int] = Query(None, ge=1),
    ):
    """JST基準で picture が存在する日付の一覧を返す。account_id 未指定なら全アカウント横断。"""
    return crud.list_picture_dates(account_id=account_id, trip_id=trip_id)

# ---------------------------
# Read (by date)
# ---------------------------
@router.get("/by-date")
def get_pictures_by_date(
    date: str = Query(..., description="YYYY-MM-DD (JST)"),
    account_id: Optional[int] = Query(None, ge=1),
    trip_id: Optional[int] = Query(None, ge=1),
    thumb_w: int = Query(256, ge=64, le=1024),
):
    """指定日の（JST 00:00〜翌00:00）に撮影された写真のメタ情報を返す。"""
    try:
        items = crud.list_pictures_by_date(
            account_id=account_id,
            target_date=date,
            trip_id=trip_id,
            order_desc=False,
            thumb_w=thumb_w,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return items

# ---------------------------
# Binary: full image
# ---------------------------
@router.get("/{picture_id}/image")
def get_image(picture_id: int):
    res: Optional[Tuple[str, bytes]] = crud.get_picture_image(picture_id)
    if not res:
        raise HTTPException(status_code=415, detail="unsupported or corrupt image data")
    content_type, binary = res
    return Response(
        content=binary,
        media_type=content_type,
        headers={"Cache-Control": "no-store, max-age=0, must-revalidate"},
    )

# ---------------------------
# Binary: thumbnail
# ---------------------------
@router.get("/{picture_id}/thumbnail")
def get_thumbnail(picture_id: int, w: int = Query(256, ge=64, le=1024)):
    res: Optional[Tuple[str, bytes]] = crud.get_picture_thumbnail(
        picture_id, max_px=w, prefer_webp=True
    )
    if not res:
        raise HTTPException(status_code=415, detail="unsupported or corrupt image data")
    content_type, binary = res
    return Response(
        content=binary,
        media_type=content_type,
        headers={"Cache-Control": "no-store, max-age=0, must-revalidate"},
    )

# ---------------------------
# Delete
# ---------------------------
@router.delete("/{picture_id}", status_code=204)
def delete_picture(
    picture_id: int,
    account_id: Optional[int] = Query(None, ge=1),
    ):
    ok = crud.delete_picture_one(picture_id=picture_id, owner_account_id=account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="picture not found")
    # 204 No Content
    return Response(status_code=204)