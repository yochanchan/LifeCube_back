from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List

import pandas as pd
import sqlalchemy
from sqlalchemy import insert, delete, update, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from db_control.connect import engine

# セッションファクトリ
SessionLocal = sessionmaker(bind=engine)


# ---------- 共通ユーティリティ ----------
def _row_to_dict(row: Any) -> Dict[str, Any]:
    """SQLAlchemy ORM オブジェクト → dict へ変換（date は isoformat）"""
    return {
        "id": row.id,
        "user_name": row.user_name,
        "sex": row.sex,
        "birthday": row.birthday.isoformat() if isinstance(row.birthday, date) else None,
        "shozoku": row.shozoku,
        "shokui": row.shokui,
        "skill": row.skill,
        "other": row.other,
    }


# ---------- CRUD ----------
def myinsert(model, values: dict[str, Any]) -> None:
    """1レコード挿入"""
    with SessionLocal() as session, session.begin():
        try:
            session.execute(insert(model).values(**values))
        except IntegrityError as e:
            session.rollback()
            raise e


def myselect(model, record_id: int) -> List[Dict[str, Any]]:
    """主キー検索して list[dict] で返却"""
    with SessionLocal() as session, session.begin():
        result = session.query(model).filter(model.id == record_id).all()
        return [_row_to_dict(row) for row in result]


def myselectAll(model) -> List[Dict[str, Any]]:
    """全件取得"""
    with SessionLocal() as session, session.begin():
        df = pd.read_sql(select(model), con=session.bind)
    # pandas が date を自動で文字列化してくれる
    return df.to_dict(orient="records")


def myupdate(model, values: dict[str, Any]) -> None:
    """主キー更新 (全項目)"""
    record_id = values.pop("id")
    with SessionLocal() as session, session.begin():
        try:
            session.execute(update(model).where(model.id == record_id).values(**values))
        except IntegrityError as e:
            session.rollback()
            raise e


def mydelete(model, record_id: int) -> bool:
    """主キー削除"""
    with SessionLocal() as session, session.begin():
        res = session.execute(delete(model).where(model.id == record_id))
        return res.rowcount > 0
