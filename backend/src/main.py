from fastapi import FastAPI
from sqlmodel import select
from src.database import SessionDep, create_db_and_tables
from src.models import State

app = FastAPI()


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


@app.get("/states/")
def get_states(session: SessionDep) -> list[State]:
    states = session.exec(select(State)).all()
    return list(states)
