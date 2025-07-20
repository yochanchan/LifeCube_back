from sqlalchemy import create_engine
from pathlib import Path

import os
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()
CA_FILE = Path("/tmp/BaltimoreCyberTrustRoot.pem")

# データベース接続情報
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_NAME = os.getenv('DB_NAME')

# MySQLのURL構築
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

SSL_CA_PATH = os.getenv('SSL_CA_PATH')
# エンジンの作成
engine = create_engine(
    DATABASE_URL,
    echo=True,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args = {
    "ssl": {"ca": str(CA_FILE)}   # ← PyMySQL が理解できる形
    }
)
