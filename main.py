import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import _WEAK_SECRET, settings
from app.database import init_db
from app.limiter import limiter
from app.routers import alerts, auth, config, ingestion, invitations, metrics, tenants
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def _validate_production_settings() -> None:
    """Crash at startup if critical secrets are still set to defaults."""
    errors = []
    if settings.SECRET_KEY == _WEAK_SECRET:
        errors.append("SECRET_KEY is still the default placeholder — set a strong random value")
    if not settings.FERNET_KEY:
        errors.append("FERNET_KEY is not set — required for encrypting Stripe/Slack credentials")
    if errors:
        msg = "\n  - ".join(["Production startup failed:"] + errors)
        raise RuntimeError(msg)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.is_production:
        _validate_production_settings()
        logger.info("Production mode — strict security checks passed")
    else:
        logger.info("Development mode (ENVIRONMENT=%s)", settings.ENVIRONMENT)
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


# Disable interactive docs in production — they expose the full API surface
_docs_url    = None if settings.is_production else "/docs"
_redoc_url   = None if settings.is_production else "/redoc"
_openapi_url = None if settings.is_production else "/openapi.json"

app = FastAPI(
    title="Vigilyx",
    description="Proactive Stripe revenue anomaly detection. Multi-tenant.",
    version="0.5.0",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — origins configured via ALLOWED_ORIGINS env var (comma-separated)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router,        prefix="/auth",        tags=["Auth"])
app.include_router(tenants.router,     prefix="/tenants",     tags=["Tenants"])
app.include_router(alerts.router,      prefix="/alerts",      tags=["Alerts"])
app.include_router(config.router,      prefix="/config",      tags=["Config"])
app.include_router(metrics.router,     prefix="/metrics",     tags=["Metrics"])
app.include_router(invitations.router, prefix="/invitations", tags=["Invitations"])
app.include_router(ingestion.router, prefix="/ingestion", tags=["Ingestion"])


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "version": "0.5.0"}
