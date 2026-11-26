"""Composizione e consegna delle notifiche di allarme.

Email, SMS e voce condividono qui il contesto del messaggio e l'outbox
persistente. In demo `local_preview` e `simulated` non generano traffico
verso l'esterno: il messaggio resta visibile nella scheda SOC.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import Settings
from .mailer import (
    MailDeliveryError,
    MailNotConfigured,
    alert_recipients_from,
    send_alert,
)
from .sms import SmsDeliveryError, SmsNotConfigured, send_sms

ALERT_LABELS = {
    "SOS": "SOS",
    "IGNITION_OUT_OF_HOURS": "Accensione fuori orario",
    "JAMMING": "Jamming GPS/GSM",
    "UNPLUG": "Taglio alimentazione",
    "THEFT": "Movimento a motore spento",
    "FUEL_THEFT": "Calo carburante",
    "SPEED": "Velocità",
    "GEOFENCE_ENTER": "Ingresso cantiere",
    "GEOFENCE_EXIT": "Uscita cantiere",
    "GEOFENCE_CROSS": "Attraversamento confine",
    "HARSH_ACCEL": "Accelerazione brusca",
    "HARSH_BRAKE": "Frenata brusca",
    "SAFETY": "Non conformità sicurezza",
    "MAINTENANCE_DUE": "Manutenzione scaduta",
}

# La voce e' riservata alle emergenze: un geofence o una velocita' eccessiva
# restano su dashboard, email e SMS.
VOICE_CRITICAL_KINDS = {"SOS", "JAMMING", "UNPLUG", "THEFT", "FUEL_THEFT"}

DEFAULT_SMS_TEMPLATE = (
    "[{{app_name}} ALERT] Evento critico sul mezzo {{plate}} "
    "({{alarm_type}}) alle {{time}}. Posizione: {{maps_link}}"
)
DEFAULT_VOICE_TEMPLATE = (
    "Attenzione. Qui centrale operativa {{app_name}}. È stato rilevato un "
    "allarme critico di tipo {{alarm_type}} sul veicolo targato {{plate}}. "
    "Verificare immediatamente la posizione sulla piattaforma."
)


def _render(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = re.sub(r"{{\s*" + re.escape(key) + r"\s*}}", value, rendered)
    # Un segnaposto sconosciuto non deve finire in un messaggio operativo.
    return re.sub(r"{{\s*[a-zA-Z0-9_]+\s*}}", "", rendered).strip()


def alert_label(kind: str) -> str:
    return ALERT_LABELS.get(kind, kind.replace("_", " ").title())


def maps_link(latitude: float | None, longitude: float | None) -> str:
    if latitude is None or longitude is None:
        return ""
    return f"https://www.google.com/maps?q={latitude:.5f},{longitude:.5f}"


def alert_context(
    store,
    settings: Settings,
    imei: str,
    kinds: list[str],
    latitude: float | None,
    longitude: float | None,
    ts_ms: int,
) -> dict[str, str]:
    device = store.device(imei) or {}
    plate = str(device.get("plate") or imei)
    try:
        moment = datetime.fromtimestamp(ts_ms / 1000, ZoneInfo("Europe/Rome"))
    except (OSError, OverflowError, ValueError):
        moment = datetime.fromtimestamp(ts_ms / 1000, timezone.utc)
    return {
        "app_name": settings.app_name or settings.company,
        "plate": plate,
        "imei": imei,
        "alarm_type": ", ".join(alert_label(kind) for kind in kinds),
        "time": moment.strftime("%d/%m/%Y %H:%M"),
        "maps_link": maps_link(latitude, longitude)
        or "non disponibile (modalita' privacy)",
        "latitude": "" if latitude is None else f"{latitude:.5f}",
        "longitude": "" if longitude is None else f"{longitude:.5f}",
    }


def _targets(store, settings: Settings, imei: str, channel: str) -> list[str]:
    """Destinatari del cliente, fallback globale e, in demo, il sink locale."""
    resolved = store.notification_targets(imei)
    if channel == "email":
        raw = resolved["emails"] or settings.alert_emails
        return [part.strip() for part in (raw or "").split(",") if part.strip()]
    raw = resolved["phones"] or settings.sms_to
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def _record(
    store,
    settings: Settings,
    imei: str,
    channel: str,
    provider: str,
    mode: str,
    recipients: list[str],
    subject: str | None,
    body: str,
    status: str,
    detail: str | None = None,
) -> None:
    store.record_notification_outbox(
        imei=imei,
        channel=channel,
        provider=provider,
        mode=mode,
        recipients=", ".join(recipients),
        subject=subject,
        body=body,
        status=status,
        detail=detail,
    )


def dispatch_email(
    store,
    settings: Settings,
    imei: str,
    kinds: list[str],
    details: list[dict],
    latitude: float,
    longitude: float,
    ts_ms: int,
) -> dict | None:
    if not settings.smtp_enabled or not kinds:
        return None
    allowed = [
        kind
        for kind in kinds
        if store.can_dispatch(
            imei, kind, "email", settings.alert_cooldown_minutes
        )
    ]
    if not allowed:
        return None
    recipients = _targets(store, settings, imei, "email")
    if not recipients:
        recipients = alert_recipients_from(settings)
    if not recipients:
        return None
    context = alert_context(store, settings, imei, allowed, latitude, longitude, ts_ms)
    subject = f"Allarme {', '.join(allowed)} - {context['plate']} ({imei})"
    body = (
        f"Mezzo: {context['plate']} ({imei})\n"
        f"Allarmi: {', '.join(alert_label(kind) for kind in allowed)}\n"
        f"Posizione: {latitude:.5f}, {longitude:.5f}\n"
        f"Mappa: {context['maps_link']}\n"
        f"Ora: {context['time']}\n"
        + "".join(
            f"Dettaglio: {alert_label(item['kind'])} - {item['detail']}\n"
            for item in details
            if item.get("kind") in allowed
        )
    )
    status = "sent"
    detail = None
    try:
        send_alert(settings, subject, body, recipients)
    except (MailNotConfigured, MailDeliveryError) as exc:
        if settings.smtp_mode in ("local_preview", "preview", "simulated"):
            status = "preview"
            detail = str(exc)
        else:
            status = "failed"
            detail = str(exc)
    _record(
        store,
        settings,
        imei,
        "email",
        "smtp-local" if settings.smtp_mode == "local_preview" else "smtp",
        settings.smtp_mode,
        recipients,
        subject,
        body,
        status,
        detail,
    )
    # Anche l'anteprima locale e' una consegna registrata: come per SMS e voce
    # simulati, il cooldown deve valere, altrimenti l'outbox si riempie a ogni
    # record dello stesso allarme.
    if status in ("sent", "preview"):
        for kind in allowed:
            store.mark_dispatched(imei, kind, "email")
    return {"channel": "email", "status": status, "kinds": allowed}


def dispatch_sms(
    store,
    settings: Settings,
    imei: str,
    kinds: list[str],
    latitude: float,
    longitude: float,
    ts_ms: int,
) -> dict | None:
    if not settings.sms_enabled or not kinds:
        return None
    allowed = [
        kind
        for kind in kinds
        if store.can_dispatch(imei, kind, "sms", settings.alert_cooldown_minutes)
    ]
    if not allowed:
        return None
    simulated = settings.sms_mode in ("simulated", "preview")
    recipients = _targets(store, settings, imei, "sms")
    if not recipients and simulated and settings.demo_mode:
        recipients = ["demo (simulato)"]
    if not recipients:
        return None
    context = alert_context(store, settings, imei, allowed, latitude, longitude, ts_ms)
    body = _render(settings.sms_template_critical or DEFAULT_SMS_TEMPLATE, context)
    provider = settings.sms_provider or "gateway"
    status = "simulated" if simulated else "sent"
    detail = None
    if not simulated:
        try:
            send_sms(settings, body, recipients)
        except (SmsNotConfigured, SmsDeliveryError) as exc:
            status = "failed"
            detail = str(exc)
    _record(
        store,
        settings,
        imei,
        "sms",
        provider,
        settings.sms_mode,
        recipients,
        None,
        body,
        status,
        detail,
    )
    if status in ("sent", "simulated"):
        for kind in allowed:
            store.mark_dispatched(imei, kind, "sms")
    return {"channel": "sms", "status": status, "kinds": allowed}


def dispatch_voice(
    store,
    settings: Settings,
    imei: str,
    kinds: list[str],
    latitude: float,
    longitude: float,
    ts_ms: int,
) -> dict | None:
    if not settings.voice_enabled:
        return None
    critical = [kind for kind in kinds if kind in VOICE_CRITICAL_KINDS]
    if not critical:
        return None
    allowed = [
        kind
        for kind in critical
        if store.can_dispatch(imei, kind, "voice", settings.alert_cooldown_minutes)
    ]
    if not allowed:
        return None
    simulated = settings.voice_mode in ("simulated", "preview")
    recipients = _targets(store, settings, imei, "sms")
    if not recipients and simulated and settings.demo_mode:
        recipients = ["demo (simulato)"]
    if not recipients:
        return None
    context = alert_context(store, settings, imei, allowed, latitude, longitude, ts_ms)
    context["voice_language"] = settings.voice_language
    body = _render(settings.voice_tts_template or DEFAULT_VOICE_TEMPLATE, context)
    status = "simulated" if simulated else "failed"
    detail = None
    if not simulated:
        detail = (
            "adattatore vocale live non incluso: usare VOICE_MODE=simulated "
            "oppure integrare il provider nel modulo notifications"
        )
    _record(
        store,
        settings,
        imei,
        "voice",
        settings.voice_provider or settings.voice_mode,
        settings.voice_mode,
        recipients,
        None,
        body,
        status,
        detail,
    )
    if status == "simulated":
        for kind in allowed:
            store.mark_dispatched(imei, kind, "voice")
    return {"channel": "voice", "status": status, "kinds": allowed}
