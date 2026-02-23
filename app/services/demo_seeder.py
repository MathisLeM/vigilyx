"""
Demo seeder service
===================
Seeds Acme-profile demo data for a freshly created tenant.
Called as a FastAPI BackgroundTask on signup so the user sees
a populated dashboard immediately after account creation.
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models.daily_revenue import DailyRevenueMetrics
from app.models.raw_balance_transaction import RawBalanceTransaction
from app.models.stripe_connection import StripeConnection
from data_contracts.stripe_schemas import (
    DISPUTE_CATEGORIES,
    REFUND_CATEGORIES,
    REVENUE_CATEGORIES,
    StripeBalanceTransaction,
)
from simulation.stripe_simulator import SCENARIOS, StripeSimulator

logger = logging.getLogger(__name__)

DEMO_STRIPE_ACCOUNT_ID = "acct_acme_demo_001"
DEMO_DAYS = 90
DEMO_PROFILE = "saas_stable"
DEMO_SEED = 42


def seed_demo_for_tenant(tenant_id: int) -> None:
    """
    Run in a BackgroundTask after signup.
    Creates demo raw transactions, daily metrics, stripe connection,
    and anomaly detection for the given tenant.
    """
    db = SessionLocal()
    try:
        logger.info("Demo seeder: starting for tenant_id=%s", tenant_id)

        # 1. Generate simulated Stripe transactions
        sim = StripeSimulator(
            profile=DEMO_PROFILE,
            seed=DEMO_SEED,
            stripe_account_id=DEMO_STRIPE_ACCOUNT_ID,
            start_date=date.today() - timedelta(days=DEMO_DAYS - 1),
        )
        scenarios = SCENARIOS.get(DEMO_PROFILE, [])
        raw_txns = sim.generate(days=DEMO_DAYS, anomaly_scenarios=scenarios)

        # 2. Insert raw transactions
        inserted = 0
        for raw in raw_txns:
            try:
                txn = StripeBalanceTransaction.model_validate(raw)
            except Exception:
                continue
            if txn.currency != "usd":
                continue

            row = RawBalanceTransaction(
                tenant_id=tenant_id,
                stripe_account_id=DEMO_STRIPE_ACCOUNT_ID,
                stripe_id=txn.id,
                stripe_object=txn.object,
                amount=txn.amount,
                fee=txn.fee,
                net=txn.net,
                currency=txn.currency,
                usd_exchange_rate=1.0,
                amount_usd=txn.amount,
                fee_usd=txn.fee,
                net_usd=txn.net,
                type=txn.type,
                reporting_category=txn.reporting_category,
                status=txn.status,
                source_id=txn.source,
                created_at=txn.created_datetime(),
                available_on=txn.available_on_datetime(),
                description=txn.description,
                fee_details_json=json.dumps([fd.model_dump() for fd in txn.fee_details]),
                metadata_json=json.dumps(txn.metadata),
                ingestion_source="simulation",
            )
            db.add(row)
            try:
                db.flush()
                inserted += 1
            except IntegrityError:
                db.rollback()

        db.commit()
        logger.info("Demo seeder: inserted %s raw transactions", inserted)

        # 3. Aggregate daily metrics
        bounds_row = db.query(
            RawBalanceTransaction.created_at
        ).filter(
            RawBalanceTransaction.tenant_id == tenant_id,
            RawBalanceTransaction.stripe_account_id == DEMO_STRIPE_ACCOUNT_ID,
        ).order_by(RawBalanceTransaction.created_at).first()

        if not bounds_row:
            return

        start_date = (date.today() - timedelta(days=DEMO_DAYS - 1))
        end_date = date.today()
        current = start_date

        while current <= end_date:
            day_start = datetime(current.year, current.month, current.day, 0, 0, 0, tzinfo=timezone.utc)
            day_end = datetime(current.year, current.month, current.day, 23, 59, 59, tzinfo=timezone.utc)

            rows = db.query(RawBalanceTransaction).filter(
                RawBalanceTransaction.tenant_id == tenant_id,
                RawBalanceTransaction.stripe_account_id == DEMO_STRIPE_ACCOUNT_ID,
                RawBalanceTransaction.created_at >= day_start,
                RawBalanceTransaction.created_at <= day_end,
            ).all()

            gross_revenue = total_fees = net_revenue = charge_count = 0
            refund_amount = refund_count = 0
            dispute_amount = dispute_count = 0

            for row in rows:
                cat = row.reporting_category
                if cat in REVENUE_CATEGORIES:
                    gross_revenue += row.amount_usd or row.amount
                    total_fees += row.fee_usd or row.fee
                    net_revenue += row.net_usd or row.net
                    charge_count += 1
                elif cat in REFUND_CATEGORIES:
                    refund_amount += abs(row.amount_usd or row.amount)
                    refund_count += 1
                elif cat in DISPUTE_CATEGORIES:
                    dispute_amount += abs(row.amount_usd or row.amount)
                    dispute_count += 1

            avg_charge_value = (gross_revenue // charge_count) if charge_count > 0 else None
            fee_rate = (total_fees / gross_revenue) if gross_revenue > 0 else None
            refund_rate = (refund_amount / gross_revenue) if gross_revenue > 0 else None
            net_balance_change = net_revenue - refund_amount - dispute_amount

            existing = db.query(DailyRevenueMetrics).filter(
                DailyRevenueMetrics.tenant_id == tenant_id,
                DailyRevenueMetrics.stripe_account_id == DEMO_STRIPE_ACCOUNT_ID,
                DailyRevenueMetrics.snapshot_date == current,
            ).first()

            obj = existing or DailyRevenueMetrics(
                tenant_id=tenant_id,
                stripe_account_id=DEMO_STRIPE_ACCOUNT_ID,
                currency="usd",
                snapshot_date=current,
            )
            if not existing:
                db.add(obj)

            obj.gross_revenue = gross_revenue
            obj.total_fees = total_fees
            obj.net_revenue = net_revenue
            obj.charge_count = charge_count
            obj.avg_charge_value = avg_charge_value
            obj.fee_rate = fee_rate
            obj.gross_revenue_usd = gross_revenue
            obj.total_fees_usd = total_fees
            obj.net_revenue_usd = net_revenue
            obj.avg_charge_value_usd = avg_charge_value
            obj.refund_amount = refund_amount
            obj.refund_count = refund_count
            obj.refund_rate = refund_rate
            obj.refund_amount_usd = refund_amount
            obj.dispute_amount = dispute_amount
            obj.dispute_count = dispute_count
            obj.dispute_amount_usd = dispute_amount
            obj.net_balance_change_usd = net_balance_change
            obj.computed_at = datetime.now(timezone.utc)

            try:
                db.flush()
            except IntegrityError:
                db.rollback()

            current += timedelta(days=1)

        db.commit()
        logger.info("Demo seeder: daily metrics aggregated")

        # 4. Create demo StripeConnection
        existing_conn = db.query(StripeConnection).filter(
            StripeConnection.tenant_id == tenant_id,
            StripeConnection.stripe_account_id == DEMO_STRIPE_ACCOUNT_ID,
        ).first()

        if not existing_conn:
            conn = StripeConnection(
                tenant_id=tenant_id,
                name="Acme SaaS (Demo)",
                encrypted_api_key=None,
                stripe_account_id=DEMO_STRIPE_ACCOUNT_ID,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(conn)
            db.commit()

        # 5. Run anomaly detection
        from app.services.alert_service import run_detection_pipeline
        alerts = run_detection_pipeline(
            db, tenant_id,
            detection_days=14,
            stripe_account_id=DEMO_STRIPE_ACCOUNT_ID,
        )
        logger.info("Demo seeder: generated %s alerts for tenant_id=%s", len(alerts), tenant_id)

    except Exception as exc:
        logger.error("Demo seeder failed for tenant_id=%s: %s", tenant_id, exc, exc_info=True)
    finally:
        db.close()
