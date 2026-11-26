"""Invio SMS tramite un gateway HTTP generico.

Nessun fornitore cablato: si configura `DEVICEHUB_SMS_URL` con un endpoint che
accetta `POST` JSON nel formato:

    {"to": ["+39..."], "text": "...", "from": "..."}

Il token opzionale viaggia come `Authorization: Bearer ...`. Cosi' funziona con
un webhook interno o con la maggior parte dei gateway che espongono un
endpoint JSON; senza URL l'invio resta disattivato, non simulato.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .config import Settings


class SmsNotConfigured(RuntimeError):
    """Manca l'URL del gateway o un destinatario."""


class SmsDeliveryError(RuntimeError):
    """Il gateway ha rifiutato la richiesta o non ha risposto."""


def recipients_from(settings: Settings) -> list[str]:
    return [
        part.strip()
        for part in (settings.sms_to or "").split(",")
        if part.strip()
    ]


def send_sms(
    settings: Settings, text: str, recipients: list[str] | None = None
) -> list[str]:
    """Invia il testo ai destinatari indicati; ritenta sugli errori di rete."""
    if not settings.sms_url:
        raise SmsNotConfigured(
            "invio SMS non configurato: impostare DEVICEHUB_SMS_URL"
        )
    targets = recipients or recipients_from(settings)
    if not targets:
        raise SmsNotConfigured(
            "nessun destinatario SMS: impostare DEVICEHUB_SMS_TO"
        )
    payload: dict[str, object] = {"to": targets, "text": text}
    if settings.sms_from:
        payload["from"] = settings.sms_from
    headers = {"Content-Type": "application/json"}
    if settings.sms_token:
        headers["Authorization"] = f"Bearer {settings.sms_token}"
    request = urllib.request.Request(
        settings.sms_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    attempts = max(0, int(settings.sms_retries)) + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                response.read(2048)
            return targets
        except urllib.error.HTTPError as exc:
            # Un 4xx non migliora ritentando: credenziali o numero sbagliati.
            if 400 <= exc.code < 500:
                raise SmsDeliveryError(f"invio SMS non riuscito: {exc}") from exc
            last_error = exc
        except OSError as exc:
            last_error = exc
        if attempt < attempts - 1:
            time.sleep(0.4 * (2**attempt))
    raise SmsDeliveryError(f"invio SMS non riuscito: {last_error}")
