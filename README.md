# FDA Safety Monitor
A dashboard that tracks US food recalls and foodborne illness alongside FDA spending.

## Team Members

| Name | GitHubID | Role / Focus |
| --- | --- | --- |
| Chris | tophercruzio | Data Engineer. Data cleaning and api endpoints |
| Hersh | HershR | Backend/Database engineer |
| Paul | pryu11 | Data Engineer. Data cleaning and api endpoints |
| Carlos | ccamposlozano | GCP Deployment Engineer |
| Dylan | DylanSidhu03 | Frontend engineer and Dashboard visualizations |

---

## Problem Statement
We want to track food recall activity and foodborne illness in the USA, both current and historical, and compare it against FDA funding. We think budget cuts lead to fewer or slower recalls, which then leads to more people getting sick. The dashboard is meant for food safety journalists, public health researchers, and members of Congress working on budgets.

---

## Data Sources
All four sources are free, public, and need no API key. Last checked 2026-09-30.

| # | Source & Link | Method | What it contains | Update frequency | Access requirements |
| --- | --- | --- | --- | --- | --- |
| 1 | [openFDA Food Enforcement](https://api.fda.gov/food/enforcement.json) | API | Official FDA food recalls from 2012 on. Includes recall class, company state, and initiation, classification, and report dates | Weekly | None |
| 2 | [FDA Recall Announcements](https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts) | Scraped | Recall announcements as companies post them: date, brand, product, category, reason, company. No state field | Daily | 30s delay between requests |
| 3 | [CDC BEAM Dashboard](https://data.cdc.gov/Foodborne-Waterborne-and-Related-Diseases/BEAM-Dashboard-Report-Data/jbhn-e8xn/about_data) | API | Lab confirmed Salmonella, STEC, Campylobacter, Shigella, and Vibrio samples by state, month, and source type | Monthly | None |
| 4 | [USASpending](https://api.usaspending.gov/api/v2/agency/075/sub_agency/?fiscal_year=2025) | API | FDA spending by fiscal year, listed under HHS (agency 075) | Daily | None |

---

## Integration Goal
USASpending gives us FDA spending per fiscal year. openFDA tells us when recalls happen, how serious they are, and how long FDA took to classify them. The scraped announcements show recalls before they reach openFDA. CDC BEAM shows how many people actually got sick.

We join on state and year-month, and map each month to a fiscal year to match it with spending. Announcements don't share an ID with openFDA, so we match them on company, product, and a two-week date window.

We use the CDC human sample counts to check the recall data. Fewer inspections could mean fewer recalls even if food isn't any safer, but illness counts come from hospitals and labs and don't depend on FDA's budget.

---

## Setup Instructions (Locally)

### Prerequisites
- Python 3.13
- Docker Desktop
- A GCP service account JSON key with write access to the project's Cloud Storage bucket

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
source .venv/bin/activate
pip install -r requirements.txt 
pre-commit install
```

### 3. Configure environment variables
```bash
cd backend
cp .env.template .env
```

Fill in `DB_PASSWORD` and the GCP values in `.env`.

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

### 4. Start the backend
From `backend/`:
```bash
docker compose up -d
```

The API runs at http://localhost:8080 (docs at `/docs`) and Postgres at `localhost:5439`. On startup the server fills the `state` and `fiscal_year` tables from `backend/data/`. The server reloads on code changes. If it doesn't, or you changed `requirements.txt`, rebuild:
```bash
docker compose up --build -d
```

Stop the containers:
```bash
docker compose down
```

Stop the containers and delete the database:
```bash
docker compose down -v
```

### 5. Call the API
Each scraper pulls data from one source and saves it as JSON in the bucket:
```python
import requests

requests.post(
    "http://localhost:8080/fda-recalls/scrape/"
).json()  # openFDA recalls + FDA announcements
requests.post(
    "http://localhost:8080/cdc/scrape/"
).json()  # CDC BEAM illness counts
requests.post(
    "http://localhost:8080/usaspending/scrape/"
).json()  # FDA spending
```

Each response has the number of rows written for each table. See [backend/README.md](backend/README.md) for the full list of routes.

---

## Repository Structure
```
.
├── backend/
│   ├── data/
│   │   ├── fiscal_years.json
│   │   └── state_codes.json
│   ├── src/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── cdc.py
│   │   │   │   ├── fiscal_years.py
│   │   │   │   ├── recall_scraper.py
│   │   │   │   ├── states.py
│   │   │   │   └── usaspending.py
│   │   │   └── router.py
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── database.py
│   │   ├── seed_db.py
│   │   ├── gcp_service.py
│   │   ├── config.py
│   │   └── enums.py
│   ├── Dockerfile
│   ├── docker-compose.yaml
│   ├── requirements.txt
│   ├── .dockerignore
│   ├── .env.template
│   └── README.md
├── frontend/
│   ├── app.py
│   └── .env.template
├── documents/
│   └── postgres-erd.md
├── requirements.txt
├── .gitattributes
├── .pre-commit-config.yaml
├── .python-version
└── README.md
```
