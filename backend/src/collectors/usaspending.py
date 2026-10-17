from datetime import datetime, timezone
from decimal import Decimal

import requests
from fastapi import APIRouter, HTTPException
from sqlmodel import col, select
from src.database import SessionDep
from src.db_utils import save_rows
from src.models import FDAFunding
from src.storage import get_bucket, get_credientials, save_raw
from uuid6 import uuid7

router = APIRouter()

SOURCE = "usaspending"
TOPTIER_CODE = "075"  # code for HHS; FDA is a sub-agency under HHS
USASPENDING_URL = (
    "https://api.usaspending.gov/api/v2/agency/"
    + TOPTIER_CODE
    + "/sub_agency/"
)
FIRST_FISCAL_YEAR = 2017


def fetch_fda_record(fiscal_year, bucket, run_id):
    """
    Checks the USASpending API pages and fetches the FDA record
    for the given fiscal year.

    Once it locates the record, saves it to the GCS bucket
    along with its metadata (fiscal_year, toptier_code).

    Returns None if FDA record is not found until the last page.
    """
    page = 1

    while True:
        request_params = {
            "fiscal_year": fiscal_year,
            "page": page,
            "limit": 10,
        }
        resp = requests.get(USASPENDING_URL, params=request_params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        for record in payload["results"]:
            if record["abbreviation"] == "FDA":
                fda_data = {
                    "fiscal_year": fiscal_year,
                    "toptier_code": TOPTIER_CODE,
                    "record": record,
                }
                save_raw(
                    bucket,
                    run_id,
                    SOURCE,
                    resp.url,
                    f"{fiscal_year}_{page}",
                    fda_data,
                )
                return record

        if not payload["page_metadata"]["hasNext"]:
            return None

        page = page + 1


def scrape_funding(bucket, run_id):
    """
    Calls fetch_fda_record() between
    the FIRST_FISCAL_YEAR(2017) and the current year.

    Converts each year's record into a FDAFunding object format and
    returns a list of objects.

    Skips if record is not found in that year.
    """
    today = datetime.now(timezone.utc).date()
    rows = []

    for fiscal_year in range(FIRST_FISCAL_YEAR, today.year + 1):
        record = fetch_fda_record(fiscal_year, bucket, run_id)
        if record is None:
            continue

        row = FDAFunding(
            fiscal_year=fiscal_year,
            collected_at=today,
            total_obligations=Decimal(str(record["total_obligations"])),
            transaction_count=record["transaction_count"],
            new_award_count=record["new_award_count"],
        )
        rows.append(row)

    return rows


@router.post("/scrape/")
def scrape(session: SessionDep):
    """
    Collects FDA funding data (2017 ~ current) from USASpending API.

    Saves the raw data into the GCS bucket and
    the cleaned data into the fda_funding table

    Returns the number of saved rows in a
    dictionary format - {"fda_funding": saved}
    """
    bucket = get_bucket(get_credientials())
    run_id = str(uuid7())
    rows = scrape_funding(bucket, run_id)
    saved = save_rows(session, rows)
    session.commit()
    return {"fda_funding": saved}


@router.get("/", response_model=list[FDAFunding])
def get_fda_funding(session: SessionDep):
    """
    Returns all records saved in the fda_funding table.

    If the same year's records were recorded over multiple days,
    each record is saved on seperate rows.
    """
    return session.exec(select(FDAFunding)).all()


@router.get("/{fiscal_year}", response_model=FDAFunding)
def get_fda_funding_by_year(session: SessionDep, fiscal_year: int):
    """
    Returns the most recently collected FDA funding record
    for the given fiscal year.

    Returns 404 error if no record is found in that year.
    """
    statement = (
        select(FDAFunding)
        .where(FDAFunding.fiscal_year == fiscal_year)
        .order_by(col(FDAFunding.collected_at).desc())
    )

    result = session.exec(statement).first()

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No FDA funding data found for fiscal year {fiscal_year}",
        )

    return result
