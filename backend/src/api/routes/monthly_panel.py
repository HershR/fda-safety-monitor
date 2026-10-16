from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from statistics import median
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from sqlmodel import Session, func, select
from src.database import SessionDep
from src.enums import PathogenSource
from src.models import (
    FiscalYear,
    IllnessMonthly,
    MonthlyPanel,
    RecallEvent,
    State,
)
from src.utils.pipeline.db_utils import save_rows

router = APIRouter()

FIRST_YEAR = 2012


def month_range(year_month: str) -> tuple[date, date]:
    """Returns (first day of month, first day of next month)"""
    year, month = map(int, year_month.split("-"))
    start = date(year, month, 1)
    end = date(year + month // 12, month % 12 + 1, 1)
    return start, end


def all_months(last_day: date) -> list[str]:
    """YYYY-MM strings from FIRST_YEAR to last_day"""
    months, year, month = [], FIRST_YEAR, 1
    while (year, month) <= (last_day.year, last_day.month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = year + month // 12, month % 12 + 1
    return months


def find_fiscal_year(
    fiscal_years: Sequence[FiscalYear], day: date
) -> int | None:
    for fy in fiscal_years:
        if fy.fy_start <= day <= fy.fy_end:
            return fy.fiscal_year
    return None


def build_month(
    year_month: str,
    fiscal_year: int,
    state_codes: Sequence[str],
    events: Sequence[RecallEvent],
    illness: Sequence[IllnessMonthly],
) -> list[MonthlyPanel]:
    """One row per state for the given month"""
    events_by_state: dict[str | None, list[RecallEvent]] = defaultdict(list)
    for e in events:
        events_by_state[e.state_code].append(e)

    human = defaultdict(int)
    food = defaultdict(int)
    for row in illness:
        if row.source_type == PathogenSource.HUMAN:
            human[row.state_code] += row.isolate_count
        elif row.source_type == PathogenSource.FOOD:
            food[row.state_code] += row.isolate_count

    rows = []
    for state in state_codes:
        state_events = events_by_state[state]
        class_i = 0
        for e in state_events:
            if e.classification == "Class I":
                class_i += 1
        lags = [
            e.classification_lag_days
            for e in state_events
            if e.classification_lag_days is not None
        ]
        rows.append(
            MonthlyPanel(
                state_code=state,
                year_month=year_month,
                fiscal_year=fiscal_year,
                recall_events=len(state_events),
                class_i_events=class_i,
                class_i_share=(
                    Decimal(class_i) / len(state_events)
                    if state_events
                    else None
                ),
                median_classification_lag=(
                    Decimal(median(lags)) if lags else None
                ),
                isolates_human=human.get(state),
                isolates_food_reference=food.get(state),
            )
        )
    return rows


def rebuild_month(
    session: Session,
    year_month: str,
    state_codes: Sequence[str],
    fiscal_years: Sequence[FiscalYear],
) -> int:
    start, end = month_range(year_month)
    fiscal_year = find_fiscal_year(fiscal_years, start)
    if fiscal_year is None:
        raise HTTPException(
            status_code=500,
            detail=f"No fiscal year for {year_month}, "
            "add it to data/fiscal_years.json",
        )
    events = session.exec(
        select(RecallEvent).where(
            RecallEvent.report_date >= start,
            RecallEvent.report_date < end,
            RecallEvent.state_code.is_not(None),
        )
    ).all()
    illness = session.exec(
        select(IllnessMonthly).where(IllnessMonthly.year_month == year_month)
    ).all()
    rows = build_month(year_month, fiscal_year, state_codes, events, illness)
    return save_rows(session, rows, True)


def rebuild_months(session: Session, months: list[str]) -> int:
    """
    Rebuilds the given YYYY-MM months, skipping months after the latest recall.
    Does not delete old rows, existing rows are overwritten.
    """
    last_report = session.exec(select(func.max(RecallEvent.report_date))).one()
    if last_report is None:
        return 0
    last_month = f"{last_report.year:04d}-{last_report.month:02d}"
    state_codes = session.exec(select(State.state_code)).all()
    fiscal_years = session.exec(select(FiscalYear)).all()

    saved = 0
    for year_month in months:
        if year_month <= last_month:
            saved += rebuild_month(
                session, year_month, state_codes, fiscal_years
            )
    session.commit()
    return saved


def rebuild_panel(session: Session) -> int:
    last_report = session.exec(select(func.max(RecallEvent.report_date))).one()
    if last_report is None:
        return 0
    return rebuild_months(session, all_months(last_report))


@router.get("/", response_model=list[MonthlyPanel])
def get_monthly_panels(
    session: SessionDep,
    states: Annotated[list[str] | None, Query()] = None,
    start_year: int | None = None,
    end_year: int | None = None,
    fiscal_year: int | None = None,
):
    """List panel rows, filtered by states, calendar years or fiscal year"""
    statement = select(MonthlyPanel)
    if states:
        statement = statement.where(MonthlyPanel.state_code.in_(states))
    if start_year:
        statement = statement.where(
            MonthlyPanel.year_month >= f"{start_year}-01"
        )
    if end_year:
        statement = statement.where(
            MonthlyPanel.year_month <= f"{end_year}-12"
        )
    if fiscal_year:
        statement = statement.where(MonthlyPanel.fiscal_year == fiscal_year)
    statement = statement.order_by(
        MonthlyPanel.year_month, MonthlyPanel.state_code
    )
    return session.exec(statement).all()


@router.get("/{year_month}", response_model=list[MonthlyPanel])
def get_monthly_panel(
    session: SessionDep,
    year_month: str,
    states: Annotated[list[str] | None, Query()] = None,
):
    """Panel rows for one YYYY-MM month, optionally filtered by states"""
    statement = select(MonthlyPanel).where(
        MonthlyPanel.year_month == year_month
    )
    if states:
        statement = statement.where(MonthlyPanel.state_code.in_(states))
    statement = statement.order_by(MonthlyPanel.state_code)
    results = session.exec(statement).all()
    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"Monthly panel for {year_month} was not found",
        )
    return results


@router.post("/rebuild/")
def rebuild(session: SessionDep):
    """Rebuild every month from 2012 to the latest recall"""
    return {"monthly_panel": rebuild_panel(session)}


@router.post("/rebuild/{year}")
def rebuild_year(session: SessionDep, year: int):
    """Rebuild all months of one year, up to the latest recall"""
    months = [f"{year:04d}-{month:02d}" for month in range(1, 13)]
    return {"monthly_panel": rebuild_months(session, months)}


@router.post("/rebuild/{year}/{month}")
def rebuild_year_month(
    session: SessionDep, year: int, month: Annotated[int, Path(ge=1, le=12)]
):
    """Rebuild one month"""
    return {
        "monthly_panel": rebuild_months(session, [f"{year:04d}-{month:02d}"])
    }
