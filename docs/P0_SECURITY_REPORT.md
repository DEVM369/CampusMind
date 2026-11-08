# Security Validation Scope

This document describes security controls and the evidence needed to validate them. It is not a production certification. See [SECURITY.md](SECURITY.md) for the trust model and [DEPLOYMENT.md](DEPLOYMENT.md) for operating instructions.

## Controls

- HTTP identity comes from an authenticated session. Client-supplied actor IDs must match that identity. A user cannot select another identity in the UI.
- Passwords use scrypt. Interactive recovery revokes the account's existing sessions atomically. Missing-login creation is explicitly limited to a named test database at migration head `20260926_0011`.
- RBAC checks guard tools, administration, ingestion and approvals. Backend authorization failures fail closed.
- Document authorization covers metadata, chunks, versions, source downloads and updates. Knowledge ACL is applied before evidence can be used.
- PostgreSQL transactions switch to a restricted runtime role. The role and forced chunk RLS policy are checked before protected operations proceed.
- Graph relationships require active, readable PostgreSQL source evidence. Stale or inaccessible provenance cannot become an answer citation.
- Classroom and library writes require prepare, an explicit owner approval, and execution-time authorization and availability checks. Locks and uniqueness constraints protect replay and inventory races.

## Evidence Boundaries

The offline suite covers session identity, actor spoofing, document authorization, role mapping, password recovery and approval invariants using controlled local fixtures. The runner blocks external sockets and non-SQLite database connections. Passing these tests does not prove PostgreSQL RLS or database concurrency.

The network-isolated Docker smoke proves API startup and bundled UI assets. The read-only runtime checker verifies liveness, infrastructure status and the expected schema version. Neither checker authenticates users or writes business records.

Deployment acceptance must separately retain sanitized results for browser login and roles, ownership of student data, anonymous knowledge ACL, PostgreSQL runtime-role/RLS checks, approval ownership, replay, concurrent last-copy requests and restart recovery. Record the tested snapshot and environment, and distinguish newly executed checks from historical reports.

## Before Public Distribution

Review the exact source inventory for credentials and private data; rebuild the frontend and image; migrate an empty isolated database to `20260926_0011`; run PostgreSQL integration acceptance; reproduce offline evaluation; and obtain a real CI run. The owner has chosen to publish this snapshot without an open-source license, so do not describe it as reusable or commercially licensed. Regenerate manifests only after final source edits. Do not include local audit archives or raw service diagnostics in the public package.

Deterministic embeddings and extractive answers are suitable for offline functional evaluation. They are not evidence of online language-model answer quality.
