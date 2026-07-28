from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.tasks import router as tasks_router
from app.api.memories import router as memories_router
from app.api.skills import router as skills_router
from app.api.projects import router as projects_router
from app.api.search import router as search_router
from app.core.config import get_settings
from app.db import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.app_env in {"development", "test"}:
        Base.metadata.create_all(bind=engine)
    settings.data_root.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )

    @app.get(f"{settings.api_prefix}/health", tags=["system"])
    def health():
        return {"status": "ok", "service": settings.app_name}

    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(admin_router, prefix=settings.api_prefix)
    app.include_router(tasks_router, prefix=settings.api_prefix)
    app.include_router(memories_router, prefix=settings.api_prefix)
    app.include_router(skills_router, prefix=settings.api_prefix)
    app.include_router(projects_router, prefix=settings.api_prefix)
    app.include_router(search_router, prefix=settings.api_prefix)
    return app


app = create_app()
