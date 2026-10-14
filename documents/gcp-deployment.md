# Backend deployment on GCP

[gcloud_command.sh](../gcloud_command.sh) builds the backend from
`backend/Dockerfile` and deploys it to Cloud Run. Google Cloud builds and stores
the image, so Docker Desktop does not need to be running.

The backend is private and uses Cloud SQL, Cloud Storage, and a database password
stored in Secret Manager. Frontend deployment and Scheduler jobs are still pending.

## Configuration

These steps are for the person deploying the backend. Team members who only call
the deployed API need an authorized Google account, not a local deployment file.

Install the Google Cloud CLI and sign in:

```bash
gcloud auth login
```

Before deploying, prepare a GCP project with billing enabled, a backend service
account, a Cloud SQL PostgreSQL instance with a database and user, a Storage bucket,
and a Secret Manager secret containing that user's database password. The script
does not create these resources. A Cloud SQL instance with only a private IP needs
additional network configuration.

Create `deploy.local.sh` in the repository root and fill in the values for your
project. This file is ignored by Git. The script does not load `backend/.env`.

```bash
export GCP_PROJECT_ID="YOUR_PROJECT_ID"
export GCP_REGION="YOUR_REGION"
export GCP_API_SERVICE="YOUR_API_SERVICE"
export GCP_BACKEND_SERVICE_ACCOUNT="YOUR_SERVICE_ACCOUNT_EMAIL"
export GCP_SQL_INSTANCE="YOUR_PROJECT:YOUR_SQL_REGION:YOUR_INSTANCE"
export GCP_BUCKET_NAME="YOUR_BUCKET"
export GCP_DB_NAME="YOUR_DATABASE"
export GCP_DB_USER="postgres"
export GCP_DB_PASSWORD_SECRET="YOUR_PASSWORD_SECRET"
export GCP_DB_SECRET_VERSION="YOUR_SECRET_VERSION"
```

Use the secret's name and version, not the password itself. Cloud Run uses the
backend service account without a downloaded JSON key.

## Deploy

Run commands from the repository root. For initial setup, after preparing the
resources above:

```bash
bash gcloud_command.sh all
```

This enables the required Google APIs, grants the backend account access to Cloud
SQL, bucket objects, and the password secret, then deploys and prints the API URL.
Your account needs permission to enable APIs, assign those permissions, build and
deploy the service, and use the backend service account.

For later code updates:

```bash
bash gcloud_command.sh api
```

This builds a new image and creates or updates the private Cloud Run service using
the configuration in `deploy.local.sh`. No manual image build or push is needed.
`deploy` is an alias for `api`. Running the script without an argument runs `all`,
including the permission setup.

## Verify

Show the service URL:

```bash
bash gcloud_command.sh urls
```

Copy only the HTTPS address into `API_URL` below. Use a Google account with
Cloud Run Invoker access on the service:

```bash
API_URL="https://YOUR_SERVICE_URL"
curl --fail-with-body -H "Authorization: Bearer $(gcloud auth print-identity-token)" "$API_URL/"
curl --fail-with-body -H "Authorization: Bearer $(gcloud auth print-identity-token)" "$API_URL/states/"
```

The first request checks the API response; the second reads states from the
database. Requests without authentication should be rejected.

For FastAPI's interactive documentation, run the local authenticated proxy and
open `http://localhost:8080/docs` in your browser:

```bash
source deploy.local.sh
gcloud run services proxy "$GCP_API_SERVICE" --project="$GCP_PROJECT_ID" --region="$GCP_REGION" --port=8080
```

On October 13, 2026, deployment with `api` succeeded. Authenticated requests to `/`
and `/states/` returned HTTP 200 with 59 states, and an unauthenticated request to
`/` returned HTTP 403. Initial setup with `all`/`bootstrap`, collection and bucket
writes, and the documentation proxy still need end-to-end verification.
