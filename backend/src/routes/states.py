from fastapi import APIRouter, HTTPException, Response, status
from sqlmodel import select
from src.database import SessionDep
from src.models import State

router = APIRouter()


@router.get("/", response_model=list[State])
def get_states(session: SessionDep):
    """Get all State code and state names"""
    states = session.exec(select(State)).all()
    return states


@router.get("/{state_code}", response_model=State)
async def get_state(session: SessionDep, state_code: str):
    """Fetch a State's details"""
    statement = select(State).where(State.state_code == state_code)
    result = session.exec(statement).first()
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"State with state code {state_code} was not found",
        )
    return result


@router.post(
    "/find_or_create",
    status_code=status.HTTP_201_CREATED,
    response_model=State,
)
async def find_or_create_state(
    session: SessionDep, state: State, response: Response
):
    """Create a new State, if it exists return it"""
    existing_state = session.exec(
        select(State).where(State.state_code == state.state_code)
    ).first()
    if existing_state:
        response.status_code = status.HTTP_200_OK
        return existing_state
    session.add(state)
    session.commit()
    session.refresh(state)
    return state
