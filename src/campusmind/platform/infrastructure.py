from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from campusmind.config import Settings, get_settings

"""CampusMind infrastructure domain."""

# ---- app/infrastructure/types.py ----
@dataclass(slots=True)
class DependencyCheck:
    ok: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def healthy(cls, message: str = "ok", details: dict[str, Any] | None = None) -> "DependencyCheck":
        return cls(ok=True, message=message, details=details or {})

    @classmethod
    def unhealthy(cls, message: str, details: dict[str, Any] | None = None) -> "DependencyCheck":
        return cls(ok=False, message=message, details=details or {})

# ---- app/infrastructure/neo4j.py ----
def check_neo4j(settings: Settings | None = None) -> DependencyCheck:
    settings = settings or get_settings()
    driver = None
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=settings.infra_connect_timeout,
        )
        driver.verify_connectivity()
        with driver.session(database=settings.neo4j_database) as session:
            record = session.run("RETURN 'neo4j-ok' AS status").single()
        # The query above deliberately avoids APOC/plugins. A successful RETURN proves Cypher access.
        return DependencyCheck.healthy(details={"status": record["status"]})
    except Exception as exc:
        return DependencyCheck.unhealthy(str(exc))
    finally:
        if driver is not None:
            driver.close()

# ---- app/infrastructure/object_storage.py ----
def _client(settings: Settings):
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.rustfs_endpoint,
        aws_access_key_id=settings.rustfs_access_key,
        aws_secret_access_key=settings.rustfs_secret_key,
        region_name=settings.rustfs_region,
        config=Config(
            signature_version="s3v4",
            connect_timeout=settings.infra_connect_timeout,
            read_timeout=max(30, settings.infra_connect_timeout),
            retries={"max_attempts": 2},
            s3={"addressing_style": "path"},
        ),
    )


class RustFSObjectStorage:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = _client(self.settings)
        self.bucket = self.settings.rustfs_bucket

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            self.client.create_bucket(Bucket=self.bucket)

    def put_bytes(
        self,
        object_key: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> None:
        self.ensure_bucket()
        self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=content,
            ContentType=content_type,
            Metadata=metadata or {},
        )

    def get_bytes(self, object_key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=object_key)
        return response["Body"].read()

    def head(self, object_key: str) -> dict:
        return self.client.head_object(Bucket=self.bucket, Key=object_key)

    def delete(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_key)

    def presigned_get_url(self, object_key: str, *, expires_seconds: int = 900) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=expires_seconds,
        )


def check_rustfs(settings: Settings | None = None) -> DependencyCheck:
    settings = settings or get_settings()
    try:
        client = _client(settings)
        response = client.list_buckets()
        bucket_names = [bucket["Name"] for bucket in response.get("Buckets", [])]
        return DependencyCheck.healthy(
            details={
                "endpoint": settings.rustfs_endpoint,
                "authenticated": True,
                "buckets": bucket_names,
            }
        )
    except Exception as exc:
        return DependencyCheck.unhealthy(str(exc))

# ---- app/infrastructure/postgres.py ----
def check_postgres(settings: Settings | None = None) -> DependencyCheck:
    settings = settings or get_settings()
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(
            settings.sqlalchemy_database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": int(settings.infra_connect_timeout)},
        )
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT
                          current_setting('server_version') AS pg_version,
                          COALESCE((SELECT extversion FROM pg_extension WHERE extname='vector'), 'missing') AS vector_version,
                          COALESCE((SELECT extversion FROM pg_extension WHERE extname='pg_trgm'), 'missing') AS pg_trgm_version
                        """
                    )
                ).mappings().one()
            if row["vector_version"] == "missing":
                return DependencyCheck.unhealthy("PostgreSQL reachable but pgvector is missing")
            return DependencyCheck.healthy(
                details={
                    "postgresql": row["pg_version"],
                    "pgvector": row["vector_version"],
                    "pg_trgm": row["pg_trgm_version"],
                }
            )
        finally:
            engine.dispose()
    except Exception as exc:  # diagnostic endpoint: preserve useful error text
        return DependencyCheck.unhealthy(str(exc))

# ---- app/infrastructure/redis_store.py ----
def check_redis(settings: Settings | None = None) -> DependencyCheck:
    settings = settings or get_settings()
    client = None
    try:
        import redis

        client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            db=settings.redis_db,
            socket_connect_timeout=settings.infra_connect_timeout,
            socket_timeout=settings.infra_connect_timeout,
            decode_responses=True,
        )
        if client.ping() is not True:
            return DependencyCheck.unhealthy("Redis PING did not return PONG")
        info = client.info(section="server")
        return DependencyCheck.healthy(details={"redis_version": info.get("redis_version", "unknown")})
    except Exception as exc:
        return DependencyCheck.unhealthy(str(exc))
    finally:
        if client is not None:
            client.close()
