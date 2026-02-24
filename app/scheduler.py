import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings

logger = logging.getLogger(__name__)
_scheduler = BackgroundScheduler()

# Consecutive ingestion failure counters per connection (in-memory, resets on success or restart)
_ingestion_failures: dict[int, int] = {}
_FAILURE_ALERT_THRESHOLD = 3


# ── Detection job ─────────────────────────────────────────────────────────────

def _detection_job():
    """
    Run anomaly detection pipeline for all active tenants × all their
    tested Stripe connections. Each connection is detected independently
    so alerts are tagged with the correct stripe_account_id.
    """
    from app.database import SessionLocal
    from app.models.stripe_connection import StripeConnection
    from app.models.tenant import Tenant
    from app.services.alert_service import run_detection_pipeline

    db = SessionLocal()
    try:
        tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
        for tenant in tenants:
            connections = (
                db.query(StripeConnection)
                .filter(
                    StripeConnection.tenant_id == tenant.id,
                    StripeConnection.stripe_account_id.isnot(None),
                )
                .all()
            )
            if not connections:
                # Fallback: run once with no account filter (legacy / untested tenants)
                try:
                    alerts = run_detection_pipeline(db, tenant.id, detection_days=1)
                    logger.info(
                        "Scheduler detection — tenant %s (%s) [no conn]: %d new alert(s)",
                        tenant.id, tenant.slug, len(alerts),
                    )
                except Exception as exc:
                    logger.exception(
                        "Detection error for tenant %s (no conn): %s", tenant.id, exc
                    )
                continue

            for conn in connections:
                try:
                    alerts = run_detection_pipeline(
                        db, tenant.id,
                        detection_days=1,
                        stripe_account_id=conn.stripe_account_id,
                    )
                    logger.info(
                        "Scheduler detection — tenant %s (%s) conn '%s': %d new alert(s)",
                        tenant.id, tenant.slug, conn.name, len(alerts),
                    )
                except Exception as exc:
                    logger.exception(
                        "Detection error for tenant %s conn '%s': %s",
                        tenant.id, conn.name, exc,
                    )
    finally:
        db.close()


# ── Ingestion job ─────────────────────────────────────────────────────────────

def _ingestion_job():
    """
    Run incremental Stripe ingestion for all active tenants × all their
    Stripe connections that have an API key.

    Only connections with both an encrypted_api_key AND a discovered
    stripe_account_id (i.e. tested at least once) are included.
    Untested connections are silently skipped — the user must hit
    "Test Connection" in the UI first.

    Runs every hour so fresh data is available when detection fires.
    """
    from app.database import SessionLocal
    from app.models.stripe_connection import StripeConnection
    from app.models.tenant import Tenant
    from app.services.ingestion.balance_ingester import run_ingestion
    from app.services.ingestion.stripe_client import StripeAuthError, StripeClientError

    db = SessionLocal()
    try:
        tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
        for tenant in tenants:
            connections = (
                db.query(StripeConnection)
                .filter(
                    StripeConnection.tenant_id == tenant.id,
                    StripeConnection.encrypted_api_key.isnot(None),
                    StripeConnection.stripe_account_id.isnot(None),
                )
                .all()
            )

            if not connections:
                logger.debug(
                    "Scheduler ingestion — tenant %s: no ready connections, skipping",
                    tenant.id,
                )
                continue

            for conn in connections:
                try:
                    result = run_ingestion(
                        db=db,
                        tenant_id=tenant.id,
                        connection=conn,
                        force_full=False,
                    )
                    logger.info(
                        "Scheduler ingestion — tenant %s (%s) conn '%s': "
                        "inserted=%d skipped=%d features=%d",
                        tenant.id, tenant.slug, conn.name,
                        result.raw_inserted,
                        result.raw_skipped,
                        result.features_written,
                    )
                    _ingestion_failures.pop(conn.id, None)  # reset on success
                except StripeAuthError as exc:
                    _ingestion_failures[conn.id] = _ingestion_failures.get(conn.id, 0) + 1
                    logger.error(
                        "Scheduler ingestion — tenant %s conn '%s': auth error: %s",
                        tenant.id, conn.name, exc,
                    )
                    if _ingestion_failures[conn.id] >= _FAILURE_ALERT_THRESHOLD:
                        logger.error(
                            "PERSISTENT AUTH FAILURE — tenant %s conn '%s' has failed %d times in a row; "
                            "check that the Stripe API key is still valid",
                            tenant.id, conn.name, _ingestion_failures[conn.id],
                        )
                except StripeClientError as exc:
                    _ingestion_failures[conn.id] = _ingestion_failures.get(conn.id, 0) + 1
                    logger.warning(
                        "Scheduler ingestion — tenant %s conn '%s': Stripe error: %s",
                        tenant.id, conn.name, exc,
                    )
                    if _ingestion_failures[conn.id] >= _FAILURE_ALERT_THRESHOLD:
                        logger.warning(
                            "PERSISTENT STRIPE ERROR — tenant %s conn '%s' has failed %d times in a row",
                            tenant.id, conn.name, _ingestion_failures[conn.id],
                        )
                except Exception as exc:
                    _ingestion_failures[conn.id] = _ingestion_failures.get(conn.id, 0) + 1
                    logger.exception(
                        "Scheduler ingestion — tenant %s conn '%s': unexpected error: %s",
                        tenant.id, conn.name, exc,
                    )
                    if _ingestion_failures[conn.id] >= _FAILURE_ALERT_THRESHOLD:
                        logger.error(
                            "PERSISTENT FAILURE — tenant %s conn '%s' has failed %d times in a row",
                            tenant.id, conn.name, _ingestion_failures[conn.id],
                        )
    finally:
        db.close()


# ── Retraining job ────────────────────────────────────────────────────────────

def _retraining_job():
    """
    Nightly job: retrain per-account Isolation Forest models for all
    Stripe connections that have >= 30 days of daily_revenue_metrics data.
    Runs at 03:00 UTC daily so fresh ingested data is available.
    """
    from app.database import SessionLocal
    from app.models.stripe_connection import StripeConnection
    from app.models.tenant import Tenant
    from app.services.detection.account_trainer import train_account_model

    db = SessionLocal()
    try:
        tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
        for tenant in tenants:
            connections = (
                db.query(StripeConnection)
                .filter(
                    StripeConnection.tenant_id == tenant.id,
                    StripeConnection.stripe_account_id.isnot(None),
                )
                .all()
            )
            for conn in connections:
                try:
                    meta = train_account_model(db, tenant.id, conn.stripe_account_id)
                    if meta:
                        logger.info(
                            "Scheduler retraining — tenant %s conn '%s': "
                            "trained on %d feature rows",
                            tenant.id, conn.name, meta.get("feature_rows", 0),
                        )
                    else:
                        logger.debug(
                            "Scheduler retraining — tenant %s conn '%s': "
                            "not enough data, skipped",
                            tenant.id, conn.name,
                        )
                except Exception as exc:
                    logger.exception(
                        "Scheduler retraining — tenant %s conn '%s': error: %s",
                        tenant.id, conn.name, exc,
                    )
    finally:
        db.close()


# ── Scheduler lifecycle ───────────────────────────────────────────────────────

def start_scheduler():
    # Ingestion: incremental pull every hour for connections with a Stripe key
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

    # Retraining: nightly at 03:00 UTC for accounts with 30+ days of data
    _scheduler.add_job(
        _retraining_job,
        trigger=CronTrigger(hour=3, minute=0),
        id="model_retraining",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started — ingestion every 1h, detection every %dh, retraining daily at 03:00 UTC",
        settings.SCHEDULER_INTERVAL_HOURS,
    )


def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
