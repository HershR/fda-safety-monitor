# FDA Safety Monitor

The dashboard looks at whether cuts to FDA funding lead to fewer or slower food recalls and more foodborne illness across the US. It’s meant for journalists, public health researchers, and members of Congress working on budgets.

**Live web app:** https://fda-monitor-web-180707148327.us-east1.run.app

**API (private):** In submission doc

---

## Team Members

| Name | GitHubID | Role / Focus |
| --- | --- | --- |
| Chris | tophercruzio | Data Engineer. Data cleaning and api endpoints FDA |
| Hersh | HershR | Backend/Database engineer, data transformers |
| Paul | pryu11 | Data Engineer. Data cleaning and api endpoints Funding and CDC |
| Carlos | ccamposlozano | GCP Deployment Engineer |
| Dylan | DylanSidhu03 | Frontend engineer and Dashboard visualizations |

---

## Problem Statement
With the budget cuts to FDA by the current administration, we wanted to see if they have had an adverse effect on food safety in the USA. We track FDA spending over the years along with food recall activity: the number of recalls, how severe they are, and how long FDA takes to classify them. Alongside this, we track foodborne illness reported by the CDC. We expect lower funding to lead to fewer or slower recalls and in turn more people getting sick.

## Data Sources and Integration Goal

### Data Sources
All four sources are free, public, and need no API key. Last checked 2026-09-30.

| # | Source & Link | Method | What it contains | Update frequency | Access requirements |
| --- | --- | --- | --- | --- | --- |
| 1 | [openFDA Food Enforcement](https://api.fda.gov/food/enforcement.json) | API | Official FDA food recalls from 2012 on. Includes recall class, company state, and initiation, classification, and report dates | Weekly | None |
| 2 | [FDA Recall Announcements](https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts) | Scraped | Recall announcements as companies post them: date, brand, product, category, reason, company. No state field | Daily | None |
| 3 | [CDC BEAM Dashboard](https://data.cdc.gov/Foodborne-Waterborne-and-Related-Diseases/BEAM-Dashboard-Report-Data/jbhn-e8xn/about_data) | API | Lab-confirmed Salmonella, STEC, Campylobacter, Shigella, and Vibrio samples by state, month, and source type | Monthly | None |
| 4 | [USASpending](https://api.usaspending.gov/api/v2/agency/075/sub_agency/?fiscal_year=2025) | API | FDA spending by fiscal year, listed under HHS (agency 075) | Daily | None |


### Integration Goal
USASpending shows how much FDA spends each fiscal year. openFDA lists official food recalls after FDA has reviewed them, including how serious each one was and how long the review took. The FDA announcements page posts a company's press release when a recall starts, often weeks before the FDA reviews and classifies it. CDC BEAM counts lab-confirmed illnesses from food.

We track recalls and illnesses by state and month. Each recall counts towards the month the FDA reported it. FDA spending is a single number per fiscal year and applied nationally, so we compare it with the national recall and illness totals for the same year. Announcements and openFDA recalls don't share an ID, so we link them by company name and how close their dates are. Some links will be wrong or missing, but it shows which announced recalls haven't reached openFDA yet.

We use the CDC human sample counts to check the recall data. Fewer inspections could mean fewer recalls even if food isn't any safer, but illness counts come from hospitals and labs and don't depend on FDA's budget. So we could see an increase in illness even though recalls are down.

---

## Repository Structure

### Important files
| File | Description |
| --- | --- |
| `backend/`| FastAPI server |
| `backend/src/main.py`| app instance |
| `backend/src/router.py` | registers routes |
| `backend/src/collectors/`| data collector endpoints, each collector stores raw data in a gcp bucket and cleaned data in database |
| `backend/src/transform.py`| used for creating monthly state summaries and matching Recall Announcements to Recall events (experimental) |
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
| `POST` | `/fda-recalls/scrape/` | pull openFDA recalls + FDA announcements, then match announcements to recalls | Run id + number of rows altered + announcements matched |
| `POST` | `/cdc/scrape/` | pull CDC BEAM monthly isolates by state/pathogen | Run id + number of rows altered |
| `POST` | `/usaspending/scrape/` | pull FDA spending per fiscal year | Run id + number of rows altered |

**Data**

| Method | Path | Purpose | Example |
| --- | --- | --- | --- |
| `GET` | `/fda-recalls/` | all recall events, newest first | |
| `GET` | `/fda-recalls/announcements/unmatched/` | announcements not matched to an openFDA recall, newest first | |
| `GET` | `/cdc/{state_code}` | monthly illness counts for a state | `/cdc/CA` |
| `GET` | `/usaspending/` | all fda funding records | |
| `GET` | `/usaspending/{fiscal_year}` | latest fda funding record for a year | `/usaspending/2025` |
| `GET` | `/state-monthly-summary/` | recalls + illness per state per month, filterable by `states`, `start_year`, `end_year`, `fiscal_year` | `/state-monthly-summary/?states=CA&start_year=2020&end_year=2024` |
| `GET` | `/state-monthly-summary/{year_month}` | fetch one month, filterable by states | `/state-monthly-summary/2025-03?states=CA&states=TX` |
| `POST` | `/state-monthly-summary/rebuild/` | rebuild the summary table | |
| `POST` | `/state-monthly-summary/rebuild/{year}` | rebuild all states for a single year | |
| `POST` | `/state-monthly-summary/rebuild/{year}/{month}` | rebuild the summary table for all state for a single month | `/state-monthly-summary/rebuild/2020/1` |

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


## Known Issues

When deployed to Google Cloud Run, the FDA web scrapers can be blocked with a 401 unauthorized error. This only affects the collection of Recall Announcements.

Matching Recall Announcements to official Recall events is not perfect. It matches based on a timeframe and company name similarity. The wrong event could be linked, or an event could be missed. Requires a revisit.