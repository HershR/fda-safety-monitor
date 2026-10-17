from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.router import api_router
from src.database import create_db_and_tables
from src.seed_db import seed_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # start up
    create_db_and_tables()
    seed_db()
    yield
    # shutdown


app = FastAPI(lifespan=lifespan)
app.include_router(api_router)


@app.get("/")
def get_root():
    return {"message": "fda monitor backend running"}
