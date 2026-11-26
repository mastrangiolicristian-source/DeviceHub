"""Link con token per il report: si aprono senza account, con scadenza.

Il token viaggia nell'indirizzo; nel database resta solo l'impronta SHA-256,
quindi un backup del database non contiene link utilizzabili.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from .config import Settings
from .store import TelemetryStore

MAX_TOKEN_CHARS = 200


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_base(settings: Settings) -> str:
    base = (settings.public_base_url or "").rstrip("/")
    if base:
        return base
    return f"http://{settings.api_host}:{settings.api_port}"


def create_link(
    settings: Settings,
    store: TelemetryStore,
    snapshot_id: int,
    hours: int,
    actor: str,
    base: str | None = None,
    max_uses: int | None = None,
) -> dict:
    plain = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=max(1, int(hours)))
    expires_at = expires.isoformat(timespec="seconds")
    limit = max(1, int(max_uses or settings.link_max_uses))
    store.create_report_token(
        _hash(plain), int(snapshot_id), expires_at, actor, limit
    )
    store.record_admin_action(actor, "report_link", str(snapshot_id), f"ore={hours}")
    # L'indirizzo configurato vince; altrimenti si usa l'host della richiesta
    # (utile dietro tunnel o proxy) e solo come ultima risorsa il loopback.
    resolved = (settings.public_base_url or "").rstrip("/")
    if not resolved:
        resolved = (base or "").rstrip("/") or public_base(settings)
    return {
        "url": f"{resolved}/r/{plain}",
        "token": plain,
        "expires_at": expires_at,
        "max_uses": limit,
    }


def resolve(store: TelemetryStore, token: str) -> dict | None:
    if not token or len(token) > MAX_TOKEN_CHARS:
        return None
    return store.report_token(_hash(token))
