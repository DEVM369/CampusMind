# Deployment

## Prerequisites

- Python 3.12; Node.js 22 is needed to rebuild or validate the frontend, but not to serve an already built UI.
- A dedicated PostgreSQL 17 instance with pgvector 0.8.6. Migration 0008 changes cluster-level roles, so do not run the migrations in a shared PostgreSQL cluster without reviewing those roles.
- Neo4j, Redis, and RustFS configured for the same environment. Their connectivity is checked separately from database schema readiness.

Copy `.env.example` to `.env` and fill in the real endpoints and credentials. `.env` stays local and is ignored by Git. The values in `.env.example` are placeholders, not a working deployment. The configured PostgreSQL login must be able to create extensions, tables, and the `campusmind_runtime` role during migration.

Use `RAG_EMBEDDING_PROVIDER=deterministic` for the offline checks and isolated acceptance environment. This selects local deterministic embeddings; it does not disable every chat endpoint. The validation commands below never submit chat or agent requests to a model.

## Windows local run

From the project root with the `campusmind` Python environment active:

```powershell
python -m pip install -e ".[dev]"
python -m alembic upgrade head
.\scripts\seed_demo.ps1
python -m scripts.seed_library
.\scripts\validate.ps1
.\scripts\run.ps1
```

`seed_demo.ps1` prompts separately for a demo-user and admin password, hashes them with scrypt, and only fills passwords missing from the synthetic seed accounts. It does not overwrite existing password hashes. Keep these demo credentials out of public deployments. `seed_library` adds synthetic book inventory; it does not call an embedding or chat model.

Open `http://127.0.0.1:8000/ui/` or `http://127.0.0.1:8000/docs`. Log in with `student001` or `admin` and the password chosen during seeding. The browser no longer accepts arbitrary user IDs as authentication.

## Reset a forgotten demo password (Ubuntu)

The command reads the password twice without echoing it, requires 12-256 characters (matching the login API's maximum), stores only the existing scrypt hash format, and revokes every unrevoked session for that account in the same database transaction. Unsupported terminals are rejected before visible-input fallback. Passwords are never command-line arguments, environment variables, or output.

For a running API container, copy only `scripts/reset_demo_passwords.py` from the updated checkout to the Ubuntu operator's home directory. For example, run `scp scripts/reset_demo_passwords.py operator@ubuntu-host:campusmind-reset-password.py` from the checkout on your workstation, using your real SSH login and host. No environment file is transferred.

Then run this group in the Ubuntu terminal. Choose the existing API container from the list. If Docker requires elevated access, use `sudo docker` for these Docker commands.

Run these commands directly in the Ubuntu shell. Windows PowerShell can remove the inner quotes when forwarding a complex command through `ssh`, causing errors such as `"docker ps" accepts no arguments`. If that happens, cancel the remote command with Ctrl+C and use the Ubuntu terminal; the Python file already uploaded by `scp` does not need to be transferred again.

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
read -r -p 'CampusMind API container name: ' CM_API_CONTAINER
docker cp "$HOME/campusmind-reset-password.py" "${CM_API_CONTAINER}:/tmp/campusmind-reset-password.py" &&
docker exec -it -e RAG_EMBEDDING_PROVIDER=deterministic "$CM_API_CONTAINER" \
  python /tmp/campusmind-reset-password.py student001 --verify-login
```

This reuses the running container's database environment, including deployments originally started with `--env-file test.env`; never display, source, or paste that file. No image rebuild or API restart is needed. The temporary Python file contains code only. It can be copied into the existing image because the image intentionally excludes development scripts.

`--verify-login` contacts only `http://127.0.0.1:8000` inside the container, verifies `POST /api/v1/auth/login`, the returned username, role and superuser flag via `GET /api/v1/auth/me`, and logs out the verification session. It bypasses environment proxies, does not follow redirects, and never prints cookies. HTTP verification failure does not undo a successful password reset. Neither operation invokes an LLM or an embedding service.

Recover `student001` first and log into `/ui/` with the new password. Once verified, repeat the last command with `admin`, choosing a distinct password. Any previously logged-in browser must log in again. Never share the passwords in logs or chat.

If the account is absent, the reset command stops without creating accounts or changing passwords or sessions. Check which database the API container actually uses and whether that database contains the selected synthetic account before retrying. A test database can have integration-test users without the baseline `student001` or `admin` accounts. Do not rerun the entire seed process or switch databases solely to suppress a reset failure. Older copied versions report this condition as `Password reset failed (RuntimeError)`, which is unrelated to password length.

After a read-only check confirms that the selected synthetic login is missing from the intended isolated test database, copy the latest script into the container and use the explicit creation option:

```bash
docker exec -it -e RAG_EMBEDDING_PROVIDER=deterministic "$CM_API_CONTAINER" \
  python /tmp/campusmind-reset-password.py student001 \
  --create-missing-in-test-db campusmind_p0_test --verify-login
```

This option checks the connected PostgreSQL database name against the supplied name (which must end in `_test`) and requires migration head `20260926_0011`. It creates only the selected missing login and its `student` or `admin` role assignment, using the same hidden password input. It does not grant privileges to an existing account: if that username already exists, creation stops and the ordinary reset command must be used. User creation, password hashing, role creation and assignment commit together or roll back together. Existing users, passwords, sessions and role definitions are preserved.

New `student001` logins are not automatically attached to an existing `students` record. Academic records and course results need separate synthetic data setup and ownership checks; login success alone does not establish that student queries have data. The `admin` option creates a synthetic administrator login in the checked test database only. Run it separately after verifying student login, using a different password.

For an Ubuntu source deployment with Python dependencies already installed, run `PYTHONPATH=src python -m scripts.reset_demo_passwords student001 --verify-login` from the updated repository root with its configured `.env`. The same command supports `admin`. Omit `--verify-login` when the API is not running locally on port 8000.

## Ubuntu API container with external infrastructure

The supported minimal deployment keeps PostgreSQL, Neo4j, Redis and RustFS as separately managed services. On Linux, the API uses host networking so the addresses already configured for those services also work inside the API container. There is no automatic migration, seed, or dependency creation during API startup.

For a **new installation**, run from the repository root in Ubuntu after installing Node.js 22 and Docker. Prepare a local `.env` with service credentials; do not print or transfer it in support messages. These commands create a new named API container and stop if that name already exists. They do not replace an existing deployment.

```bash
npm ci --prefix frontend &&
npm run check --prefix frontend &&
docker build -f infra/docker/Dockerfile -t campusmind-api:local .
```

Review the target database before the explicit migration step:

```bash
docker run --rm --network host --env-file .env \
  -e RAG_EMBEDDING_PROVIDER=deterministic campusmind-api:local python -m alembic upgrade head &&
docker run -d --name campusmind-api --restart unless-stopped --network host \
  --env-file .env -e RAG_EMBEDDING_PROVIDER=deterministic campusmind-api:local
```

Seed synthetic accounts from a Windows source checkout using `scripts/seed_demo.ps1` with the intended database configured. Its hidden prompts pass passwords to `scripts/seed_core.py` only for the subprocess lifetime and clear the environment afterward. The Python seed module itself does not prompt. A freshly migrated database has no demo accounts. The guarded missing-login option described above can provision logins from Ubuntu in a named isolated test database; it does not seed academic records. Do not attach a login to an arbitrary existing student record.

The image contains the API, migrations, frozen baseline SQL, built frontend, and two read-only smoke scripts. Development, password recovery and seed scripts are excluded. Run `docker exec campusmind-api python scripts/check_runtime.py` to verify health, dependency status, migration head and UI assets. With host networking the API listens on the host's port 8000. Restrict exposure through the host firewall/reverse proxy; use HTTPS before handling credentials over an untrusted network.

`unless-stopped` restarts the container after an unexpected process exit or Docker daemon restart, unless an operator explicitly stopped it. A controlled `docker restart campusmind-api` tests process recovery, not host boot or Docker daemon recovery. Perform restart acceptance during an agreed test window, then poll `check_runtime.py` until it passes and verify both accounts in the browser. Never print `docker inspect` environment fields. Inspect only `.HostConfig.NetworkMode` and `.HostConfig.RestartPolicy.Name` when checking policy.

For the isolated test deployment, copy `scripts/accept_restart.py` and `scripts/check_runtime.py` to the same directory on the Ubuntu host. Run `sudo python3 accept_restart.py --container campusmind-api --test-database campusmind_p0_test --restart` from that directory. The script first checks the actual database name, head, deterministic embedding setting and both account roles using a read-only transaction inside the container. It then verifies the container policy and all runtime checks before restarting only the named API. Omit `--restart` for a read-only preflight. It does not change deployment settings, reset passwords or seed academic records. `CM_RESTART_ACCEPTANCE_PASSED` means controlled restart recovery only; host boot, RLS and concurrent approvals remain separate checks.

On Docker Desktop or a bridge network, use an explicit published port and service addresses reachable from that network. `127.0.0.1` refers to the container in bridge mode. The host-network command above targets Linux.

## Student identity and PostgreSQL RLS acceptance

`scripts/accept_student_security.py` is an operator acceptance command for the isolated test database. Copy it into the running API container; no image rebuild is needed. It requires PostgreSQL at head `20260926_0011`, an exact `--test-database` name ending in `_test`, deterministic embeddings in both the container and running API, and the existing active `student001` and `admin` logins with their expected roles.

Run in an interactive Ubuntu terminal after copying the script:

```bash
sudo docker exec -it campusmind-api python /tmp/accept_student_security.py \
  --test-database campusmind_p0_test --provision-missing
```

Enter the **existing** password for `student001`, then the existing password for `admin`. These hidden prompts verify login and `/auth/me`; they do not reset passwords. Proxy lookup and redirects are disabled, and HTTP calls stay on loopback port 8000 inside the container. Verification sessions are individually logged out; existing browser sessions are preserved. Unsupported hidden-input terminals stop rather than echoing a password.

`--provision-missing` explicitly permits one atomic fixture transaction. It adds a reserved synthetic college/department/major, two courses, and a profile bound only to `student001`: student number `CM-ACCEPT-STUDENT001`, 7 earned credits, and 160 required credits. An inactive peer account with no password or role supplies a distinct ownership negative control. The script does not attach arbitrary pre-existing student records. Reserved IDs, codes, owners and values must match on rerun; a conflict rolls back the fixture transaction. Existing account passwords, roles, sessions and unrelated academic records are not overwritten. Omitting the flag requires the fixtures to exist already.

The same transaction creates five database-only synthetic evidence chunks: public, campus, own personal, peer personal and a quarantined injection sample. No files are uploaded to object storage. The script then checks:

- SQL student ownership and consistency between course credits and the student summary.
- Actual PostgreSQL forced RLS under a non-superuser/non-BYPASSRLS runtime role in read-only transactions: public scope, campus scope, each personal owner, and anonymous scope after a personal transaction on the same physical connection.
- HTTP login/roles, own profile/credits/grades, a forged peer actor denied with 403, and anonymous student access denied with 401.
- Document ownership, anonymous protected-document denial, and public-only `/rag/search` with both a visible positive control and protected negative controls.

Only deterministic retrieval is called. `/chat`, `/model-check`, agent endpoints and online models are not called. `CM_STUDENT_SECURITY_ACCEPTANCE_PASSED` covers these checks only. HITL replay/concurrency, host boot, empty-database migration and a new image/CI run remain separate acceptance work. Synthetic fixtures are retained after a later HTTP/RLS failure so results can be inspected and rerun; the script does not delete data.

## Approval, replay and PostgreSQL concurrency acceptance

Copy both `scripts/accept_hitl.py` and `scripts/accept_student_security.py` into `/tmp/` in the running API container. The HITL script reuses the existing target, login and secret-redaction helpers. The image excludes operator scripts, so they must be transferred explicitly; no image rebuild or environment-file transfer is required.

In an interactive Ubuntu terminal:

```bash
sudo docker exec -it campusmind-api python /tmp/accept_hitl.py \
  --test-database campusmind_p0_test --run-synthetic-actions \
  --report-dir /tmp/campusmind-acceptance
```

The command checks the actual named PostgreSQL database, migration head, deterministic embedding setting and existing account roles. Enter the existing `student001` and `admin` passwords at the hidden prompts. It logs out only its own verification sessions. Without `--run-synthetic-actions`, it performs database/account preflight and does not run the action scenarios.

The explicit action flag authorizes scripted approval/rejection decisions for synthetic resources. Each run adds three new single-copy synthetic books and owned traces with a unique run identifier. Classroom scenarios use the built-in synthetic room catalog on three unused dates in 2090-2097, checked against both existing approval requests and reservations. The script never resets stock, changes an existing booking or deletes data. A second run creates new resources. A failed run can leave its synthetic approvals/reservations and traces for inspection.

For both library and classroom tools, it verifies prepare creates no reservation; anonymous, forged actor, foreign owner, missing approval, missing explicit decision, invalid candidate and wrong-tool requests fail; rejection stays rejected on replay; and concurrent confirmations of one approval return two HTTP 200 responses with one new effect and one idempotent response. A later replay must preserve the same SQL reservation ID.

It also races two distinct owners for the same last book copy and for one classroom slot. Both cases must return HTTP 200/409 with one reservation. A controller holds only the test resource's transaction-scoped advisory lock until PostgreSQL reports both HTTP transactions blocked, including transitive waits on an approval row. The lock is released before workers are joined, including failure paths. Missing contention evidence fails acceptance. Inventory and per-approval execution audit/tool-call counts are checked against the committed SQL state.

`--report-dir` writes a new `hitl-<run-id>.json` using exclusive creation. It records check names, HTTP statuses, observed waiters and SQL counts/IDs for synthetic reservations, with no passwords, cookies, environment contents or raw error responses. Reports remain inside the container unless separately exported. `CM_HITL_ACCEPTANCE_PASSED` covers these HTTP and PostgreSQL action checks, not an online model, frontend approval clicks, host reboot, a rebuilt image or CI execution. Agent/chat/model-check endpoints are not invoked.

## Validation

`python scripts/check_project.py` is the shared local/CI entry. `scripts/validate.ps1` delegates to it. It checks static structure, runs pytest with external sockets and non-SQLite connections blocked, checks OpenAPI, and validates the built frontend. It stops on the first failing command. Dependencies must already be installed; the checker does not install packages or start a persistent server.

GitHub Actions uses `python scripts/check_project.py --build-frontend --docker-image campusmind-api:ci` after installing dependencies. The image smoke runs an owned API process in an ephemeral `--network none` container, fetches liveness and UI assets, and expects readiness HTTP 503 without infrastructure. It does not touch an existing API container. `CM_DOCKER_IMAGE_SMOKE_PASSED` therefore proves packaging and HTTP startup only.

`python scripts/check_runtime.py --base-url http://your-api-host:8000 --json` checks a running deployment without authentication or writes. Output includes only paths, HTTP status and pass/fail, never raw infrastructure responses. `--liveness-only` deliberately skips dependencies and schema and is not deployment acceptance.

Real PostgreSQL RLS, concurrent approval, graph ingestion, restart recovery, and model quality need separate evidence. Neither the isolated image smoke nor a green offline workflow certifies them. Keep passwords and raw private infrastructure diagnostics out of acceptance reports.

## Offline functional benchmark

Run the checked-in synthetic benchmark from the project root with the `campusmind` environment:

```powershell
python scripts/run_offline_benchmark.py --output reports/offline/benchmark-v1.json
```

The runner uses `datasets/offline_benchmark_v1.json`, deterministic retrieval rules and no database, network, graph service, embedding API or language model. It writes raw per-case route, evidence, citation, refusal, retry, fallback and latency records, then prints A-E comparison metrics. The corpus includes public/campus/private ACL cases, stale graph provenance, graph-to-text fallback, retry and invalid-citation refusal. Recompute the aggregate values from the `raw_cases` array with `recompute_metrics()`; do not copy the printed numbers into a claim about online model quality. The report is offline functional evidence only and is not a deployment or publication certificate.
