from contextlib import asynccontextmanager
import logging
import sys

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import json

from app.api.v1 import auth, commands, admin, notifications, geo
from app.api.v1 import settings as settings_router
from app.api.v1 import vehicles
from app.api.v1 import analytics
from app.config import settings
from app.services.cache import cache_get, cache_set, init_cache, close_cache
import asyncio


from app.security import decode_token
from app.config import settings

class CacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "GET" and "/api/v1/vehicles/" in request.url.path:
            # We cache expensive analytical routes
            path = request.url.path
            if "overview" in path or "analytics" in path or "statistics" in path or "history" in path or "trips" in path or "charging" in path:
                # Exclude live status
                if "/status" not in path and "/pulse" not in path:
                    
                    # Extract user_id from cookie to scope cache keys securely
                    user_id = "anonymous"
                    token = request.cookies.get("access_token")
                    # If there's no token, we do not cache user endpoints to prevent unauthenticated cache poisoning
                    if not token:
                        return await call_next(request)
                    try:
                        # decode_token securely validates signature via python-jose
                        payload = decode_token(token)
                        if payload.get("type") == "access":
                            user_id = payload.get("sub")
                            if not user_id:
                                return await call_next(request)
                        else:
                            return await call_next(request)
                    except Exception:
                        return await call_next(request)
                            
                    accept_header = request.headers.get("accept", "application/json")
                    cache_key = f"ivdrive:api:cache:{user_id}:{path}:{accept_header}"
                    if request.url.query:
                        cache_key += f"?{request.url.query}"

                        
                    cached_data = await cache_get(cache_key)
                    if cached_data:
                        # Add header to show it was cached
                        response = JSONResponse(content=cached_data)
                        response.headers["X-Cache"] = "HIT"
                        return response

                    response = await call_next(request)
                    
                    if response.status_code == 200 and response.headers.get("content-type") == "application/json":
                        # Prevent memory leaks: only cache if the body is already materialized (e.g. JSONResponse)
                        # Do not consume body_iterator for StreamingResponses.
                        if isinstance(response, JSONResponse) and hasattr(response, "body"):
                            body_bytes = response.body
                            try:
                                json_data = json.loads(body_bytes.decode())
                                await cache_set(cache_key, json_data, expire_seconds=60)
                            except Exception as e:
                                logging.error(f"Cache middleware serialization error: {e}")
                            return response
                    return response
        
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_cache()
    # So that logger.info() from app (e.g. STATISTICS_QUERY_DEBUG) appears in docker logs
    if getattr(settings, "statistics_query_debug", False):
        app_logger = logging.getLogger("app")
        app_logger.setLevel(logging.INFO)
        if not app_logger.handlers:
            h = logging.StreamHandler(sys.stderr)
            h.setLevel(logging.INFO)
            app_logger.addHandler(h)
    yield
    await close_cache()


app = FastAPI(
    title="iVDrive API",
    description="Electric vehicle monitoring API for Volkswagen Group EVs",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(CacheMiddleware)

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
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["notifications"])
app.include_router(geo.router, prefix="/api/v1/geo", tags=["geo"])


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": "Invalid request parameters", "details": exc.errors()}}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, StarletteHTTPException):
        return await http_exception_handler(request, exc)
    if isinstance(exc, RequestValidationError):
        return await validation_exception_handler(request, exc)
    logging.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred."}}
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
