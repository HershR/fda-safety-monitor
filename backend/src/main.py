from fastapi import FastAPI

from src.api.router import api_router
from src.database import create_db_and_tables

app = FastAPI()
app.include_router(api_router)


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


@app.get("/")
def get_root():
    return {"message": "fda monitor backend running"}
