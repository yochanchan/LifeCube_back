# backend/api/pictures.py
from __future__ import annotations

from datetime import datetime, timezone, timedelta
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
from db_control.mymodels import Picture  # 所有チェック用に参照
from api.deps import CurrentUser, get_current_user  # ★ 依存関数

router = APIRouter(prefix="/api/pictures", tags=["pictures"])

# ─────────────────────────────────────────
# DB セッション（PoC向けにこのモジュール内で完結）
# ─────────────────────────────────────────
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# ─────────────────────────────────────────
# JST ヘルパ
# ─────────────────────────────────────────
JST = timezone(timedelta(hours=9))

# ─────────────────────────────────────────
# device_id の簡易推定（User-Agent から）
# ─────────────────────────────────────────
def _pick_device_id(request: Request, provided: Optional[str]) -> Optional[str]:
    if provided:
        v = provided.strip()
        return v[:100] if v else None

    ua = request.headers.get("user-agent") or ""
    for key, label in [
        ("iPhone", "iphone"),
        ("iPad", "ipad"),
        ("Android", "android"),
        ("Windows", "windows"),
        ("Macintosh", "mac"),
        ("Linux", "linux"),
    ]:
        if key in ua:
            return label
    return None

# ─────────────────────────────────────────
# 管理者/一般で account_id を決める
# 一般: 自分のアカウントに固定
# 管理者: None（＝全件）
# ─────────────────────────────────────────
def _effective_account_id(user: CurrentUser) -> Optional[int]:
    return None if user.role == "admin" else user.account_id

# 所有チェック（画像バイナリや削除で使用）
def _assert_can_access_picture(db: Session, picture_id: int, user: CurrentUser) -> None:
    pic = db.get(Picture, picture_id)
    if not pic:
        raise HTTPException(status_code=404, detail="picture not found")
    if user.role != "admin" and pic.account_id != user.account_id:
        raise HTTPException(status_code=403, detail="forbidden")

# ---------------------------
# Create (upload)
# ---------------------------
@router.post("", status_code=201)
async def create_picture(
    request: Request,
    current: CurrentUser = Depends(get_current_user),  # ★ ログイン必須
    # ファイル本体（必須）
    file: UploadFile = File(..., description="Captured image file"),
    # メタ
    trip_id: Optional[int] = Form(None),
    device_id: Optional[str] = Form(None),  # 指定無ければ UA から推定
    pictured_at: Optional[datetime] = Form(
        None,
        description="ISO8601. Omit to use server-side JST now.",
    ),
    db: Session = Depends(get_db),
):
    account_id = current.account_id
    device_id_final = _pick_device_id(request, device_id)

    # pictured_at が未指定なら「サーバ側 JST 現在」を採用
    pictured_at_final: datetime = pictured_at or datetime.now(JST)

    try:
        image_binary = await file.read()
        content_type = file.content_type or "application/octet-stream"

        pic_id = crud.create_picture_with_data(
            db=db,
            account_id=account_id,
            trip_id=trip_id,
            device_id=device_id_final,
            image_binary=image_binary,
            content_type=content_type,
            pictured_at=pictured_at_final,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ★ レスポンス拡張：image_path を追加（フル画像URL）
    return {
        "picture_id": pic_id,
        "thumbnail_path": f"/api/pictures/{pic_id}/thumbnail?w=256",  # 互換のため残す
        "image_path": f"/api/pictures/{pic_id}/image",                # ← 新規
        "pictured_at": pictured_at_final.isoformat(),                 # 例: 2025-08-16T12:34:56+09:00
        "device_id": device_id_final,                                 # 例: "android" / "dev_xxx" / None
    }

# ---------------------------
# Read (dates)
# ---------------------------
@router.get("/dates", response_model=List[str])
def get_dates(
    # 互換のため残すが、サーバ側で上書きする
    account_id: Optional[int] = Query(None, ge=1),
    trip_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),  # ★ ログイン必須
):
    effective_id = _effective_account_id(current)
    return crud.list_picture_dates(db=db, account_id=effective_id, trip_id=trip_id)

# ---------------------------
# Read (by date)
# ---------------------------
@router.get("/by-date")
def get_pictures_by_date(
    date: str = Query(..., description="YYYY-MM-DD (JST)"),
    # 互換のため残すが、サーバ側で上書きする
    account_id: Optional[int] = Query(None, ge=1),
    trip_id: Optional[int] = Query(None, ge=1),
    thumb_w: int = Query(256, ge=64, le=1024),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),  # ★ ログイン必須
):
    effective_id = _effective_account_id(current)
    try:
        return crud.list_pictures_by_date(
            db=db,
            account_id=effective_id,
            target_date=date,
            trip_id=trip_id,
            order_desc=False,
            thumb_w=thumb_w,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------------------
# Binary: full image
# ---------------------------
@router.get("/{picture_id}/image")
def get_image(
    picture_id: int,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),  # ★ ログイン必須 & 所有チェック
):
    _assert_can_access_picture(db, picture_id, current)
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
    current: CurrentUser = Depends(get_current_user),  # ★ 同上
):
    _assert_can_access_picture(db, picture_id, current)
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
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),  # ★ ログイン必須
):
    # 一般: 自分のだけ、管理者: だれのでも
    owner_account_id = None if current.role == "admin" else current.account_id
    ok = crud.delete_picture_one(db=db, picture_id=picture_id, owner_account_id=owner_account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="picture not found")
    return Response(status_code=204)
