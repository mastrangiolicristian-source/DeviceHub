"""Configurazione da variabili d'ambiente, con default sicuri per lo sviluppo."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from email.utils import parseaddr
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .auth import random_secret


def _load_dotenv() -> None:
    """Carica un `.env` opzionale senza sovrascrivere l'ambiente.

    Il servizio in produzione riceve le variabili dal supervisor; in demo un
    `.env` nella directory di avvio evita di ripetere ogni volta la riga di
    comando. I valori restano in memoria e non vengono mai scritti nei log.
    """
    if os.getenv("DEVICEHUB_SKIP_DOTENV") or os.getenv("PYTEST_CURRENT_TEST"):
        # I test devono partire dall'ambiente isolato, non dal `.env` della demo.
        return
    path = Path(os.getenv("DEVICEHUB_ENV_FILE", ".env"))
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key or key in os.environ:
            continue
        try:
            parts = shlex.split(value, comments=True, posix=True)
        except ValueError:
            parts = [value.strip().strip('"').strip("'")]
        os.environ[key] = " ".join(parts) if parts else ""


def _env(*names: str, default: str = "") -> str:
    """Prima variabile presente, inclusi i valori vuoti espliciti."""
    for name in names:
        if name in os.environ:
            return os.environ[name]
    return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _bool_env(*names: str, default: bool) -> bool:
    for name in names:
        if name in os.environ:
            return os.environ[name].strip().lower() in ("1", "true", "yes", "on")
    return default


@dataclass(frozen=True)
class Settings:
    db_path: str
    tcp_host: str
    tcp_port: int
    api_host: str
    api_port: int
    api_token: str
    allow_unknown_devices: bool
    reject_unknown_devices: bool
    log_io: bool
    profile_path: str | None
    idle_timeout: float
    public_host: str
    public_port: int
    apn: str
    codec: int
    douts: int
    company: str
    app_name: str = ""
    # Sfondo aziendale (white-label): URL dell'immagine dietro il vetro.
    # La classe che accende il livello entra nell'HTML, non arriva dallo script.
    custom_bg_image: str = ""
    environment: str = "production"
    demo_mode: bool = False
    demo_trigger_token: str = ""
    admin_password: str = ""
    admin_tenant: str = "Default"
    session_secret: str = field(default_factory=random_secret)
    session_ttl_hours: int = 12
    max_login_attempts: int = 5
    lock_minutes: int = 15
    co2_kg_per_liter: float = 2.65
    fuel_l_per_100km: float = 8.0
    signing_key_path: str = ""
    smtp_enabled: bool = True
    smtp_mode: str = "live"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    report_from: str = ""
    mail_from_name: str = ""
    report_recipients: str = ""
    public_base_url: str = ""
    # Aggiornamenti: manifest JSON del canale di rilascio e cartella da aggiornare.
    update_url: str = ""
    update_dir: str = ""
    monthly_auto: bool = False
    monthly_hour: int = 3
    monthly_email: bool = True
    # Mese civile e report: i confini vengono convertiti da questo fuso a UTC.
    report_timezone: str = "Europe/Rome"
    # 0 = conserva tutto lo storico delle posizioni.
    position_retention_days: int = 0
    # 0 = conserva gli allarmi (e le posizioni SOS) senza scadenza.
    alert_retention_days: int = 0
    # Ingresso digitale che attiva la modalita' privacy dal tracker (0 = off).
    privacy_io_id: int = 0
    link_hours: int = 72
    link_max_uses: int = 25
    link_attempt_limit: int = 10
    link_block_minutes: int = 15
    login_ip_attempt_limit: int = 20
    login_ip_block_minutes: int = 15
    alert_emails: str = ""
    fuel_price_eur: float = 1.75
    idle_l_per_hour: float = 2.0
    fuel_theft_liters: float = 15.0
    unplug_enabled: bool = True
    unplug_min_voltage: float = 8.0
    unplug_drop_voltage: float = 3.0
    sos_io_id: int = 251
    sms_enabled: bool = False
    sms_mode: str = "live"
    sms_provider: str = ""
    sms_url: str = ""
    sms_token: str = ""
    sms_to: str = ""
    sms_from: str = ""
    sms_template_critical: str = ""
    sms_retries: int = 2
    sms_receipt_token: str = ""
    voice_enabled: bool = False
    voice_mode: str = "simulated"
    voice_provider: str = ""
    voice_caller_id: str = ""
    voice_language: str = "it-IT"
    voice_tts_template: str = ""
    alert_cooldown_minutes: int = 10
    webhook_url: str = ""
    webhook_secret: str = ""
    webhook_retries: int = 2
    webhook_max_attempts: int = 20
    webhook_max_pending: int = 1000
    driver_io_id: int = 0
    harsh_accel_kmh_s: float = 8.0
    harsh_brake_kmh_s: float = 10.0

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        api_token = os.getenv("DEVICEHUB_API_TOKEN", "")
        codec = int(os.getenv("DEVICEHUB_CODEC", "142"), 0)
        # Un solo interruttore: rifiutare gli IMEI non abilitati implica non
        # accettare quelli sconosciuti, senza dipendere da una seconda variabile.
        reject_unknown = _bool("DEVICEHUB_REJECT_UNKNOWN", False)
        allow_unknown = not reject_unknown
        # Senza token l'API resta in ascolto solo su loopback.
        api_host = os.getenv("DEVICEHUB_API_HOST", "127.0.0.1" if not api_token else "0.0.0.0")
        public_host = os.getenv("DEVICEHUB_PUBLIC_HOST", "127.0.0.1")
        app_name = _env("APP_NAME", default="")
        company = _env(
            "DEVICEHUB_COMPANY", "APP_NAME", default="CM FleetHUD VisionOS"
        )
        environment = _env("ENVIRONMENT", default="production")
        report_timezone = _env("DEVICEHUB_REPORT_TIMEZONE", default="Europe/Rome")
        try:
            ZoneInfo(report_timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(
                f"DEVICEHUB_REPORT_TIMEZONE non valido: {report_timezone}"
            ) from exc
        demo_mode = _bool_env(
            "DEVICEHUB_DEMO_MODE", "DEMO_MODE", default=environment == "demo"
        )
        smtp_mode = _env("DEVICEHUB_SMTP_MODE", "SMTP_MODE", default="live").lower()
        smtp_host = _env("DEVICEHUB_SMTP_HOST", "SMTP_HOST", default="")
        smtp_enabled = _bool_env(
            "DEVICEHUB_SMTP_ENABLED", "SMTP_ENABLED", default=bool(smtp_host)
        )
        if not smtp_enabled:
            smtp_host = ""
        smtp_starttls = _bool_env(
            "DEVICEHUB_SMTP_STARTTLS",
            "SMTP_STARTTLS",
            default=smtp_mode != "local_preview",
        )
        smtp_from = _env("DEVICEHUB_REPORT_FROM", "SMTP_FROM", default="")
        smtp_from_name, smtp_from_address = parseaddr(smtp_from)
        sms_mode = _env("DEVICEHUB_SMS_MODE", "SMS_MODE", default="live").lower()
        sms_url = _env("DEVICEHUB_SMS_URL", "SMS_URL", default="")
        sms_enabled = _bool_env(
            "DEVICEHUB_SMS_ENABLED",
            "SMS_ENABLED",
            default=bool(sms_url) or sms_mode == "simulated",
        )
        voice_enabled = _bool_env("DEVICEHUB_VOICE_ENABLED", "VOICE_ENABLED", default=False)
        return cls(
            db_path=os.getenv("DEVICEHUB_DB", "devicehub.db"),
            tcp_host=os.getenv("DEVICEHUB_TCP_HOST", "0.0.0.0"),
            tcp_port=int(os.getenv("DEVICEHUB_TCP_PORT", "5027")),
            api_host=api_host,
            api_port=int(os.getenv("DEVICEHUB_API_PORT", "8010")),
            api_token=api_token,
            allow_unknown_devices=allow_unknown,
            reject_unknown_devices=reject_unknown,
            log_io=_bool("DEVICEHUB_LOG_IO", False),
            profile_path=os.getenv("DEVICEHUB_PROFILE") or None,
            idle_timeout=float(os.getenv("DEVICEHUB_IDLE_TIMEOUT", "120")),
            public_host=public_host,
            public_port=int(os.getenv("DEVICEHUB_PUBLIC_PORT", "5027")),
            apn=os.getenv("DEVICEHUB_APN", ""),
            codec=codec,
            # FMC150 QKIB0: 3 uscite (2 relè + sirena). QJIB0: 2.
            douts=int(os.getenv("DEVICEHUB_DOUTS", "3")),
            company=company,
            app_name=app_name or company,
            custom_bg_image=_env(
                "DEVICEHUB_CUSTOM_BG_IMAGE", "APP_BG_IMAGE", default=""
            ).strip(),
            environment=environment,
            demo_mode=demo_mode,
            # Se impostato, il trigger demo richiede l'header X-Demo-Token.
            demo_trigger_token=_env(
                "DEVICEHUB_DEMO_TRIGGER_TOKEN", "DEMO_TRIGGER_TOKEN", default=""
            ).strip(),
            # Solo per il primo avvio: crea l'amministratore. Mai in un file.
            admin_password=os.getenv("DEVICEHUB_ADMIN_PASSWORD", ""),
            admin_tenant=os.getenv("DEVICEHUB_ADMIN_TENANT", "Default"),
            session_secret=os.getenv("DEVICEHUB_SESSION_SECRET") or random_secret(),
            session_ttl_hours=int(os.getenv("DEVICEHUB_SESSION_TTL_HOURS", "12")),
            max_login_attempts=int(os.getenv("DEVICEHUB_MAX_LOGIN_ATTEMPTS", "5")),
            lock_minutes=int(os.getenv("DEVICEHUB_LOCK_MINUTES", "15")),
            # Fattori dichiarati per la stima ESG (gasolio su veicolo commerciale).
            co2_kg_per_liter=float(os.getenv("DEVICEHUB_CO2_KG_PER_LITER", "2.65")),
            fuel_l_per_100km=float(os.getenv("DEVICEHUB_FUEL_L_PER_100KM", "8.0")),
            # Chiave privata Ed25519 per firmare gli snapshot ESG.
            signing_key_path=os.getenv("DEVICEHUB_SIGNING_KEY", ""),
            # Invio del report mensile e degli allarmi: SMTP del cliente.
            smtp_enabled=smtp_enabled,
            smtp_mode=smtp_mode,
            smtp_host=smtp_host,
            smtp_port=int(_env("DEVICEHUB_SMTP_PORT", "SMTP_PORT", default="587")),
            smtp_user=_env("DEVICEHUB_SMTP_USER", "SMTP_USER", default=""),
            smtp_password=_env(
                "DEVICEHUB_SMTP_PASSWORD", "SMTP_PASSWORD", "SMTP_PASS", default=""
            ),
            smtp_starttls=smtp_starttls,
            report_from=smtp_from_address,
            mail_from_name=_env(
                "DEVICEHUB_MAIL_FROM_NAME", "SMTP_FROM_NAME", default=smtp_from_name
            ),
            report_recipients=os.getenv("DEVICEHUB_REPORT_TO", ""),
            # Indirizzo pubblico per i link nelle email (es. https://api.esempio.it).
            public_base_url=os.getenv("DEVICEHUB_PUBLIC_URL", ""),
            # Manifest del canale di rilascio e cartella dell'installazione.
            update_url=os.getenv("DEVICEHUB_UPDATE_URL", "").strip(),
            update_dir=os.getenv("DEVICEHUB_UPDATE_DIR", "").strip(),
            # Chiusura mensile automatica e link per il cliente.
            monthly_auto=_bool("DEVICEHUB_MONTHLY_AUTO", False),
            monthly_hour=int(os.getenv("DEVICEHUB_MONTHLY_HOUR", "3")),
            monthly_email=_bool("DEVICEHUB_MONTHLY_EMAIL", True),
            report_timezone=report_timezone,
            position_retention_days=int(
                os.getenv("DEVICEHUB_POSITION_RETENTION_DAYS", "0")
            ),
            alert_retention_days=int(
                os.getenv("DEVICEHUB_ALERT_RETENTION_DAYS", "0")
            ),
            privacy_io_id=int(os.getenv("DEVICEHUB_PRIVACY_IO_ID", "0")),
            link_hours=int(os.getenv("DEVICEHUB_LINK_HOURS", "72")),
            link_max_uses=int(os.getenv("DEVICEHUB_LINK_MAX_USES", "25")),
            link_attempt_limit=int(
                os.getenv("DEVICEHUB_LINK_ATTEMPT_LIMIT", "10")
            ),
            link_block_minutes=int(
                os.getenv("DEVICEHUB_LINK_BLOCK_MINUTES", "15")
            ),
            # Tentativi di accesso falliti per indirizzo, prima del blocco.
            login_ip_attempt_limit=int(
                os.getenv("DEVICEHUB_LOGIN_IP_ATTEMPT_LIMIT", "20")
            ),
            login_ip_block_minutes=int(
                os.getenv("DEVICEHUB_LOGIN_IP_BLOCK_MINUTES", "15")
            ),
            # Destinatari degli allarmi (geofence, velocita', furto, SOS).
            alert_emails=_env("DEVICEHUB_ALERT_TO", "ALERT_TO", default=""),
            fuel_price_eur=float(os.getenv("DEVICEHUB_FUEL_PRICE_EUR", "1.75")),
            idle_l_per_hour=float(os.getenv("DEVICEHUB_IDLE_L_PER_HOUR", "2.0")),
            fuel_theft_liters=float(
                os.getenv("DEVICEHUB_FUEL_THEFT_LITERS", "15")
            ),
            # Taglio alimentazione esterna: tensione esterna (AVL 66) in calo.
            unplug_enabled=_bool("DEVICEHUB_UNPLUG_ENABLED", True),
            unplug_min_voltage=float(
                os.getenv("DEVICEHUB_UNPLUG_MIN_VOLTAGE", "8.0")
            ),
            unplug_drop_voltage=float(
                os.getenv("DEVICEHUB_UNPLUG_DROP_VOLTAGE", "3.0")
            ),
            # AVL ID del pulsante SOS: va confermato sul dispositivo.
            sos_io_id=int(os.getenv("DEVICEHUB_SOS_IO_ID", "251")),
            # SMS: simulated registra in outbox, live usa il gateway HTTP.
            sms_enabled=sms_enabled,
            sms_mode=sms_mode,
            sms_provider=_env("DEVICEHUB_SMS_PROVIDER", "SMS_PROVIDER", default=""),
            sms_url=sms_url,
            sms_token=_env("DEVICEHUB_SMS_TOKEN", "SMS_TOKEN", default=""),
            sms_to=_env("DEVICEHUB_SMS_TO", "SMS_TO", default=""),
            sms_from=_env(
                "DEVICEHUB_SMS_FROM", "SMS_FROM", "SMS_SENDER_ID", default=""
            ),
            sms_template_critical=_env(
                "DEVICEHUB_SMS_TEMPLATE_CRITICAL", "SMS_TEMPLATE_CRITICAL", default=""
            ),
            sms_retries=int(_env("DEVICEHUB_SMS_RETRIES", "SMS_RETRIES", default="2")),
            sms_receipt_token=_env(
                "DEVICEHUB_SMS_RECEIPT_TOKEN", "SMS_RECEIPT_TOKEN", default=""
            ),
            voice_enabled=voice_enabled,
            voice_mode=_env(
                "DEVICEHUB_VOICE_MODE", "VOICE_MODE", default="simulated"
            ).lower(),
            voice_provider=_env(
                "DEVICEHUB_VOICE_PROVIDER", "VOICE_PROVIDER", default=""
            ),
            voice_caller_id=_env(
                "DEVICEHUB_VOICE_CALLER_ID", "VOICE_CALLER_ID", default=""
            ),
            voice_language=_env(
                "DEVICEHUB_VOICE_LANGUAGE", "VOICE_LANGUAGE", default="it-IT"
            ),
            voice_tts_template=_env(
                "DEVICEHUB_VOICE_TTS_TEMPLATE", "VOICE_TTS_TEMPLATE", default=""
            ),
            alert_cooldown_minutes=int(
                _env(
                    "DEVICEHUB_ALERT_COOLDOWN_MINUTES",
                    "ALERT_COOLDOWN_MINUTES",
                    default="10",
                )
            ),
            webhook_url=os.getenv("DEVICEHUB_WEBHOOK_URL", ""),
            webhook_secret=os.getenv("DEVICEHUB_WEBHOOK_SECRET", ""),
            webhook_retries=int(os.getenv("DEVICEHUB_WEBHOOK_RETRIES", "2")),
            webhook_max_attempts=int(
                os.getenv("DEVICEHUB_WEBHOOK_MAX_ATTEMPTS", "20")
            ),
            webhook_max_pending=int(
                os.getenv("DEVICEHUB_WEBHOOK_MAX_PENDING", "1000")
            ),
            driver_io_id=int(os.getenv("DEVICEHUB_DRIVER_IO_ID", "0")),
            harsh_accel_kmh_s=float(
                os.getenv("DEVICEHUB_HARSH_ACCEL_KMH_S", "8")
            ),
            harsh_brake_kmh_s=float(
                os.getenv("DEVICEHUB_HARSH_BRAKE_KMH_S", "10")
            ),
        )
