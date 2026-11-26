"""Promemoria manutenzione: allarme in dashboard e email per gli interventi scaduti."""

from __future__ import annotations

import asyncio
import logging

from .config import Settings
from .mailer import (
    MailDeliveryError,
    MailNotConfigured,
    send_alert,
)
from .store import TelemetryStore

LOGGER = logging.getLogger("devicehub.reminders")


def run_maintenance_reminders(
    settings: Settings, store: TelemetryStore
) -> list[dict]:
    """Apre un allarme per ogni mezzo con interventi scaduti; invia un riepilogo."""
    due = store.maintenance_due()
    created: list[dict] = []
    for item in due:
        detail = f"{item['kind']} scaduto"
        if item.get("due_date"):
            detail += f" il {item['due_date']}"
        if item.get("due_odometer_km") is not None:
            detail += f" a {item['due_odometer_km']:.0f} km"
        if store.raise_alert(item["imei"], "MAINTENANCE_DUE", "HIGH", detail, None):
            created.append(item)

    if not created or not settings.alert_emails:
        return created

    lines = [
        f"- {item.get('plate') or item['imei']}: {item['kind']} "
        f"(scadenza {item.get('due_date') or item.get('due_odometer_km')})"
        for item in created
    ]
    try:
        send_alert(
            settings,
            f"Manutenzione scaduta: {len(created)} interventi",
            "Interventi da pianificare:\n\n" + "\n".join(lines) + "\n",
        )
    except (MailNotConfigured, MailDeliveryError) as exc:
        LOGGER.warning("promemoria manutenzione non inviato: %s", exc)
    return created


async def maintenance_scheduler(
    settings: Settings, store: TelemetryStore, hours: int = 12
) -> None:
    """Controllo periodico; il primo giro parte subito."""
    while True:
        try:
            await asyncio.to_thread(run_maintenance_reminders, settings, store)
        except Exception:  # pragma: no cover - il loop non deve morire
            LOGGER.exception("errore nei promemoria manutenzione")
        await asyncio.sleep(max(1, hours) * 3600)
