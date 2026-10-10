import requests
from fastapi import APIRouter
from uuid6 import uuid7
from src.database import SessionDep
from src.enums import PathogenSource
from src.gcp_service import get_bucket, get_credientials
from src.models import IllnessMonthly
from src.utils.bucket_utils import save_raw
from src.utils.db_utils import save_rows

router = APIRouter()

SOURCE = "cdc_beam"
CDC_URL = "https://data.cdc.gov/resource/jbhn-e8xn.json"
PAGE_SIZE = 5000


def fetch_isolates(bucket, run_id: str) -> list[IllnessMonthly]:
    params = {
        "$select": (
            "state, year, month, pathogen, source_type, "
            "sum(number_of_isolates) as isolate_count"
        ),
        "$group": "state, year, month, pathogen, source_type",
        "$limit": PAGE_SIZE,
    }

    rows = []
    offset = 0
    page = 1
    while True:
        resp = requests.get(
            CDC_URL, params={**params, "$offset": offset}, timeout=60
        )
        resp.raise_for_status()
        payload = resp.json()
        save_raw(bucket, run_id, SOURCE, resp.url, page, payload)
        if not payload:
            break

        for r in payload:
            state_code = r["state"]
            if len(state_code) != 2 or not state_code.isalpha():
                continue  # skip placeholder codes like "??"
            rows.append(
                IllnessMonthly(
                    state_code=state_code,
                    year_month=f"{int(r['year']):04d}-{int(r['month']):02d}",
                    pathogen=r["pathogen"],
                    source_type=PathogenSource(r["source_type"].lower()),
                    isolate_count=int(r["isolate_count"]),
                )
            )

        if len(payload) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        page += 1

    return rows


@router.post("/scrape/")
def scrape(session: SessionDep):
    bucket = get_bucket(get_credientials())
    run_id = str(uuid7())
    rows = fetch_isolates(bucket, run_id)
    saved = save_rows(session, rows)
    session.commit()
    return {"illness_monthly": saved}