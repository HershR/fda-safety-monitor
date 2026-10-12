#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="fda-safety-monitor"
REGION="us-east1"
API_SERVICE="fda-monitor-api"
SERVICE_ACCOUNT="fda-monitor-backend-service-ac@${PROJECT_ID}.iam.gserviceaccount.com"
SQL_INSTANCE="${PROJECT_ID}:us-east1:fda-monitor-db"
BUCKET="fda-safety-monitor-data-2026"
PASSWORD_SECRET="fda-monitor-db-password"
SECRET_VERSION="1"
IMAGE_REPOSITORY="${REGION}-docker.pkg.dev/${PROJECT_ID}/fda-monitor/backend"
VERIFIED_IMAGE="${IMAGE_REPOSITORY}@sha256:c8180b8f08a044e4473264c5ea002a2d1a99deb4e5ce8a16ea5c21ea39f735d3"
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'HELP'
Usage: bash gcloud_command.sh COMMAND [ARGUMENT]
  build TAG       Build a linux/amd64 backend image with a new tag.
  push TAG        Upload that image; record the digest printed by Docker.
  api [IMAGE]     Deploy the verified image, or a full repository@sha256:digest.
  urls            Print the API URL.
  revisions       List revisions before choosing a recovery target.
  rollback NAME   Route all traffic to an existing, verified ready revision.
  help            Show this help without contacting GCP.

Prerequisites: existing SQL instance, bucket, registry, runtime identity and
secret version with the documented IAM roles. Build/push also require Docker
and: gcloud auth configure-docker us-east1-docker.pkg.dev
HELP
}

deploy_api() {
  local image="${1:-$VERIFIED_IMAGE}"
  if [[ "$image" != "${IMAGE_REPOSITORY}@sha256:"* ]] ||
     [[ ! "${image##*@sha256:}" =~ ^[a-f0-9]{64}$ ]]; then
    echo "Use a full image reference with a SHA-256 digest from this repository." >&2
    exit 1
  fi
  gcloud run deploy "$API_SERVICE" \
    --project="$PROJECT_ID" --region="$REGION" --platform=managed \
    --image="$image" --service-account="$SERVICE_ACCOUNT" \
    --execution-environment=gen2 --set-cloudsql-instances="$SQL_INSTANCE" \
    --set-env-vars="DB_HOST=/cloudsql/${SQL_INSTANCE},DB_PORT=5432,DB_USER=postgres,DB_NAME=fda_data,GCP_PROJECT_ID=${PROJECT_ID},GCP_BUCKET_NAME=${BUCKET}" \
    --set-secrets="DB_PASSWORD=${PASSWORD_SECRET}:${SECRET_VERSION}" \
    --port=8080 --cpu=1 --memory=512Mi \
    --min-instances=0 --max-instances=1 --concurrency=8 --timeout=300 \
    --no-allow-unauthenticated
}

case "${1:-help}" in
  build)
    tag="${2:?Provide a new image tag, such as cloudrun-v2}"
    docker build --platform linux/amd64 \
      -t "${IMAGE_REPOSITORY}:${tag}" "$ROOT_DIR/backend"
    ;;
  push)
    tag="${2:?Provide the tag built by the build command}"
    docker push "${IMAGE_REPOSITORY}:${tag}"
    ;;
  api)
    deploy_api "${2:-$VERIFIED_IMAGE}"
    ;;
  urls)
    gcloud run services describe "$API_SERVICE" \
      --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)'
    ;;
  revisions)
    gcloud run revisions list --service="$API_SERVICE" \
      --project="$PROJECT_ID" --region="$REGION"
    ;;
  rollback)
    revision="${2:?Provide a verified ready revision from the revisions command}"
    gcloud run services update-traffic "$API_SERVICE" \
      --project="$PROJECT_ID" --region="$REGION" \
      --to-revisions="${revision}=100"
    ;;
  help|--help|-h) usage ;;
  *) usage >&2; exit 1 ;;
esac
