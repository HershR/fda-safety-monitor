from collections import defaultdict
from datetime import date, datetime, timezone

import stealth_requests as requests
from bs4 import BeautifulSoup
from curl_cffi.requests.exceptions import RequestException
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from src.config import GCP_SERVICE_ACCOUNT_KEY
from src.database import SessionDep
from src.db_utils import save_rows
from src.models import RecallAnnouncement, RecallEvent, RecallProduct, State
from src.storage import get_bucket, get_credientials, save_raw
from src.transform import match_announcements
from uuid6 import uuid7

router = APIRouter()

FDA = "https://www.fda.gov"
PAGE = "/safety/recalls-market-withdrawals-safety-alerts"
OPENFDA = "https://api.fda.gov/food/enforcement.json"
OPENFDA_SOURCE = "openfda"
ANNOUNCEMENT_SOURCE = "fda_announcements"
OPENFDA_FIRST_YEAR = 2012
OPENFDA_PAGE_SIZE = 1000  # openFDA max rows per request
OPENFDA_MAX_SKIP = 25000  # openFDA won't page past this
ANNOUNCEMENT_PAGE_SIZE = 5000


def text(cell) -> str:
    return BeautifulSoup(str(cell or ""), "html.parser").get_text(
        " ", strip=True
    )


def scrape_announcements(bucket, run_id) -> list[RecallAnnouncement]:
    params = {
        "view_name": "recall_solr_index",
        "view_display_id": "recall_datatable_block_1",
        "view_path": PAGE,
        "start": 0,
        "length": ANNOUNCEMENT_PAGE_SIZE,
    }
    resp = requests.get(
        f"{FDA}/datatables/views/ajax",
        params=params,
        timeout=60,
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    if not resp.ok:
        print(
            f"FDA announcements {resp.status_code}: "
            f"server={resp.headers.get('Server')} body={resp.text[:300]}"
        )
    resp.raise_for_status()
    payload = resp.json()
    save_raw(bucket, run_id, ANNOUNCEMENT_SOURCE, resp.url, 1, payload)
    if len(payload["data"]) >= ANNOUNCEMENT_PAGE_SIZE:
        raise RuntimeError("FDA announcement list may be truncated")

    announcements = []
    for row in payload["data"]:
        date_cell, brand, product, category, reason, company = row[:6]
        if "Food & Beverages" not in text(category):
            continue
        link = BeautifulSoup(str(brand), "html.parser").find("a")
        if not link:
            continue  # announcement_id comes from the link
        resource_link = link.get("href")
        if not resource_link:
            print(
                f"Recalled Announcment Parsing Error: Missing resource link for item: [{date_cell}|{brand}|{product}|{company}]"
            )
            continue
        url = f"{FDA}{resource_link}"
        announcements.append(
            RecallAnnouncement(
                announcement_id=url.rstrip("/").rsplit("/", 1)[-1],
                announce_date=datetime.strptime(
                    text(date_cell), "%m/%d/%Y"
                ).date(),
                brand=text(brand),
                product=text(product),
                category=text(category),
                reason=text(reason),
                company=text(company),
                detail_url=url,
                in_openfda=False,
            )
        )
    return announcements


def fetch_openfda_records(bucket, run_id) -> list[dict]:
    records = []
    for year in range(OPENFDA_FIRST_YEAR, datetime.now(timezone.utc).year + 1):
        skip = 0
        page = 1
        while skip <= OPENFDA_MAX_SKIP:
            resp = requests.get(
                OPENFDA,
                timeout=60,
                params={
                    "search": f"report_date:[{year}0101 TO {year}1231]",
                    "limit": OPENFDA_PAGE_SIZE,
                    "skip": skip,
                },
            )
            if resp.status_code == 404:
                break  # openFDA returns 404 when nothing matches
            resp.raise_for_status()
            payload = resp.json()
            save_raw(
                bucket,
                run_id,
                OPENFDA_SOURCE,
                resp.url,
                f"{year}_{page}",
                payload,
            )

            results = payload.get("results", [])
            records.extend(results)
            if len(results) < OPENFDA_PAGE_SIZE:
                break
            skip = skip + OPENFDA_PAGE_SIZE
            page = page + 1
    return records


def build_events_and_products(
    records, valid_state_codes
) -> tuple[list[RecallEvent], list[RecallProduct]]:

    def date_from_string(s: str) -> date | None:
        return datetime.strptime(s, "%Y%m%d").date() if s else None

    by_event = defaultdict(list)
    for r in records:
        by_event[r["event_id"]].append(r)

    events: list[RecallEvent] = []
    products: list[RecallProduct] = []
    for event_id, recs in by_event.items():
        r = recs[0]
        if not r.get("recall_initiation_date") or not r.get("report_date"):
            continue  # these are required
        initiated = date_from_string(r.get("recall_initiation_date"))
        classified = date_from_string(r.get("center_classification_date"))
        report_date = date_from_string(r.get("report_date"))
        state = r.get("state", "")
        if initiated is None or classified is None or report_date is None:
            print(
                f"Recall Event Parsing Error: Missing or malformed dates for {event_id}"
            )
            continue
        classification_lag = (classified - initiated).days

        events.append(
            RecallEvent(
                event_id=event_id,
                state_code=state if state in valid_state_codes else None,
                classification=r["classification"],
                recall_initiation_date=initiated,
                center_classification_date=classified,
                report_date=report_date,
                status=r["status"],
                voluntary_mandated=r["voluntary_mandated"],
                recalling_firm=r["recalling_firm"],
                classification_lag_days=classification_lag
                if classified
                else None,
                product_count=len(recs),
            )
        )
        products += [
            RecallProduct(
                recall_number=p["recall_number"],
                event_id=event_id,
                product_description=p["product_description"],
                product_quantity=p["product_quantity"],
                reason_for_recall=p["reason_for_recall"],
                distribution_pattern=p["distribution_pattern"],
            )
            for p in recs
        ]
    return events, products


@router.post("/scrape/")
def scrape(session: SessionDep):
    """Scrape FDA food recalls from openFDA and FDA announcements page.

    Returns:
        dict: ``run_id`` for this run, the number of rows saved to
        ``recall_event``, ``recall_product``, and ``recall_announcement``,
        and how many announcements were matched to a recall event.
    Raises:
        HTTPError: If fda.gov returns an error

    """
    run_id = str(uuid7())
    bucket = get_bucket(
        get_credientials() if GCP_SERVICE_ACCOUNT_KEY else None
    )
    valid_state_codes = set(session.exec(select(State.state_code)).all())

    # openFDA
    records = fetch_openfda_records(bucket, run_id)
    events, products = build_events_and_products(records, valid_state_codes)
    saved = {
        "recall_event": save_rows(session, events),  # type: ignore
        "recall_product": save_rows(session, products),  # type: ignore
    }
    session.commit()  # kept even if announcements fail below

    # FDA announcements
    try:
        announcements = scrape_announcements(bucket, run_id)
        saved["recall_announcement"] = save_rows(session, announcements)  # type: ignore
        session.commit()
    except (RequestException, RuntimeError) as e:
        raise HTTPException(
            status_code=502,
            detail=f"openFDA saved {saved}; FDA announcements failed: {e}",
        )

    # Link announcements to openFDA events. Saving announcements above
    # resets their event_id, so this runs on every scrape
    saved["announcements_matched"] = match_announcements(session)
    session.commit()

    return {"run_id": run_id, **saved}


@router.get("/", response_model=list[RecallEvent])
def get_recall_events(session: SessionDep):
    statement = select(RecallEvent).order_by(RecallEvent.report_date.desc())
    return session.exec(statement).all()
