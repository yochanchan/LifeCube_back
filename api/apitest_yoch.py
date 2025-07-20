from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/youc", tags=["starter"])


from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
import requests
import json
from db_control import crud, mymodels



##### insert　this.Userをinsertする。Userが型ヒントですよ。
@router.post("/user")
def create_user(user: mymodels.User):
    values = user.dict()
    tmp = crud.myinsert(mymodels.User, values)
    result = crud.myselect(mymodels.User, values.get("id"))

    if result:
        result_obj = json.loads(result)
        return result_obj if result_obj else None
    return HTTPException(status_code=402, detail="Something wrong")



@router.get("/user")
def read_one_user(id: str = Query(...)):
    result = crud.myselect(mymodels.User, id)
    if not result:
        raise HTTPException(status_code=404, detail="user not found")
    result_obj = json.loads(result)
    return result_obj[0] if result_obj else None


@router.get("/allusers")
def read_all_user():
    result = crud.myselectAll(mymodels.User)
    # 結果がNoneの場合は空配列を返す
    if not result:
        return []
    # JSON文字列をPythonオブジェクトに変換
    return json.loads(result)


@router.put("/user")
def update_user(user: mymodels.User):
    values = user.dict()
    values_original = values.copy()
    tmp = crud.myupdate(mymodels.User, values)
    result = crud.myselect(mymodels.User, values_original.get("id"))
    if not result:
        raise HTTPException(status_code=404, detail="user not found")
    result_obj = json.loads(result)
    return result_obj[0] if result_obj else None


@router.delete("/user")
def delete_user(id: str = Query(...)):
    result = crud.mydelete(mymodels.User, id)
    if not result:
        raise HTTPException(status_code=404, detail="user not found")
    return {"id": id, "status": "deleted"}

