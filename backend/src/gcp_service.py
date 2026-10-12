from google.cloud import storage
from google.oauth2 import service_account

from src.config import GCP_BUCKET, GCP_PROJECT_ID, GCP_SERVICE_ACCOUNT_KEY


def get_credientials():
    return service_account.Credentials.from_service_account_file(
        GCP_SERVICE_ACCOUNT_KEY
    )


def get_bucket(credentials=None):
    if credentials:
        client = storage.Client(
            project=GCP_PROJECT_ID, credentials=credentials
        )
    else:
        client = storage.Client(project=GCP_PROJECT_ID)
    return client.bucket(GCP_BUCKET)
