from datetime import date
from decimal import Decimal

import requests
from fastapi import APIRouter
from uuid6 import uuid7
from src.database import SessionDep
from src.gcp_service import get_bucket, get_credientials
from src.models import FDAFunding
from src.utils.pipeline.bucket_utils import save_raw
from src.utils.pipeline.db_utils import save_rows

router = APIRouter()

SOURCE = "usaspending"
TOPTIER_CODE = "075"
USASPENDING_URL = "https://api.usaspending.gov/api/v2/agency/" + TOPTIER_CODE + "/sub_agency/"
FIRST_FISCAL_YEAR = 2017


def fetch_fda_record(fiscal_year, bucket, run_id):
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
                save_raw(bucket, run_id, SOURCE, resp.url, page, fda_data)
                return record

        if not payload["page_metadata"]["hasNext"]:
            return None

        page = page + 1


def scrape_funding(bucket, run_id):
    today = date.today()
    rows = []

    for fiscal_year in range(FIRST_FISCAL_YEAR, today.year + 1):
        record = fetch_fda_record(fiscal_year, bucket, run_id)
        if record is None:
            continue  # no FDA data for this year yet

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
    bucket = get_bucket(get_credientials())
    run_id = str(uuid7())
    rows = scrape_funding(bucket, run_id)
    saved = save_rows(session, rows)
    session.commit()
    return {"fda_funding": saved}
