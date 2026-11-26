"""Retention delle posizioni: elimina a lotti lo storico oltre N giorni.

La scelta e' dell'operatore (`DEVICEHUB_POSITION_RETENTION_DAYS`): con 0 il
job non parte e lo storico resta completo. I report mensili gia' chiusi sono
payload indipendenti dalle posizioni, quindi restano verificabili.
"""

from __future__ import annotations

import asyncio
import logging

from .config import Settings
from .store import TelemetryStore

LOGGER = logging.getLogger("devicehub.retention")


def run_retention(settings: Settings, store: TelemetryStore) -> int:
    removed = store.prune_positions(settings.position_retention_days)
    if removed:
        LOGGER.info(
            "retention: eliminate %d posizioni oltre %d giorni",
            removed,
            settings.position_retention_days,
        )
    alerts = store.prune_alerts(settings.alert_retention_days)
    if alerts:
        LOGGER.info(
            "retention: eliminati %d allarmi oltre %d giorni",
            alerts,
            settings.alert_retention_days,
        )
    return removed + alerts


async def retention_scheduler(
    settings: Settings, store: TelemetryStore, hours: int = 24
) -> None:
    """Un giro all'avvio, poi uno al giorno."""
    if (
        settings.position_retention_days <= 0
        and settings.alert_retention_days <= 0
    ):
        return
    while True:
        try:
            await asyncio.to_thread(run_retention, settings, store)
        except Exception:  # pragma: no cover - il loop non deve morire
            LOGGER.exception("retention delle posizioni non riuscita")
        await asyncio.sleep(max(1, hours) * 3600)
