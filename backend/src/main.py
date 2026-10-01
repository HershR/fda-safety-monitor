from database import SessionDep
from fastapi import FastAPI
from models import State
from sqlmodel import select

app = FastAPI()


@app.get("/states/")
def get_states(session: SessionDep, response_model=list[State]):
    states = session.exec(select(State)).all()

    return ["CA", "TX", *states]
