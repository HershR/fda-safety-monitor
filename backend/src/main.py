from database import SessionDep, create_db_and_tables
from fastapi import FastAPI
from models import State
from sqlmodel import select

app = FastAPI()


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


@app.get("/states/")
def get_states(session: SessionDep) -> list[State]:
    states = session.exec(select(State)).all()
    return list(states)
