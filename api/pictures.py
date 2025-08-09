from __future__ import annotations

from typing import List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Response

from db_control import crud

router = APIRouter(prefix="/api/pictures", tags=["pictures"])

@router.get("/dates", response_model=List[str])
def get_dates(
    account_id: Optional[int] = Query(None, ge=1),
    trip_id: Optional[int] = Query(None, ge=1),
):
    """
    JST 基準で picture が存在する日付の一覧を返す。
    account_id 未指定なら全アカウント横断で集計。
    """
    return crud.list_picture_dates(account_id=account_id, trip_id=trip_id)

@router.get("/by-date")
def get_pictures_by_date(
    date: str = Query(..., description="YYYY-MM-DD (JST)"),
    account_id: Optional[int] = Query(None, ge=1),
    trip_id: Optional[int] = Query(None, ge=1),
    thumb_w: int = Query(256, ge=64, le=1024),
):
    """
    指定日の（JST 00:00〜翌00:00）に撮影された写真のメタ情報を返す。
    account_id 未指定なら全アカウント横断。
    """
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

@router.get("/{picture_id}/image")
def get_image(picture_id: int):
    res: Optional[Tuple[str, bytes]] = crud.get_picture_image(picture_id)
    if not res:
        raise HTTPException(status_code=404, detail="picture not found")
    content_type, binary = res
    return Response(content=binary, media_type=content_type)

@router.get("/{picture_id}/thumbnail")
def get_thumbnail(picture_id: int, w: int = Query(256, ge=64, le=1024)):
    res: Optional[Tuple[str, bytes]] = crud.get_picture_thumbnail(picture_id, max_px=w, prefer_webp=True)
    if not res:
        raise HTTPException(status_code=404, detail="picture not found")
    content_type, binary = res
    return Response(content=binary, media_type=content_type)
