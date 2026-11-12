# Acceptance Evidence

This ledger distinguishes reported deployment results from local checks and pending work. A running image and the current source snapshot can differ. Source manifests inventory the current files; they do not prove those files have been deployed.

## Deployment evidence

On 2026-11-07, the operator confirmed that `student001` and `admin` both logged in through the browser. The guarded recovery command separately verified `/auth/login`, `/auth/me` and each account's expected role. Passwords were entered interactively and were not retained in reports.

The read-only runtime checker returned success for liveness, infrastructure health, readiness, schema head `20260926_0011`, the UI entry and required JavaScript/CSS assets.

The operator then ran `accept_restart.py` with an explicitly named isolated test database and `--restart`. Output confirmed the database/head/embedding/account guards, Linux host networking, `unless-stopped`, passing runtime checks before restart, and `CM_RESTART_ACCEPTANCE_PASSED` after restart. This is controlled container restart recovery, not host reboot or Docker daemon recovery. The student academic profile count was zero at that time.

The operator subsequently completed `accept_student_security.py` and returned `CM_STUDENT_SECURITY_ACCEPTANCE_PASSED`. The named test database now has the reserved synthetic student profile, two courses and seven earned credits. Both existing logins/roles passed HTTP verification. The live PostgreSQL checks passed for anonymous public scope, authenticated campus scope, the personal owner, a different personal owner, and anonymous scope after personal scope on the same physical connection. HTTP checks passed own profile/credits/grades, cross-student and anonymous denial, document ownership, and anonymous public-only retrieval. These results belong to the existing deployment and its synthetic fixtures.

The operator then updated only the running API source for the audit compatibility fix and completed `accept_hitl.py`, returning `CM_HITL_ACCEPTANCE_PASSED`. Library and classroom prepare/reject/replay checks passed. Concurrent confirmation of one approval returned HTTP `200, 200` with one effect and one idempotent response. Two-owner last-resource races returned HTTP `200, 409`. Each of the four PostgreSQL races observed two blocked HTTP transactions before the controller released its transaction-scoped advisory lock. The sanitized report was retained inside the container; synthetic resources, approvals and traces remain retained. This proves the current running deployment's HITL and PostgreSQL contention behavior after the hot update, not a fresh image build.

The operator then built a fresh image from a clean staged context containing the updated source and ran its isolated HTTP smoke with `--network none`. The image returned `CM_DOCKER_IMAGE_SMOKE_PASSED`, confirming the repaired audit compatibility code is included in a clean image and that liveness/UI startup works without external services. This smoke does not prove an empty PostgreSQL migration or a live deployment using the new image, and the existing `campusmind-api` container was not replaced.

The operator then created a new database in the isolated `15432` PostgreSQL container and ran the fresh image's Alembic command against it. All migrations from the baseline through `20260926_0011` completed, and a separate query confirmed the final revision. Existing databases and containers were not deleted or changed.

## Local evidence

The shared checker passed a frontend rebuild, static validation, 187 offline tests and OpenAPI checks before the restart command was delivered. After the HITL and benchmark additions, that snapshot passed 238 tests; static architecture validation, frontend validation and manifest checks also passed. These tests block external network/database access and do not establish live PostgreSQL behavior.

The student security acceptance script passed 19 focused local fixture, rollback, target-guard and HTTP checks. Its separate live PostgreSQL results are recorded above; SQLite tests are not RLS evidence. See [deployment instructions](DEPLOYMENT.md#student-identity-and-postgresql-rls-acceptance).

The HITL acceptance script has focused offline coverage for resource isolation, atomic fixture rollback, HTTP authorization/rejection/replay, duplicate execution audit detection and race-orchestrator failure handling. SQLite tests adapt PostgreSQL-specific UUID reflection and locks; they do not prove PostgreSQL contention. The real script requires two observed blocked HTTP transactions before releasing each synthetic resource lock. `scripts/run_offline_benchmark.py` and `datasets/offline_benchmark_v1.json` now provide a fixed synthetic corpus with ACL negatives, stale graph provenance, graph-to-text fallback, retry, invalid-citation refusal, route expectations and A-E policy outputs. `reports/offline/benchmark-v1.json` contains raw per-case records; `recompute_metrics()` recomputes the reported metrics. This is deterministic/extractive offline functional evidence only.

## GitHub and model connectivity evidence

On 2026-11-12 the repository was published to `DEVM369/CampusMind`. The initial workflow exposed a runtime-checker mismatch with cache-versioned frontend URLs. Commit `e5eeb9d` repaired the checker and added regression coverage. Its [GitHub Actions run](https://github.com/DEVM369/CampusMind/actions/runs/43203146245) completed successfully with 245 offline tests, frontend and architecture validation, benchmark, OpenAPI, Docker build and isolated image HTTP smoke.

The eight deployment-mode read-only runtime checks were repeated against the Ubuntu deployment and passed. A separate real model check showed that its former Qwen endpoint was unavailable. After the owner selected DeepSeek, a real short request using the workstation's existing DeepSeek configuration returned a nonempty response from `deepseek-v4-flash`. This is a workstation connectivity check, not a completed Ubuntu provider update or an answer-quality benchmark. The new deployment helper verifies the real provider again after applying the update remotely.

The chat layout was checked in an isolated browser using mocked API responses at six desktop, tablet and mobile sizes. These checks covered suggestions, sending, citation expansion, new conversations, inline errors and layout bounds. They do not establish real model or database behavior.

The updated local checker passed 258 offline tests, frontend validation, architecture validation, the offline benchmark and OpenAPI after the DeepSeek configuration and deployment-helper changes. The new tests cover configuration precedence, credential scoping, archive traversal protection and runtime-file restoration on model verification failure.

## Pending evidence

- Applying the current DeepSeek and UI6 source changes to the Ubuntu deployment, followed by real question-and-answer acceptance.
- The offline benchmark is implemented and locally verified; a fresh rerun after future source edits remains required. Its deterministic/extractive results must not be described as online LLM quality.
- The owner chose not to add an open-source license; public display must not be described as granting reuse rights. Publishing the repository and passing CI do not constitute a signed release.
