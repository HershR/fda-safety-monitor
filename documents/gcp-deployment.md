# GCP Deployment Status

Owner: Carlos Campos Lozano | Updated: October 12, 2026

The backend has been tested locally with Cloud SQL and Cloud Storage. Cloud Run deployment and scheduled collection are still pending.

## Resources

| Resource | Configuration |
| --- | --- |
| Project | `fda-safety-monitor` |
| Storage bucket | `fda-safety-monitor-data-2026` (`us-central1`) |
| Cloud SQL instance | `fda-monitor-db` (`us-east1`) |
| Database | `fda_data` |
| SQL connection name | `fda-safety-monitor:us-east1:fda-monitor-db` |
| Backend service account | `fda-monitor-backend-service-ac@fda-safety-monitor.iam.gserviceaccount.com` |

The service account has Cloud SQL Client and Storage Object Admin. Cloud Run, Cloud Build, Artifact Registry, Cloud Scheduler, and Secret Manager APIs are enabled. Deployment should reuse the existing database and bucket.

## Verified results

Tests used a temporary local backend on port `8081`, connected through the Cloud SQL Auth Proxy on port `5433`.

| Test | Result |
| --- | --- |
| Backend startup against Cloud SQL | Tables initialized and seed transaction completed |
| `GET /states/` | Returned state records |
| `POST /usaspending/scrape/` | HTTP 200 with `{"fda_funding":10}` |
| Direct SQL query after repeated collection | 10 records for collection date `2026-10-12`, covering fiscal years 2017-2026 |
| Bucket listing after the team's [PR #10](https://github.com/HershR/fda-safety-monitor/pull/10) | 10 distinct objects named for years 2017-2026 in the new run |

PR #10 corrected the raw-file naming collision by including the fiscal year. The retest confirmed separate filenames and no additional database rows for the same collection date. CDC and recall ingestion have not yet been verified against Cloud SQL.

To check funding records after connecting to `fda_data`:

```sql
SELECT collected_at, COUNT(*) AS records,
       MIN(fiscal_year) AS first_year, MAX(fiscal_year) AS last_year
FROM public.fda_funding
GROUP BY collected_at
ORDER BY collected_at;
```

## Configuration notes

- Docker Compose overrides `.env` with `DB_HOST=db` and `DB_PORT=5432`. The Cloud SQL test used a temporary connection override; the regular local setup still points to Docker PostgreSQL.
- A dropped database connection caused an HTTP 500 during local testing. A fresh database connection succeeded, and restarting the temporary backend restored operation. Connection resilience still needs attention before deployment.
- Keep passwords in Secret Manager for deployment and use an attached service account for GCP access. Do not commit `.env`, tokens, or JSON keys.

## Remaining work

- Prepare and test the backend and frontend containers for Cloud Run.
- Configure runtime identities, database secrets, and the Cloud SQL connection.
- Deploy the API and web app as separate services.
- Configure authenticated Cloud Scheduler jobs and verify their results.
- Add `gcloud_command.sh` for reproducible configuration, deployment, and scheduling.
- Document service URLs, architecture, and deployment and recovery procedures.
