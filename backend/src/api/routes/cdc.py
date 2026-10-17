import requests
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from uuid6 import uuid7
from src.database import SessionDep
from src.enums import PathogenSource
from src.gcp_service import get_bucket, get_credientials
from src.models import IllnessMonthly, State
from src.utils.pipeline.bucket_utils import save_raw
from src.utils.pipeline.db_utils import save_rows

router = APIRouter()

SOURCE = "cdc"
CDC_URL = "https://data.cdc.gov/resource/jbhn-e8xn.json"
PAGE_SIZE = 5000


def fetch_isolates(bucket, run_id, valid_state_codes):
    """
    Checks the CDC BEAM Socrata API pages and fetches the
    isolate counts by state, year, month, pathogen, source_type
 
    Saves the raw data into the GCS bucket via save_raw().
    Skip the row if its state code is not included in valid_state_codes.

    Converts the cleaned data into an IllnessMonthly object format
    and returns a list of objects.
    """
    rows = []
    offset = 0
    page = 1

    while True:
        request_params = {
            "$select": (
                "state, year, month, pathogen, source_type, "
                "sum(number_of_isolates) as isolate_count"
            ),
            "$group": "state, year, month, pathogen, source_type",
            "$limit": PAGE_SIZE,
            "$offset": offset,
        }

        resp = requests.get(CDC_URL, params=request_params, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        save_raw(bucket, run_id, SOURCE, resp.url, page, payload)

        if not payload:
            break

        for r in payload:
            state_code = r["state"]
            if state_code not in valid_state_codes:
                continue  # skip non-US codes (e.g. "AB" = Alberta, Canada)

            row = IllnessMonthly(
                state_code=state_code,
                year_month=f"{int(r['year']):04d}-{int(r['month']):02d}",
                pathogen=r["pathogen"],
                source_type=PathogenSource(r["source_type"].lower()),
                isolate_count=int(r["isolate_count"]),
            )
            rows.append(row)

        if len(payload) < PAGE_SIZE:
            break

        offset = offset + PAGE_SIZE
        page = page + 1

    return rows


@router.post("/scrape/")
def scrape(session: SessionDep):
    """
    Collects monthly isolate cases by pathogen from CDC BEAM API.
 
    Fetches valid_state_codes by checking the state table
    and filters out non-valid state codes from CDC records.
    Saves the raw data into the GCS bucket and
    the cleaned data into the illness_monthly table
 
    Returns the number of saved rows in a 
    dictionary format - {"illness_monthly": saved}
    """
    states = session.exec(select(State)).all()
    valid_state_codes = set()
    for s in states:
        valid_state_codes.add(s.state_code)

    bucket = get_bucket(get_credientials())
    run_id = str(uuid7())
    rows = fetch_isolates(bucket, run_id, valid_state_codes)
    saved = save_rows(session, rows)
    session.commit()
    return {"illness_monthly": saved}


@router.get("/{state_code}", response_model=list[IllnessMonthly])
def get_illness_monthly_by_state(session: SessionDep, state_code: str):
    """
    Returns all monthly CDC records for the given state code.
 
    Returns 404 error if no record is found for that state.
    """
    statement = select(IllnessMonthly).where(IllnessMonthly.state_code == state_code)
    results = session.exec(statement).all()

    if len(results) == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No illness data found for state {state_code}",
        )

    return results
