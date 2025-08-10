from __future__ import annotations
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os

load_dotenv()

# 共通情報
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME")

# MySQLのURL構築
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ── 環境で CA パスが指定されていれば追加 ──
SSL_CA_PATH = os.getenv("SSL_CA_PATH")  # .env で指定（ローカルだけ入れる）

connect_args = {}
if SSL_CA_PATH:
    connect_args["ssl_ca"] = SSL_CA_PATH

engine = create_engine(
    DATABASE_URL,
    echo=True,             # 運用時は False 推奨
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args=connect_args,
)
