"""Invio del report mensile per email, via SMTP.

Nessun fornitore specifico: si usano le credenziali SMTP che il cliente ha
gia' (la casella del proprio dominio o un servizio qualsiasi). Senza
`DEVICEHUB_SMTP_HOST`, `DEVICEHUB_REPORT_FROM` e un destinatario l'invio resta
disattivato e l'endpoint risponde 503: nessun invio simulato.
"""

from __future__ import annotations

import re
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from .config import Settings

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MailNotConfigured(RuntimeError):
    """Manca la configurazione SMTP o un destinatario."""


class MailDeliveryError(RuntimeError):
    """Il server SMTP ha rifiutato o non ha risposto."""


def report_url(settings: Settings, snapshot_id: int) -> str:
    base = (settings.public_base_url or "").rstrip("/")
    if not base:
        base = f"http://{settings.api_host}:{settings.api_port}"
    return f"{base}/report/{int(snapshot_id)}"


def recipients_from(settings: Settings) -> list[str]:
    return [
        part.strip()
        for part in (settings.report_recipients or "").split(",")
        if part.strip()
    ]


def alert_recipients_from(settings: Settings) -> list[str]:
    raw = settings.alert_emails or settings.report_recipients
    targets = [part.strip() for part in (raw or "").split(",") if part.strip()]
    # In anteprima locale l'indirizzo del mittente e' anche la casella demo:
    # Mailpit/MailHog accettano qualsiasi destinatario e l'operatore vede il
    # messaggio senza dover configurare una casella reale.
    if not targets and settings.smtp_mode == "local_preview" and settings.report_from:
        targets = [settings.report_from]
    return targets


def sender_name(settings: Settings) -> str:
    return settings.mail_from_name or settings.company


def send_alert(
    settings: Settings, subject: str, body: str, recipients: list[str] | None = None
) -> list[str]:
    """Invia un allarme via email; solleva se SMTP o destinatari mancano."""
    if not settings.smtp_enabled or not settings.smtp_host or not settings.report_from:
        raise MailNotConfigured(
            "invio non configurato: impostare SMTP_ENABLED, DEVICEHUB_SMTP_HOST e"
            " DEVICEHUB_REPORT_FROM"
        )
    targets = recipients or alert_recipients_from(settings)
    if not targets:
        raise MailNotConfigured("nessun destinatario per gli allarmi")
    invalid = [address for address in targets if not EMAIL_RE.match(address)]
    if invalid:
        raise MailNotConfigured(f"indirizzi non validi: {', '.join(invalid)}")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((sender_name(settings), settings.report_from))
    message["To"] = ", ".join(targets)
    message.set_content(body)
    try:
        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=15
        ) as client:
            client.ehlo()
            if settings.smtp_starttls:
                client.starttls()
                client.ehlo()
            if settings.smtp_user:
                client.login(settings.smtp_user, settings.smtp_password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailDeliveryError(f"invio non riuscito: {exc}") from exc
    return targets


def build_report_message(
    settings: Settings,
    snapshot: dict,
    recipients: list[str],
    url: str | None = None,
    attachment: tuple[str, bytes] | None = None,
    display_name: str | None = None,
) -> EmailMessage:
    url = url or report_url(settings, snapshot["id"])
    sender = display_name or sender_name(settings)
    fingerprint = snapshot.get("fingerprint") or "non firmato"
    digest = snapshot.get("digest") or "-"
    message = EmailMessage()
    message["Subject"] = (
        f"Report mensile flotta {snapshot['period']} - {sender}"
    )
    message["From"] = formataddr((sender, settings.report_from))
    message["To"] = ", ".join(recipients)
    message.set_content(
        f"""Buongiorno,

il report del mese {snapshot['period']} e' disponibile qui:

{url}

Documento: snapshot {snapshot['id']}, congelato il {snapshot.get('created_at', '')}.
Impronta SHA-256: {digest}
Chiave di firma: {fingerprint}

La pagina si apre con le credenziali della piattaforma e si puo' stampare o
salvare in PDF. La firma Ed25519 si puo' verificare anche senza accesso alla
pagina /verify, caricando il file esportato.

{sender_name(settings)}
"""
    )
    message.add_alternative(
        f"""<!DOCTYPE html>
<html lang="it"><body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#12202f">
<p>Buongiorno,</p>
<p>il report del mese <strong>{snapshot['period']}</strong> e' disponibile:</p>
<p><a href="{url}" style="color:#0e7490">{url}</a></p>
<p style="font-size:13px;color:#5b6b7c">
Snapshot {snapshot['id']}, congelato il {snapshot.get('created_at', '')}.<br>
Impronta SHA-256: <code>{digest}</code><br>
Chiave di firma: <code>{fingerprint}</code>
</p>
<p style="font-size:13px;color:#5b6b7c">
La pagina si apre con le credenziali della piattaforma e si puo' stampare o
salvare in PDF. La firma si puo' verificare anche senza accesso, dalla pagina
/verify.
</p>
<p style="font-size:13px;color:#5b6b7c">{sender_name(settings)}</p>
</body></html>""",
        subtype="html",
    )
    if attachment:
        filename, data = attachment
        message.add_attachment(
            data, maintype="application", subtype="pdf", filename=filename
        )
    return message


def send_report(
    settings: Settings,
    snapshot: dict,
    recipients: list[str] | None = None,
    url: str | None = None,
    attachment: tuple[str, bytes] | None = None,
    display_name: str | None = None,
) -> list[str]:
    """Invia il report e restituisce i destinatari effettivi."""
    if not settings.smtp_enabled or not settings.smtp_host or not settings.report_from:
        raise MailNotConfigured(
            "invio non configurato: impostare SMTP_ENABLED, DEVICEHUB_SMTP_HOST e"
            " DEVICEHUB_REPORT_FROM"
        )
    targets = [address for address in (recipients or recipients_from(settings))]
    if not targets:
        raise MailNotConfigured(
            "nessun destinatario: usare ?to=... oppure DEVICEHUB_REPORT_TO"
        )
    invalid = [address for address in targets if not EMAIL_RE.match(address)]
    if invalid:
        raise MailNotConfigured(f"indirizzi non validi: {', '.join(invalid)}")

    message = build_report_message(
        settings, snapshot, targets, url, attachment, display_name
    )
    try:
        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=15
        ) as client:
            client.ehlo()
            if settings.smtp_starttls:
                client.starttls()
                client.ehlo()
            if settings.smtp_user:
                client.login(settings.smtp_user, settings.smtp_password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailDeliveryError(f"invio non riuscito: {exc}") from exc
    return targets
