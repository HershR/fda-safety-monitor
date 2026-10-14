### 6. Run the dashboard
The dashboard reads data from the API, so keep the backend from step 4 running and run the scrapers in step 5 first. Open a second terminal at the repository root:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r frontend/requirements.txt
cp frontend/.env.template frontend/.env
streamlit run frontend/app.py
```

The dashboard opens at http://localhost:8501.

| Variable | Description | Example |
| --- | --- | --- |
| `API_BASE_URL` | URL of the backend API | `http://localhost:8080` |

The default `API_BASE_URL` matches the local Docker backend, so `frontend/.env` doesn't need changes. If a section says there is no data yet, run that source's scraper in step 5. If the page says it could not reach the API, check that the backend containers are running with `docker compose ps` from `backend/`.
