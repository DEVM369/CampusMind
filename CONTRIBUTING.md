# Contributing

Use Python 3.12 and Node.js 22. Install `requirements-dev.txt` and run `npm ci --prefix frontend` from the repository root. Keep credentials in ignored local environment files. Use synthetic data in tests and examples.

Run `python scripts/check_project.py --build-frontend` before proposing a change. With Docker available, add `--docker-image campusmind-api:check` to verify image packaging and HTTP startup in an isolated network. Checks never require online models. Database and concurrency acceptance require a dedicated test environment and separate evidence.

Keep changes within the existing domain modules. Add focused tests for behavior or security changes. Do not modify frozen historical migrations or baseline SQL; create a new migration for schema changes. Review authorization, evidence provenance and approval requirements when touching retrieval or actions.

Update deployment or API documentation when behavior changes. Run `python scripts/build_manifest.py` after final edits, then `python scripts/build_manifest.py --check`. Inventories describe bytes in the development snapshot; they do not certify a release.

Do not include local environment files, passwords, session cookies, database exports, private reports or workstation paths in contributions. This snapshot intentionally has no open-source license; public display does not grant permission to reuse, modify or redistribute the code. Add an explicit license before inviting external reuse or contributions.
