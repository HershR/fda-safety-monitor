#!/usr/bin/env bash
#
# gcloud_command.sh — deploy this project on GCP (backend only for now).
#
#   ./gcloud_command.sh all        # everything, in order (first-time setup)
#   ./gcloud_command.sh bootstrap  # enable APIs and grant backend permissions
#   ./gcloud_command.sh api        # redeploy the API only
#   ./gcloud_command.sh urls       # print the deployed URLs
#
# This deploys straight from source with `gcloud run deploy --source`, the
# same way HW3 did.
#
# TODO(team): change every value in the CONFIG block, then delete this line.
# Also, make any necessary updates. - Your data should be regularly collected by the scheduler.

set -euo pipefail

# Resolve paths from this script and optionally load the team's local settings.
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [ -f deploy.local.sh ]; then
  source deploy.local.sh
fi

# ─── CONFIG : UPDATE THIS : ADD COMMENTS TO FILL IN. ──────────────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-your-gcp-project-id}"
REGION="${GCP_REGION:-}"         # keep the same region everywhere

API_SERVICE="${GCP_API_SERVICE:-}" # Cloud Run service name for the API
API_DIR="./backend"                     # folder holding the API Dockerfile
API_PORT=8080                           # must match EXPOSE/CMD in backend/Dockerfile

# Our backend uses Cloud SQL and a runtime service account instead of a JSON key.
# Create the account, SQL instance/database/user, bucket, and password secret first.
# A Cloud SQL instance with only a private IP also needs network configuration.
SERVICE_ACCOUNT="${GCP_BACKEND_SERVICE_ACCOUNT:-}"
SQL_INSTANCE="${GCP_SQL_INSTANCE:-}"      # PROJECT:REGION:INSTANCE
BUCKET="${GCP_BUCKET_NAME:-}"
DATABASE="${GCP_DB_NAME:-}"
DB_USER="${GCP_DB_USER:-postgres}"
PASSWORD_SECRET="${GCP_DB_PASSWORD_SECRET:-}" # Secret Manager name, not the password
SECRET_VERSION="${GCP_DB_SECRET_VERSION:-}"  # Version containing that user's password
# ─────────────────────────────────────────────────────────────────────────────

# ─── validation ──────────────────────────────────────────────────────────────
for _var in PROJECT_ID REGION API_SERVICE API_DIR API_PORT \
            SERVICE_ACCOUNT SQL_INSTANCE BUCKET DATABASE DB_USER \
            PASSWORD_SECRET SECRET_VERSION; do
  if [[ -z "${!_var}" || "${!_var}" == YOUR_* ]]; then
    echo "ERROR: $_var is empty or still a placeholder -- fill in the CONFIG block at the top of" \
         "this script before running it." >&2
    exit 1
  fi
done
unset _var

if [ "$PROJECT_ID" = "your-gcp-project-id" ]; then
  echo "ERROR: PROJECT_ID is still the placeholder. Edit the CONFIG block." >&2
  exit 1
fi
for _dir in "$API_DIR"; do
  if [ ! -f "$_dir/Dockerfile" ]; then
    echo "ERROR: no Dockerfile in '$_dir'." >&2
    exit 1
  fi
done
unset _dir

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }

# ─── one-time project setup ──────────────────────────────────────────────────
bootstrap() {
  gcloud services enable --project="$PROJECT_ID" \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    storage.googleapis.com

  log "Letting the Cloud Run runtime service account access Cloud SQL and Storage"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role=roles/cloudsql.client --condition=None
  gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
    --project="$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role=roles/storage.objectUser

  log "Letting the Cloud Run runtime service account read the database password"
  gcloud secrets add-iam-policy-binding "$PASSWORD_SECRET" \
    --project="$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role=roles/secretmanager.secretAccessor
}

# ─── API service ─────────────────────────────────────────────────────────────
deploy_api() {
  log "Deploying ${API_SERVICE} from ${API_DIR} (Cloud Build builds the image)"
  gcloud run deploy "$API_SERVICE" \
    --source "$API_DIR" \
    --project="$PROJECT_ID" \
    --region "$REGION" \
    --port="$API_PORT" \
    --no-allow-unauthenticated \
    --timeout=300 \
    --max-instances=1 \
    --service-account="$SERVICE_ACCOUNT" \
    --execution-environment=gen2 \
    --set-cloudsql-instances="$SQL_INSTANCE" \
    --set-env-vars="DB_HOST=/cloudsql/${SQL_INSTANCE},DB_PORT=5432,DB_USER=${DB_USER},DB_NAME=${DATABASE},GCP_PROJECT_ID=${PROJECT_ID},GCP_BUCKET_NAME=${BUCKET}" \
    --set-secrets="DB_PASSWORD=${PASSWORD_SECRET}:${SECRET_VERSION}" \
    --cpu=1 --memory=512Mi --min-instances=0 --concurrency=8
}

api_url() {
  local url
  url=$(gcloud run services describe "$API_SERVICE" \
    --project="$PROJECT_ID" --region "$REGION" --format="value(urls[0])")
  if [ -z "$url" ]; then
    url=$(gcloud run services describe "$API_SERVICE" \
      --project="$PROJECT_ID" --region "$REGION" --format="value(status.url)")
  fi
  if [ -z "$url" ]; then
    echo "ERROR: could not resolve the URL for Cloud Run service" \
         "'$API_SERVICE' in $REGION. Deploy it first." >&2
    exit 1
  fi
  echo "$url"
}

# ─── Web app ─────────────────────────────────────────────────────────────────
# TODO(team): add deploy_web when the frontend is ready.

# ─── Cloud Scheduler ─────────────────────────────────────────────────────────
# TODO(team): add authenticated collection jobs in the next update.

show_urls() {
  local url; url="$(api_url)"
  echo "API     : $url"
}

# ─── entry point ─────────────────────────────────────────────────────────────
case "${1:-all}" in
  all)       bootstrap; deploy_api; show_urls ;;
  bootstrap) bootstrap ;;
  api|deploy) deploy_api ;;
  urls)      show_urls ;;
  *) echo "usage: $0 {all|bootstrap|api|deploy|urls}" >&2; exit 1 ;;
esac

log "Done."
