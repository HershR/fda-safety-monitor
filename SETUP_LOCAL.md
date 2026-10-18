# Setup Local Development
This document contains how to run the dashboard locally using docker.

### Prerequisites

- Python 3.13+, Docker Desktop
- A GCP Project with a bucket
- A GCP service account key with read/write permission on your bucket

### 1. Clone the repository
```bash
git clone https://github.com/HershR/fda-safety-monitor.git
cd fda-safety-monitor
```

### 2. Install dependencies
```bash
# install deps for both backend and frontend
# for local development
python -m venv .venv
source .venv/bin/activate # activate your venv
pip install -r requirements.txt 
```

### 3. Configure environment variables
```bash
cp .env.template .env
```
And set the following env variables
| Variable | Description | Example |
| --- | --- | --- |
| `DB_NAME` | Database name | `fda_data` |
| `DB_HOST` | Database host (set to `db` inside Docker) | `localhost` |
| `DB_PORT` | Database port | `5432` |
| `DB_USER` | Database user | `postgres` |
| `DB_PASSWORD` | Database password | `your-db-password` |
| `GCP_PROJECT_ID` | GCP project ID | `your-project-name` |
| `GCP_BUCKET_NAME` | Bucket the scraper writes to | `fda-monitor-raw` |
| `GCP_SERVICE_ACCOUNT_KEY` | Path to the key inside the container | `/tmp/gcp-key.json` |
| `LOCAL_GCP_SERVICE_ACCOUNT_KEY` | Path to the key on your machine | `/Users/you/keys/gcp-key.json` |

Docker mounts `LOCAL_GCP_SERVICE_ACCOUNT_KEY` into the container at `GCP_SERVICE_ACCOUNT_KEY`, so the local path must be set before starting the containers.

### 4. Start the application
```bash
docker compose up -d
```

The Webapp runs at http://localhost:8501 (clear cache to see new data)
The API runs at http://localhost:8080 (docs at `/docs`)
Postgres runs at http://localhost:5439.
On startup the API server fills the `state` and `fiscal_year` tables with data in `backend/data/`. Both webapp and API server reloads on code changes. If it doesn't, or you changed `requirements.txt`, rebuild:
```bash
docker compose up --build -d
```
### 5. Call the API
Each scraper pulls data from one source and saves it as JSON in the bucket:
```python
import requests

requests.post("http://localhost:8080/fda-recalls/scrape/").json()  # openFDA recalls + FDA announcements
requests.post("http://localhost:8080/cdc/scrape/").json()  # CDC BEAM illness counts
requests.post("http://localhost:8080/usaspending/scrape/").json()  # FDA spending
requests.post("http://localhost:8080/state-monthly-summary/rebuild/").json()  # Build monthly summaries for each state based on the data, call after all the other 3
```
### 6. Tear down 
```bash
docker compose down
docker compose down -v #remove database volume
```

### 7. Mock GCS Storage
If you do now want the local development server to add files to your GCS bucket, then mock the GCS connection with this image: https://github.com/fsouza/fake-gcs-server
and add it your docker compose file.