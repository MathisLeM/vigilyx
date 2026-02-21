"""
ALERT SERVICE — Phase 3
=========================
Orchestrates the full anomaly detection pipeline:

  1. Load DailyRevenueMetrics from the FEATURE layer as a DataFrame
     (replaces the Phase 1 kpi_service stub).
  2. Run MADDetector + ZScoreDetector on each of the 9 Stripe-aligned metrics.
  3. Flag dual-confirmed alerts (both methods agree = higher confidence).
  4. Compute severity from % deviation off the rolling median baseline.
  5. Persist new AnomalyAlert rows (idempotent — dedup on unique constraint).

Metrics monitored (all USD, dollars not cents):
  net_revenue_usd       — what lands in the balance after fees
  gross_revenue_usd     — what customers paid pre-fee
  charge_count          — number of successful charges
  avg_charge_value_usd  — average ticket size
  fee_rate              — Stripe fee as fraction of gross (0.0–1.0)
  refund_amount_usd     — total refunds issued
  refund_rate           — refund_amount / gross_revenue (0.0–1.0)
  dispute_amount_usd    — total dispute / chargeback amounts
  net_balance_change_usd — net_revenue - refunds - disputes
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.alert import AnomalyAlert, AlertSeverity, DetectionMethod
from app.models.daily_revenue import DailyRevenueMetrics
from app.services.detection.mad_detector import MADDetector
from app.services.detection.zscore_detector import ZScoreDetector

# ── Metrics that the detection pipeline monitors ──────────────────────────────

DETECTION_METRICS = [
    "net_revenue_usd",
    "gross_revenue_usd",
    "charge_count",
    "avg_charge_value_usd",
    "fee_rate",
    "refund_amount_usd",
    "refund_rate",
    "dispute_amount_usd",
    "net_balance_change_usd",
]

# ── Root-cause hints ──────────────────────────────────────────────────────────

HINT_MAP: dict[tuple[str, str], str] = {
    ("net_revenue_usd", "spike"): (
        "Net revenue spike detected. Check for large one-time payments, new enterprise "
        "deals, or bulk charges that may indicate a billing error."
    ),
    ("net_revenue_usd", "drop"): (
        "Net revenue drop detected. Investigate payment failures, gateway outages, "
        "subscription cancellations, or a seasonal drop-off."
    ),
    ("gross_revenue_usd", "spike"): (
        "Gross revenue spike. Review large one-off charges, pricing changes, or "
        "unexpected billing runs. Check if fees are proportional."
    ),
    ("gross_revenue_usd", "drop"): (
        "Gross revenue dropped. Investigate checkout conversion, gateway errors, "
        "and whether any coupons or discounts were applied in bulk."
    ),
    ("charge_count", "spike"): (
        "Unusually high transaction volume. Verify for bot activity, retry storms, "
        "or a successful marketing campaign driving volume."
    ),
    ("charge_count", "drop"): (
        "Transaction count dropped significantly. Check checkout funnel conversion, "
        "payment gateway errors, and API health."
    ),
    ("avg_charge_value_usd", "spike"): (
        "Average ticket size increased. Review product mix changes, upsell activity, "
        "or unusually large one-off payments."
    ),
    ("avg_charge_value_usd", "drop"): (
        "Average ticket size fell. Check for discount abuse, plan downgrades, "
        "or a shift toward lower-value products."
    ),
    ("fee_rate", "spike"): (
        "Stripe fee rate is abnormally high. Check for unusual card types (international, "
        "corporate), manually-keyed transactions, or a pricing plan change."
    ),
    ("fee_rate", "drop"): (
        "Stripe fee rate dropped — likely positive. Could indicate a shift to lower-cost "
        "card types or a negotiated rate taking effect."
    ),
    ("refund_amount_usd", "spike"): (
        "High refund volume. Investigate product quality issues, billing errors, "
        "or potential fraudulent activity. Review refund reasons in Stripe."
    ),
    ("refund_amount_usd", "drop"): (
        "Refund volume is below baseline — positive signal. No immediate action required."
    ),
    ("refund_rate", "spike"): (
        "Refund rate is unusually high. Urgent: check for fraud, bulk customer complaints, "
        "product defects, or incorrect charges."
    ),
    ("refund_rate", "drop"): (
        "Refund rate is below baseline — positive signal. No immediate action required."
    ),
    ("dispute_amount_usd", "spike"): (
        "Dispute / chargeback volume spiked. Urgent: review Stripe Radar rules, "
        "check for fraud patterns, and contact Stripe support if rate exceeds 0.75%."
    ),
    ("dispute_amount_usd", "drop"): (
        "Dispute volume is below baseline — positive signal. "
        "No immediate action required."
    ),
    ("net_balance_change_usd", "spike"): (
        "Net balance change is unusually high. Verify no double-charges or "
        "unexpected bulk payments occurred."
    ),
    ("net_balance_change_usd", "drop"): (
        "Net balance change dropped sharply. Could indicate elevated refunds/disputes "
        "combined with a revenue dip. Review all three components."
    ),
}


def _get_hint(metric_name: str, direction: str) -> str:
    return HINT_MAP.get(
        (metric_name, direction),
        f"Unusual {direction} detected in {metric_name}. Review recent activity.",
    )


# ── DataFrame loader ──────────────────────────────────────────────────────────

def _load_metrics_df(
    db: Session,
    tenant_id: int,
    start: date,
    end: date,
    stripe_account_id: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load DailyRevenueMetrics for a tenant into a DataFrame suitable for detection.

    Monetary values are converted from INTEGER CENTS to FLOAT DOLLARS.
    Rate values (fee_rate, refund_rate) are kept as-is (0.0–1.0).
    Returns an empty DataFrame if no data exists.
    """
    query = (
        db.query(DailyRevenueMetrics)
        .filter(
            DailyRevenueMetrics.tenant_id == tenant_id,
            DailyRevenueMetrics.snapshot_date >= start,
            DailyRevenueMetrics.snapshot_date <= end,
        )
    )
    if stripe_account_id is not None:
        query = query.filter(DailyRevenueMetrics.stripe_account_id == stripe_account_id)
    rows = query.order_by(DailyRevenueMetrics.snapshot_date.asc()).all()

    if not rows:
        return pd.DataFrame()

    records = []
    for r in rows:
        records.append({
            "snapshot_date":        r.snapshot_date,
            "net_revenue_usd":      (r.net_revenue_usd or 0) / 100,
            "gross_revenue_usd":    (r.gross_revenue_usd or 0) / 100,
            "charge_count":         float(r.charge_count or 0),
            "avg_charge_value_usd": (r.avg_charge_value_usd / 100) if r.avg_charge_value_usd else None,
            "fee_rate":             r.fee_rate,       # already 0.0–1.0
            "refund_amount_usd":    (r.refund_amount_usd or 0) / 100,
            "refund_rate":          r.refund_rate,    # already 0.0–1.0
            "dispute_amount_usd":   (r.dispute_amount_usd or 0) / 100,
            "net_balance_change_usd": (r.net_balance_change_usd or 0) / 100,
        })

    df = pd.DataFrame(records)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df = df.set_index("snapshot_date").sort_index()
    return df


# ── Detection orchestration ───────────────────────────────────────────────────

def _direction(series: pd.Series, idx, window: int) -> str:
    """Spike = above rolling median of prior history; drop = below."""
    loc = series.index.get_loc(idx)
    start = max(0, loc - window)
    history = series.iloc[start:loc]
    if len(history) == 0:
        return "spike"
    return "spike" if series[idx] > history.median() else "drop"


def _run_detectors(df: pd.DataFrame) -> list[dict]:
    """
    Run MAD + Z-score detectors on each metric column in the DataFrame.

    Returns a flat list of anomaly dicts with keys:
        snapshot_date, metric_name, metric_value,
        detection_method, score, threshold, direction, baseline_median
    """
    from app.config import settings

    detectors = [MADDetector(), ZScoreDetector()]
    results = []

    for metric in DETECTION_METRICS:
        if metric not in df.columns:
            continue

        series = df[metric].dropna().astype(float)
        if len(series) < 7:
            continue

        for detector in detectors:
            scores, baselines = detector.score(series)

            for idx in series.index:
                score_val = float(scores[idx])
                if score_val <= detector.threshold:
                    continue

                baseline_val = (
                    float(baselines[idx])
                    if baselines is not None and not np.isnan(baselines[idx])
                    else None
                )
                snap_date = idx.date() if hasattr(idx, "date") else idx

                results.append({
                    "snapshot_date":    snap_date,
                    "metric_name":      metric,
                    "metric_value":     float(series[idx]),
                    "detection_method": detector.name,
                    "score":            round(score_val, 4),
                    "threshold":        detector.threshold,
                    "direction":        _direction(series, idx, settings.ROLLING_WINDOW_DAYS),
                    "baseline_median":  baseline_val,
                })

    return results


# ── Severity ──────────────────────────────────────────────────────────────────

def _compute_severity(pct_deviation: float) -> AlertSeverity:
    if pct_deviation < 75:
        return AlertSeverity.LOW
    if pct_deviation < 200:
        return AlertSeverity.MEDIUM
    return AlertSeverity.HIGH


def _bump_severity(severity: AlertSeverity) -> AlertSeverity:
    if severity == AlertSeverity.LOW:
        return AlertSeverity.MEDIUM
    return AlertSeverity.HIGH


# ── Persistence ───────────────────────────────────────────────────────────────

def persist_alerts(
    db: Session,
    tenant_id: int,
    anomalies: list[dict],
    stripe_account_id: Optional[str] = None,
) -> list[AnomalyAlert]:
    """
    Persist anomaly dicts as AnomalyAlert rows, skipping duplicates.

    Dual-confirmation strategy:
      When both MAD and Z-score fire on the same (date, metric), we store a
      SINGLE row with detection_method=DUAL, averaged scores, and severity
      bumped one level (dual agreement = higher statistical confidence).
      Single-method alerts are stored as MAD or ZSCORE respectively.

    Dedup key: (tenant_id, stripe_account_id, snapshot_date, metric_name, detection_method).
    """
    # Group anomalies by (date, metric) to find dual-confirmed pairs
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for a in anomalies:
        by_key[(a["snapshot_date"], a["metric_name"])].append(a)

    created = []
    for key, group in by_key.items():
        methods = {g["detection_method"] for g in group}
        is_dual = "MAD" in methods and "ZSCORE" in methods

        if is_dual:
            # Pick MAD as the primary (more robust baseline)
            mad = next(g for g in group if g["detection_method"] == "MAD")
            zs  = next(g for g in group if g["detection_method"] == "ZSCORE")

            avg_score = round((mad["score"] + zs["score"]) / 2, 4)
            baseline  = mad.get("baseline_median")
            pct_deviation = (
                abs(mad["metric_value"] - baseline) / abs(baseline) * 100
                if baseline and baseline != 0 else 0.0
            )
            severity = _bump_severity(_compute_severity(pct_deviation))
            # IF gating boost: if any member of the group was flagged, boost once more
            if any(g.get("if_boost") for g in group) and severity != AlertSeverity.HIGH:
                severity = _bump_severity(severity)

            alert = AnomalyAlert(
                tenant_id=tenant_id,
                stripe_account_id=stripe_account_id,
                snapshot_date=mad["snapshot_date"],
                metric_name=mad["metric_name"],
                metric_value=mad["metric_value"],
                detection_method=DetectionMethod.DUAL,
                score=avg_score,
                threshold=mad["threshold"],
                direction=mad["direction"],
                pct_deviation=round(pct_deviation, 1),
                is_dual_confirmed=True,
                hint=_get_hint(mad["metric_name"], mad["direction"]),
                severity=severity,
            )
        else:
            # Single-method alert
            a = group[0]
            baseline = a.get("baseline_median")
            pct_deviation = (
                abs(a["metric_value"] - baseline) / abs(baseline) * 100
                if baseline and baseline != 0 else 0.0
            )
            severity = _compute_severity(pct_deviation)
            # IF gating boost: IF confirmed this anomaly, bump severity once
            if a.get("if_boost") and severity != AlertSeverity.HIGH:
                severity = _bump_severity(severity)

            alert = AnomalyAlert(
                tenant_id=tenant_id,
                stripe_account_id=stripe_account_id,
                snapshot_date=a["snapshot_date"],
                metric_name=a["metric_name"],
                metric_value=a["metric_value"],
                detection_method=DetectionMethod(a["detection_method"]),
                score=a["score"],
                threshold=a["threshold"],
                direction=a["direction"],
                pct_deviation=round(pct_deviation, 1),
                is_dual_confirmed=False,
                hint=_get_hint(a["metric_name"], a["direction"]),
                severity=severity,
            )

        db.add(alert)
        try:
            db.flush()
            created.append(alert)
        except IntegrityError:
            db.rollback()

    db.commit()
    return created


# ── Public API ────────────────────────────────────────────────────────────────

# ── Daily combo hint engine ───────────────────────────────────────────────────

_SEVERITY_ORDER = {AlertSeverity.LOW: 0, AlertSeverity.MEDIUM: 1, AlertSeverity.HIGH: 2}


def generate_combo_hint(alerts: list) -> str:
    """
    Analyse the combination of anomalies detected on a single day and return
    a contextual root-cause narrative.

    Uses a priority-ordered rule set: the first matching pattern wins.
    Falls back to a generic summary when no pattern matches.

    `alerts` can be AnomalyAlert ORM objects or any object with
    .metric_name and .direction attributes.
    """
    spiking  = {a.metric_name for a in alerts if a.direction == "spike"}
    dropping = {a.metric_name for a in alerts if a.direction == "drop"}

    # ── High-priority combos (most specific) ─────────────────────────────────

    if "refund_rate" in spiking and "dispute_amount_usd" in spiking:
        return (
            "FRAUD WAVE pattern: both refund rate and dispute volume spiked simultaneously. "
            "This combination is the strongest indicator of an active fraud attack or a severe "
            "product/service crisis. Recommended actions: (1) Enable Stripe Radar enhanced rules "
            "immediately, (2) review all chargebacks opened today, (3) contact Stripe support if "
            "dispute rate exceeds 0.75% of charges, (4) check for unusual card BINs or geographies."
        )

    if "net_revenue_usd" in dropping and "charge_count" in dropping:
        return (
            "OUTAGE / GATEWAY FAILURE pattern: revenue and transaction count dropped together — "
            "the strongest signal of a processing outage or checkout breakdown. "
            "Recommended actions: (1) check Stripe status page and API error logs, "
            "(2) verify checkout funnel end-to-end, (3) review failed payment rates in Stripe, "
            "(4) alert engineering if error rate is elevated."
        )

    if "net_revenue_usd" in spiking and "charge_count" in spiking:
        extra = ""
        if "refund_amount_usd" in spiking:
            extra = " The simultaneous refund spike is a red flag — audit for duplicate charges."
        return (
            "HIGH-VOLUME EVENT pattern: revenue and transaction count both surged. "
            "Could be a successful marketing campaign, a scheduled billing run, or an API retry storm."
            + extra +
            " Verify with the marketing/ops team and check for accidental duplicate charges in Stripe."
        )

    if "net_revenue_usd" in spiking and "refund_amount_usd" in spiking:
        return (
            "BILLING ERROR pattern: revenue and refunds both spiked on the same day. "
            "This often indicates accidental double-charges that were quickly refunded, "
            "or a bulk billing run partially reversed. Audit today's charge list in Stripe manually "
            "and cross-check with your billing system logs."
        )

    if "avg_charge_value_usd" in spiking and "net_revenue_usd" in spiking and "charge_count" not in spiking:
        return (
            "ENTERPRISE DEAL pattern: average ticket and net revenue both increased without "
            "a volume surge. This is typically a large one-off payment or a new high-value "
            "customer contract. Verify the charge is intentional, correctly attributed, and "
            "properly recognised in your accounting system."
        )

    if "avg_charge_value_usd" in dropping and "net_revenue_usd" in dropping:
        return (
            "DOWNGRADE WAVE pattern: average ticket size and net revenue both fell. "
            "This combination points to plan downgrades, bulk coupon redemption, or a shift "
            "toward lower-value customer segments. Review recent subscription changes, "
            "discount campaigns, and the product mix for this period."
        )

    if "fee_rate" in spiking and "net_revenue_usd" in dropping:
        return (
            "MARGIN SQUEEZE pattern: Stripe fee rate increased while net revenue dropped — "
            "you are paying more in fees and collecting less. Likely causes: shift toward "
            "higher-cost card types (international, corporate), more manually-keyed transactions, "
            "or a Stripe pricing change. Compare card mix this week versus baseline."
        )

    # ── Mid-priority: single-dimension combos ────────────────────────────────

    if ("refund_amount_usd" in spiking or "refund_rate" in spiking) and "net_revenue_usd" not in dropping:
        return (
            "ISOLATED REFUND SURGE: refund volume increased without a concurrent revenue drop, "
            "meaning the refunds relate to charges from prior periods. "
            "Investigate refund reasons in Stripe, check for product/service complaints filed "
            "recently, and assess whether a customer communication is warranted."
        )

    if "dispute_amount_usd" in spiking:
        return (
            "CHARGEBACK SPIKE: dispute volume increased. Even without a refund surge, rising "
            "chargebacks threaten your Stripe account health. Review the disputed charges for "
            "common patterns (product, geography, card type), strengthen evidence collection "
            "for dispute responses, and monitor your dispute rate closely."
        )

    if "net_balance_change_usd" in dropping:
        return (
            "NET BALANCE COLLAPSE: the composite daily balance change dropped sharply. "
            "This metric captures the net effect of revenue, refunds, and disputes together. "
            "Decompose by reviewing each component: check if net_revenue_usd, refund_amount_usd, "
            "and dispute_amount_usd individually show anomalies, then address the dominant driver."
        )

    if "fee_rate" in spiking or "fee_rate" in dropping:
        direction = "increased" if "fee_rate" in spiking else "decreased"
        context = (
            "higher fees may be eroding margins — check card mix and transaction types."
            if "fee_rate" in spiking
            else "lower fees may reflect a negotiated rate or a shift to lower-cost cards — generally positive."
        )
        return (
            f"FEE RATE ANOMALY: Stripe processing fee rate {direction} without a major revenue event. "
            + context.capitalize()
        )

    # ── Fallback: broad multi-metric patterns ────────────────────────────────

    if len(spiking) >= 3:
        metrics = ", ".join(sorted(spiking))
        return (
            f"BROAD SURGE: {len(spiking)} metrics spiked simultaneously ({metrics}). "
            "A wide-front surge often points to a high-volume external event — marketing campaign, "
            "seasonal peak, or an automated billing batch. Cross-reference with your event calendar "
            "and CRM, and verify no system-level issues (retries, double-processing) are involved."
        )

    if len(dropping) >= 3:
        metrics = ", ".join(sorted(dropping))
        return (
            f"BROAD DECLINE: {len(dropping)} metrics dropped simultaneously ({metrics}). "
            "A broad decline across multiple indicators is a high-priority signal. "
            "Start with infrastructure: check Stripe status, API gateway health, and checkout "
            "conversion rates. Escalate to engineering if the pattern persists into the next day."
        )

    # ── Generic fallback ─────────────────────────────────────────────────────

    affected = sorted({a.metric_name for a in alerts})
    n = len(alerts)
    dirs = []
    if spiking:
        dirs.append(f"{len(spiking)} spike(s)")
    if dropping:
        dirs.append(f"{len(dropping)} drop(s)")
    return (
        f"{n} anomal{'y' if n == 1 else 'ies'} detected ({', '.join(dirs)}) across: "
        f"{', '.join(METRIC_LABELS_SHORT.get(m, m) for m in affected)}. "
        "Review each metric individually and look for shared operational events on this date."
    )


# Short labels used in the generic fallback narrative
METRIC_LABELS_SHORT: dict[str, str] = {
    "net_revenue_usd":        "net revenue",
    "gross_revenue_usd":      "gross revenue",
    "charge_count":           "charge count",
    "avg_charge_value_usd":   "avg charge",
    "fee_rate":               "fee rate",
    "refund_amount_usd":      "refunds",
    "refund_rate":            "refund rate",
    "dispute_amount_usd":     "disputes",
    "net_balance_change_usd": "net balance",
}


def resolve_alert(db: Session, alert_id: int, tenant_id: int) -> Optional[AnomalyAlert]:
    alert = (
        db.query(AnomalyAlert)
        .filter(AnomalyAlert.id == alert_id, AnomalyAlert.tenant_id == tenant_id)
        .first()
    )
    if not alert:
        return None
    alert.is_resolved = True
    alert.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return alert


def get_alerts(
    db: Session,
    tenant_id: int,
    resolved: Optional[bool] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
    stripe_account_id: Optional[str] = None,
) -> list[AnomalyAlert]:
    query = db.query(AnomalyAlert).filter(AnomalyAlert.tenant_id == tenant_id)
    if resolved is not None:
        query = query.filter(AnomalyAlert.is_resolved == resolved)
    if start:
        query = query.filter(AnomalyAlert.snapshot_date >= start)
    if end:
        query = query.filter(AnomalyAlert.snapshot_date <= end)
    if stripe_account_id is not None:
        query = query.filter(AnomalyAlert.stripe_account_id == stripe_account_id)
    return query.order_by(
        AnomalyAlert.snapshot_date.desc(), AnomalyAlert.created_at.desc()
    ).all()


def get_alert_stats(db: Session, tenant_id: int) -> dict:
    all_alerts = db.query(AnomalyAlert).filter(AnomalyAlert.tenant_id == tenant_id).all()
    unresolved = [a for a in all_alerts if not a.is_resolved]
    by_severity = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    for a in unresolved:
        by_severity[a.severity.value] += 1
    return {
        "total": len(all_alerts),
        "unresolved": len(unresolved),
        "by_severity": by_severity,
    }


def run_detection_pipeline(
    db: Session,
    tenant_id: int,
    detection_days: int = 7,
    stripe_account_id: Optional[str] = None,
) -> list[AnomalyAlert]:
    """
    Full detection flow:
      1. Load ROLLING_WINDOW_DAYS + detection_days of DailyRevenueMetrics.
      2. Run MAD + Z-score on all 9 Stripe-aligned metrics.
      3. Filter results to the last detection_days only (context window used for baseline).
      4. Persist new alerts (with stripe_account_id), skip duplicates.
      5. Return newly created alerts.
    """
    from app.config import settings

    today = date.today()
    detection_start = today - timedelta(days=detection_days - 1)
    context_start = today - timedelta(days=settings.ROLLING_WINDOW_DAYS + detection_days)

    df = _load_metrics_df(
        db, tenant_id, start=context_start, end=today, stripe_account_id=stripe_account_id
    )
    if df.empty:
        return []

    all_anomalies = _run_detectors(df)

    # Only persist anomalies within the detection window
    # (the extra history was only used for the rolling baseline)
    filtered = [a for a in all_anomalies if a["snapshot_date"] >= detection_start]

    # Apply Isolation Forest gating (suppress false-positive LOWs, boost confirmed MEDIUMs)
    # Fails safely: if model not available or not enough history, anomalies pass through unchanged
    from app.services.detection.isolation_forest import apply_if_gating
    filtered = apply_if_gating(filtered, df, tenant_id, stripe_account_id=stripe_account_id)

    new_alerts = persist_alerts(db, tenant_id, filtered, stripe_account_id=stripe_account_id)

    # Send Slack notification if the tenant has a webhook configured
    from app.services.slack_notifier import notify_new_alerts
    notify_new_alerts(db, tenant_id, new_alerts)

    return new_alerts
