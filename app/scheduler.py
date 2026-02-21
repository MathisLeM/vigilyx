import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings

logger = logging.getLogger(__name__)
_scheduler = BackgroundScheduler()


# ── Detection job ─────────────────────────────────────────────────────────────

def _detection_job():
    """Run anomaly detection pipeline for all active tenants."""
    from app.database import SessionLocal
    from app.models.tenant import Tenant
    from app.services.alert_service import run_detection_pipeline

    db = SessionLocal()
    try:
        tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
        for tenant in tenants:
            try:
                alerts = run_detection_pipeline(db, tenant.id, detection_days=1)
                logger.info(
                    "Scheduler detection — tenant %s (%s): %d new alert(s)",
                    tenant.id,
                    tenant.slug,
                    len(alerts),
                )
            except Exception as exc:
                logger.exception("Detection error for tenant %s: %s", tenant.id, exc)
    finally:
        db.close()


# ── Ingestion job ─────────────────────────────────────────────────────────────

def _ingestion_job():
    """
    Run incremental Stripe ingestion for all active tenants that have
    a Stripe API key configured.

    Runs every hour so fresh data is available when detection fires.
    Tenants without a configured key are silently skipped.
    """
    from app.database import SessionLocal
    from app.models.tenant import Tenant
    from app.models.tenant_config import TenantConfig
    from app.services.ingestion.balance_ingester import (
        DEFAULT_ACCOUNT_ID,
        run_ingestion,
    )
    from app.services.ingestion.stripe_client import StripeAuthError, StripeClientError

    db = SessionLocal()
    try:
        tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
        for tenant in tenants:
            cfg = (
                db.query(TenantConfig)
                .filter(TenantConfig.tenant_id == tenant.id)
                .first()
            )
            if not cfg or not cfg.stripe_api_key:
                logger.debug(
                    "Scheduler ingestion — tenant %s: no Stripe key, skipping",
                    tenant.id,
                )
                continue

            try:
                result = run_ingestion(
                    db=db,
                    tenant_id=tenant.id,
                    stripe_account_id=DEFAULT_ACCOUNT_ID,
                    force_full=False,
                )
                logger.info(
                    "Scheduler ingestion — tenant %s (%s): "
                    "inserted=%d skipped=%d features=%d",
                    tenant.id,
                    tenant.slug,
                    result.raw_inserted,
                    result.raw_skipped,
                    result.features_written,
                )
            except StripeAuthError as exc:
                logger.error(
                    "Scheduler ingestion — tenant %s: auth error: %s", tenant.id, exc
                )
            except StripeClientError as exc:
                logger.warning(
                    "Scheduler ingestion — tenant %s: Stripe error: %s", tenant.id, exc
                )
            except Exception as exc:
                logger.exception(
                    "Scheduler ingestion — tenant %s: unexpected error: %s",
                    tenant.id, exc,
                )
    finally:
        db.close()


# ── Scheduler lifecycle ───────────────────────────────────────────────────────

def start_scheduler():
    # Ingestion: incremental pull every hour for tenants with a Stripe key
    _scheduler.add_job(
        _ingestion_job,
        trigger=IntervalTrigger(hours=1),
        id="stripe_ingestion",
        replace_existing=True,
        max_instances=1,
    )

    # Detection: run on configured interval (default 24 h)
    _scheduler.add_job(
        _detection_job,
        trigger=IntervalTrigger(hours=settings.SCHEDULER_INTERVAL_HOURS),
        id="kpi_detection",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started — ingestion every 1h, detection every %dh",
        settings.SCHEDULER_INTERVAL_HOURS,
    )


def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
