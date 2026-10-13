# Backend deployment

The backend runs on Cloud Run and connects to Cloud SQL and Cloud Storage.
The SQL password comes from Secret Manager. The API requires authentication.
Local development still uses Docker Compose with `fastapi dev`.

## Before deploying

Use the existing project, database, bucket, and Docker repository. Ask the team
for their values; the examples here are placeholders. The backend service account
needs Cloud SQL Client, access to write to the bucket, and Secret Accessor on the
database password secret. Cloud Run uses this account instead of a JSON key file.

Set the variables below in your terminal using `export NAME=value`. Do not save
real values in this guide or the script. The script does not read `backend/.env`.

| Variable | What to set |
| --- | --- |
| `GCP_PROJECT_ID` | Project ID |
| `GCP_REGION` | Region for Cloud Run and Artifact Registry |
| `GCP_API_SERVICE` | Backend service name |
| `GCP_REPOSITORY` | Docker repository name |
| `GCP_BACKEND_SERVICE_ACCOUNT` | Service account email |
| `GCP_SQL_INSTANCE` | Connection name, in the form `PROJECT:REGION:INSTANCE` |
| `GCP_BUCKET_NAME` | Bucket name |
| `GCP_DB_NAME` | Database name |
| `GCP_DB_USER` | Database user; defaults to `postgres` |
| `GCP_DB_PASSWORD_SECRET` | Name of the password secret, not the password |
| `GCP_DB_SECRET_VERSION` | Secret version number |

Cloud Run, Cloud SQL Admin, Artifact Registry, and Secret Manager APIs must be
enabled. Your account also needs permission to upload images, deploy the service,
and use its service account. This setup uses the Cloud SQL integration with a
socket under `/cloudsql/`; private-IP-only instances need extra network setup.

## Deploying a change

From the repository root, run these one at a time. Use a new tag for each version:

```bash
gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev"
bash gcloud_command.sh build backend-v1
bash gcloud_command.sh push backend-v1
```

The push prints a digest that identifies the uploaded image. Replace
`IMAGE_REFERENCE` below with the full image address:
`REGION-docker.pkg.dev/PROJECT/REPOSITORY/backend@sha256:DIGEST`.

```bash
bash gcloud_command.sh api IMAGE_REFERENCE
```

This updates Cloud Run. It uses port 8080, 1 CPU, 512 MiB, 0–1 revision instances,
up to 8 simultaneous requests per instance, and a 5-minute request timeout.
It connects to Cloud SQL without needing the proxy on your laptop.

To check the URL and deployed revisions:

```bash
bash gcloud_command.sh urls
bash gcloud_command.sh revisions
```

## What was tested

The earlier deployment returned 403 without authentication and 200 with
authentication on `/states/`. USAspending collection saved 10 files in the bucket
and 10 SQL records for 2017–2026. Local Compose also started and returned states.
These results are from the earlier image; the revised script has not deployed yet.

The four pytest checks cover database connection settings and credentials with
and without a JSON file. They do not connect to Google Cloud:

```bash
python -m pip install -r backend/tests/requirements.txt
PYTHONPATH=backend python -m pytest backend/tests/test_deployment_config.py -v
```

After a new deployment, repeat the authentication checks, call
`POST /usaspending/scrape/`, and check the bucket and database. That POST writes
data. Its response counts processed records, not necessarily new rows.

## If a deployment fails

Check the logs and list the revisions. To send traffic back to a previously
working revision, replace `REVISION_NAME` and run:

```bash
bash gcloud_command.sh rollback REVISION_NAME
```

This does not undo database changes or bucket writes. Keep the old image and
secret version available. We have not tested rollback yet.

## Still to do

- Test CDC and recalls on Cloud Run.
- Test the revised script's build, push, deploy, and rollback actions.
- Deploy the frontend and add authenticated Scheduler jobs.
- Confirm what the rubric means by "two Cloud Scheduler jobs (per data source)".

The current code keeps `echo=True` for SQL logs; the earlier deployed image did
not. That change needs a new image to reach Cloud Run. Automatic reload after a
local edit has not been separately tested. Keep service URLs, revision names,
and other project-specific details in the team's private notes.
