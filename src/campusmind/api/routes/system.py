import asyncio

from fastapi import APIRouter, HTTPException, status

from campusmind.api.schemas import DatabaseSchemaStatus
from campusmind.api.schemas import SystemHealthResponse
from campusmind.platform.health import DatabaseSchemaService
from campusmind.platform.health import SystemHealthService

router = APIRouter()


@router.get("/health", response_model=SystemHealthResponse)
async def infrastructure_health() -> SystemHealthResponse:
    """Return a diagnostic result for every infrastructure baseline infrastructure dependency."""
    return await SystemHealthService().check_all()


@router.get("/readiness", response_model=SystemHealthResponse)
async def readiness() -> SystemHealthResponse:
    """Return HTTP 503 until infrastructure and the expected schema are ready."""
    result = await SystemHealthService().check_all()
    if result.status != "healthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result.model_dump(mode="json"),
        )
    try:
        schema = await asyncio.to_thread(DatabaseSchemaService().status)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database schema check unavailable",
        ) from exc
    if schema.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=schema.model_dump(mode="json"),
        )
    return result


@router.get("/database", response_model=DatabaseSchemaStatus)
def database_schema_status() -> DatabaseSchemaStatus:
    """Report baseline database schema revision, required tables and seed-data counts."""
    return DatabaseSchemaService().status()
