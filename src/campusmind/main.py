from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from campusmind.platform.security import AuthorizationBackendError, AuthorizationDenied

from campusmind.api.router import api_router
from campusmind.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # External systems are verified by readiness endpoints. Keeping startup
    # side-effect free allows rolling deployments during transient dependency outages.
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        description=(
            "CampusMind - enterprise Agentic GraphRAG platform for smart-campus "
            "knowledge services and governed business actions"
        ),
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AuthorizationDenied)
    async def authorization_denied(request, exc):
        return JSONResponse(status_code=403, content={"detail": "Access denied"})

    @app.exception_handler(AuthorizationBackendError)
    async def authorization_unavailable(request, exc):
        return JSONResponse(status_code=503, content={"detail": "Authorization unavailable"})

    app.include_router(api_router)

    # The production frontend lives in frontend/ and is served directly by the
    # same FastAPI process.  API routes remain unchanged.
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    frontend_dist = frontend_dir / "dist"
    frontend_public = frontend_dist if frontend_dist.is_dir() else frontend_dir
    if frontend_public.is_dir():
        app.mount("/ui", StaticFiles(directory=frontend_public, html=True), name="ui")

    @app.get("/", tags=["system"])
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "status": "running",
            "docs": "/docs",
            "ui": "/ui/",
        }

    @app.get("/health", tags=["system"])
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
