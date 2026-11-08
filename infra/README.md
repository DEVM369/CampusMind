# Infrastructure Assets

`docker/Dockerfile` packages the CampusMind API. PostgreSQL, Neo4j, Redis and RustFS are external dependencies configured through environment variables.

The Linux deployment uses host networking and `--restart unless-stopped`; see [deployment instructions](../docs/DEPLOYMENT.md#ubuntu-api-container-with-external-infrastructure). Migration and seed steps are explicit. The image includes a read-only runtime checker. CI also runs an ephemeral image with `--network none` to test HTTP startup and bundled frontend assets without contacting infrastructure or models.

`postgres/schema_v1.sql` and `postgres/drop_schema_v1.sql` are retained only because Alembic revision `20260923_0001` executes those frozen baseline SQL files. New schema changes must use Alembic revisions rather than editing the baseline.
