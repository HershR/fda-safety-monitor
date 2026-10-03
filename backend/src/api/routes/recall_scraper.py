import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup
from fastapi import APIRouter
from google.cloud import storage
from google.oauth2 import service_account
from src.config import GCP_BUCKET, GCP_PROJECT_ID, GCP_SERVICE_ACCOUNT_KEY
from src.models import RecallAnnouncement, RecallEvent, RecallProduct

router = APIRouter()

FDA = "https://www.fda.gov"
PAGE = "/safety/recalls-market-withdrawals-safety-alerts"
OPENFDA = "https://api.fda.gov/food/enforcement.json"


def text(cell) -> str:
    return BeautifulSoup(str(cell or ""), "html.parser").get_text(
        " ", strip=True
    )


def scrape_announcements() -> list[RecallAnnouncement]:
    # json endpoint
    params = {
        "view_name": "recall_solr_index",
        "view_display_id": "recall_datatable_block_1",
        "view_path": PAGE,
        "start": 0,
        "length": 5000,
    }
    resp = requests.get(
        f"{FDA}/datatables/views/ajax",
        params=params,
        timeout=60,
        headers={
            "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    resp.raise_for_status()

    announcements = []
    for row in resp.json()["data"]:
        date_cell, brand, product, category, reason, company = row[:6]
        if "Food & Beverages" not in text(category):
            continue
        link = BeautifulSoup(str(brand), "html.parser").find("a")
        url = FDA + link["href"] if link else ""
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


def fetch_events_and_products() -> tuple[
    list[RecallEvent], list[RecallProduct]
]:
    since = date.today() - timedelta(days=365)
    resp = requests.get(
        OPENFDA,
        timeout=60,
        params={
            "search": f"report_date:[{since:%Y%m%d} TO {date.today():%Y%m%d}]",
            "limit": 1000,
        },
    )
    resp.raise_for_status()

    def d(s: str) -> date:
        return datetime.strptime(s, "%Y%m%d").date() if s else None

    by_event = defaultdict(list)
    for r in resp.json()["results"]:
        by_event[r["event_id"]].append(r)

    events, products = [], []
    for event_id, recs in by_event.items():
        r = recs[0]
        if not r.get("recall_initiation_date") or not r.get("report_date"):
            continue  # these two are still required
        initiated = d(r["recall_initiation_date"])
        classified = d(r.get("center_classification_date"))
        state = r.get("state", "")
        events.append(
            RecallEvent(
                event_id=event_id,
                state_code=state if len(state) == 2 else None,
                classification=r["classification"],
                recall_initiation_date=initiated,
                center_classification_date=classified,
                report_date=d(r["report_date"]),
                status=r["status"],
                voluntary_mandated=r["voluntary_mandated"],
                recalling_firm=r["recalling_firm"],
                classification_lag_days=(classified - initiated).days
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
def scrape():
    events, products = fetch_events_and_products()
    tables = {
        "recall_announcement": scrape_announcements(),
        "recall_event": events,
        "recall_product": products,
    }
    service_account_key = GCP_SERVICE_ACCOUNT_KEY
    project_id = GCP_PROJECT_ID
    credentials = service_account.Credentials.from_service_account_file(
        service_account_key
    )
    bucket = storage.Client(
        project=project_id, credentials=credentials
    ).bucket(GCP_BUCKET)
    for name, rows in tables.items():
        bucket.blob(f"fda_recalls/{name}.json").upload_from_string(
            json.dumps([r.model_dump(mode="json") for r in rows]),
            content_type="application/json",
        )
    return {name: len(rows) for name, rows in tables.items()}
