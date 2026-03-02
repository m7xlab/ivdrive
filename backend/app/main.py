from contextlib import asynccontextmanager
import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, commands, admin
from app.api.v1 import settings as settings_router
from app.api.v1 import vehicles
from app.api.v1 import analytics
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # So that logger.info() from app (e.g. STATISTICS_QUERY_DEBUG) appears in docker logs
    if getattr(settings, "statistics_query_debug", False):
        app_logger = logging.getLogger("app")
        app_logger.setLevel(logging.INFO)
        if not app_logger.handlers:
            h = logging.StreamHandler(sys.stderr)
            h.setLevel(logging.INFO)
            app_logger.addHandler(h)
    yield


app = FastAPI(
    title="iVDrive API",
    description="Electric vehicle monitoring API for Volkswagen Group EVs",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(vehicles.router, prefix="/api/v1/vehicles", tags=["vehicles"])
app.include_router(commands.router, prefix="/api/v1/vehicles", tags=["commands"])
app.include_router(settings_router.router, prefix="/api/v1/settings", tags=["settings"])
app.include_router(analytics.router, prefix="/api/v1/vehicles", tags=["analytics"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])


@app.get("/health")
async def health():
    return {"status": "ok"}
