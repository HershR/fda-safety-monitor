import os

from sqlalchemy.engine import URL

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_BUCKET = os.getenv("GCP_BUCKET_NAME")
GCP_SERVICE_ACCOUNT_KEY = os.getenv("GCP_SERVICE_ACCOUNT_KEY")

DB_NAME = os.getenv("DB_NAME", "fda_data")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

DATABASE_URI = URL.create(
    "postgresql+psycopg",
    username=DB_USER,
    password=DB_PASSWORD,
    host=None if DB_HOST.startswith("/") else DB_HOST,
    port=int(DB_PORT),
    database=DB_NAME,
    query={"host": DB_HOST} if DB_HOST.startswith("/") else {},
)
