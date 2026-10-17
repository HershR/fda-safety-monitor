from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from sqlmodel import select
from src.database import SessionDep
from src.models import StateMonthlySummary
from src.transform import rebuild_all, rebuild_months

router = APIRouter()


@router.get("/", response_model=list[StateMonthlySummary])
def get_state_monthly_summaries(
    session: SessionDep,
    states: Annotated[list[str] | None, Query()] = None,
    start_year: int | None = None,
    end_year: int | None = None,
    fiscal_year: int | None = None,
):
    """List summary rows, filtered by states, calendar years or fiscal year"""
    statement = select(StateMonthlySummary)
    if states:
        statement = statement.where(StateMonthlySummary.state_code.in_(states))  # type: ignore
    if start_year:
        statement = statement.where(
            StateMonthlySummary.year_month >= f"{start_year}-01"
        )
    if end_year:
        statement = statement.where(
            StateMonthlySummary.year_month <= f"{end_year}-12"
        )
    if fiscal_year:
        statement = statement.where(
            StateMonthlySummary.fiscal_year == fiscal_year
        )
    statement = statement.order_by(
        StateMonthlySummary.year_month, StateMonthlySummary.state_code
    )
    return session.exec(statement).all()


@router.get("/{year_month}", response_model=list[StateMonthlySummary])
def get_state_monthly_summary(
    session: SessionDep,
    year_month: str,
    states: Annotated[list[str] | None, Query()] = None,
):
    """Get the State Monthly Summary for one month(YYYY-mm), optionally filtered by states"""
    statement = select(StateMonthlySummary).where(
        StateMonthlySummary.year_month == year_month
    )
    if states:
        statement = statement.where(StateMonthlySummary.state_code.in_(states))  # type: ignore
    statement = statement.order_by(StateMonthlySummary.state_code)
    results = session.exec(statement).all()
    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"State monthly summary for {year_month} was not found",
        )
    return results


@router.post("/rebuild/")
def rebuild(session: SessionDep):
    """Rebuild every month from 2012 to the latest recall"""
    return {"state_monthly_summary": rebuild_all(session)}


@router.post("/rebuild/{year}")
def rebuild_year(session: SessionDep, year: int):
    """Rebuild all months of one year, up to the latest recall"""
    months = [f"{year:04d}-{month:02d}" for month in range(1, 13)]
    return {"state_monthly_summary": rebuild_months(session, months)}


@router.post("/rebuild/{year}/{month}")
def rebuild_year_month(
    session: SessionDep, year: int, month: Annotated[int, Path(ge=1, le=12)]
):
    """Rebuild one month"""
    return {
        "state_monthly_summary": rebuild_months(
            session, [f"{year:04d}-{month:02d}"]
        )
    }
