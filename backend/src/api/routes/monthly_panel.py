from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlmodel import select
from src.database import SessionDep
from src.models import MonthlyPanel

router = APIRouter()


@router.get("/", response_model=list[MonthlyPanel])
def get_monthly_panels(session: SessionDep):
    return session.exec(select(MonthlyPanel)).all()


@router.get("/{year_month}", response_model=list[MonthlyPanel])
def get_monthly_panel(session: SessionDep, year_month: str):
    statement = select(MonthlyPanel).where(
        MonthlyPanel.year_month == year_month
    )
    results = session.exec(statement).all()
    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"Monthly panel for {year_month} was not found",
        )
    return results


@router.post("/rebuild/")
def rebuild(session: SessionDep):
    pass
