# GCP Deployment Status

Owner: Carlos Campos Lozano | Updated: October 12, 2026

The private backend is deployed on Cloud Run. USAspending collection was verified
with 10 files in Storage and 10 SQL records for fiscal years 2017-2026, collected
on `2026-10-12`. Local development startup and database reads also passed.
Web deployment and scheduled collection remain pending.

## Resources

| Resource | Configuration |
| --- | --- |
| Project | `fda-safety-monitor` |
| Storage bucket | `fda-safety-monitor-data-2026` (`us-central1`) |
| Cloud SQL instance | `fda-monitor-db` (`us-east1`) |
| Database | `fda_data` |
| SQL connection name | `fda-safety-monitor:us-east1:fda-monitor-db` |
| Backend service account | `fda-monitor-backend-service-ac@fda-safety-monitor.iam.gserviceaccount.com` |
| Database password secret | `fda-monitor-db-password`, version `1`; backend service account has Secret Accessor on this secret |
| Artifact Registry | Docker repository `fda-monitor` in `us-east1`; `us-east1-docker.pkg.dev/fda-safety-monitor/fda-monitor` |

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
- `pool_pre_ping=True` checks database connections before reuse. It does not retry interrupted transactions.
- Keep passwords in Secret Manager for deployment and use an attached service account for GCP access. Do not commit `.env`, tokens, or JSON keys.

## Backend container preparation

The database password is stored in `fda-monitor-db-password`, version `1`, with
automatic replication. The image is stored in the `fda-monitor` repository:
`us-east1-docker.pkg.dev/fda-safety-monitor/fda-monitor/backend:cloudrun-v1`.
Its registry digest is
`sha256:c8180b8f08a044e4473264c5ea002a2d1a99deb4e5ce8a16ea5c21ea39f735d3`.

The backend service account has `roles/cloudsql.client` and
`roles/storage.objectAdmin` at project scope, plus
`roles/secretmanager.secretAccessor` on `fda-monitor-db-password`.

The backend Dockerfile preserves the `src` package and places seed JSON files in
`src/data`, matching the paths used by the application. It starts the application
with `fastapi run src/main.py --host 0.0.0.0 --port 8080`, following the course
Dockerfile examples. Configure the Cloud Run container port as `8080` to match.
Docker Compose overrides the command to retain development reload and mounts
source and seed files at the new paths.

For Cloud Run, leave `GCP_SERVICE_ACCOUNT_KEY` unset to use Application Default
Credentials from the attached service account. Explicit key files remain
supported for local development. Set `DB_HOST` to
`/cloudsql/fda-safety-monitor:us-east1:fda-monitor-db`, `DB_PORT` to `5432`, and
attach that Cloud SQL instance to the service. Supply `DB_PASSWORD` from Secret
Manager. The SQLAlchemy URL object preserves special characters in passwords.

The current source retains `echo=True` for SQL logging. The deployed image has
SQL logging disabled. A new build and deployment are required to apply that
source change to Cloud Run.

Four isolated tests pass for TCP and Unix socket connection parameters,
passwords containing reserved characters, default credentials, and explicit
local key credentials. Run them from the repository root:

```bash
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v
```

These tests do not contact GCP. The backend image built successfully for
`linux/amd64` with the tag `fda-monitor-backend:cloud-run` on October 12:

```bash
docker build --platform linux/amd64 -t fda-monitor-backend:cloud-run ./backend
```

An isolated container check with networking disabled successfully imported
`src.main` and parsed both seed JSON files from the image. This check did not run
the application's startup hook or connect to SQL or Storage.

The built image also passed startup and `GET /states/` on local port `8082`
using Cloud SQL through the proxy.

### Initial Cloud Run deployment

Service `fda-monitor-api` was deployed in `us-east1` with revision
`fda-monitor-api-00001-bnl` receiving 100% of traffic.

- URL: https://fda-monitor-api-180707148327.us-east1.run.app
- URL returned by `status.url` and the script:
  https://fda-monitor-api-w35ngw63aa-ue.a.run.app
- Authentication required (`--no-allow-unauthenticated`). Anonymous
  `GET /states/` returned HTTP 403; the same request with a developer ID token
  returned HTTP 200 and state records.
- Runtime identity: the existing backend service account listed above.
- Cloud SQL instance attached: `fda-safety-monitor:us-east1:fda-monitor-db`.
- Database: `fda_data`, user `postgres`, socket directory
  `/cloudsql/fda-safety-monitor:us-east1:fda-monitor-db`, port `5432`.
- Password: Secret Manager `fda-monitor-db-password:1`.
- Storage: project `fda-safety-monitor`, bucket `fda-safety-monitor-data-2026`;
  no service account key file configured.
- Runtime: second generation, port `8080`, 1 CPU, 512 MiB, minimum 0 and maximum
  1 revision instances, concurrency 8, request timeout 300 seconds.

An authenticated `POST /usaspending/scrape/` returned HTTP 200 with
`{"fda_funding":10}`. This route uploads raw files using Application Default
Credentials and commits funding rows before returning. No service account key
file is configured. The subsequent bucket listing confirmed 10 distinct objects
for run `01a131d1-2996-72bf-a553-b9ed73f481cd`, covering fiscal years 2017-2026
under `raw/usaspending/2026-10-12/`. Their timestamps span
`2026-10-12T20:32:34Z` through `2026-10-12T20:32:41Z`.
An independent query through the local proxy, using secret version `1` in memory,
confirmed `2026-10-12 | 10 | 2017 | 2026` for collection date, row count, minimum
year, and maximum year.
The API response count is not a count of newly inserted rows because existing
primary keys are updated.

The service uses the Cloud Run Cloud SQL integration and does
not depend on the local proxy.

### Local development compatibility check

The updated development Compose configuration passed validation with
`config --quiet`. A temporary backend built from the current source started with
`fastapi dev`, the updated source/data mounts, and `echo=True`, using the existing
local PostgreSQL service at `db:5432`. `GET http://127.0.0.1:8083/states/` returned
state records and HTTP 200. This validates local startup and database reads;
automatic reload after a source edit was not separately exercised.

From the repository root, with the local Compose database already running:

```bash
docker compose --env-file backend/.env -f backend/docker-compose.yaml config --quiet
docker compose --env-file backend/.env -f backend/docker-compose.yaml \
  run --rm --no-deps --build -p 127.0.0.1:8083:8080 server
```

In another terminal:

```bash
curl --fail-with-body --show-error --max-time 15 http://127.0.0.1:8083/states/
```

Stop only this temporary backend with Ctrl+C in its attached terminal. The
`--rm` option removes the temporary container; the existing database and other
services remain in place. This check does not change Cloud Run.

### Local image startup check (Docker Desktop on macOS)

With the existing Cloud SQL Auth Proxy listening on port `5433`, run from the
repository root and enter the Cloud SQL password when prompted:

```bash
python - <<'PYTHON'
import os
import subprocess
from getpass import getpass

environment = os.environ.copy()
environment["DB_PASSWORD"] = getpass("Cloud SQL password (hidden): ")
subprocess.run(
    [
        "docker", "compose", "-p", "fda-cloudrun-check",
        "-f", "backend/docker-compose.cloudrun-test.yaml",
        "run", "--rm", "--no-deps", "--service-ports",
        "-e", "DB_PASSWORD", "api",
    ],
    env=environment,
    check=True,
)
PYTHON
```

This separate Compose project tests the built image without source mounts on
`http://127.0.0.1:8082`. Compose parses the local `.env` and overrides the database
host and port to reach the proxy. Enter the Cloud SQL password rather than the
local PostgreSQL password from `.env`.

Avoid `docker run --env-file backend/.env` with quoted values: it preserves the
surrounding quotes. Compose interprets them as environment-file syntax.

After startup completes, verify a database-backed route from another terminal:

```bash
curl --fail-with-body --show-error --max-time 15 http://127.0.0.1:8082/states/
```

An older temporary backend on port `8081` had `DB_HOST=db` and `DB_PORT=5432` in
its container configuration. Its successful response alone must not be used as
evidence of Cloud SQL access.

The check runs the normal table and seed initialization against Cloud SQL.
It does not mount credentials or validate Storage access. Stop the check with Ctrl+C, then
remove only its temporary containers and network:

```bash
docker compose -p fda-cloudrun-check -f backend/docker-compose.cloudrun-test.yaml down
```

References: [Cloud Run container contract](https://docs.cloud.google.com/run/docs/container-contract),
[Cloud SQL connection](https://docs.cloud.google.com/sql/docs/postgres/connect-run),
and [Cloud Run service identity](https://docs.cloud.google.com/run/docs/securing/service-identity).

## Reproducible backend deployment and recovery

`gcloud_command.sh` follows the course template's configuration block and command
selection structure. It uses the existing resources and the tested image-based
deployment workflow. The API is private and uses an attached service account
instead of a JSON key. Web and Scheduler commands are not implemented yet.

From the repository root:

```bash
bash gcloud_command.sh help
bash gcloud_command.sh urls
bash gcloud_command.sh revisions
```

For a future code change, choose a new tag and complete each step successfully
before continuing:

```bash
bash gcloud_command.sh build cloudrun-v2
bash gcloud_command.sh push cloudrun-v2
```

Copy the full repository reference and digest returned by the push, then pass
that immutable image reference to `bash gcloud_command.sh api IMAGE_REFERENCE`.
Without an image argument, `api` redeploys the initially verified digest with
secret version `1`. It does not build or upload local code changes. Record the
new revision and rerun anonymous/authenticated `/states/` checks and collection
verification before declaring the new revision healthy.

For recovery, list revisions and select a previously tested ready revision. The
initial verified revision is `fda-monitor-api-00001-bnl`. If it is still available
and ready, restore traffic with:

```bash
bash gcloud_command.sh rollback fda-monitor-api-00001-bnl
```

Traffic rollback does not undo database writes, schema changes, bucket objects,
or password rotation. Keep referenced image digests and secret versions
available. If the old revision no longer exists, redeploy its retained digest
with compatible configuration. No rollback or redeployment was executed while
preparing this script. Shell syntax and the offline help command passed.
The `urls` command returned the service's `status.url`, and `revisions` confirmed
`fda-monitor-api-00001-bnl` is ready and active. The script's build, push, deploy,
and rollback commands have not been executed; the initial deployment and tests
used the equivalent manual workflow documented above.

## Remaining work

- Prepare and test the frontend container; CDC and recall collection tests are still pending.
- Verify the backend deployment script commands and recovery procedure.
- Deploy the web app separately and configure authenticated API access.
- Configure authenticated Cloud Scheduler jobs and verify their results.
- Clarify the rubric's "two Cloud Scheduler jobs (per data source)" requirement
  before finalizing scheduling scope.
- Extend `gcloud_command.sh` with web deployment and authenticated scheduling.
- Add the web URL and complete the architecture and recovery documentation.
