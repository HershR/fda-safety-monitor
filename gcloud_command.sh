#!/usr/bin/env bash

set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [ -f deploy.local.sh ]; then
  source deploy.local.sh
fi

PROJECT_ID="${GCP_PROJECT_ID:-your-gcp-project-id}"
REGION="${GCP_REGION:-}"

API_SERVICE="${GCP_API_SERVICE:-}"
API_DIR="./backend"
API_PORT=8080

WEB_SERVICE="${GCP_WEB_SERVICE:-fda-monitor-web}"
WEB_DIR="./frontend"
WEB_PORT=8501
WEB_ACCOUNT="fda-monitor-frontend@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_ACCOUNT="fda-monitor-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_TZ="Etc/UTC"
MESSAGE_BODY='{}'

SERVICE_ACCOUNT="${GCP_BACKEND_SERVICE_ACCOUNT:-}"
SQL_INSTANCE="${GCP_SQL_INSTANCE:-}"
BUCKET="${GCP_BUCKET_NAME:-}"
DATABASE="${GCP_DB_NAME:-}"
DB_USER="${GCP_DB_USER:-postgres}"
PASSWORD_SECRET="${GCP_DB_PASSWORD_SECRET:-}"
SECRET_VERSION="${GCP_DB_SECRET_VERSION:-}"

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

deploy_api() {
  log "Deploying ${API_SERVICE} from ${API_DIR} (Cloud Build builds the image)"
  gcloud run deploy "$API_SERVICE" \
    --source "$API_DIR" \
    --project="$PROJECT_ID" \
    --region "$REGION" \
    --port="$API_PORT" \
    --no-allow-unauthenticated \
    --timeout=1500 \
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

deploy_web() {
  if [[ ! -s "$WEB_DIR/app.py" || ! -s "$WEB_DIR/requirements.txt" ]]; then
    echo "ERROR: merge feature/dashboard before deploying the frontend." >&2
    return 1
  fi
  local url; url="$(api_url)"
  local access_flag=--no-allow-unauthenticated
  case "${GCP_WEB_PUBLIC:-false}" in
    true) access_flag=--allow-unauthenticated ;;
    false) ;;
    *) echo "ERROR: GCP_WEB_PUBLIC must be true or false." >&2; return 1 ;;
  esac

  if ! gcloud iam service-accounts describe "$WEB_ACCOUNT" \
      --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud iam service-accounts create fda-monitor-frontend --project="$PROJECT_ID"
  fi
  gcloud run services add-iam-policy-binding "$API_SERVICE" \
    --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:$WEB_ACCOUNT" --role=roles/run.invoker

  log "Deploying ${WEB_SERVICE} from ${WEB_DIR}, pointing at ${url}"
  gcloud run deploy "$WEB_SERVICE" \
    --source "$WEB_DIR" \
    --project="$PROJECT_ID" \
    --region "$REGION" \
    --port="$WEB_PORT" \
    "$access_flag" \
    --max-instances=1 \
    --service-account="$WEB_ACCOUNT" \
    --set-env-vars="API_BASE_URL=$url"
}

schedule_job() {
  local job="$1" schedule="$2" path="$3" url="$4"
  local action=create
  if gcloud scheduler jobs describe "$job" \
      --project="$PROJECT_ID" --location="$REGION" >/dev/null 2>&1; then
    action=update
  fi

  log "Running '${action}' on scheduler job '${job}' (${schedule} ${SCHEDULER_TZ})"
  gcloud scheduler jobs "$action" http "$job" \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --schedule="$schedule" \
    --time-zone="$SCHEDULER_TZ" \
    --uri="${url}${path}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body="$MESSAGE_BODY" \
    --oidc-service-account-email="$SCHEDULER_ACCOUNT" \
    --oidc-token-audience="$url" \
    --attempt-deadline=1800s \
    --max-retry-attempts=0
}

deploy_scheduler() {
  local url; url="$(api_url)"
  gcloud services enable cloudscheduler.googleapis.com --project="$PROJECT_ID"
  if ! gcloud iam service-accounts describe "$SCHEDULER_ACCOUNT" \
      --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud iam service-accounts create fda-monitor-scheduler --project="$PROJECT_ID"
  fi
  gcloud run services add-iam-policy-binding "$API_SERVICE" \
    --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:$SCHEDULER_ACCOUNT" --role=roles/run.invoker
  gcloud run services update "$API_SERVICE" \
    --project="$PROJECT_ID" --region="$REGION" --timeout=1500

  schedule_job fda-collect-recalls "0 10 * * *" /fda-recalls/scrape/ "$url"
  schedule_job fda-collect-funding "0 12 * * *" /usaspending/scrape/ "$url"
  schedule_job fda-collect-cdc "0 14 1 * *" /cdc/scrape/ "$url"
}

show_urls() {
  local url; url="$(api_url)"
  echo "API     : $url"
}

case "${1:-all}" in
  all)       bootstrap; deploy_api; show_urls ;;
  bootstrap) bootstrap ;;
  api|deploy) deploy_api ;;
  web) deploy_web ;;
  scheduler) deploy_scheduler ;;
  urls)      show_urls ;;
  *) echo "usage: $0 {all|bootstrap|api|deploy|scheduler|web|urls}" >&2; exit 1 ;;
esac

log "Done."
