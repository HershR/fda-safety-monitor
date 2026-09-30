from datetime import UTC, datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel
from src.enums import PathogenSource


class State(SQLModel, table=True):
    state_code: str = Field(primary_key=True, max_length=2)
    state_name: str


class FiscalYear(SQLModel, table=True):
    fiscal_year: int = Field(primary_key=True)
    fy_start: datetime = Field(default=lambda: datetime.now(UTC))
    fy_end: datetime = Field(default=lambda: datetime.now(UTC))


class FDAFunding(SQLModel, table=True):
    fiscal_year: int = Field(
        primary_key=True, foreign_key="fiscal_year.fiscal_year"
    )
    collected_at: datetime = Field(default=lambda: datetime.now(UTC))
    total_obligations: Decimal
    transaction_count: int
    new_award_count: int


class IllnessMonthly(SQLModel, table=True):
    state_code: str = Field(max_length=2)
    year_month: str = Field(max_length=7)
    pathogen: str
    source_type: PathogenSource
    isolate_count: int
    collected_at: datetime = Field(default=lambda: datetime.now(UTC))


class RecallEvent(SQLModel, table=True):
    event_id: str
    state_code: str
    classification: str
    recall_initiation_date: datetime
