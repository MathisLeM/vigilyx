import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import alerts, auth, config, ingestion, metrics, tenants
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Vigilyx",
    description=(
        "Proactive anomaly detection for payments and business metrics. "
        "Phase 1: Stripe-aligned data architecture with simulated data. "
        "Multi-tenant, revenue-monitoring focused."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router,    prefix="/auth",    tags=["Auth"])
app.include_router(tenants.router, prefix="/tenants", tags=["Tenants"])
app.include_router(alerts.router,  prefix="/alerts",  tags=["Alerts"])
app.include_router(config.router,  prefix="/config",  tags=["Config"])
app.include_router(metrics.router,    prefix="/metrics",    tags=["Metrics"])
app.include_router(ingestion.router,  prefix="/ingestion",  tags=["Ingestion"])


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "version": "0.4.0", "phase": 3}
