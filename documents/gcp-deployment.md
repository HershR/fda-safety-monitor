# GCP Deployment

Owner: Carlos Campos Lozano | Updated: October 12, 2026

The backend is deployed on Cloud Run. Authentication, Cloud SQL access, and
USAspending collection are verified. Web deployment and Scheduler are pending.

## Resources

| Resource | Configuration |
| --- | --- |
| Project | `fda-safety-monitor` |
| Cloud Run | `fda-monitor-api` in `us-east1` |
| Revision | `fda-monitor-api-00001-bnl`, 100% of traffic |
| Cloud SQL | `fda-safety-monitor:us-east1:fda-monitor-db` |
| Database / user | `fda_data` / `postgres` |
| Storage bucket | `fda-safety-monitor-data-2026` in `us-central1` |
| Service account | `fda-monitor-backend-service-ac@fda-safety-monitor.iam.gserviceaccount.com` |
| Password secret | `fda-monitor-db-password`, version `1` |
| Image repository | `us-east1-docker.pkg.dev/fda-safety-monitor/fda-monitor/backend` |

API: https://fda-monitor-api-180707148327.us-east1.run.app

The script returns the service's other URL:
https://fda-monitor-api-w35ngw63aa-ue.a.run.app

The service account has Cloud SQL Client and Storage Object Admin at project
scope, and Secret Accessor on the password secret. Cloud Run, Cloud Build,
Artifact Registry, Scheduler, and Secret Manager APIs are enabled.

## Configuration

- The image uses `fastapi run` on port 8080. Local Compose uses `fastapi dev`.
- Cloud Run connects through `/cloudsql/fda-safety-monitor:us-east1:fda-monitor-db`
  on port 5432. It does not depend on the proxy running on a developer's laptop.
- Cloud Run reads the SQL password from Secret Manager and uses its assigned
  service account for Storage. No JSON key is deployed.
- Local Compose still uses `db:5432` and the configured local JSON key.
- `URL.create` handles passwords with special characters. `pool_pre_ping` checks
  connections before reuse but does not retry interrupted transactions.
- Runtime settings: second generation, 1 CPU, 512 MiB, 0–1 revision instances,
  concurrency 8, and a 300-second request timeout.

The deployed image is tagged `cloudrun-v1`, with digest:

```text
sha256:c8180b8f08a044e4473264c5ea002a2d1a99deb4e5ce8a16ea5c21ea39f735d3
```

The current source keeps `echo=True`; the deployed image has SQL logging disabled.
A new image and deployment are needed to apply that difference. Do not commit
`.env`, passwords, tokens, or JSON keys.

## Tests completed

| Test | Result |
| --- | --- |
| Configuration tests | Four passed; no GCP connection required |
| Local Compose | Startup passed; `/states/` on port 8083 returned HTTP 200 |
| Built image with local Cloud SQL proxy | Startup and `/states/` on port 8082 passed |
| Cloud Run without authentication | `/states/` returned HTTP 403 |
| Cloud Run with authentication | `/states/` returned HTTP 200 |
| Cloud Run USAspending collection | HTTP 200 with `{"fda_funding":10}` |
| Storage inspection | 10 files for fiscal years 2017–2026 |
| Direct Cloud SQL query | 10 rows for collection date `2026-10-12`, covering 2017–2026 |
| Deployment script | Syntax, help, URL lookup, and revision listing passed |

The verified Storage run is `01a131d1-2996-72bf-a553-b9ed73f481cd` under
`raw/usaspending/2026-10-12/`. The team's [PR #10](https://github.com/HershR/fda-safety-monitor/pull/10)
added the year to filenames to prevent overwrites. SQL updates existing primary
keys, so the API's count does not mean 10 new rows were inserted.

Run the configuration tests from the repository root:

```bash
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v
```

To repeat the local development check with the existing Compose database running:

```bash
docker compose --env-file backend/.env -f backend/docker-compose.yaml config --quiet
docker compose --env-file backend/.env -f backend/docker-compose.yaml \
  run --rm --no-deps --build -p 127.0.0.1:8083:8080 server
```

In another terminal, request `http://127.0.0.1:8083/states/`. Stop the temporary
server with Ctrl+C. Automatic reload after an edit was not separately tested.

For SQL verification, connect to Cloud SQL's `fda_data` database and run:

```sql
SELECT collected_at, COUNT(*) AS records,
       MIN(fiscal_year) AS first_year, MAX(fiscal_year) AS last_year
FROM public.fda_funding
GROUP BY collected_at
ORDER BY collected_at DESC;
```

Local and Cloud SQL passwords may differ. The successful SQL check used secret
version `1`. For the separate image test on port 8082, build the image as
`fda-monitor-backend:cloud-run` and use `backend/docker-compose.cloudrun-test.yaml`
with the proxy on port 5433 and a runtime `DB_PASSWORD` override. That setup has
no Storage credentials. Compose parses quoted `.env` values; `docker run
--env-file` preserves the quotes and can cause authentication failures.

## Deploy and recover

`gcloud_command.sh` follows the course template's configuration and action layout.
It reuses existing resources and separates building, uploading, and deploying.
The initial deployment used manual commands; the script's build, push, deploy,
and rollback actions have not yet been executed through the script.

Read-only commands:

```bash
bash gcloud_command.sh help
bash gcloud_command.sh urls
bash gcloud_command.sh revisions
```

For a future update, choose a new image tag. Run each step only after the previous
one succeeds. Docker authentication must already be configured for
`us-east1-docker.pkg.dev`.

```bash
bash gcloud_command.sh build cloudrun-v2
bash gcloud_command.sh push cloudrun-v2
```

Then run `bash gcloud_command.sh api IMAGE_REFERENCE`, replacing `IMAGE_REFERENCE`
with the full repository path followed by `@sha256:` and the digest from the push.
This updates Cloud Run. Without an image argument, `api` redeploys the initial
image, not current local code. Retest authentication, SQL, and collection results.

To recover, list revisions and choose a previously tested ready revision. If the
initial revision is still ready and available, this restores traffic to it:

```bash
bash gcloud_command.sh rollback fda-monitor-api-00001-bnl
```

Rollback has not been tested. It does not undo database changes, Storage writes,
or password rotation. Keep old image digests and secret versions available.

## Remaining work

- Test deployed CDC and recall collection.
- Verify the remaining script commands and recovery procedure.
- Deploy the web app separately with authenticated API access.
- Add authenticated Scheduler jobs and verify their results. Clarify the rubric's
  "two Cloud Scheduler jobs (per data source)" requirement first.
- Extend the script and documentation for the web app and scheduling.
