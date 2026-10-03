# Backend

FastAPI server and Postgres database, run with Docker Compose. Run all commands from the `backend/` directory.

## Environment variables
```bash
cp .env.template .env
```

Fill in `DB_PASSWORD` and the GCP values.

| Variable | Description |
| --- | --- |
| `DB_NAME` | Database name |
| `DB_HOST` | Database host. Docker Compose sets this to `db` |
| `DB_PORT` | Database port |
| `DB_USER` | Database user |
| `DB_PASSWORD` | Database password |
| `GCP_PROJECT_ID` | GCP project ID |
| `GCP_BUCKET_NAME` | Cloud Storage bucket for scraped data |
| `GCP_SERVICE_ACCOUNT_KEY` | Path to the service account key inside the container (default `/tmp/gcp-key.json`) |
| `LOCAL_GCP_SERVICE_ACCOUNT_KEY` | Path to the service account key on your machine |

Compose mounts the key from `LOCAL_GCP_SERVICE_ACCOUNT_KEY` to `GCP_SERVICE_ACCOUNT_KEY`. If the local path is empty, `docker compose up` fails.

## Run with Docker

Start the containers:
```bash
docker compose up -d
```

- API: http://localhost:8080 (docs at http://localhost:8080/docs)
- Postgres: `localhost:5439`

`src/` is mounted into the container, so the server reloads when you edit code. If it doesn't, or you changed `requirements.txt`, rebuild:
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

## Routes

| Method | Path | Description |
| --- | --- | --- |
| GET | `/` | Health check |
| GET | `/states/` | List all states |
| GET | `/states/{state_code}` | Get one state |
| POST | `/states/` | Add a state |
| GET | `/fiscal_years/` | List all fiscal years |
| GET | `/fiscal_years/{year}` | Get one fiscal year |
| POST | `/fiscal_years/` | Add a fiscal year |
| POST | `/fda-recalls/scrape/` | Pull openFDA recalls from the last year and current FDA food recall announcements, then upload them to `fda_recalls/` in the bucket as `recall_event.json`, `recall_product.json`, and `recall_announcement.json` |

## Code layout
```
src/
├── api/
│   ├── routes/          # One file per resource
│   └── router.py        # Registers each route file under its prefix
├── main.py              # App entry point, creates tables on startup
├── models.py            # SQLModel tables
├── database.py          # Engine and session dependency
├── config.py            # Reads environment variables
└── enums.py
```

## Adding a route
1. Create a file in `src/api/routes/` with `router = APIRouter()` and your endpoints.
2. Import it in `src/api/router.py` and register it with `api_router.include_router(...)`, giving it a prefix and tag.
