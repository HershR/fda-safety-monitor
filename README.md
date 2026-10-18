# FDA Safety Monitor

A dashboard that tracks US food recalls and foodborne illness alongside FDA spending.
This project aim to figure out if reduction in FDA budget leads to a delay in recall announcements and increase in human/food related illnesses across the USA. We hope this dashboard proves usefull to members of congress when working on future budgets.

**Live web app:** `https://fda-monitor-web-180707148327.us-east1.run.app`
**API (private):** In submission doc

---

## Team Members

| Name | GitHubID | Role / Focus |
| --- | --- | --- |
| Chris | tophercruzio | Data Engineer. Data cleaning and api endpoints FDA |
| Hersh | HershR | Backend/Database engineer |
| Paul | pryu11 | Data Engineer. Data cleaning and api endpoints Funding and CDC |
| Carlos | ccamposlozano | GCP Deployment Engineer |
| Dylan | DylanSidhu03 | Frontend engineer and Dashboard visualizations |

---

## Problem Statement

We want to track food recall activity and foodborne illness in the USA, both current and historical, and compare it against FDA funding. We think budget cuts lead to fewer or slower recalls, which then leads to more people getting sick. The dashboard is meant for food safety journalists, public health researchers, and members of Congress working on budgets.

## Data Sources and Integration Goal

### Data Sources
All four sources are free, public, and need no API key. Last checked 2026-09-30.

| # | Source & Link | Method | What it contains | Update frequency | Access requirements |
| --- | --- | --- | --- | --- | --- |
| 1 | [openFDA Food Enforcement](https://api.fda.gov/food/enforcement.json) | API | Official FDA food recalls from 2012 on. Includes recall class, company state, and initiation, classification, and report dates | Weekly | None |
| 2 | [FDA Recall Announcements](https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts) | Scraped | Recall announcements as companies post them: date, brand, product, category, reason, company. No state field | Daily | 30s delay between requests |
| 3 | [CDC BEAM Dashboard](https://data.cdc.gov/Foodborne-Waterborne-and-Related-Diseases/BEAM-Dashboard-Report-Data/jbhn-e8xn/about_data) | API | Lab confirmed Salmonella, STEC, Campylobacter, Shigella, and Vibrio samples by state, month, and source type | Monthly | None |
| 4 | [USASpending](https://api.usaspending.gov/api/v2/agency/075/sub_agency/?fiscal_year=2025) | API | FDA spending by fiscal year, listed under HHS (agency 075) | Daily | None |

---

### Integration Goal
USASpending gives us FDA spending per fiscal year. openFDA tells us when recalls happen, how serious they are, and how long FDA took to classify them. The scraped announcements show recalls before they reach openFDA. CDC BEAM shows how many people actually got sick.

We join on state and year-month, and map each month to a fiscal year to match it with spending. Announcements don't share an ID with openFDA, so we match them on company, product, and a two-week date window.

We use the CDC human sample counts to check the recall data. Fewer inspections could mean fewer recalls even if food isn't any safer, but illness counts come from hospitals and labs and don't depend on FDA's budget.

---

## Repository Structure

### Where to find things
| File | Description |
| --- | --- |
| `backend/`| FastAPI server |
| `backend/src/main.py`| app instance |
| `backend/src/router.py` | routes |
| `backend/src/collectors/`, data collector endpoints, each collector stores raw data in a gcp bucket and cleaned data in database |
| `backend/src/transform.py`| used for creating monthly state summaries |
| `backend/src/storage.py` | gcp bucket helpers |
| `frontend/` | Streamlit dashboard |
| `gcloud_command.sh` | GCP setup file |
| `.env.template` | local development env template |

```
.
├── backend/
│   ├── src/
│   │   ├── main.py
│   │   ├── router.py
│   │   ├── collectors/          # fda_recalls.py, cdc.py, usaspending.py
│   │   ├── routes/              # states.py, fiscal_years.py, state_monthly_summary.py
│   │   ├── transform.py
│   │   ├── storage.py
│   │   ├── db_utils.py
│   │   ├── models.py
│   │   ├── database.py
│   │   ├── seed_db.py
│   │   ├── config.py
│   │   └── enums.py
│   ├── data/                    # fiscal_years.json, state_codes.json
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
├── documents/
│   ├── gcp-deployment.md
│   └── postgres-erd.md
├── .env.template
├── docker-compose.yaml
├── docker-compose.gcs-mock.yaml
├── gcloud_command.sh
├── requirements.txt
├── SETUP_LOCAL.md
├── SETUP_GCP.md
└── README.md
```
---

## API Endpoints

FastAPI docs are at http://localhost:8080/docs when running locally. The deployed API is private, so use `gcloud run services proxy <API_SERVICE> --region <REGION> --port 8080` and open the same URL.

**Collectors** (called by Cloud Scheduler)

| Method | Path | Purpose | Returns |
| --- | --- | --- | --- |
| `POST` | `/fda-recalls/scrape/` | pull openFDA recalls + FDA announcements | Run id + number of rows altered |
| `POST` | `/cdc/scrape/` | pull CDC BEAM monthly isolates by state/pathogen | Run id + number of rows altered |
| `POST` | `/usaspending/scrape/` | pull FDA spending per fiscal year | Run id + number of rows altered |

**Data**

| Method | Path | Purpose | Example |
| --- | --- | --- | --- |
| `GET` | `/fda-recalls/` | all recall events, newest first | |
| `GET` | `/cdc/{state_code}` | monthly illness counts for a state | `/cdc/CA` |
| `GET` | `/usaspending/` | all fda funding records | |
| `GET` | `/usaspending/{fiscal_year}` | latest fda funding record for a year | `/usaspending/2025` |
| `GET` | `/state-monthly-summary/` | recalls + illness per state per month, filterable by `states`, `start_year`, `end_year`, `fiscal_year` | `/state-monthly-summary/?states=CA&start_year=2020&end_year=2024` |
| `GET` | `/state-monthly-summary/{year_month}` | fetch one month, filterable by states | `/state-monthly-summary/2025-03?state=CA&states=TX` |
| `POST` | `/state-monthly-summary/rebuild/` | rebuild the summary table | |
| `POST` | `/state-monthly-summary/rebuild/{year}/` | rebuild all states for a single year | |
| `POST` | `/state-monthly-summary/rebuild/{year}/{month}/` | rebuild the summary table for all state for a single month | `/state-monthly-summary/rebuild/2020/01/` |

**Other tables**

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/states/`, `/states/{state_code}` | get state codes and names |
| `GET` | `/fiscal_years/`, `/fiscal_years/{year}` | get fiscal year start/end dates |
| `POST` | `/states/find_or_create`, `/fiscal_years/find_or_create` | add a row if it doesn't exist |
| `GET` | `/` | health check |

---

## Local Setup
Instructions [Here](SETUP_LOCAL.md)
## GCP Setup
Instructions [Here](SETUP_GCP.md)


## Know Issues

When deployed to Google Cloud Run, the FDA web scrapers can be blocked with a 401 unauthorized error. This only effects the collection of Recall Announcments.

Work around involves triggering the FDA scarping endpoints locally and having the local setup point to your gcp database.