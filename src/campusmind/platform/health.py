from __future__ import annotations

from sqlalchemy import inspect, text
from alembic.config import Config
from alembic.script import ScriptDirectory
from pathlib import Path
from campusmind.platform.db import get_engine
from campusmind.api.schemas import DatabaseSchemaStatus
import asyncio
from time import perf_counter
from typing import Callable
from campusmind.platform.infrastructure import check_neo4j
from campusmind.platform.infrastructure import check_rustfs
from campusmind.platform.infrastructure import check_postgres
from campusmind.platform.infrastructure import check_redis
from campusmind.platform.infrastructure import DependencyCheck
from campusmind.api.schemas import ComponentHealth, SystemHealthResponse

"""CampusMind health domain."""

def _configured_alembic_heads() -> set[str]:
    """Return migration heads configured by this CampusMind checkout."""

    project_root = (
        Path(__file__).resolve().parents[3]
    )

    config_path = (
        project_root
        / "alembic.ini"
    )

    if not config_path.exists():
        return set()

    config = Config(
        str(config_path)
    )

    script = (
        ScriptDirectory
        .from_config(config)
    )

    return set(
        script.get_heads()
    )


# ---- app/services/database_schema.py ----
EXPECTED_TABLES = {
    "roles", "permissions", "role_permissions", "users", "user_roles", "auth_sessions",
    "colleges", "departments", "majors", "students", "teachers", "courses",
    "course_prerequisites", "student_courses", "teaching_assignments", "course_schedules",
    "knowledge_bases", "documents", "document_versions", "document_permissions", "document_chunks",
    "conversations", "messages", "agent_runs", "agent_steps", "tool_calls", "audit_logs",
    "evaluation_datasets", "evaluation_cases", "evaluation_results",
    "evaluation_benchmark_runs", "evaluation_case_measurements",
    "campus_action_requests", "classroom_reservations", "library_books", "library_inventory",
    "library_reservations", "library_loans",
    "research_teacher_profiles", "research_areas", "teacher_research_areas",
    "research_labs", "research_lab_memberships", "research_projects", "research_project_members",
    "research_papers", "research_paper_authors",
    "observability_traces", "observability_spans",
}


class DatabaseSchemaService:
    def status(self) -> DatabaseSchemaStatus:
        with get_engine().connect() as conn:
            tables = set(inspect(conn).get_table_names())
            missing = sorted(EXPECTED_TABLES - tables)
            revision = None
            if "alembic_version" in tables:
                revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()

            seed_counts: dict[str, int] = {}
            for table in ("users", "courses", "knowledge_bases", "document_chunks", "evaluation_cases"):
                if table in tables:
                    seed_counts[table] = int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())

            configured_heads = _configured_alembic_heads()

            healthy = (
                not missing
                and revision is not None
                and revision in configured_heads
            )
            return DatabaseSchemaStatus(
                status="ready" if healthy else "incomplete",
                revision=revision,
                table_count=len(tables),
                expected_table_count=len(EXPECTED_TABLES) + 1,
                missing_tables=missing,
                seed_counts=seed_counts,
            )

# ---- app/services/system_health.py ----
class SystemHealthService:
    checks: dict[str, Callable[[], DependencyCheck]] = {
        "postgres": check_postgres,
        "neo4j": check_neo4j,
        "redis": check_redis,
        "rustfs": check_rustfs,
    }

    @staticmethod
    async def _run_check(check: Callable[[], DependencyCheck]) -> tuple[DependencyCheck, float]:
        started = perf_counter()
        result = await asyncio.to_thread(check)
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return result, latency_ms

    async def check_all(self) -> SystemHealthResponse:
        names = list(self.checks)
        results = await asyncio.gather(*(self._run_check(self.checks[name]) for name in names))

        components: dict[str, ComponentHealth] = {}
        for name, (result, latency_ms) in zip(names, results, strict=True):
            components[name] = ComponentHealth(
                status="healthy" if result.ok else "unhealthy",
                message=result.message,
                latency_ms=latency_ms,
                details=result.details,
            )

        all_healthy = all(component.status == "healthy" for component in components.values())
        return SystemHealthResponse(
            status="healthy" if all_healthy else "degraded",
            components=components,
        )
