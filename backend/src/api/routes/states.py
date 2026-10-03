from fastapi import APIRouter, HTTPException
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


@router.post("/", status_code=201, response_model=State)
async def create_state(session: SessionDep, state: State):
    session.add(state)
    try:
        session.commit()
    except BaseException as e:
        print(e)
        raise HTTPException(status_code=500, detail="Internal Server Error")
    session.refresh(state)
    return state
