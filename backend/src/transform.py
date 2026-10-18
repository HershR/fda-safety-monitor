import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from statistics import median

from fastapi import HTTPException
from sqlmodel import Session, func, select

from src.db_utils import save_rows
from src.enums import PathogenSource
from src.models import (
    FiscalYear,
    IllnessMonthly,
    RecallAnnouncement,
    RecallEvent,
    State,
    StateMonthlySummary,
)

FIRST_YEAR = 2012


def month_range(year_month: str) -> tuple[date, date]:
    """Get the first day of the selected month and first day of next month"""
    year_month_split = year_month.split("-")
    if len(year_month_split) != 2:
        raise ValueError("Provided year_month is invalid format: ", year_month)
    year, month = int(year_month_split[0]), int(year_month_split[1])

    start = date(year, month, 1)
    if month == 12:
        end_year = year + 1
        end_month = 1
    else:
        end_year = year
        end_month = month + 1
    end = date(end_year, end_month, 1)
    return start, end


def all_months(last_day: date) -> list[str]:
    """Get all YYYY-MM strings from FIRST_YEAR to last_day"""
    months = []
    year = FIRST_YEAR
    month = 1
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
) -> list[StateMonthlySummary]:
    """Create a monthly summary for the givent states for the given month"""
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
            StateMonthlySummary(
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
            RecallEvent.state_code.is_not(None),  # type: ignore
        )
    ).all()
    illness = session.exec(
        select(IllnessMonthly).where(IllnessMonthly.year_month == year_month)
    ).all()
    rows = build_month(year_month, fiscal_year, state_codes, events, illness)
    return save_rows(session, rows, True)  # type: ignore


def rebuild_months(session: Session, months: list[str]) -> int:
    """
    Rebuilds the given YYYY-MM months, skipping months after the latest recall.
    Does not delete old rows, existing rows are updated.
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


def rebuild_all(session: Session) -> int:
    last_report = session.exec(select(func.max(RecallEvent.report_date))).one()
    if last_report is None:
        return 0
    return rebuild_months(session, all_months(last_report))


# Announcements usually come out on or shortly after the day the recall starts
DAYS_BEFORE_INITIATION = 7
DAYS_AFTER_INITIATION = 30
MIN_COMPANY_SIMILARITY = 0.85
COMPANY_SUFFIXES = {
    "inc",
    "llc",
    "co",
    "corp",
    "corporation",
    "company",
    "ltd",
}


def clean_company(name: str) -> str:
    # remove puntuation and common suffixes
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    return " ".join(w for w in words if w not in COMPANY_SUFFIXES)


def is_same_company(a: str, b: str) -> bool:
    similarity = SequenceMatcher(
        None, clean_company(a), clean_company(b)
    ).ratio()
    return similarity >= MIN_COMPANY_SIMILARITY


def find_recall_event(
    session: Session, announcement: RecallAnnouncement
) -> RecallEvent | None:
    """Recall event from the same company that started closest to the announcement"""
    announced = announcement.announce_date
    events = session.exec(
        select(RecallEvent).where(
            RecallEvent.recall_initiation_date
            >= announced - timedelta(days=DAYS_AFTER_INITIATION),
            RecallEvent.recall_initiation_date
            <= announced + timedelta(days=DAYS_BEFORE_INITIATION),
        )
    ).all()

    same_company = [
        e
        for e in events
        if is_same_company(announcement.company, e.recalling_firm)
    ]
    if not same_company:
        return None
    return min(
        same_company,
        key=lambda e: abs((e.recall_initiation_date - announced).days),
    )


def match_announcements(session: Session) -> int:
    """
    Link unmatched announcements to their openFDA recall event.
    Does not commit, returns the number of announcements matched.
    """
    announcements = session.exec(
        select(RecallAnnouncement).where(
            RecallAnnouncement.event_id.is_(None)  # type: ignore
        )
    ).all()

    matched = 0
    for announcement in announcements:
        event = find_recall_event(session, announcement)
        if event:
            announcement.event_id = event.event_id
            announcement.in_openfda = True
            session.add(announcement)
            matched += 1
    return matched
