"""
SEED DEMO -- Phase 1
====================
Populates the database with realistic Stripe-shaped simulation data.

Pipeline:
  1. Create tenants + demo users
  2. Run StripeSimulator -> list of StripeBalanceTransaction dicts
  3. Validate each dict against data_contracts/stripe_schemas.py
  4. Insert into raw_balance_transactions (idempotent -- skip duplicates)
  5. Aggregate raw -> daily_revenue_metrics (feature layer)
  6. Run anomaly detection over the last 14 days
  7. Print a structured report

Two demo tenants:
  - Acme SaaS      (profile: saas_stable, 90 days, seed=42)
  - Globex Commerce (profile: ecommerce,  90 days, seed=7)

Demo credentials (unchanged from old project):
  acme@demo.com    / demo1234  (tenant: Acme SaaS)
  globex@demo.com  / demo1234  (tenant: Globex Commerce)
  admin@demo.com   / admin1234 (admin -- sees all tenants)
"""

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Optional

# Ensure project root is on path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal, init_db
from app.models.alert import AnomalyAlert
from app.models.daily_revenue import DailyRevenueMetrics
from app.models.raw_balance_transaction import RawBalanceTransaction
from app.models.tenant import Tenant
from app.models.user import User
from app.routers.auth import hash_password
from data_contracts.stripe_schemas import (
    DISPUTE_CATEGORIES,
    REFUND_CATEGORIES,
    REVENUE_CATEGORIES,
    StripeBalanceTransaction,
)
from simulation.stripe_simulator import SCENARIOS, StripeSimulator


# -- Demo configuration --------------------------------------------------------

DEMO_USERS = {
    "acme":    {"email": "acme@demo.com",    "password": "demo1234"},
    "globex":  {"email": "globex@demo.com",  "password": "demo1234"},
    "apex":    {"email": "apex@demo.com",    "password": "demo1234"},
}

TENANT_CONFIGS = [
    {
        "name": "Acme SaaS",
        "slug": "acme",
        "stripe_account_id": "acct_acme_demo_001",
        "simulator_profile": "saas_stable",
        "simulator_seed": 42,
        "simulation_days": 90,
    },
    {
        "name": "Globex Commerce",
        "slug": "globex",
        "stripe_account_id": "acct_globex_demo_001",
        "simulator_profile": "ecommerce",
        "simulator_seed": 7,
        "simulation_days": 90,
    },
    {
        "name": "Apex Consulting",
        "slug": "apex",
        "stripe_account_id": "acct_apex_demo_001",
        "simulator_profile": "high_ticket_b2b",
        "simulator_seed": 13,
        "simulation_days": 90,
    },
]

BASE_CURRENCY = "usd"


# -- Step 1: Tenant + user creation --------------------------------------------

def ensure_tenant(db, name: str, slug: str) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
    if not tenant:
        tenant = Tenant(name=name, slug=slug)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        print(f"  [+] Created tenant: {tenant.name} (id={tenant.id})")
    else:
        print(f"  [=] Tenant exists: {tenant.name} (id={tenant.id})")
    return tenant


def ensure_user(db, email: str, password: str, tenant_id: Optional[int], is_admin: bool = False):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            hashed_password=hash_password(password),
            tenant_id=tenant_id,
            is_admin=is_admin,
        )
        db.add(user)
        db.commit()
        print(f"  [+] Created user: {email}")
    else:
        print(f"  [=] User exists:  {email}")


# -- Step 2: Raw ingestion -----------------------------------------------------

def ingest_raw_transactions(
    db,
    tenant_id: int,
    stripe_account_id: str,
    raw_dicts: list[dict],
) -> tuple[int, int]:
    """
    Validate and insert raw Stripe transaction dicts into raw_balance_transactions.

    Returns (inserted, skipped) counts.
    Idempotent: existing stripe_ids are skipped silently.
    """
    inserted = 0
    skipped = 0
    validation_errors = 0

    for raw in raw_dicts:
        # Validate against data contract
        try:
            txn = StripeBalanceTransaction.model_validate(raw)
        except Exception as exc:
            print(f"    [!] Validation error for {raw.get('id', '?')}: {exc}")
            validation_errors += 1
            continue

        # USD conversion (trivial for USD-native accounts; placeholder for multi-currency)
        if txn.currency == BASE_CURRENCY:
            usd_rate = 1.0
            amount_usd = txn.amount
            fee_usd = txn.fee
            net_usd = txn.net
        else:
            # Phase 2: fetch real FX rate. For now, skip non-USD rows.
            skipped += 1
            continue

        row = RawBalanceTransaction(
            tenant_id=tenant_id,
            stripe_account_id=stripe_account_id,
            stripe_id=txn.id,
            stripe_object=txn.object,
            amount=txn.amount,
            fee=txn.fee,
            net=txn.net,
            currency=txn.currency,
            usd_exchange_rate=usd_rate,
            amount_usd=amount_usd,
            fee_usd=fee_usd,
            net_usd=net_usd,
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
            skipped += 1

    db.commit()
    if validation_errors:
        print(f"    [!] {validation_errors} rows failed validation")
    return inserted, skipped


# -- Step 3: Feature aggregation -----------------------------------------------

def aggregate_daily_metrics(
    db,
    tenant_id: int,
    stripe_account_id: str,
    currency: str = "usd",
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> int:
    """
    Aggregate raw_balance_transactions -> daily_revenue_metrics.

    For each (tenant, account, currency, date) combination, compute:
      - gross/net/fee revenue from charge rows
      - refund totals from refund rows
      - dispute totals from dispute rows
      - composite net_balance_change

    Upserts existing rows (recomputable by design).
    Returns count of rows written.
    """
    from sqlalchemy import func, case

    # Determine date range from raw data if not specified
    if not start_date or not end_date:
        bounds = (
            db.query(
                func.min(RawBalanceTransaction.created_at),
                func.max(RawBalanceTransaction.created_at),
            )
            .filter(
                RawBalanceTransaction.tenant_id == tenant_id,
                RawBalanceTransaction.stripe_account_id == stripe_account_id,
                RawBalanceTransaction.currency == currency,
            )
            .first()
        )
        if not bounds or not bounds[0]:
            return 0
        start_date = bounds[0].date()
        end_date = bounds[1].date()

    written = 0
    current = start_date

    while current <= end_date:
        day_start = datetime(current.year, current.month, current.day, 0, 0, 0, tzinfo=timezone.utc)
        day_end = datetime(current.year, current.month, current.day, 23, 59, 59, tzinfo=timezone.utc)

        # Fetch all rows for this day
        rows = (
            db.query(RawBalanceTransaction)
            .filter(
                RawBalanceTransaction.tenant_id == tenant_id,
                RawBalanceTransaction.stripe_account_id == stripe_account_id,
                RawBalanceTransaction.currency == currency,
                RawBalanceTransaction.created_at >= day_start,
                RawBalanceTransaction.created_at <= day_end,
            )
            .all()
        )

        # Aggregate by category
        gross_revenue = 0
        total_fees = 0
        net_revenue = 0
        charge_count = 0

        refund_amount = 0
        refund_count = 0

        dispute_amount = 0
        dispute_count = 0

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

        # Derived metrics
        avg_charge_value = (gross_revenue // charge_count) if charge_count > 0 else None
        fee_rate = (total_fees / gross_revenue) if gross_revenue > 0 else None
        refund_rate = (refund_amount / gross_revenue) if gross_revenue > 0 else None
        net_balance_change = net_revenue - refund_amount - dispute_amount

        # Upsert
        existing = (
            db.query(DailyRevenueMetrics)
            .filter(
                DailyRevenueMetrics.tenant_id == tenant_id,
                DailyRevenueMetrics.stripe_account_id == stripe_account_id,
                DailyRevenueMetrics.currency == currency,
                DailyRevenueMetrics.snapshot_date == current,
            )
            .first()
        )

        if existing:
            obj = existing
        else:
            obj = DailyRevenueMetrics(
                tenant_id=tenant_id,
                stripe_account_id=stripe_account_id,
                currency=currency,
                snapshot_date=current,
            )
            db.add(obj)

        # USD columns (since we're only processing USD in Phase 1, orig == usd)
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
            written += 1
        except IntegrityError:
            db.rollback()

        current += timedelta(days=1)

    db.commit()
    return written


# -- Step 4: Detection run -----------------------------------------------------

def run_detection(db, tenant_id: int, detection_days: int = 14) -> list[AnomalyAlert]:
    """
    Run anomaly detection over the last N days of daily_revenue_metrics.
    Uses the existing alert_service pipeline (which we'll upgrade in Phase 3).
    """
    from app.services.alert_service import run_detection_pipeline
    return run_detection_pipeline(db, tenant_id, detection_days=detection_days)


# -- Reporting -----------------------------------------------------------------

def print_feature_summary(db, tenant_id: int, stripe_account_id: str, days: int = 10):
    """Print the last N days of computed daily_revenue_metrics."""
    rows = (
        db.query(DailyRevenueMetrics)
        .filter(
            DailyRevenueMetrics.tenant_id == tenant_id,
            DailyRevenueMetrics.stripe_account_id == stripe_account_id,
        )
        .order_by(DailyRevenueMetrics.snapshot_date.desc())
        .limit(days)
        .all()
    )

    print(f"\n  {'Date':<12} {'Charges':>8} {'Gross $':>12} {'Net $':>12} "
          f"{'Fee%':>6} {'Refunds':>8} {'Ref%':>6} {'Disputes':>8}")
    print("  " + "-" * 82)
    for r in reversed(rows):
        gross_usd = r.gross_revenue_usd / 100
        net_usd = r.net_revenue_usd / 100
        ref_usd = r.refund_amount_usd / 100
        disp_usd = r.dispute_amount_usd / 100
        fee_pct = f"{r.fee_rate * 100:.1f}%" if r.fee_rate else "--"
        ref_pct = f"{r.refund_rate * 100:.1f}%" if r.refund_rate else "--"
        print(
            f"  {str(r.snapshot_date):<12} "
            f"{r.charge_count:>8,} "
            f"${gross_usd:>10,.0f} "
            f"${net_usd:>10,.0f} "
            f"{fee_pct:>6} "
            f"${ref_usd:>6,.0f} "
            f"{ref_pct:>6} "
            f"${disp_usd:>6,.0f}"
        )


def print_alert_summary(alerts: list):
    if not alerts:
        print("  No alerts generated.")
        return
    print(f"\n  {'Date':<12} {'Metric':<28} {'Dir':<6} {'Method':<8} "
          f"{'Score':>7} {'Sev':<8} {'Dual'}")
    print("  " + "-" * 82)
    for a in sorted(alerts, key=lambda x: (x.snapshot_date, x.metric_name)):
        dual = "v" if a.is_dual_confirmed else ""
        print(
            f"  {str(a.snapshot_date):<12} "
            f"{a.metric_name:<28} "
            f"{a.direction:<6} "
            f"{a.detection_method.value:<8} "
            f"{a.score:>7.2f} "
            f"{a.severity.value:<8} "
            f"{dual}"
        )


# -- Main ----------------------------------------------------------------------

def main():
    print("\n" + "=" * 60)
    print("  VIGILYX -- Phase 1 Demo Seed")
    print("=" * 60)

    init_db()
    db = SessionLocal()

    try:
        # -- Admin user --------------------------------------------------------
        print("\n[Users]")
        ensure_user(db, "admin@demo.com", "admin1234", tenant_id=None, is_admin=True)

        for cfg in TENANT_CONFIGS:
            slug = cfg["slug"]
            print(f"\n{'-'*60}")
            print(f"  Tenant: {cfg['name']}  (profile: {cfg['simulator_profile']})")
            print(f"{'-'*60}")

            # -- 1. Tenant + user ----------------------------------------------
            tenant = ensure_tenant(db, cfg["name"], slug)
            user_creds = DEMO_USERS[slug]
            ensure_user(db, user_creds["email"], user_creds["password"], tenant.id)

            # -- 2. Simulate Stripe transactions -------------------------------
            print(f"\n  [Simulation] Generating {cfg['simulation_days']} days "
                  f"({cfg['simulator_profile']}) ...")
            sim = StripeSimulator(
                profile=cfg["simulator_profile"],
                seed=cfg["simulator_seed"],
                stripe_account_id=cfg["stripe_account_id"],
                start_date=date.today() - timedelta(days=cfg["simulation_days"] - 1),
            )
            scenarios = SCENARIOS.get(cfg["simulator_profile"], [])
            raw_txns = sim.generate(days=cfg["simulation_days"], anomaly_scenarios=scenarios)

            summary = sim.summary(raw_txns)
            print(f"  Generated {len(raw_txns):,} transactions:")
            for cat, stats in sorted(summary.items()):
                amount_usd = stats["total_amount"] / 100
                print(f"    {cat:<20} count={stats['count']:>6,}  total=${amount_usd:>12,.2f}")

            # -- 3. Ingest raw layer -------------------------------------------
            print(f"\n  [RAW] Inserting into raw_balance_transactions ...")
            inserted, skipped = ingest_raw_transactions(
                db, tenant.id, cfg["stripe_account_id"], raw_txns
            )
            print(f"  Inserted: {inserted:,}  |  Skipped (dup/non-USD): {skipped:,}")

            # -- 4. Aggregate feature layer ------------------------------------
            print(f"\n  [FEATURES] Aggregating daily_revenue_metrics ...")
            n_days_written = aggregate_daily_metrics(
                db, tenant.id, cfg["stripe_account_id"], currency="usd"
            )
            print(f"  Written: {n_days_written} daily rows")

            # Print last 10 days as sanity check
            print(f"\n  Last 10 days of daily_revenue_metrics:")
            print_feature_summary(db, tenant.id, cfg["stripe_account_id"], days=10)

            # -- 5. Run detection ----------------------------------------------
            print(f"\n  [DETECTION] Running anomaly detection (last 14 days) ...")
            # NOTE: alert_service currently reads from KPISnapshot (old model).
            # In Phase 3 we migrate it to read from DailyRevenueMetrics.
            # For Phase 1, we skip detection to avoid schema mismatch.
            # Uncomment the line below once Phase 3 is complete:
            # alerts = run_detection(db, tenant.id, detection_days=14)
            print("  Detection skipped (Phase 3 will wire this to the new feature table).")
            print(f"  Raw + feature layers are fully populated and ready for inspection.")

        print(f"\n{'='*60}")
        print("  Seed complete. Start the API:")
        print("    uvicorn main:app --host 127.0.0.1 --port 8000 --reload")
        print("  Start the frontend:")
        print("    cd frontend && npm run dev")
        print()
        print("  Demo credentials:")
        print("    acme@demo.com    / demo1234   (Acme SaaS — saas_stable)")
        print("    globex@demo.com  / demo1234   (Globex Commerce — ecommerce)")
        print("    apex@demo.com    / demo1234   (Apex Consulting — high_ticket_b2b)")
        print("    admin@demo.com   / admin1234  (Admin)")
        print(f"{'='*60}\n")

    finally:
        db.close()


if __name__ == "__main__":
    main()
