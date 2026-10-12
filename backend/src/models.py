from datetime import UTC, date, datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel

from src.enums import PathogenSource


class State(SQLModel, table=True):
    __tablename__ = "state"

    state_code: str = Field(primary_key=True, max_length=2)
    state_name: str


class FiscalYear(SQLModel, table=True):
    __tablename__ = "fiscal_year"

    fiscal_year: int = Field(primary_key=True)
    fy_start: date
    fy_end: date


class RecallEvent(SQLModel, table=True):
    __tablename__ = "recall_event"

    event_id: str = Field(primary_key=True)
    state_code: str | None = Field(default=None, max_length=2, foreign_key="state.state_code")
    classification: str
    recall_initiation_date: date
    center_classification_date: date | None = None
    report_date: date
    status: str
    voluntary_mandated: str
    recalling_firm: str
    classification_lag_days: int |None = None
    product_count: int
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RecallProduct(SQLModel, table=True):
    __tablename__ = "recall_product"

    recall_number: str = Field(primary_key=True)
    event_id: str = Field(foreign_key="recall_event.event_id")
    product_description: str
    product_quantity: str
    reason_for_recall: str
    distribution_pattern: str


class RecallAnnouncement(SQLModel, table=True):
    __tablename__ = "recall_announcement"

    announcement_id: str = Field(primary_key=True)
    announce_date: date
    event_id: str | None = Field(
        default=None, foreign_key="recall_event.event_id"
    )
    brand: str
    product: str
    category: str
    reason: str
    company: str
    detail_url: str
    in_openfda: bool
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IllnessMonthly(SQLModel, table=True):
    __tablename__ = "illness_monthly"

    state_code: str = Field(
        primary_key=True, max_length=2, foreign_key="state.state_code"
    )
    year_month: str = Field(primary_key=True, max_length=7)
    pathogen: str = Field(primary_key=True)
    source_type: PathogenSource = Field(primary_key=True)
    isolate_count: int
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FDAFunding(SQLModel, table=True):
    __tablename__ = "fda_funding"

    fiscal_year: int = Field(
        primary_key=True, foreign_key="fiscal_year.fiscal_year"
    )
    collected_at: date = Field(primary_key=True)
    total_obligations: Decimal
    transaction_count: int
    new_award_count: int


class MonthlyPanel(SQLModel, table=True):
    __tablename__ = "monthly_panel"

    state_code: str = Field(
        primary_key=True, max_length=2, foreign_key="state.state_code"
    )
    year_month: str = Field(primary_key=True, max_length=7)
    fiscal_year: int = Field(foreign_key="fiscal_year.fiscal_year")
    recall_events: int
    class_i_events: int
    class_i_share: Decimal
    median_classification_lag: Decimal
    isolates_human: int
    isolates_food_reference: int
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
