#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$ROOT_DIR/deploy.local.sh" ]]; then
  source "$ROOT_DIR/deploy.local.sh"
fi

PROJECT_ID="${GCP_PROJECT_ID:-YOUR_PROJECT_ID}"
REGION="${GCP_REGION:-YOUR_REGION}"
API_SERVICE="${GCP_API_SERVICE:-YOUR_API_SERVICE}"
REPOSITORY="${GCP_REPOSITORY:-YOUR_REPOSITORY}"
SERVICE_ACCOUNT="${GCP_BACKEND_SERVICE_ACCOUNT:-YOUR_SERVICE_ACCOUNT_EMAIL}"
SQL_INSTANCE="${GCP_SQL_INSTANCE:-YOUR_PROJECT:YOUR_SQL_REGION:YOUR_INSTANCE}"
BUCKET="${GCP_BUCKET_NAME:-YOUR_BUCKET}"
DATABASE="${GCP_DB_NAME:-YOUR_DATABASE}"
DB_USER="${GCP_DB_USER:-postgres}"
PASSWORD_SECRET="${GCP_DB_PASSWORD_SECRET:-YOUR_PASSWORD_SECRET}"
SECRET_VERSION="${GCP_DB_SECRET_VERSION:-YOUR_SECRET_VERSION}"
IMAGE_REPOSITORY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/backend"

usage() {
  cat <<'HELP'
Usage: bash gcloud_command.sh COMMAND [ARGUMENT]
  deploy          Build in Google Cloud and update the existing private backend.
  build TAG       Build the backend image locally.
  push TAG        Upload the image to Artifact Registry.
  api IMAGE       Deploy a full image reference to the private API service.
  urls            Print the API URL.
  revisions       List API revisions.
  rollback NAME   Route traffic to a previously tested ready revision.
  help            Show this help.

Set the GCP variables listed in documents/gcp-deployment.md before use.
The script reuses existing resources. Web and Scheduler are not included yet.
HELP
}

require_config() {
  for value in "$@"; do
    if [[ -z "$value" || "$value" == YOUR_* ]]; then
      echo "Set the required GCP variables before running this command." >&2
      exit 1
    fi
  done
}

deploy_api() {
  require_config "$PROJECT_ID" "$REGION" "$API_SERVICE" "$SERVICE_ACCOUNT" \
    "$SQL_INSTANCE" "$BUCKET" "$DATABASE" "$DB_USER" "$PASSWORD_SECRET" "$SECRET_VERSION"
  gcloud run deploy "$API_SERVICE" \
    --project="$PROJECT_ID" --region="$REGION" --platform=managed \
    --image="$1" --service-account="$SERVICE_ACCOUNT" \
    --execution-environment=gen2 --set-cloudsql-instances="$SQL_INSTANCE" \
    --set-env-vars="DB_HOST=/cloudsql/${SQL_INSTANCE},DB_PORT=5432,DB_USER=${DB_USER},DB_NAME=${DATABASE},GCP_PROJECT_ID=${PROJECT_ID},GCP_BUCKET_NAME=${BUCKET}" \
    --set-secrets="DB_PASSWORD=${PASSWORD_SECRET}:${SECRET_VERSION}" \
    --port=8080 --cpu=1 --memory=512Mi \
    --min-instances=0 --max-instances=1 --concurrency=8 --timeout=300 \
    --no-allow-unauthenticated
}

case "${1:-deploy}" in
  deploy)
    require_config "$PROJECT_ID" "$REGION" "$API_SERVICE"
    gcloud run services describe "$API_SERVICE" \
      --project="$PROJECT_ID" --region="$REGION" --format='value(metadata.name)' >/dev/null
    gcloud run deploy "$API_SERVICE" \
      --project="$PROJECT_ID" --region="$REGION" \
      --source="$ROOT_DIR/backend" --no-allow-unauthenticated
    ;;
  build)
    require_config "$PROJECT_ID" "$REGION" "$REPOSITORY"
    tag="${2:?Provide a new image tag}"
    docker build --platform linux/amd64 \
      -t "${IMAGE_REPOSITORY}:${tag}" "$ROOT_DIR/backend"
    ;;
  push)
    require_config "$PROJECT_ID" "$REGION" "$REPOSITORY"
    tag="${2:?Provide the image tag to upload}"
    docker push "${IMAGE_REPOSITORY}:${tag}"
    ;;
  api)
    deploy_api "${2:?Provide the full image reference to deploy}"
    ;;
  urls)
    require_config "$PROJECT_ID" "$REGION" "$API_SERVICE"
    gcloud run services describe "$API_SERVICE" \
      --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)'
    ;;
  revisions)
    require_config "$PROJECT_ID" "$REGION" "$API_SERVICE"
    gcloud run revisions list --service="$API_SERVICE" \
      --project="$PROJECT_ID" --region="$REGION"
    ;;
  rollback)
    require_config "$PROJECT_ID" "$REGION" "$API_SERVICE"
    revision="${2:?Provide a previously tested ready revision}"
    gcloud run services update-traffic "$API_SERVICE" \
      --project="$PROJECT_ID" --region="$REGION" --to-revisions="${revision}=100"
    ;;
  help|--help|-h) usage ;;
  *) usage >&2; exit 1 ;;
esac
