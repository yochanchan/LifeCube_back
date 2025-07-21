from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import json
from datetime import date
from db_control import crud, mymodels

router = APIRouter(prefix="/youc", tags=["yochan"])

##### Userの型定義
class User(BaseModel):
    id: int = Field(..., ge=1, description="必須（1以上）")
    user_name: str
    sex: str
    birthday: date
    shozoku: str | None = None
    shokui: str | None = None
    skill: str | None = None
    other: str | None = None


# ---------- CRUD Endpoints ----------user: Userが型ヒントで、response_model=Userが戻り値の指定
@router.post("/yochan_optional", response_model=User)
def create_user(user: User):
    """ユーザー新規作成"""
    crud.myinsert(mymodels.Users, user.model_dump())
    fetched = crud.myselect(mymodels.Users, user.id)
    if not fetched:
        raise HTTPException(status_code=502, detail="Insert failed")
    return fetched[0]


@router.get("/yochan_optional", response_model=User)
def read_one_user(id: int = Query(..., ge=1)):
    """ユーザー1件取得"""
    fetched = crud.myselect(mymodels.Users, id)
    if not fetched:
        raise HTTPException(status_code=404, detail="User not found")
    return fetched[0]



@router.put("/yochan_optional", response_model=User)
def update_user(user: User):
    """ユーザー更新"""
    crud.myupdate(mymodels.Users, user.model_dump())
    fetched = crud.myselect(mymodels.Users, user.id)
    if not fetched:
        raise HTTPException(status_code=404, detail="User not found after update")
    return fetched[0]


@router.delete("/yochan_optional")
def delete_user(id: int = Query(..., ge=1)):
    """ユーザー削除"""
    deleted = crud.mydelete(mymodels.Users, id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": id, "status": "deleted"}
