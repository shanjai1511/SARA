"""
Crawl failure alerting for SARA.

Supported channels (configure in .env):
  Email:  ALERT_EMAIL_TO, ALERT_SMTP_HOST, ALERT_SMTP_PORT,
          ALERT_SMTP_USER, ALERT_SMTP_PASSWORD
  Slack:  ALERT_SLACK_WEBHOOK_URL

Both channels are optional — if not configured, alerting is silently skipped.
Call send_failure_alert() / send_success_alert() from crawl_runner.
"""
from __future__ import annotations

import logging
import os
import smtplib
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import requests as _requests

logger = logging.getLogger(__name__)


def _smtp_config() -> Optional[dict]:
    """Return SMTP config dict if all required vars are set, else None."""
    to_addr = os.environ.get("ALERT_EMAIL_TO", "").strip()
    host = os.environ.get("ALERT_SMTP_HOST", "").strip()
    user = os.environ.get("ALERT_SMTP_USER", "").strip()
    password = os.environ.get("ALERT_SMTP_PASSWORD", "").strip()
    if not (to_addr and host and user and password):
        return None
    return {
        "to": to_addr,
        "from": os.environ.get("ALERT_EMAIL_FROM", user),
        "host": host,
        "port": int(os.environ.get("ALERT_SMTP_PORT", "587")),
        "user": user,
        "password": password,
    }


def _slack_webhook() -> Optional[str]:
    url = os.environ.get("ALERT_SLACK_WEBHOOK_URL", "").strip()
    return url or None


def _send_email(subject: str, body: str) -> None:
    cfg = _smtp_config()
    if not cfg:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from"]
    msg["To"] = cfg["to"]
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(cfg["user"], cfg["password"])
            smtp.sendmail(cfg["from"], cfg["to"], msg.as_string())
        logger.info("Alert email sent to %s: %s", cfg["to"], subject)
    except Exception as e:
        logger.warning("Alert email failed: %s", e)


def _send_slack(text: str) -> None:
    webhook = _slack_webhook()
    if not webhook:
        return
    try:
        resp = _requests.post(webhook, json={"text": text}, timeout=10)
        if resp.status_code != 200:
            logger.warning("Slack alert returned %d: %s", resp.status_code, resp.text[:200])
        else:
            logger.info("Slack alert sent")
    except Exception as e:
        logger.warning("Slack alert failed: %s", e)


def send_failure_alert(
    project: str,
    site: str,
    schedule_id: str,
    stage: str,
    error_detail: str = "",
) -> None:
    """Send failure alert via all configured channels."""
    subject = f"[SARA] Crawl FAILED — {project}/{site} (schedule {schedule_id})"
    body = (
        f"A SARA crawl has failed.\n\n"
        f"  Project:     {project}\n"
        f"  Site:        {site}\n"
        f"  Schedule ID: {schedule_id}\n"
        f"  Stage:       {stage}\n"
    )
    if error_detail:
        body += f"\nError detail:\n{error_detail}\n"

    body += (
        "\nDiagnostic commands:\n"
        f"  grep 'error' logs/pipeline.log | tail -20\n"
        f"  cat logs/crawl_status.json | python -m json.tool\n"
    )

    _send_email(subject, body)
    slack_text = (
        f":x: *SARA crawl FAILED* — `{project}/{site}` | schedule `{schedule_id}` | stage: `{stage}`"
    )
    if error_detail:
        slack_text += f"\n```{error_detail[:500]}```"
    _send_slack(slack_text)


def send_success_alert(
    project: str,
    site: str,
    schedule_id: str,
    records: int = 0,
) -> None:
    """Send success alert. Only fires if ALERT_NOTIFY_SUCCESS=true in env."""
    if os.environ.get("ALERT_NOTIFY_SUCCESS", "false").lower() != "true":
        return

    subject = f"[SARA] Crawl completed — {project}/{site} (schedule {schedule_id})"
    body = (
        f"A SARA crawl completed successfully.\n\n"
        f"  Project:     {project}\n"
        f"  Site:        {site}\n"
        f"  Schedule ID: {schedule_id}\n"
        f"  Records:     {records:,}\n"
    )
    _send_email(subject, body)
    _send_slack(
        f":white_check_mark: *SARA crawl complete* — `{project}/{site}` | "
        f"schedule `{schedule_id}` | {records:,} records"
    )
