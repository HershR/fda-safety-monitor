from database import SessionDep
from fastapi import FastAPI, HTTPException
from models import State
from sqlmodel import select
from pathlib import Path

app = FastAPI()


@app.get("/states/")
def get_states(session: SessionDep, response_model=list[State]):
    states = session.exec(select(State)).all()

    return states


@app.get("/states/fill/")
def populate_states_table(session: SessionDep):
    states = session.exec(select(State)).all()
    if states:
        raise HTTPException(500, detail="States already filled")

    try:
        with open(
            f"{Path(__file__).resolve().parent}/data/state-codes.json", "r"
        ) as file:
            import json

            data = json.load(file)
            for key, value in data.items():
                state = State(state_code=key, state_name=value)
                session.add(state)
            session.commit()
            session.refresh()
    except BaseException as e:
        print(e)
        raise HTTPException(500, detail=f"Failed to populate states: {e}")
    return {"message": "State loaded"}
