import json
from datetime import date
from decimal import Decimal

import requests
from fastapi import APIRouter
from src.gcp_service import get_bucket, get_credientials
from src.models import FDAFunding

router = APIRouter()

USASPENDING_BASE_URL = "https://api.usaspending.gov/api/v2/agency"
HHS_TOPTIER_CODE = "075"  # FDA is a sub-agency under HHS
FDA_ABBREVIATION = "FDA"
FIRST_FISCAL_YEAR = 2017  # matches the FDA recall data's earliest year


def fetch_fda_subagency_record(fiscal_year: int) -> dict | None:
    """
    Query USASpending's agency/sub_agency endpoint for HHS (toptier 075)
    for the given fiscal year, paging through results, and return the
    sub-agency record whose abbreviation is "FDA".

    Returns None instead of raising when the FDA simply has no record for
    that fiscal year yet (some early years have no data).
    """
    url = f"{USASPENDING_BASE_URL}/{HHS_TOPTIER_CODE}/sub_agency/"
    page = 1
    while True:
        resp = requests.get(
            url,
            params={"fiscal_year": fiscal_year, "page": page, "limit": 10},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()

        for record in payload.get("results", []):
            if record.get("abbreviation") == FDA_ABBREVIATION:
                return record

        if not payload.get("page_metadata", {}).get("hasNext"):
            return None
        page += 1


def scrape_fda_funding() -> list[FDAFunding]:
    """
    Fetch the FDA's USASpending record for every fiscal year from
    FIRST_FISCAL_YEAR through the current year, skipping any year with
    no data, and return one FDAFunding row per year collected today.
    """
    today = date.today()
    rows = []
    for fiscal_year in range(FIRST_FISCAL_YEAR, today.year + 1):
        record = fetch_fda_subagency_record(fiscal_year)
        if record is None:
            continue
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
def scrape():
    rows = scrape_fda_funding()

    credentials = get_credientials()
    bucket = get_bucket(credentials)
    today = date.today().isoformat()
    bucket.blob(f"fda_funding/{today}_fda_funding.json").upload_from_string(
        json.dumps([r.model_dump(mode="json") for r in rows]),
        content_type="application/json",
    )
    return {"fda_funding": len(rows)}
