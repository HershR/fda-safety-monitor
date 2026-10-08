import json
import uuid
from datetime import UTC, datetime

from google.cloud.storage.bucket import Bucket


def save_raw(
    bucket: Bucket,
    run_id: str,
    source: str,
    url: str,
    page: int | None = 1,
    payload: str | None = "",
):
    """Saves a JSON string to a bucket instance with meta data"""
    now = datetime.now(UTC)
    path = f"raw/{source}/{now.strftime('%Y-%m-%d')}/{source}_{run_id}_{page}.json"
    body = {
        "_meta": {
            "source": source,
            "url": url,
            "fetched_at": now.isoformat(),
        },
        "payload": payload,
    }
    bucket.blob(path).upload_from_string(
        json.dumps(body), content_type="application/json"
    )
    return path


def read_raw(bucket: Bucket, source: str, day: str, run_id: str | None = None):
    """Fetch a saved file from a bucket"""
    for blob in bucket.list_blobs(prefix=f"raw/{source}/{day}/"):
        if run_id is None or f"_{run_id}_" in blob.name:
            yield json.loads(blob.download_as_text())
