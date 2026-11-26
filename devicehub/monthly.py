"""Chiusura mensile: crea lo snapshot, lo firma e (se configurato) lo invia.

Il lavoro puo' essere avviato a mano, dall'API o dal processo principale: qui
sta la logica, cosi' i tre percorsi producono lo stesso documento.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from .config import Settings
from .esg import build_report, month_window, previous_period
from .links import create_link
from .pdf import render_report_pdf
from .mailer import (
    MailDeliveryError,
    MailNotConfigured,
    recipients_from,
    send_report,
)
from .signing import fingerprint, public_pem, sign
from .store import TelemetryStore

LOGGER = logging.getLogger(__name__)


def close_month(
    settings: Settings,
    store: TelemetryStore,
    key,
    period: str | None = None,
    tenant=None,
    actor: str = "scheduler",
) -> dict:
    """Congela e firma il mese. Se esiste gia', non lo ricrea."""
    now = datetime.now(timezone.utc)
    if period is None:
        period = previous_period(now, settings.report_timezone)
    since_ms, until_ms, period = month_window(
        period, now, settings.report_timezone
    )
    report = build_report(store, settings, tenant, since_ms, until_ms)
    payload = json.dumps(
        {
            "period": period,
            "from": datetime.fromtimestamp(
                since_ms / 1000, timezone.utc
            ).isoformat(timespec="seconds"),
            "to": datetime.fromtimestamp(
                until_ms / 1000, timezone.utc
            ).isoformat(timespec="seconds"),
            **report,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    signature = sign(key, payload)
    public = public_pem(key)
    key_fp = fingerprint(public)
    tenant_key = "" if tenant is None else str(tenant)
    snapshot_id = store.save_esg_snapshot(
        period,
        tenant_key,
        payload,
        digest,
        signature,
        public,
        key_fp,
        actor,
    )
    if snapshot_id is None:
        return {"status": "exists", "period": period}
    store.record_admin_action(actor, "esg_snapshot", period, f"digest={digest[:12]}")
    return {
        "status": "created",
        "id": snapshot_id,
        "period": period,
        "digest": digest,
        "signature": signature,
        "fingerprint": key_fp,
    }


def run_monthly(
    settings: Settings,
    store: TelemetryStore,
    key,
    period: str | None = None,
    actor: str = "scheduler",
) -> dict:
    """Chiude il mese e, se l'invio e' configurato, manda il report con link."""
    result = close_month(settings, store, key, period, None, actor)
    if result["status"] != "created":
        return result
    if not settings.monthly_email:
        result["email"] = "disattivata"
        return result
    recipients = recipients_from(settings)
    if not recipients or not settings.smtp_host or not settings.report_from:
        result["email"] = "non configurata"
        return result
    link = create_link(settings, store, result["id"], settings.link_hours, actor)
    row = store.esg_snapshot(result["id"])
    snapshot = {
        "id": row["id"],
        "period": row["period"],
        "created_at": row["created_at"],
        "digest": row["digest"],
        "fingerprint": fingerprint(row["public_key"])
        if row.get("public_key")
        else None,
    }
    try:
        branding = store.tenant_branding(row["tenant_key"]) or {}
        attachment = (
            f"report-{row['period']}.pdf",
            render_report_pdf(
                settings, snapshot, json.loads(row["payload"]), branding
            ),
        )
        sent = send_report(
            settings,
            snapshot,
            recipients,
            url=link["url"],
            attachment=attachment,
            display_name=branding.get("display_name"),
        )
    except (MailNotConfigured, MailDeliveryError) as exc:
        LOGGER.warning("invio del report mensile non riuscito: %s", exc)
        result["email"] = {"error": str(exc)}
        return result
    result["email"] = {"sent": sent}
    result["link"] = link["url"]
    return result


def seconds_until_next(hour: int, now: datetime | None = None) -> float:
    """Secondi all'ora indicata (UTC) del prossimo giorno utile."""
    now = now or datetime.now(timezone.utc)
    target = now.replace(hour=max(0, min(23, hour)), minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


async def monthly_scheduler(settings: Settings, job) -> None:
    """Esegue la chiusura all'avvio (se manca) e poi ogni giorno all'ora scelta."""
    if not settings.monthly_auto:
        return
    try:
        LOGGER.info("chiusura mensile all'avvio: %s", job(None, "scheduler"))
    except Exception:
        LOGGER.exception("chiusura mensile all'avvio non riuscita")
    while True:
        wait = seconds_until_next(settings.monthly_hour)
        LOGGER.info("prossima chiusura mensile tra %.0f secondi", wait)
        await asyncio.sleep(wait)
        try:
            LOGGER.info("chiusura mensile: %s", job(None, "scheduler"))
        except Exception:
            LOGGER.exception("chiusura mensile non riuscita")
