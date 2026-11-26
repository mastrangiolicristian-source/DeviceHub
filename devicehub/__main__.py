"""Avvio del servizio: ingestione TCP + API HTTP nello stesso processo."""

from __future__ import annotations

import asyncio
import logging
import os

import uvicorn

from .api import create_app
from .config import Settings
from .ingest import IngestServer
from .monthly import monthly_scheduler
from .reminders import maintenance_scheduler
from .retention import retention_scheduler
from .profiles import DeviceProfile
from .store import TelemetryStore


def build_store(settings: Settings) -> TelemetryStore:
    profile = (
        DeviceProfile.from_file(settings.profile_path)
        if settings.profile_path
        else DeviceProfile("default")
    )
    logging.info("profilo dispositivo: %s", profile.name)
    return TelemetryStore(settings.db_path, profile)


def seed_admin(settings: Settings, store: TelemetryStore) -> None:
    """Primo avvio: crea l'amministratore dalle variabili d'ambiente.

    La password non ha un default: senza `DEVICEHUB_ADMIN_PASSWORD` il login
    resta disattivato e il servizio va in modalita' primo avvio, dichiarata
    nella pagina e in /health.
    """
    if store.count_users():
        return
    if not settings.admin_password:
        logging.warning(
            "Nessun utente configurato: login disattivato (modalita' primo avvio)."
            " Impostare DEVICEHUB_ADMIN_PASSWORD per attivare l'accesso."
        )
        return
    tenant_id = store.ensure_tenant(settings.admin_tenant)
    created = store.create_user(
        "admin",
        settings.admin_password,
        "admin",
        tenant_id,
        "Amministratore",
        must_change=True,
    )
    if created:
        logging.info(
            "creato utente admin per il cliente %s: cambiare la password al primo accesso",
            settings.admin_tenant,
        )


async def serve(settings: Settings | None = None) -> None:
    settings = settings or Settings.from_env()
    store = build_store(settings)
    seed_admin(settings, store)
    ingest = IngestServer(settings, store)
    await ingest.start()

    app = create_app(settings, store, ingest)
    monthly_task = None
    if settings.monthly_auto:
        monthly_task = asyncio.create_task(
            monthly_scheduler(settings, app.state.monthly_job)
        )
    reminder_task = asyncio.create_task(maintenance_scheduler(settings, store))
    retention_task = None
    if (
        settings.position_retention_days > 0
        or settings.alert_retention_days > 0
    ):
        retention_task = asyncio.create_task(
            retention_scheduler(settings, store)
        )
    config = uvicorn.Config(
        app, host=settings.api_host, port=settings.api_port, log_level="info"
    )
    api = uvicorn.Server(config)

    if not settings.api_token:
        logging.warning(
            "DEVICEHUB_API_TOKEN non impostato: API in ascolto su %s",
            settings.api_host,
        )
    if os.getenv("DEVICEHUB_SESSION_SECRET") is None:
        logging.warning(
            "DEVICEHUB_SESSION_SECRET non impostato: chiave di sessione generata ora,"
            " gli accessi decadranno al riavvio"
        )

    try:
        await asyncio.gather(ingest._server.serve_forever(), api.serve())
    finally:
        if monthly_task is not None:
            monthly_task.cancel()
        if retention_task is not None:
            retention_task.cancel()
        reminder_task.cancel()
        await ingest.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(serve())


if __name__ == "__main__":
    main()
