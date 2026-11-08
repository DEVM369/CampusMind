import pytest

from campusmind.platform.infrastructure import DependencyCheck
from campusmind.platform.health import SystemHealthService


@pytest.mark.asyncio
async def test_all_dependencies_healthy():
    service = SystemHealthService()
    service.checks = {
        "postgres": lambda: DependencyCheck.healthy(details={"pgvector": "0.8.6"}),
        "neo4j": lambda: DependencyCheck.healthy(),
        "redis": lambda: DependencyCheck.healthy(),
        "rustfs": lambda: DependencyCheck.healthy(),
    }
    result = await service.check_all()
    assert result.status == "healthy"
    assert set(result.components) == {"postgres", "neo4j", "redis", "rustfs"}
    assert all(item.status == "healthy" for item in result.components.values())


@pytest.mark.asyncio
async def test_one_dependency_failure_degrades_system():
    service = SystemHealthService()
    service.checks = {
        "postgres": lambda: DependencyCheck.healthy(),
        "neo4j": lambda: DependencyCheck.unhealthy("connection refused"),
        "redis": lambda: DependencyCheck.healthy(),
        "rustfs": lambda: DependencyCheck.healthy(),
    }
    result = await service.check_all()
    assert result.status == "degraded"
    assert result.components["neo4j"].status == "unhealthy"
