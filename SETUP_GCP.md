# Setup Deploy to GCP
This document contains how to deploy the API and dashboard to Cloud Run using `gcloud_command.sh`.

### Prerequisites

- A GCP project with billing enabled
- A Cloud Storage bucket
- A service account for the API
- A Cloud SQL PostgreSQL instance with a database and user
- A Secret Manager secret holding the database password
- GCP CLI installed, logged in and project set
- Appropriate account permissions to enable APIs, grant roles, and deploy to Cloud Run.

### 1. Configure the deployment
Create `deploy.local.sh` in the repository root. Do NOT commit this file.
```bash
export GCP_PROJECT_ID="YOUR_PROJECT_ID"
export GCP_REGION="YOUR_REGION"
export GCP_API_SERVICE="YOUR_API_SERVICE_NAME" # eg fda-api
export GCP_BACKEND_SERVICE_ACCOUNT="YOUR_SERVICE_ACCOUNT_EMAIL"
export GCP_SQL_INSTANCE="YOUR_PROJECT:YOUR_SQL_REGION:YOUR_INSTANCE"
export GCP_BUCKET_NAME="YOUR_BUCKET_NAME" # eg: fda-bucket
export GCP_DB_NAME="YOUR_DATABASE_NAME" # eg: fda-database
export GCP_DB_USER="YOUR_DATABASE_USER"  # eg: postgres
export GCP_DB_PASSWORD_SECRET="YOUR_PASSWORD_SECRET" # name in secret manager
export GCP_DB_SECRET_VERSION="YOUR_SECRET_VERSION" # version in secret manager
export GCP_WEB_PUBLIC=true # false to keep webapp private
```
Cloud Run uses the service account directly, so no JSON key is needed.

### 2. Deploy
```bash
./gcloud_command.sh all
```

Or one piece at a time while iterating:

```bash
./gcloud_command.sh bootstrap   # enable APIs, create Artifact Registry repo
./gcloud_command.sh api         # rebuild + redeploy the API
./gcloud_command.sh web         # rebuild + redeploy the web app
./gcloud_command.sh scheduler   # (re)create the Cloud Scheduler job
./gcloud_command.sh urls        # print both service URLs
```



### 3. Schedule data collection
This creates the Cloud Scheduler jobs (times in UTC):
| Job | Schedule | Endpoint |
| --- | --- | --- |
| FDA recalls and announcements | Daily 10:00 | `/fda-recalls/scrape/` |
| FDA funding | Daily 12:00 | `/usaspending/scrape/` |
| CDC illness | 1st of each month 14:00 | `/cdc/scrape/` |

Note monthly state summaries are not scheduled, as they are optional.

### 4. Check the deployment
Print the API URL:
```bash
bash gcloud_command.sh urls
```
The API server is private by default, so requests need an idenitiy token:
```bash
API_URL="https://YOUR_SERVICE_URL"
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" "$API_URL/"
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" "$API_URL/states"
```
A request without the token should get a 403.

**You can trigger a scraper or a monthly rebuild manually using curl as well**

To open the API docs, start a local proxy and go to http://localhost:8080/docs:
```bash
source deploy.local.sh
gcloud run services proxy "$GCP_API_SERVICE" --project="$GCP_PROJECT_ID" --region="$GCP_REGION" --port=8080
```