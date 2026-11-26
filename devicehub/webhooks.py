"""Webhook in uscita firmati, con retry sugli errori temporanei."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .config import Settings


class WebhookNotConfigured(RuntimeError):
    """Manca URL o segreto del webhook."""


class WebhookDeliveryError(RuntimeError):
    """Il destinatario non ha accettato il webhook."""


class WebhookRejected(WebhookDeliveryError):
    """4xx: configurazione o payload errati, ritentare non serve."""


def signature(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def enqueue_webhook(store, event: str, data: dict, max_pending: int = 1000) -> int:
    """Accoda l'evento; se la coda è piena va in overflow, senza perdite."""
    return store.enqueue_webhook(
        event, json.dumps(data, sort_keys=True), max_pending
    )


def flush_outbox(store, settings: Settings, limit: int = 20) -> dict:
    """Consegna gli eventi scaduti e pianifica i fallimenti."""
    if not settings.webhook_url or not settings.webhook_secret:
        raise WebhookNotConfigured("webhook non configurato")
    store.prune_webhooks(7)
    store.promote_overflow(settings.webhook_max_pending)
    delivered = 0
    failed = 0
    for row in store.due_webhooks(limit):
        try:
            send_webhook(settings, row["event"], json.loads(row["payload"]))
        except WebhookRejected as exc:
            store.webhook_failed(
                int(row["id"]), str(exc), settings.webhook_max_attempts,
                permanent=True,
            )
            failed += 1
        except WebhookDeliveryError as exc:
            store.webhook_failed(
                int(row["id"]), str(exc), settings.webhook_max_attempts
            )
            failed += 1
        else:
            store.webhook_delivered(int(row["id"]))
            delivered += 1
    return {"delivered": delivered, "failed": failed}


def send_webhook(settings: Settings, event: str, data: dict) -> int:
    """Consegna l'evento; ritorna il numero di tentativi usati."""
    if not settings.webhook_url or not settings.webhook_secret:
        raise WebhookNotConfigured(
            "webhook non configurato: impostare DEVICEHUB_WEBHOOK_URL e"
            " DEVICEHUB_WEBHOOK_SECRET"
        )
    payload = {
        "event": event,
        "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data": data,
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = signature(settings.webhook_secret, body)
    headers = {
        "Content-Type": "application/json",
        "X-DeviceHub-Event": event,
        "X-DeviceHub-Signature": f"sha256={digest}",
    }
    attempts = max(0, int(settings.webhook_retries)) + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(
            settings.webhook_url, data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                response.read(2048)
            return attempt + 1
        except urllib.error.HTTPError as exc:
            # Un 4xx non migliora ritentando: configurazione o payload errati.
            if 400 <= exc.code < 500:
                raise WebhookRejected(f"webhook rifiutato: {exc}") from exc
            last_error = exc
        except OSError as exc:
            last_error = exc
        if attempt < attempts - 1:
            time.sleep(0.3 * (2**attempt))
    raise WebhookDeliveryError(f"webhook non consegnato: {last_error}")
