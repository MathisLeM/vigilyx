"""
Slack webhook notifier for Vigilyx anomaly alerts.

Called after the detection pipeline runs. Sends a formatted Slack
Block Kit message to the tenant's configured webhook when new alerts
meet the configured severity threshold.

Alert levels
------------
HIGH            — only HIGH severity alerts
MEDIUM_AND_HIGH — MEDIUM and HIGH severity alerts
ALL             — all alerts (LOW, MEDIUM, HIGH)

Notes
-----
- Errors are logged but never propagated: a Slack failure must never
  prevent detection results from being saved or returned.
- The webhook URL is stored Fernet-encrypted in tenant_configs and
  decrypted here on the fly.
"""

import logging
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_SEVERITY_EMOJI = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "⚪"}
_SEVERITY_COLOR = {"HIGH": "#ef4444", "MEDIUM": "#f59e0b", "LOW": "#6b7280"}
_DIRECTION_ARROW = {"spike": "↑", "drop": "↓"}

VALID_LEVELS = {"HIGH", "MEDIUM_AND_HIGH", "ALL"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _should_notify(severity: str, level: str) -> bool:
    if level == "ALL":
        return True
    if level == "MEDIUM_AND_HIGH":
        return severity in ("MEDIUM", "HIGH")
    return severity == "HIGH"


def _highest_severity(alerts) -> str:
    order = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
    return max(
        (a.severity.value for a in alerts),
        key=lambda s: order.get(s, 0),
        default="LOW",
    )


def _build_payload(alerts, tenant_name: str) -> dict:
    """Build a Slack Block Kit attachment payload for a batch of new alerts."""
    highest = _highest_severity(alerts)
    color = _SEVERITY_COLOR.get(highest, "#6b7280")
    n = len(alerts)

    # Group by snapshot date
    by_date: dict[str, list] = {}
    for a in alerts:
        d = str(a.snapshot_date)
        by_date.setdefault(d, []).append(a)

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Vigilyx — {n} new alert{'s' if n != 1 else ''} for {tenant_name}",
                "emoji": True,
            },
        }
    ]

    for snapshot_date in sorted(by_date):
        day_alerts = by_date[snapshot_date]
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{snapshot_date}*"},
        })

        lines = []
        for a in sorted(day_alerts, key=lambda x: x.severity.value, reverse=True):
            emoji = _SEVERITY_EMOJI.get(a.severity.value, "⚪")
            arrow = _DIRECTION_ARROW.get(a.direction, "~")
            metric = a.metric_name.replace("_", " ")
            pct = f" ({a.pct_deviation:.0f}% deviation)" if a.pct_deviation else ""
            lines.append(f"{emoji} *{metric}* {arrow}{pct}")

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        })

    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "Sent by *Vigilyx* anomaly detection"}],
    })

    return {"attachments": [{"color": color, "blocks": blocks}]}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def send_test_message(webhook_url: str, tenant_name: str) -> None:
    """Send a test Slack message to verify the webhook URL is working."""
    payload = {
        "attachments": [
            {
                "color": "#6366f1",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"✅ *Vigilyx test notification — {tenant_name}*\n\n"
                                "Slack alerts are configured correctly. "
                                "You'll receive a message here whenever anomalies are detected."
                            ),
                        },
                    }
                ],
            }
        ]
    }
    r = httpx.post(webhook_url, json=payload, timeout=8)
    r.raise_for_status()


def notify_new_alerts(db: "Session", tenant_id: int, new_alerts: list) -> None:
    """
    Send a Slack notification for newly detected alerts.

    Fetches the tenant's Slack config from the DB, filters alerts by the
    configured severity level, and posts to the webhook if any pass.

    Errors are caught and logged — never propagated to the caller.
    """
    if not new_alerts:
        return

    # Lazy imports to avoid circular import issues
    from app.models.tenant import Tenant
    from app.models.tenant_config import TenantConfig
    from app.services.crypto import decrypt_key

    cfg = (
        db.query(TenantConfig)
        .filter(TenantConfig.tenant_id == tenant_id)
        .first()
    )
    if not cfg or not cfg.slack_webhook_url:
        return

    level = cfg.slack_alert_level or "HIGH"
    filtered = [a for a in new_alerts if _should_notify(a.severity.value, level)]
    if not filtered:
        return

    try:
        webhook_url = decrypt_key(cfg.slack_webhook_url)
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        tenant_name = tenant.name if tenant else f"Tenant {tenant_id}"

        payload = _build_payload(filtered, tenant_name)
        r = httpx.post(webhook_url, json=payload, timeout=8)
        r.raise_for_status()

        logger.info(
            "Slack notification sent — tenant=%s filtered_alerts=%d",
            tenant_id,
            len(filtered),
        )
    except Exception as exc:
        logger.warning(
            "Slack notification failed for tenant %s: %s", tenant_id, exc
        )
