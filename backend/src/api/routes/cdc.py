import json
from datetime import date

import requests
from fastapi import APIRouter
from src.enums import PathogenSource
from src.gcp_service import get_bucket, get_credientials
from src.models import IllnessMonthly

router = APIRouter()

CDC_BASE_URL = "https://data.cdc.gov/resource/jbhn-e8xn.json"
PAGE_SIZE = 5000


def fetch_illness_monthly() -> list[IllnessMonthly]:
    """
    Pull the CDC BEAM Dashboard isolate counts, aggregated server-side
    (via Socrata's SoQL $select/$group) down to one row per
    (state, year, month, pathogen, source_type) — the dataset itself has
    one row per serotype/species, which is finer-grained than
    IllnessMonthly's primary key, so we ask the API to sum
    number_of_isolates within each group instead of summing it ourselves
    after downloading everything.

    Pages through results with $limit/$offset since the raw dataset has
    ~260k rows (grouped, far fewer, but still enough to paginate safely).
    """
    params_base = {
        "$select": (
            "state, year, month, pathogen, source_type, "
            "sum(number_of_isolates) as isolate_count"
        ),
        "$group": "state, year, month, pathogen, source_type",
        "$limit": PAGE_SIZE,
    }

    rows = []
    offset = 0
    while True:
        resp = requests.get(
            CDC_BASE_URL,
            params={**params_base, "$offset": offset},
            timeout=60,
        )
        resp.raise_for_status()
        page = resp.json()
        if not page:
            break

        for r in page:
            state_code = r["state"]
            if len(state_code) != 2 or not state_code.isalpha():
                # A few rows carry placeholder/unknown codes (e.g. "??")
                # instead of a real 2-letter state. Skip them here; revisit
                # if we need those isolates counted somewhere during cleaning.
                continue
            rows.append(
                IllnessMonthly(
                    state_code=state_code,
                    year_month=f"{int(r['year']):04d}-{int(r['month']):02d}",
                    pathogen=r["pathogen"],
                    source_type=PathogenSource(r["source_type"].lower()),
                    isolate_count=int(r["isolate_count"]),
                )
            )

        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    return rows


@router.post("/scrape/")
def scrape():
    rows = fetch_illness_monthly()

    credentials = get_credientials()
    bucket = get_bucket(credentials)
    today = date.today().isoformat()
    bucket.blob(
        f"illness_monthly/{today}_illness_monthly.json"
    ).upload_from_string(
        json.dumps([r.model_dump(mode="json") for r in rows]),
        content_type="application/json",
    )
    return {"illness_monthly": len(rows)}
