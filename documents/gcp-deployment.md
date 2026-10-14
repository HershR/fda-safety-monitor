# Backend deployment on GCP

Deploy the backend to Cloud Run using [gcloud_command.sh](../gcloud_command.sh).
The service connects to Cloud SQL and Cloud Storage, reads the database password
from Secret Manager, and requires authenticated requests.

The script uses existing GCP resources. Resource creation, frontend deployment,
and Cloud Scheduler configuration are outside its scope. For local development,
see the [backend README](../backend/README.md).

## Update the backend

Create `deploy.local.sh` in the project root:

```bash
export GCP_PROJECT_ID="YOUR_PROJECT_ID"
export GCP_REGION="YOUR_REGION"
export GCP_API_SERVICE="YOUR_API_SERVICE"
```

Use the values from the team. This file is ignored by Git.

Run:

```bash
bash gcloud_command.sh
```

Google Cloud builds the image and updates the existing backend. The database
settings and secrets stay the same. You need permission to deploy and use Cloud
Build. This command has not been tested end to end yet.

The backend is private. Each team member needs Cloud Run Invoker access.
To test it:

```bash
gcloud auth login
API_URL=$(bash gcloud_command.sh urls)
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" "$API_URL/states/"
```

Opening the URL directly in a browser can return Forbidden because the browser
does not send the token. Frontend and Scheduler access still need to be set up.

The steps below are for deploying an image manually.

## Prerequisites

- Docker and the Google Cloud CLI, authenticated with an account that can upload
  images, deploy Cloud Run services, and use the backend service account.
- An existing Cloud SQL database, Cloud Storage bucket, Artifact Registry Docker
  repository, and database password secret.
- Cloud Run, Cloud SQL Admin, Artifact Registry, and Secret Manager APIs enabled.
- A backend service account with Cloud SQL Client, bucket write access, and
  Secret Accessor on the database password secret. Cloud Run uses this account
  without a JSON key file.

The script connects to Cloud SQL through a `/cloudsql/` socket. Instances with
only a private IP require additional network configuration.

## Configuration

Export these variables in your terminal with `export NAME=value`. Get the
resource values from the team; do not commit passwords or service account keys.
The script does not load `backend/.env`.

| Variable | Value |
| --- | --- |
| `GCP_PROJECT_ID` | Project ID |
| `GCP_REGION` | Region for Cloud Run and Artifact Registry |
| `GCP_API_SERVICE` | Backend service name |
| `GCP_REPOSITORY` | Artifact Registry Docker repository name |
| `GCP_BACKEND_SERVICE_ACCOUNT` | Backend service account email |
| `GCP_SQL_INSTANCE` | Connection name: `PROJECT:REGION:INSTANCE` |
| `GCP_BUCKET_NAME` | Cloud Storage bucket name |
| `GCP_DB_NAME` | Database name |
| `GCP_DB_USER` | Database user; defaults to `postgres` |
| `GCP_DB_PASSWORD_SECRET` | Password secret name, not the password |
| `GCP_DB_SECRET_VERSION` | Secret version number |

## Deploy

Run from the repository root. Use a new image tag for each release:

```bash
gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev"
bash gcloud_command.sh build backend-v1
bash gcloud_command.sh push backend-v1
```

Use the digest printed by the push to deploy the uploaded image. Replace
`IMAGE_REFERENCE` with its full address:
`REGION-docker.pkg.dev/PROJECT/REPOSITORY/backend@sha256:DIGEST`.

```bash
bash gcloud_command.sh api IMAGE_REFERENCE
```

Cloud Run settings, including resource limits and timeout, are defined in
`gcloud_command.sh`.

## Verify

Get the service URL and deployed revisions:

```bash
bash gcloud_command.sh urls
bash gcloud_command.sh revisions
```

- Confirm that unauthenticated requests are rejected and authenticated requests
  to `/docs` and `GET /states/` return HTTP 200.
- To verify data collection, call `POST /usaspending/scrape/` with authentication
  and check the resulting Cloud Storage files and database records. This call
  writes data; its response counts processed records, not necessarily new rows.

The local configuration tests check database connection settings and credential
selection. They do not connect to GCP or validate a deployment:

```bash
python -m pip install -r backend/tests/requirements.txt
PYTHONPATH=backend python -m pytest backend/tests/test_deployment_config.py -v
```

## Rollback

Inspect Cloud Run logs and revisions if a deployment fails. To restore traffic
to a previously working revision, replace `REVISION_NAME` and run:

```bash
bash gcloud_command.sh rollback REVISION_NAME
```

Rollback changes traffic routing only; it does not undo database changes or
bucket writes. Keep the previous image and secret version available.

## Validation status

The current script's build, push, deploy, and rollback workflow still requires
end-to-end validation. CDC and recall collection also require validation on
Cloud Run.
