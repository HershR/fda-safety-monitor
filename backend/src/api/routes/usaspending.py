from datetime import date
from decimal import Decimal

import requests
from fastapi import APIRouter
from uuid6 import uuid7
from src.database import SessionDep
from src.gcp_service import get_bucket, get_credientials
from src.models import FDAFunding
from src.utils.bucket_utils import save_raw
from src.utils.db_utils import save_rows

router = APIRouter()

SOURCE = "usaspending"
USASPENDING_URL = "https://api.usaspending.gov/api/v2/agency/075/sub_agency/"
FIRST_FISCAL_YEAR = 2017


def fetch_fda_record(fiscal_year: int, bucket, run_id: str) -> dict | None:
    page = 1
    while True:
        resp = requests.get(
            USASPENDING_URL,
            params={"fiscal_year": fiscal_year, "page": page, "limit": 10},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        save_raw(bucket, run_id, SOURCE, resp.url, page, payload)

        for record in payload["results"]:
            if record["abbreviation"] == "FDA":
                return record

        if not payload["page_metadata"]["hasNext"]:
            return None
        page += 1


def scrape_funding(bucket, run_id: str) -> list[FDAFunding]:
    today = date.today()
    rows = []
    for fiscal_year in range(FIRST_FISCAL_YEAR, today.year + 1):
        record = fetch_fda_record(fiscal_year, bucket, run_id)
        if record is None:
            continue  # no FDA data for this year yet
        rows.append(
            FDAFunding(
                fiscal_year=fiscal_year,
                collected_at=today,
                total_obligations=Decimal(str(record["total_obligations"])),
                transaction_count=record["transaction_count"],
                new_award_count=record["new_award_count"],
            )
        )
    return rows


@router.post("/scrape/")
def scrape(session: SessionDep):
    bucket = get_bucket(get_credientials())
    run_id = str(uuid7())
    rows = scrape_funding(bucket, run_id)
    saved = save_rows(session, rows)
    session.commit()
    return {"fda_funding": saved}