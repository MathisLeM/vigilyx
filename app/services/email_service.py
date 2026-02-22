"""
Email notifier for Vigilyx anomaly alerts.

Sends via SMTP — works with Gmail, SendGrid SMTP, Mailgun, etc.
Configure via .env: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, FROM_EMAIL, APP_URL.

Alert levels
------------
HIGH            — only HIGH severity alerts
MEDIUM_AND_HIGH — MEDIUM and HIGH severity alerts
ALL             — all alerts (LOW, MEDIUM, HIGH)

Notes
-----
- Errors are caught and logged but never propagated: an email failure must
  never prevent detection results from being saved or returned.
- If SMTP_HOST is empty, all send attempts are skipped silently.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

VALID_LEVELS = {"HIGH", "MEDIUM_AND_HIGH", "ALL"}

_SEVERITY_EMOJI = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "⚪"}
_DIRECTION_LABEL = {"spike": "spike ↑", "drop": "drop ↓"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _should_notify(severity: str, level: str) -> bool:
    if level == "ALL":
        return True
    if level == "MEDIUM_AND_HIGH":
        return severity in ("MEDIUM", "HIGH")
    return severity == "HIGH"


def _smtp_configured() -> bool:
    from app.config import settings
    return bool(settings.SMTP_HOST and settings.FROM_EMAIL)


def _send_smtp(to_email: str, subject: str, html_body: str) -> None:
    from app.config import settings

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.FROM_EMAIL
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as s:
        s.ehlo()
        s.starttls()
        s.ehlo()
        if settings.SMTP_USER and settings.SMTP_PASS:
            s.login(settings.SMTP_USER, settings.SMTP_PASS)
        s.sendmail(settings.FROM_EMAIL, to_email, msg.as_string())


# ---------------------------------------------------------------------------
# Verification email
# ---------------------------------------------------------------------------


def send_verification_email(to_email: str, token: str, tenant_name: str) -> None:
    """Send a confirmation link to verify the email address."""
    from app.config import settings

    if not _smtp_configured():
        logger.warning("Email not configured — skipping verification email to %s", to_email)
        return

    verify_url = f"{settings.APP_URL}/profile?email_token={token}"

    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                max-width:560px;margin:0 auto;background:#111827;color:#f9fafb;
                border-radius:12px;overflow:hidden;">
      <div style="background:#6366f1;padding:28px 32px;">
        <h1 style="margin:0;font-size:20px;font-weight:700;color:#fff;">
          Vigilyx — Confirm your email
        </h1>
      </div>
      <div style="padding:32px;">
        <p style="margin:0 0 16px;color:#d1d5db;">
          You asked Vigilyx to send anomaly alerts to
          <strong style="color:#f9fafb;">{to_email}</strong>
          for <strong style="color:#f9fafb;">{tenant_name}</strong>.
        </p>
        <p style="margin:0 0 28px;color:#d1d5db;">
          Click the button below to confirm and activate email alerts.
        </p>
        <a href="{verify_url}"
           style="display:inline-block;padding:13px 28px;background:#6366f1;
                  color:#fff;text-decoration:none;border-radius:8px;
                  font-weight:600;font-size:15px;">
          Confirm email address
        </a>
        <p style="margin:28px 0 0;font-size:12px;color:#6b7280;">
          This link expires in 24 hours. If you didn't request this,
          you can safely ignore this email.
        </p>
      </div>
    </div>
    """
    try:
        _send_smtp(to_email, f"[Vigilyx] Confirm your email address — {tenant_name}", html)
        logger.info("Verification email sent to %s (tenant=%s)", to_email, tenant_name)
    except Exception as exc:
        logger.warning("Failed to send verification email to %s: %s", to_email, exc)
        raise


# ---------------------------------------------------------------------------
# Alert email
# ---------------------------------------------------------------------------


def _build_alert_html(alerts: list, tenant_name: str) -> str:
    n = len(alerts)
    header = f"{n} new alert{'s' if n != 1 else ''} detected — {tenant_name}"

    # Group by snapshot_date
    by_date: dict[str, list] = {}
    for a in alerts:
        d = str(a.snapshot_date)
        by_date.setdefault(d, []).append(a)

    rows_html = ""
    for snap_date in sorted(by_date):
        rows_html += f"""
        <tr>
          <td colspan="3"
              style="padding:12px 0 6px;font-size:13px;font-weight:600;
                     color:#9ca3af;border-top:1px solid #374151;">
            {snap_date}
          </td>
        </tr>"""
        for a in sorted(by_date[snap_date], key=lambda x: x.severity.value, reverse=True):
            emoji = _SEVERITY_EMOJI.get(a.severity.value, "⚪")
            direction = _DIRECTION_LABEL.get(a.direction, a.direction)
            metric = a.metric_name.replace("_", " ")
            pct = f"{a.pct_deviation:+.0f}%" if a.pct_deviation else "—"
            hint = a.hint or "—"
            rows_html += f"""
        <tr>
          <td style="padding:4px 12px 4px 0;font-size:13px;color:#f9fafb;white-space:nowrap;">
            {emoji} {metric}
          </td>
          <td style="padding:4px 12px 4px 0;font-size:13px;color:#9ca3af;white-space:nowrap;">
            {direction} {pct}
          </td>
          <td style="padding:4px 0;font-size:12px;color:#6b7280;">{hint}</td>
        </tr>"""

    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                max-width:600px;margin:0 auto;background:#111827;color:#f9fafb;
                border-radius:12px;overflow:hidden;">
      <div style="background:#6366f1;padding:24px 32px;">
        <h1 style="margin:0;font-size:18px;font-weight:700;color:#fff;">{header}</h1>
      </div>
      <div style="padding:28px 32px;">
        <table style="width:100%;border-collapse:collapse;">
          <thead>
            <tr>
              <th style="text-align:left;padding:0 12px 8px 0;font-size:11px;
                         font-weight:600;color:#6b7280;text-transform:uppercase;
                         letter-spacing:.05em;">Metric</th>
              <th style="text-align:left;padding:0 12px 8px 0;font-size:11px;
                         font-weight:600;color:#6b7280;text-transform:uppercase;
                         letter-spacing:.05em;">Change</th>
              <th style="text-align:left;padding:0 0 8px;font-size:11px;
                         font-weight:600;color:#6b7280;text-transform:uppercase;
                         letter-spacing:.05em;">Hint</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>
        <p style="margin:24px 0 0;font-size:12px;color:#6b7280;">
          Sent by <strong>Vigilyx</strong> anomaly detection.
        </p>
      </div>
    </div>
    """


# ---------------------------------------------------------------------------
# Public notify function (mirrors slack_notifier.notify_new_alerts)
# ---------------------------------------------------------------------------


def notify_new_alerts(db: "Session", tenant_id: int, new_alerts: list) -> None:
    """
    Send an email notification for newly detected alerts.

    Fetches the tenant's email config, filters by severity level, and
    sends only if the email is verified and SMTP is configured.

    Errors are caught and logged — never propagated to the caller.
    """
    if not new_alerts or not _smtp_configured():
        return

    from app.models.email_alert_config import EmailAlertConfig
    from app.models.tenant import Tenant

    cfg = (
        db.query(EmailAlertConfig)
        .filter(
            EmailAlertConfig.tenant_id == tenant_id,
            EmailAlertConfig.is_verified == True,
        )
        .first()
    )
    if not cfg:
        return

    level = cfg.alert_level or "HIGH"
    filtered = [a for a in new_alerts if _should_notify(a.severity.value, level)]
    if not filtered:
        return

    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        tenant_name = tenant.name if tenant else f"Tenant {tenant_id}"

        html = _build_alert_html(filtered, tenant_name)
        n = len(filtered)
        subject = f"[Vigilyx] {n} new alert{'s' if n != 1 else ''} — {tenant_name}"
        _send_smtp(cfg.alert_email, subject, html)

        logger.info(
            "Email alert sent — tenant=%s email=%s alerts=%d",
            tenant_id, cfg.alert_email, n,
        )
    except Exception as exc:
        logger.warning("Email alert failed for tenant %s: %s", tenant_id, exc)
