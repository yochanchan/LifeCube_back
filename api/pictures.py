# backend/api/pictures.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)

from sqlalchemy.orm import Session, sessionmaker

from db_control.connect import engine
from db_control import crud
from auth.session import require_session

router = APIRouter(prefix="/api/pictures", tags=["pictures"])

# ─────────────────────────────────────────
# DB セッション（このモジュール内で完結）
# ─────────────────────────────────────────
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────
# device_id の簡易推定（User-Agent から）
# ・フォームで device_id が来ていればそれを優先
# ・無ければ UA を見て "iphone" / "android" / "windows" / "mac" / "linux" 程度でラベル化
# ・最長 100 文字に丸めて picture.device_id のカラム制約に合わせる
# ─────────────────────────────────────────
def _pick_device_id(request: Request, provided: Optional[str]) -> Optional[str]:
    if provided:
        v = provided.strip()
        return v[:100] if v else None

    ua = request.headers.get("user-agent") or ""
    ua_map = [
        ("iPhone", "iphone"),
        ("iPad", "ipad"),
        ("Android", "android"),
        ("Windows", "windows"),
        ("Macintosh", "mac"),
        ("Linux", "linux"),
    ]
    for key, label in ua_map:
        if key in ua:
            return label
    return None


# ---------------------------
# Create (upload)
# ---------------------------
@router.post("", status_code=201)
async def create_picture(
    request: Request,
    # ファイル本体（必須）
    file: UploadFile = File(..., description="Captured image file"),
    # メタ
    trip_id: Optional[int] = Form(None),
    device_id: Optional[str] = Form(None),  # ← 指定が無ければ UA から推定
    pictured_at: Optional[datetime] = Form(
        None,
        description="ISO8601. Omit to use server-side JST now.",
    ),
    db: Session = Depends(get_db),
):
    """
    画像を1件登録して picture_id を返す。
    multipart/form-data でファイルを送ること。
    ※ account_id はクッキーセッションから取得（ログイン必須）
    """
    # ① セッション必須（未ログインは 401）
    s = require_session(request)
    account_id = s.account_id

    # ② device_id（フォーム優先 → UA 推定）
    device_id_final = _pick_device_id(request, device_id)

    try:
        image_binary = await file.read()
        content_type = file.content_type or "application/octet-stream"

        pic_id = crud.create_picture_with_data(
            db=db,                       # ← DI：crud 側が db: Session を受ける想定
            account_id=account_id,       # ← セッションから
            trip_id=trip_id,
            device_id=device_id_final,   # ← UA 推定 or フォーム値
            image_binary=image_binary,
            content_type=content_type,
            pictured_at=pictured_at,     # None ならサーバ側で JST 現在時刻
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "picture_id": pic_id,
        "thumbnail_path": f"/api/pictures/{pic_id}/thumbnail?w=256",
    }


# ---------------------------
# Read (dates)
# ---------------------------
@router.get("/dates", response_model=List[str])
def get_dates(
    account_id: Optional[int] = Query(None, ge=1),
    trip_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
):
    """JST基準で picture が存在する日付の一覧を返す。account_id 未指定なら全アカウント横断。"""
    return crud.list_picture_dates(db=db, account_id=account_id, trip_id=trip_id)


# ---------------------------
# Read (by date)
# ---------------------------
@router.get("/by-date")
def get_pictures_by_date(
    date: str = Query(..., description="YYYY-MM-DD (JST)"),
    account_id: Optional[int] = Query(None, ge=1),
    trip_id: Optional[int] = Query(None, ge=1),
    thumb_w: int = Query(256, ge=64, le=1024),
    db: Session = Depends(get_db),
):
    """指定日の（JST 00:00〜翌00:00）に撮影された写真のメタ情報を返す。"""
    try:
        items = crud.list_pictures_by_date(
            db=db,
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
def get_image(picture_id: int, db: Session = Depends(get_db)):
    res: Optional[Tuple[str, bytes]] = crud.get_picture_image(db=db, picture_id=picture_id)
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
def get_thumbnail(
    picture_id: int,
    w: int = Query(256, ge=64, le=1024),
    db: Session = Depends(get_db),
):
    res: Optional[Tuple[str, bytes]] = crud.get_picture_thumbnail(
        db=db, picture_id=picture_id, max_px=w, prefer_webp=True
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
    db: Session = Depends(get_db),
):
    ok = crud.delete_picture_one(db=db, picture_id=picture_id, owner_account_id=account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="picture not found")
    # 204 No Content
    return Response(status_code=204)
