from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from src.database import SessionDep
from src.models import State

router = APIRouter()


@router.get("/", response_model=list[State])
def get_states(session: SessionDep):
    states = session.exec(select(State)).all()
    return states


@router.get("/{state_code}", response_model=State)
async def get_state(session: SessionDep, state_code: str):
    statement = select(State).where(State.state_code == state_code)
    result = session.exec(statement).first()
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"State with state code {state_code} was not found",
        )
    return result


@router.post("/find_or_create", status_code=201, response_model=State)
async def find_or_create_state(session: SessionDep, state: State):
    existing_state = session.exec(
        select(State).where(State.state_code == state.state_code)
    ).first()
    if existing_state:
        return existing_state
    session.add(state)
    session.commit()
    session.refresh(state)
    return state
