from fastapi import FastAPI
from sqlmodel import select

from src.database import SessionDep, create_db_and_tables
from src.models import State
from .recall_scraper import router as recall_scraper_router

app = FastAPI()

app.include_router(recall_scraper_router)

@app.on_event("startup")
def on_startup():
    # create_db_and_tables()
    pass


@app.get("/states/")
def get_states(session: SessionDep, response_model=list[State]):
    states = session.exec(select(State)).all()
    return states
