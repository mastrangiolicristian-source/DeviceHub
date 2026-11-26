"""API HTTP: dashboard, dispositivi, comandi, provisioning, SOC e accesso.

Autenticazione a cookie firmato (nessuna dipendenza esterna) con isolamento per
tenant: un utente non amministratore vede e comanda solo i mezzi della propria
azienda. La chiave `X-Api-Key` resta come accesso macchina equivalente a un
amministratore, per script e integrazioni.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import threading
import time

from .driving import analyse
from .geofence import (
    SHAPES,
    normalize_geometry,
    normalize_schedule,
    normalize_timezone,
)
from .webhooks import WebhookNotConfigured, flush_outbox
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse

from . import updates
from .auth import COOKIE_NAME, read_session, sign_session, verify_password
from .codec12 import block_allowed, relay_command
from .config import Settings
from .dashboard import render_dashboard
from .theme import custom_bg_url
from .exports import csv_bytes, xlsx_bytes
from .esg import build_report, month_window, previous_period, report_zone
from .ingest import DeviceOffline, IngestServer
from .notifications import dispatch_email, dispatch_sms, dispatch_voice
from .provisioning import teltonika_plan
from .schemas import PasswordResetRequest, ROLES, UserCreateRequest
from .monthly import close_month, run_monthly
from .pdf import render_report_pdf
from .report import (
    render_unavailable_page,
    render_report_page,
    render_token_page,
)
from .signing import fingerprint, load_or_create_private_key, public_pem, sign, verify
from .store import TelemetryStore
from .tracks import build_history, day_bounds
from .track_export import gpx_bytes, kml_bytes
from .verticals import VERTICAL_IDS, vertical_details
from .version import __version__
from .branding import (
    BG_EXTENSIONS,
    DEFAULT_COLOR,
    MAX_BG_BYTES,
    MAX_LOGO_BYTES,
    check_background,
    check_logo,
    normalize_color,
)
from .links import create_link, resolve as resolve_link
from .mailer import (
    EMAIL_RE,
    MailDeliveryError,
    MailNotConfigured,
    recipients_from,
    send_report,
)
from .verify_page import render_verify_page
from .web import render_control_page, render_login

CAN_BLOCK = ("admin", "manager", "soc")
# Lo sfondo caricato non va in cache condivisa e va rivalidato a ogni uso.
BACKGROUND_CACHE = "private, max-age=0, must-revalidate"


def snapshot_head(row: dict) -> dict:
    return {
        "id": row["id"],
        "period": row["period"],
        "created_at": row["created_at"],
        "created_by": row["created_by"],
        "digest": row["digest"],
        "fingerprint": fingerprint(row["public_key"])
        if row.get("public_key")
        else None,
    }


def snapshot_view(row: dict) -> dict:
    """Vista comune di uno snapshot: report, impronta e firma."""
    digest_ok = hashlib.sha256(row["payload"].encode()).hexdigest() == row["digest"]
    signature_ok = bool(
        row.get("signature")
        and row.get("public_key")
        and verify(row["public_key"], row["payload"], row["signature"])
    )
    return {
        "snapshot": {
            "id": row["id"],
            "period": row["period"],
            "created_at": row["created_at"],
            "created_by": row["created_by"],
            "digest": row["digest"],
            "signature": row.get("signature"),
            "public_key": row.get("public_key"),
            "fingerprint": fingerprint(row["public_key"])
            if row.get("public_key")
            else None,
        },
        "digest_ok": digest_ok,
        "signature_ok": signature_ok,
        "verified": digest_ok and signature_ok,
        "report": json.loads(row["payload"]),
    }


def create_app(
    settings: Settings, store: TelemetryStore, ingest: IngestServer | None = None
) -> FastAPI:
    app = FastAPI(
        title="DeviceHub - ingestione flotta",
        version=__version__,
        description="Ingestione GPS Teltonika, stato dispositivi, comandi, SOC.",
    )

    key_path = settings.signing_key_path or str(
        Path(settings.db_path).with_name("esg-signing-key.pem")
    )
    signing = {"key": load_or_create_private_key(key_path)}

    def pdf_response(row: dict) -> Response:
        branding = store.tenant_branding(row["tenant_key"])
        payload = render_report_pdf(
            settings, snapshot_head(row), json.loads(row["payload"]), branding
        )
        return Response(
            content=payload,
            media_type="application/pdf",
            headers={
                "Content-Disposition":
                f'attachment; filename="report-{row["period"]}.pdf"'
            },
        )

    def monthly_job(period: str | None = None, actor: str = "scheduler") -> dict:
        return run_monthly(settings, store, signing["key"], period, actor)

    def client_ip(request: Request) -> str:
        """Indirizzo del client, tenendo conto del proxy (nginx).

        `X-Real-IP` e' impostato dal proxy; l'ultimo valore di
        `X-Forwarded-For` e' quello aggiunto dal proxy stesso. Senza header si
        usa l'indirizzo della connessione.
        """
        real = (request.headers.get("x-real-ip") or "").strip()
        if real:
            return real
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",")
        if forwarded and forwarded[-1].strip():
            return forwarded[-1].strip()
        return request.client.host if request.client else "unknown"

    def guard_token(request: Request, token: str) -> dict:
        """Valida un token: scadenza, revoca, limite di aperture, blocco per IP."""
        ip = client_ip(request)
        if store.link_blocked(ip):
            raise HTTPException(
                status_code=429,
                detail="troppi tentativi: riprovare piu' tardi",
            )
        token_row = resolve_link(store, token)
        if token_row is None:
            blocked = store.register_link_failure(
                ip, settings.link_attempt_limit, settings.link_block_minutes
            )
            if blocked:
                raise HTTPException(
                    status_code=429,
                    detail="troppi tentativi: riprovare piu' tardi",
                )
            raise HTTPException(status_code=404, detail="link non valido o scaduto")
        limit = token_row.get("max_uses") or settings.link_max_uses
        if token_row["used_count"] >= limit:
            raise HTTPException(status_code=410, detail="link esaurito")
        store.clear_link_failures(ip)
        return token_row

    app.state.monthly_job = monthly_job
    _active_pem = public_pem(signing["key"])
    if store.active_signing_key() is None:
        store.register_signing_key(fingerprint(_active_pem), _active_pem, key_path)

    # Snapshot creati prima del registro delle chiavi: recupera l'impronta
    # dalla chiave pubblica che hanno conservato e registra le chiavi ignote.
    known_keys = {key["fingerprint"] for key in store.signing_keys()}
    for legacy in store.snapshots_without_key_fingerprint():
        legacy_fp = fingerprint(legacy["public_key"])
        store.set_snapshot_key_fingerprint(legacy["id"], legacy_fp)
        if legacy_fp not in known_keys:
            store.register_signing_key(
                legacy_fp, legacy["public_key"], None, "snapshot precedenti", active=False
            )
            known_keys.add(legacy_fp)

    def open_mode() -> bool:
        """Primo avvio: nessun utente e nessuna chiave API, accesso aperto.

        Appena esiste un utente o viene impostata una chiave, l'accesso diventa
        obbligatorio. Evita sia il blocco totale all'installazione sia un
        sistema che resta aperto dopo la configurazione.
        """
        return not settings.api_token and store.count_users() == 0

    def current_user(request: Request) -> dict:
        token = request.cookies.get(COOKIE_NAME)
        if token:
            data = read_session(token, settings.session_secret)
            if data:
                user = store.get_user(str(data.get("sub") or ""))
                if user and user["active"]:
                    # Una password cambiata invalida i cookie gia' emessi.
                    if data.get("pv") != user.get("password_version"):
                        raise HTTPException(
                            status_code=401,
                            detail="Password cambiata: accedere di nuovo",
                        )
                    user.pop("password_hash", None)
                    return user
        api_key = request.headers.get("X-Api-Key")
        if settings.api_token and api_key and hmac.compare_digest(
            api_key, settings.api_token
        ):
            return {
                "username": "api",
                "role": "admin",
                "tenant_id": None,
                "tenant_name": None,
                "full_name": "Chiave API",
            }
        if open_mode():
            return {
                "username": "demo",
                "role": "admin",
                "tenant_id": None,
                "tenant_name": None,
                "full_name": "Primo avvio",
            }
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")

    def tenant_scope(user: dict) -> int | None:
        """None = vede tutto (amministratore), altrimenti il solo tenant."""
        return None if user["role"] == "admin" else user.get("tenant_id")

    def require_device(user: dict, imei: str) -> dict:
        device = store.device(imei)
        if device is None:
            raise HTTPException(status_code=404, detail="IMEI non registrato")
        tenant = tenant_scope(user)
        if tenant is not None and device.get("tenant_id") != tenant:
            raise HTTPException(status_code=403, detail="Dispositivo di un altro cliente")
        return device

    def session_payload(user: dict) -> dict:
        return {
            "sub": user["username"],
            "role": user["role"],
            "tid": user["tenant_id"],
            "pv": user.get("password_version"),
        }

    def branding_key(user: dict) -> str:
        """Tenant del branding: stringa vuota per l'amministratore (globale)."""
        tenant = tenant_scope(user)
        return "" if tenant is None else str(tenant)

    def require_branding_role(user: dict) -> None:
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(
                status_code=403, detail="Solo amministratore o responsabile"
            )

    def request_tenant_key(request: Request) -> str:
        """Tenant della sessione, se c'e'. Senza sessione vale il globale ("").

        Serve alle pagine che vengono rese lato server: il body porta gia' lo
        sfondo giusto, senza attendere lo script e senza lampi.
        """
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            return ""
        data = read_session(token, settings.session_secret)
        if data is None:
            return ""
        user = store.get_user(str(data.get("sub") or ""))
        if user is None or not user.get("active"):
            return ""
        if user["role"] == "admin":
            return ""
        return str(user.get("tenant_id") or "")

    def background_stamp(tenant_key: str, content_stamp: str | None) -> str:
        """Firma breve dell'immagine caricata: URL pubblico ma non indovinabile.

        Dipende dal contenuto, non dalla riga: cambiare modalita' non cambia la
        firma, quindi la cache del browser resta valida.
        """
        message = f"bg|{tenant_key}|{content_stamp or ''}".encode()
        return hmac.new(
            settings.session_secret.encode(), message, hashlib.sha256
        ).hexdigest()[:20]

    def background_url(tenant_key: str) -> str:
        """Sfondo effettivo del tenant: decide la modalita', senza eccezioni.

        - 'default': eredita il predefinito del server (anche se il cliente ha
          un contenuto salvato, che resta in attesa);
        - 'none': nessuno sfondo, qualunque cosa sia salvata;
        - 'custom': il contenuto del cliente, file caricato se c'e', altrimenti
          l'URL salvato.
        """
        row = store.tenant_branding(tenant_key) or {}
        mode = str(row.get("bg_mode") or "default")
        if mode == "default":
            return settings.custom_bg_image or ""
        if mode == "none":
            return ""
        if row.get("bg_data"):
            ext = BG_EXTENSIONS.get(row.get("bg_mime") or "", "png")
            stamp = background_stamp(tenant_key, row.get("bg_stamp"))
            return f"/bg/{tenant_key or '0'}/{stamp}.{ext}"
        return str(row.get("bg_image") or "")

    def cookie_options(request: Request) -> dict:
        forwarded = request.headers.get("x-forwarded-proto", "")
        host = request.headers.get("host", "").split(":")[0]
        secure = (
            request.url.scheme == "https"
            or forwarded.split(",")[0].strip() == "https"
            or host.endswith(".style.dev")
        )
        # Nella preview in iframe il cookie e' di terze parti: senza
        # SameSite=None il browser non lo rimanda e la sessione cade subito.
        return {
            "max_age": settings.session_ttl_hours * 3600,
            "httponly": True,
            "samesite": "none" if secure else "lax",
            "secure": secure,
            "path": "/",
        }

    def start_session(user: dict, request: Request, response: Response) -> dict:
        ttl = settings.session_ttl_hours * 3600
        token = sign_session(session_payload(user), settings.session_secret, ttl)
        response.set_cookie(COOKIE_NAME, token, **cookie_options(request))
        public = {key: value for key, value in user.items() if key != "password_hash"}
        return {"status": "success", "user": public}

    @app.middleware("http")
    async def renew_session(request: Request, call_next):
        """Rinnova il cookie mentre la dashboard e' in uso.

        La sessione vale `session_ttl_hours`: senza rinnovo una pagina lasciata
        aperta mostra dati vecchi e il primo salvataggio risponde 401
        ("sessione scaduta"). Rinnoviamo solo nella seconda meta' della durata,
        cosi' un accesso inutilizzato scade comunque.
        """
        response = await call_next(request)
        token = request.cookies.get(COOKIE_NAME)
        if not token or request.url.path == "/auth/logout":
            return response
        data = read_session(token, settings.session_secret)
        if data is None:
            return response
        ttl = settings.session_ttl_hours * 3600
        remaining = int(data.get("exp", 0)) - int(time.time())
        if remaining > ttl // 2:
            return response
        user = store.get_user(str(data.get("sub") or ""))
        if (
            user is None
            or not user["active"]
            or data.get("pv") != user.get("password_version")
        ):
            return response
        response.set_cookie(
            COOKIE_NAME,
            sign_session(session_payload(user), settings.session_secret, ttl),
            **cookie_options(request),
        )
        return response

    # --- pagine -----------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def dashboard_page(request: Request) -> str:
        """Dashboard operativa unificata (design VisionOS)."""
        return render_dashboard(settings, background_url(request_tenant_key(request)))

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
            '<rect width="32" height="32" rx="9" fill="#2563eb"/>'
            '<path d="M8 21h16M10 17h12M12 13h8" stroke="#fff" stroke-width="2.4"'
            ' stroke-linecap="round"/></svg>'
        )
        return Response(
            content=svg,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/bg/{tenant}/{stamp}.{ext}", include_in_schema=False)
    def background_image(tenant: str, stamp: str, ext: str, request: Request) -> Response:
        """Sfondo del cliente: firmato e servito solo mentre la modalita' e' custom.

        Lo stato del tenant viene controllato prima di ogni altra cosa: con
        'none' o 'default' la risposta e' 404 anche con un If-None-Match
        valido. Quando lo sfondo e' attivo, l'ETag sul contenuto permette al
        browser di ricevere 304 invece dell'immagine.
        """
        key = "" if tenant in ("0", "globale") else tenant
        row = store.tenant_branding(key) or {}
        data = row.get("bg_data")
        if (
            not data
            or row.get("bg_mode") != "custom"
            or stamp != background_stamp(key, row.get("bg_stamp"))
        ):
            raise HTTPException(status_code=404, detail="sfondo inesistente")
        etag = '"' + str(row.get("bg_stamp") or "") + '"'
        headers = {"Cache-Control": BACKGROUND_CACHE, "ETag": etag}
        sent = {
            part.strip()
            for part in (request.headers.get("if-none-match") or "").split(",")
            if part.strip()
        }
        if etag in sent or "W/" + etag in sent:
            return Response(status_code=304, headers=headers)
        return Response(
            content=data,
            media_type=row.get("bg_mime") or "image/png",
            headers=headers,
        )

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request) -> str:
        return render_login(settings, background_url(request_tenant_key(request)))

    @app.get("/verify", response_class=HTMLResponse)
    def verify_page(request: Request) -> str:
        """Verifica pubblica di un file esportato, interamente nel browser."""
        return render_verify_page(settings, background_url(request_tenant_key(request)))

    @app.get("/controllo", response_class=HTMLResponse)
    def control_page(request: Request) -> str:
        """Pagina di controllo essenziale: dispositivi, blocco, provisioning."""
        return render_control_page(settings, background_url(request_tenant_key(request)))

    @app.get("/health")
    def health() -> dict:
        users = store.count_users()
        return {
            "status": "ok",
            "version": __version__,
            "app_name": settings.app_name or settings.company,
            "environment": settings.environment,
            "demo_mode": settings.demo_mode,
            "tcp_port": settings.tcp_port,
            "db": settings.db_path,
            "auth": "open" if open_mode() else "required",
            "users": users,
        }

    @app.post("/api/v1/demo/trigger-alarm")
    async def trigger_demo_alarm(payload: dict, request: Request) -> dict:
        """Simula un allarme commerciale su un mezzo della flotta demo.

        Endpoint senza sessione: lo script di demo non ha cookie. Se
        `DEMO_TRIGGER_TOKEN` è configurato, richiede lo stesso valore in
        `X-Demo-Token` (o come bearer). Resta spento fuori da `DEMO_MODE` e
        non crea posizioni o mezzi nuovi.
        """
        if not settings.demo_mode:
            raise HTTPException(status_code=404, detail="demo non attiva")
        if settings.demo_trigger_token:
            supplied = (request.headers.get("x-demo-token") or "").strip()
            authorization = (request.headers.get("authorization") or "").strip()
            if not supplied and authorization.lower().startswith("bearer "):
                supplied = authorization[7:].strip()
            if not supplied or not hmac.compare_digest(
                supplied.encode("utf-8"), settings.demo_trigger_token.encode("utf-8")
            ):
                raise HTTPException(
                    status_code=401,
                    detail="token demo mancante o non valido",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        plate = str(payload.get("plate") or "").strip()
        if not plate:
            raise HTTPException(status_code=400, detail="plate obbligatoria")
        device = next(
            (
                item
                for item in store.devices()
                if str(item.get("plate") or "").lower() == plate.lower()
            ),
            None,
        )
        if device is None:
            available = sorted(
                str(item.get("plate"))
                for item in store.devices()
                if item.get("plate")
            )
            raise HTTPException(
                status_code=404,
                detail=f"mezzo non trovato; targhe demo: {', '.join(available)}",
            )
        raw_type = str(payload.get("alarm_type") or "SOS_PANIC_BUTTON").strip()
        kind = {
            "SOS_PANIC_BUTTON": "SOS",
            "PANIC_BUTTON": "SOS",
            "SOS": "SOS",
            "JAMMING": "JAMMING",
            "UNPLUG": "UNPLUG",
            "THEFT": "THEFT",
            "FUEL_THEFT": "FUEL_THEFT",
        }.get(raw_type.upper(), raw_type.upper())
        if kind not in {"SOS", "JAMMING", "UNPLUG", "THEFT", "FUEL_THEFT"}:
            raise HTTPException(
                status_code=400,
                detail="alarm_type non supportato dalla demo",
            )
        severity = str(payload.get("severity") or "CRITICAL").upper()
        if severity not in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
            raise HTTPException(status_code=400, detail="severity non valida")
        try:
            latitude = float(payload.get("lat", 42.3169))
            longitude = float(payload.get("lng", 14.0810))
            speed = float(payload.get("speed_kmh", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400, detail="lat, lng e speed_kmh devono essere numerici"
            ) from exc
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise HTTPException(status_code=400, detail="coordinate fuori intervallo")
        raw_channels = payload.get("channels") or ["email", "sms", "voice_tts"]
        if isinstance(raw_channels, str):
            raw_channels = [part.strip() for part in raw_channels.split(",")]
        channels = {
            "voice" if str(item).lower() == "voice_tts" else str(item).lower()
            for item in raw_channels
        }
        unknown = channels - {"email", "sms", "voice"}
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"canali non supportati: {', '.join(sorted(unknown))}",
            )
        if not channels:
            raise HTTPException(status_code=400, detail="nessun canale richiesto")
        ts_ms = int(time.time() * 1000)
        detail = (
            f"Demo trigger {raw_type} a {latitude:.5f}, {longitude:.5f}"
            f" · {speed:.0f} km/h"
        )
        store.raise_alert(
            device["imei"], kind, severity, detail, ts_ms, dedupe=False
        )
        details = store.alert_details(device["imei"], [kind], ts_ms)
        results: list[dict] = []
        for channel in ("email", "sms", "voice"):
            if channel not in channels:
                results.append({"channel": channel, "status": "skipped"})
                continue
            if channel == "email":
                result = await asyncio.to_thread(
                    dispatch_email,
                    store,
                    settings,
                    device["imei"],
                    [kind],
                    details,
                    latitude,
                    longitude,
                    ts_ms,
                )
            elif channel == "sms":
                result = await asyncio.to_thread(
                    dispatch_sms,
                    store,
                    settings,
                    device["imei"],
                    [kind],
                    latitude,
                    longitude,
                    ts_ms,
                )
            else:
                result = await asyncio.to_thread(
                    dispatch_voice,
                    store,
                    settings,
                    device["imei"],
                    [kind],
                    latitude,
                    longitude,
                    ts_ms,
                )
            results.append(result or {"channel": channel, "status": "skipped"})
        latest = store.alerts(limit=1)
        alert_id = latest[0]["id"] if latest else None
        store.record_admin_action(
            "demo-trigger",
            "demo_alarm",
            device["imei"],
            f"{kind} channels={','.join(sorted(channels))}",
        )
        return {
            "status": "success",
            "alert_id": alert_id,
            "imei": device["imei"],
            "plate": device["plate"],
            "alarm_type": kind,
            "severity": severity,
            "latitude": latitude,
            "longitude": longitude,
            "channels": sorted(channels),
            "outbox": results,
        }

    # --- accesso ----------------------------------------------------------

    @app.post("/auth/login")
    def login(payload: dict, request: Request, response: Response) -> dict:
        ip = client_ip(request)
        if store.login_blocked(ip):
            raise HTTPException(
                status_code=429,
                detail="troppi tentativi da questo indirizzo: riprovare piu' tardi",
            )
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        user = store.get_user(username)
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if user and user.get("locked_until") and user["locked_until"] > now_iso:
            raise HTTPException(
                status_code=429,
                detail=f"account bloccato fino alle {user['locked_until']} (UTC)",
            )
        if user and not user["active"]:
            raise HTTPException(status_code=403, detail="Utente disabilitato")
        if user and verify_password(password, user["password_hash"]):
            store.clear_login_failures(ip)
            store.register_success(username)
            return start_session(store.get_user(username) or user, request, response)

        # Anche gli username inesistenti contano per l'indirizzo: il blocco per
        # singolo account da solo non ferma il credential stuffing.
        locked = None
        detail = "credenziali non valide"
        if user:
            state = store.register_failure(
                username, settings.max_login_attempts, settings.lock_minutes
            )
            locked = state["locked_until"]
            if not locked:
                detail = (
                    "credenziali non valide"
                    f" ({state['remaining']} tentativi rimasti)"
                )
        if store.register_login_failure(
            ip, settings.login_ip_attempt_limit, settings.login_ip_block_minutes
        ):
            raise HTTPException(
                status_code=429,
                detail="troppi tentativi da questo indirizzo: riprovare piu' tardi",
            )
        if locked:
            raise HTTPException(
                status_code=429,
                detail=(
                    "troppi tentativi falliti: account bloccato per"
                    f" {settings.lock_minutes} minuti"
                ),
            )
        raise HTTPException(status_code=401, detail=detail)

    @app.post("/auth/logout")
    def logout(response: Response) -> dict:
        response.delete_cookie(COOKIE_NAME, path="/")
        return {"status": "success"}

    @app.get("/auth/me")
    def me(user: dict = Depends(current_user)) -> dict:
        return {"user": user, "auth": "open" if open_mode() else "required"}

    @app.post("/auth/password")
    def change_password(
        payload: dict,
        request: Request,
        response: Response,
        user: dict = Depends(current_user),
    ) -> dict:
        """Cambio password da parte dell'utente collegato."""
        current = str(payload.get("current") or "")
        new = str(payload.get("new") or "")
        stored = store.get_user(user["username"])
        if stored is None or not verify_password(current, stored["password_hash"]):
            raise HTTPException(status_code=401, detail="password attuale errata")
        if len(new) < 10:
            raise HTTPException(
                status_code=400, detail="la nuova password deve avere almeno 10 caratteri"
            )
        if verify_password(new, stored["password_hash"]):
            raise HTTPException(
                status_code=400, detail="la nuova password deve essere diversa"
            )
        store.set_password(user["username"], new, must_change=False)
        # La sessione corrente viene rinnovata: le altre cadono.
        return start_session(
            store.get_user(user["username"]) or stored, request, response
        )

    @app.get("/users")
    def list_users(user: dict = Depends(current_user)) -> dict:
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        rows = store.list_users()
        return {"count": len(rows), "users": rows}

    @app.post("/users", status_code=201)
    def add_user(
        payload: UserCreateRequest, user: dict = Depends(current_user)
    ) -> dict:
        """Crea un utente/cliente: i dati arrivano nel body JSON, non nell'URL."""
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        tenant_id = store.ensure_tenant(payload.tenant) if payload.tenant else None
        created = store.create_user(
            payload.username,
            payload.password,
            payload.role,
            tenant_id,
            payload.full_name,
            must_change=True,
        )
        if not created:
            raise HTTPException(status_code=409, detail="utente gia' esistente")
        store.record_admin_action(
            user["username"],
            "user_create",
            payload.username,
            f"role={payload.role} tenant={payload.tenant}",
        )
        return {
            "status": "success",
            "username": payload.username,
            "role": payload.role,
        }

    @app.post("/users/{username}/password")
    def reset_password(
        username: str,
        payload: PasswordResetRequest,
        user: dict = Depends(current_user),
    ) -> dict:
        """Reset da amministratore: la nuova password viaggia nel body JSON."""
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        if store.get_user(username) is None:
            raise HTTPException(status_code=404, detail="utente inesistente")
        store.set_password(username, payload.password, must_change=True)
        store.record_admin_action(
            user["username"], "password_reset", username, "cambio obbligatorio"
        )
        return {"status": "success", "username": username, "must_change": True}

    @app.post("/users/{username}/active")
    def set_user_active(
        username: str,
        active: bool = Query(description="true = riattiva, false = disattiva"),
        user: dict = Depends(current_user),
    ) -> dict:
        """Disattiva o riattiva un utente.

        La disattivazione chiude subito le sessioni aperte: il controllo
        sull'utente avviene a ogni richiesta, non solo al login.
        """
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        target = store.get_user(username)
        if target is None:
            raise HTTPException(status_code=404, detail="utente inesistente")
        if not active:
            if username == user["username"]:
                raise HTTPException(
                    status_code=400, detail="non puoi disattivare il tuo utente"
                )
            if target["role"] == "admin" and store.count_active_admins() <= 1:
                raise HTTPException(
                    status_code=400, detail="serve almeno un amministratore attivo"
                )
        store.set_user_active(username, active)
        store.record_admin_action(
            user["username"],
            "user_activate" if active else "user_deactivate",
            username,
        )
        return {"status": "success", "username": username, "active": active}

    @app.post("/users/{username}/unlock")
    def unlock_user(username: str, user: dict = Depends(current_user)) -> dict:
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        if not store.unlock(username):
            raise HTTPException(status_code=404, detail="utente inesistente")
        store.record_admin_action(user["username"], "user_unlock", username)
        return {"status": "success", "username": username, "locked": False}

    # --- dispositivi ------------------------------------------------------

    @app.get("/devices")
    def list_devices(user: dict = Depends(current_user)) -> dict:
        devices = store.devices(tenant_scope(user))
        for device in devices:
            device["connected"] = bool(ingest and ingest.is_connected(device["imei"]))
            # Stato del blocco ricavato dall'ultimo comando accettato: senza
            # questo l'interfaccia non puo' dire se il relÃ¨ Ã¨ aperto o chiuso.
            last = store.last_command(device["imei"])
            device["engine_blocked"] = bool(
                last and last["accepted"] and last["action"] == "BLOCK"
            )
            device["last_command"] = (
                {
                    "action": last["action"],
                    "accepted": bool(last["accepted"]),
                    "created_at": last["created_at"],
                }
                if last
                else None
            )
        return {"count": len(devices), "devices": devices}

    @app.post("/devices/{imei}/activate")
    def activate_device(
        imei: str,
        plate: str | None = Query(default=None),
        model: str | None = Query(default=None),
        user: dict = Depends(current_user),
    ) -> dict:
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        require_device(user, imei)
        updated = store.activate(imei, plate, model)
        if not updated:
            raise HTTPException(status_code=404, detail="IMEI non registrato")
        if tenant_scope(user) is not None and user.get("tenant_id") is not None:
            store.set_device_tenant(imei, user["tenant_id"])
        return {"status": "success", "imei": imei, "state": "active"}

    @app.patch("/devices/{imei}")
    def update_device(
        imei: str, payload: dict, user: dict = Depends(current_user)
    ) -> dict:
        """Aggiorna targa, modello e nota del mezzo (admin e manager)."""
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        require_device(user, imei)
        plate = str(payload.get("plate") or "").strip()
        model = str(payload.get("model") or "").strip()
        note = str(payload.get("note") or "").strip()
        if len(plate) > 24:
            raise HTTPException(status_code=400, detail="targa troppo lunga")
        if len(model) > 64:
            raise HTTPException(status_code=400, detail="modello troppo lungo")
        if len(note) > 280:
            raise HTTPException(status_code=400, detail="nota troppo lunga")
        if not store.update_device(imei, plate, model, note):
            raise HTTPException(status_code=404, detail="IMEI non registrato")
        store.record_admin_action(
            user["username"],
            "device_update",
            imei,
            f"plate={plate or '-'} model={model or '-'}",
        )
        return {"status": "success", "imei": imei, "device": store.device(imei)}

    @app.post("/devices/{imei}/privacy")
    def set_device_privacy(
        imei: str,
        enabled: bool = Query(description="true attiva, false disattiva"),
        user: dict = Depends(current_user),
    ) -> dict:
        """Modalita' privacy GDPR: coordinate non salvate, km e CAN invariati.

        Resta l'eccezione SOS: la posizione di emergenza viene conservata
        nel record dell'allarme, con la sua retention separata.
        """
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        require_device(user, imei)
        if not store.set_privacy_mode(imei, enabled, user["username"]):
            raise HTTPException(status_code=404, detail="IMEI non registrato")
        return {
            "status": "success",
            "imei": imei,
            "privacy_mode": enabled,
            "device": store.device(imei),
        }

    @app.delete("/devices/{imei}")
    def delete_device(imei: str, user: dict = Depends(current_user)) -> dict:
        """Elimina il mezzo e i dati collegati. Operazione definitiva."""
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        require_device(user, imei)
        result = store.delete_device(imei)
        store.record_admin_action(
            user["username"],
            "device_delete",
            imei,
            f"record={result['removed']}",
        )
        return {"status": "success", "imei": imei, **result}

    @app.get("/positions/{imei}")
    def positions(
        imei: str,
        limit: int = Query(default=100, ge=1, le=5000),
        user: dict = Depends(current_user),
    ) -> dict:
        require_device(user, imei)
        rows = store.positions(imei, limit)
        if not rows:
            raise HTTPException(status_code=404, detail="Nessuna posizione per questo IMEI")
        return {"imei": imei, "count": len(rows), "positions": rows}

    @app.get("/positions/{imei}/history")
    def positions_history(
        imei: str,
        date: str = Query(description="Giorno locale YYYY-MM-DD"),
        tz_offset: int = Query(default=0, ge=-840, le=840,
                               description="Minuti di offset del browser"),
        epsilon: float = Query(default=8.0, gt=0, le=200,
                              description="Tolleranza RDP in metri"),
        user: dict = Depends(current_user),
    ) -> dict:
        """Coordinate del giorno, ordinate e semplificate per il playback."""
        require_device(user, imei)
        try:
            start_ms, end_ms = day_bounds(date, tz_offset)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        rows = store.positions_day(imei, start_ms, end_ms)
        payload = build_history(rows, epsilon_m=epsilon)
        return {
            "imei": imei, "date": date, "from_ms": start_ms, "to_ms": end_ms,
            **payload,
        }

    @app.get("/positions/{imei}/history/export")
    def export_positions_history(
        imei: str,
        date: str = Query(description="Giorno locale YYYY-MM-DD"),
        tz_offset: int = Query(default=0, ge=-840, le=840),
        format: str = Query(default="gpx", pattern="^(gpx|kml)$"),
        user: dict = Depends(current_user),
    ) -> Response:
        """Scarica il tracciato grezzo del giorno in GPX o KML.

        A differenza del playback non applica RDP: il file conserva tutti i
        punti ricevuti, con orari e velocita' dove disponibili.
        """
        require_device(user, imei)
        try:
            start_ms, end_ms = day_bounds(date, tz_offset)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        rows = store.positions_day(imei, start_ms, end_ms)
        body = (
            gpx_bytes(imei, date, rows)
            if format == "gpx"
            else kml_bytes(imei, date, rows)
        )
        media = (
            "application/gpx+xml"
            if format == "gpx"
            else "application/vnd.google-earth.kml+xml"
        )
        filename = f"{imei}-{date}.{format}"
        return Response(
            content=body,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/devices/{imei}/engine_block")
    async def engine_block(
        imei: str,
        block: bool = Query(description="true = blocca, false = sblocca"),
        requested_by: str | None = Query(default=None),
        user: dict = Depends(current_user),
    ) -> dict:
        """Blocca o sblocca i due relè del mezzo.

        Il blocco viene rifiutato se l'ultima posizione indica movimento: un
        motore non si interrompe mentre il veicolo viaggia. Ogni richiesta,
        accettata o rifiutata, finisce nell'audit con l'operatore.
        """
        if user["role"] not in CAN_BLOCK:
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        require_device(user, imei)
        operator = requested_by or user["username"]
        last = store.last_position(imei)
        action = "BLOCK" if block else "UNBLOCK"

        if block:
            allowed, reason = block_allowed(last)
            if not allowed:
                store.record_command(imei, action, "-", operator, False, reason)
                raise HTTPException(status_code=409, detail=reason)

        if ingest is None:
            raise HTTPException(status_code=503, detail="Ingestione non attiva")

        # Spento solo se il dato lo dice: un None non e' un quadro spento.
        ignition_off = bool(last and last.get("ignition") == 0)
        command = relay_command(
            dout_count=settings.douts, on=block, ignition_off=ignition_off
        )
        try:
            response = await asyncio.wait_for(
                ingest.send_command(imei, command), timeout=15
            )
        except DeviceOffline as exc:
            store.record_command(imei, action, command, operator, False, str(exc))
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except asyncio.TimeoutError as exc:
            detail = "il device non ha risposto al comando"
            store.record_command(imei, action, command, operator, False, detail)
            raise HTTPException(status_code=504, detail=detail) from exc

        store.record_command(
            imei,
            action,
            command,
            operator,
            True,
            f"ignition_off={ignition_off} risposta={response}",
        )
        return {
            "status": "success",
            "imei": imei,
            "blocked": block,
            "command": command,
            "device_response": response,
        }

    @app.get("/devices/{imei}/commands")
    def command_history(
        imei: str,
        limit: int = Query(default=50, ge=1, le=500),
        user: dict = Depends(current_user),
    ) -> dict:
        require_device(user, imei)
        rows = store.commands(imei, limit)
        return {"imei": imei, "count": len(rows), "commands": rows}

    @app.get("/commands")
    def all_commands(
        limit: int = Query(default=100, ge=1, le=1000),
        user: dict = Depends(current_user),
    ) -> dict:
        rows = store.recent_commands(limit, tenant_scope(user))
        return {"count": len(rows), "commands": rows}

    # --- ESG --------------------------------------------------------------

    @app.get("/esg")
    def esg(
        days: int = Query(default=30, ge=1, le=365),
        user: dict = Depends(current_user),
    ) -> dict:
        """Emissioni stimate nel periodo, dai chilometri letti sul CAN.

        La distanza e' misurata (odometro del veicolo), il consumo e' una
        stima dichiarata: il risultato e' un indicatore, non un report
        certificato.
        """
        now = datetime.now(timezone.utc)
        since_ms = int((now - timedelta(days=days)).timestamp() * 1000)
        report = build_report(
            store, settings, tenant_scope(user), since_ms, int(now.timestamp() * 1000)
        )
        return {
            "days": days,
            "from": (now - timedelta(days=days)).isoformat(timespec="seconds"),
            "to": now.isoformat(timespec="seconds"),
            **report,
        }

    @app.post("/devices/{imei}/esg")
    def set_esg_params(
        imei: str,
        fuel_l_per_100km: float | None = Query(default=None, ge=0, le=100),
        co2_kg_per_liter: float | None = Query(default=None, ge=0, le=10),
        user: dict = Depends(current_user),
    ) -> dict:
        """Consumo e fattore di emissione del singolo mezzo.

        Omettere un parametro lo riporta al valore di flotta (`None`).
        """
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        device = require_device(user, imei)
        updated = store.set_vehicle_esg(
            imei,
            fuel_l_per_100km,
            co2_kg_per_liter,
            created_by=user["username"],
        )
        if not updated:
            raise HTTPException(status_code=404, detail="IMEI non registrato")
        store.record_admin_action(
            user["username"],
            "esg_params",
            imei,
            f"fuel={fuel_l_per_100km} factor={co2_kg_per_liter}",
        )
        return {
            "status": "success",
            "imei": imei,
            "plate": device.get("plate"),
            "fuel_l_per_100km": fuel_l_per_100km,
            "co2_kg_per_liter": co2_kg_per_liter,
        }

    # --- snapshot ESG e audit amministrativo -------------------------------

    @app.post("/esg/snapshot")
    def create_esg_snapshot(
        month: str | None = Query(default=None, description="YYYY-MM, default mese scorso"),
        user: dict = Depends(current_user),
    ) -> dict:
        """Congela i numeri di un mese: lo snapshot non viene ricalcolato."""
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        now = datetime.now(timezone.utc)
        if month is None:
            month = previous_period(now, settings.report_timezone)
        try:
            month_window(month, now, settings.report_timezone)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        tenant = tenant_scope(user)
        result = close_month(
            settings, store, signing["key"], month, tenant, user["username"]
        )
        if result["status"] != "created":
            raise HTTPException(
                status_code=409, detail=f"snapshot {result['period']} gia' esistente"
            )
        return {
            "status": "success",
            "id": result["id"],
            "period": result["period"],
            "digest": result["digest"],
            "signature": result["signature"],
            "fingerprint": result["fingerprint"],
        }

    @app.get("/esg/snapshots")
    def list_esg_snapshots(
        limit: int = Query(default=24, ge=1, le=120),
        user: dict = Depends(current_user),
    ) -> dict:
        tenant = tenant_scope(user)
        rows = store.esg_snapshots(limit, None if tenant is None else str(tenant))
        return {"count": len(rows), "snapshots": rows}

    @app.get("/esg/snapshots/{snapshot_id}")
    def get_esg_snapshot(
        snapshot_id: int, user: dict = Depends(current_user)
    ) -> dict:
        row = store.esg_snapshot(snapshot_id)
        if row is None:
            raise HTTPException(status_code=404, detail="snapshot inesistente")
        tenant = tenant_scope(user)
        if tenant is not None and row["tenant_key"] != str(tenant):
            raise HTTPException(status_code=403, detail="snapshot di un altro cliente")
        return snapshot_view(row)

    @app.get("/esg/snapshots/{snapshot_id}/export")
    def export_esg_snapshot(
        snapshot_id: int, user: dict = Depends(current_user)
    ) -> dict:
        """Documento autonomo: si verifica senza server e senza database."""
        row = store.esg_snapshot(snapshot_id)
        if row is None:
            raise HTTPException(status_code=404, detail="snapshot inesistente")
        tenant = tenant_scope(user)
        if tenant is not None and row["tenant_key"] != str(tenant):
            raise HTTPException(status_code=403, detail="snapshot di un altro cliente")
        return {
            "format": "devicehub-esg-snapshot/1",
            "snapshot": {
                "id": row["id"],
                "period": row["period"],
                "created_at": row["created_at"],
                "created_by": row["created_by"],
                "digest": row["digest"],
                "signature": row.get("signature"),
                "public_key": row.get("public_key"),
                "fingerprint": fingerprint(row["public_key"])
                if row.get("public_key")
                else None,
            },
            "payload": row["payload"],
        }

    @app.get("/esg/public-key")
    def esg_public_key(user: dict = Depends(current_user)) -> dict:
        """Chiave pubblica per verificare gli snapshot fuori dal server."""
        pem = public_pem(signing["key"])
        return {"public_key": pem, "fingerprint": fingerprint(pem)}

    @app.get("/esg/signing-keys")
    def signing_keys(user: dict = Depends(current_user)) -> dict:
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        return {"keys": store.signing_keys()}

    @app.post("/esg/signing-key/rotate")
    def rotate_signing_key(user: dict = Depends(current_user)) -> dict:
        """Genera una nuova chiave e archivia la precedente.

        Gli snapshot gia' chiusi conservano la propria chiave pubblica, quindi
        restano verificabili dopo la rotazione.
        """
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        old_pem = public_pem(signing["key"])
        old_fp = fingerprint(old_pem)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        archive = Path(key_path).with_name(
            f"esg-signing-key-{old_fp[:12]}-{stamp}.pem"
        )
        source = Path(key_path)
        if source.exists():
            source.rename(archive)
        store.retire_signing_key(old_fp)
        new_key = load_or_create_private_key(key_path)
        signing["key"] = new_key
        new_pem = public_pem(new_key)
        new_fp = fingerprint(new_pem)
        store.register_signing_key(new_fp, new_pem, key_path, user["username"])
        store.record_admin_action(
            user["username"],
            "signing_key_rotate",
            new_fp,
            f"precedente={old_fp}",
        )
        return {
            "status": "success",
            "fingerprint": new_fp,
            "previous": old_fp,
            "archived_to": str(archive),
        }

    @app.post("/esg/snapshots/{snapshot_id}/send")
    def send_esg_report(
        request: Request,
        snapshot_id: int,
        to: str | None = Query(default=None, description="indirizzi separati da virgola"),
        user: dict = Depends(current_user),
    ) -> dict:
        """Invia il link del report congelato ai destinatari indicati."""
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(
                status_code=403, detail="Solo amministratore o responsabile"
            )
        row = store.esg_snapshot(snapshot_id)
        if row is None:
            raise HTTPException(status_code=404, detail="snapshot inesistente")
        tenant = tenant_scope(user)
        if tenant is not None and row["tenant_key"] != str(tenant):
            raise HTTPException(status_code=403, detail="snapshot di un altro cliente")
        provided = [part.strip() for part in (to or "").split(",") if part.strip()]
        recipients = provided or recipients_from(settings)
        if not recipients:
            raise HTTPException(
                status_code=503,
                detail="nessun destinatario: usare ?to=... oppure DEVICEHUB_REPORT_TO",
            )
        invalid = [address for address in recipients if not EMAIL_RE.match(address)]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail="indirizzi non validi: " + ", ".join(invalid),
            )
        snapshot = snapshot_head(row)
        link = create_link(
            settings,
            store,
            snapshot_id,
            settings.link_hours,
            user["username"],
            base=str(request.base_url),
        )
        branding = store.tenant_branding(row["tenant_key"]) or {}
        attachment = (
            f"report-{row['period']}.pdf",
            render_report_pdf(
                settings, snapshot, json.loads(row["payload"]), branding
            ),
        )
        try:
            sent = send_report(
                settings,
                snapshot,
                recipients,
                url=link["url"],
                attachment=attachment,
                display_name=branding.get("display_name"),
            )
        except MailNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except MailDeliveryError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        store.record_admin_action(
            user["username"], "esg_report_sent", row["period"], ", ".join(sent)
        )
        return {
            "status": "sent",
            "period": row["period"],
            "recipients": sent,
            "link": link["url"],
            "link_expires_at": link["expires_at"],
        }

    @app.post("/esg/snapshots/{snapshot_id}/link")
    def create_snapshot_link(
        request: Request,
        snapshot_id: int,
        hours: int = Query(default=72, ge=1, le=24 * 30),
        max_uses: int | None = Query(default=None, ge=1, le=1000),
        user: dict = Depends(current_user),
    ) -> dict:
        """Crea un link con scadenza, apribile senza account."""
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(
                status_code=403, detail="Solo amministratore o responsabile"
            )
        row = store.esg_snapshot(snapshot_id)
        if row is None:
            raise HTTPException(status_code=404, detail="snapshot inesistente")
        tenant = tenant_scope(user)
        if tenant is not None and row["tenant_key"] != str(tenant):
            raise HTTPException(status_code=403, detail="snapshot di un altro cliente")
        link = create_link(
            settings,
            store,
            snapshot_id,
            hours,
            user["username"],
            base=str(request.base_url),
            max_uses=max_uses,
        )
        return {"status": "success", **link}

    @app.post("/esg/snapshots/{snapshot_id}/link/revoke")
    def revoke_snapshot_links(
        snapshot_id: int,
        token_hash: str | None = Query(default=None),
        user: dict = Depends(current_user),
    ) -> dict:
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(
                status_code=403, detail="Solo amministratore o responsabile"
            )
        row = store.esg_snapshot(snapshot_id)
        if row is None:
            raise HTTPException(status_code=404, detail="snapshot inesistente")
        tenant = tenant_scope(user)
        if tenant is not None and row["tenant_key"] != str(tenant):
            raise HTTPException(status_code=403, detail="snapshot di un altro cliente")
        if token_hash:
            revoked = 1 if store.revoke_report_token(token_hash) else 0
        else:
            revoked = store.revoke_report_tokens(snapshot_id)
        store.record_admin_action(
            user["username"], "report_link_revoke", str(snapshot_id), f"link={revoked}"
        )
        return {"status": "success", "revoked": revoked}

    @app.get("/public/report/{token}")
    def public_report(token: str, request: Request) -> dict:
        """Report di un link con token: nessun account richiesto."""
        token_row = guard_token(request, token)
        row = store.esg_snapshot(token_row["snapshot_id"])
        if row is None:
            raise HTTPException(status_code=404, detail="snapshot inesistente")
        store.touch_report_token(token_row["token_hash"])
        return snapshot_view(row)

    @app.get("/public/report/{token}/pdf")
    def public_report_pdf(token: str, request: Request) -> Response:
        """PDF del report da un link con token."""
        token_row = guard_token(request, token)
        row = store.esg_snapshot(token_row["snapshot_id"])
        if row is None:
            raise HTTPException(status_code=404, detail="snapshot inesistente")
        store.touch_report_token(token_row["token_hash"])
        return pdf_response(row)

    @app.get("/r/{token}", response_class=HTMLResponse)
    def token_report_page(token: str, request: Request) -> HTMLResponse:
        """Pagina del report per un link con token."""
        ip = client_ip(request)
        if store.link_blocked(ip):
            return HTMLResponse(
                render_unavailable_page(settings, "Troppi tentativi da questo indirizzo: riprovare tra qualche minuto.", background_url("")),
                status_code=429,
            )
        token_row = resolve_link(store, token)
        if token_row is None:
            store.register_link_failure(
                ip, settings.link_attempt_limit, settings.link_block_minutes
            )
            return HTMLResponse(
                render_unavailable_page(settings, "Il collegamento non esiste o e' scaduto.", background_url("")),
                status_code=404,
            )
        limit = token_row.get("max_uses") or settings.link_max_uses
        if token_row["used_count"] >= limit:
            return HTMLResponse(
                render_unavailable_page(settings, "Il link ha raggiunto il numero massimo di aperture: chiedere un nuovo link.", background_url("")),
                status_code=410,
            )
        store.clear_link_failures(ip)
        row = store.esg_snapshot(token_row["snapshot_id"])
        key = str(row["tenant_key"]) if row else ""
        return HTMLResponse(render_token_page(settings, token, background_url(key)))

    @app.get("/esg/snapshots/{snapshot_id}/pdf")
    def export_esg_pdf(
        snapshot_id: int, user: dict = Depends(current_user)
    ) -> Response:
        """PDF del report, scaricabile con la sessione."""
        row = store.esg_snapshot(snapshot_id)
        if row is None:
            raise HTTPException(status_code=404, detail="snapshot inesistente")
        tenant = tenant_scope(user)
        if tenant is not None and row["tenant_key"] != str(tenant):
            raise HTTPException(status_code=403, detail="snapshot di un altro cliente")
        return pdf_response(row)

    @app.get("/esg/snapshots/{snapshot_id}/links")
    def list_snapshot_links(
        snapshot_id: int, user: dict = Depends(current_user)
    ) -> dict:
        """Link creati per uno snapshot, con stato e aperture."""
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(
                status_code=403, detail="Solo amministratore o responsabile"
            )
        row = store.esg_snapshot(snapshot_id)
        if row is None:
            raise HTTPException(status_code=404, detail="snapshot inesistente")
        tenant = tenant_scope(user)
        if tenant is not None and row["tenant_key"] != str(tenant):
            raise HTTPException(status_code=403, detail="snapshot di un altro cliente")
        links = store.report_tokens(snapshot_id)
        return {
            "count": len(links),
            "snapshot": {"id": row["id"], "period": row["period"]},
            "links": links,
        }

    @app.get("/links/blocked")
    def list_blocked_addresses(user: dict = Depends(current_user)) -> dict:
        """Indirizzi con tentativi falliti sui link, per la sblocco manuale."""
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        blocks = store.link_blocks()
        return {"count": len(blocks), "blocks": blocks}

    @app.post("/links/unblock")
    def unblock_address(
        ip: str = Query(min_length=1, max_length=64),
        user: dict = Depends(current_user),
    ) -> dict:
        """Azzera tentativi e blocco di un indirizzo."""
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        store.clear_link_failures(ip)
        store.record_admin_action(user["username"], "link_unblock", ip, "")
        return {"status": "success", "ip": ip}

    @app.get("/branding/preview.pdf")
    def preview_branding_pdf(
        display_name: str | None = Query(default=None, max_length=80),
        primary_color: str | None = Query(default=None, max_length=7),
        snapshot_id: int | None = Query(default=None, ge=1),
        user: dict = Depends(current_user),
    ) -> Response:
        """Anteprima del PDF con nome e colore non ancora salvati."""
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(
                status_code=403, detail="Solo amministratore o responsabile"
            )
        tenant = tenant_scope(user)
        key = "" if tenant is None else str(tenant)
        if snapshot_id is not None:
            row = store.esg_snapshot(snapshot_id)
            if row is None or row["tenant_key"] != key:
                raise HTTPException(status_code=404, detail="snapshot inesistente")
        else:
            rows = store.esg_snapshots(1, key)
            if not rows:
                raise HTTPException(
                    status_code=404,
                    detail="nessuno snapshot: chiudere prima un mese",
                )
            row = store.esg_snapshot(rows[0]["id"])
        branding = dict(store.tenant_branding(key) or {})
        if display_name and display_name.strip():
            branding["display_name"] = display_name.strip()
        if primary_color:
            color = normalize_color(primary_color)
            if color is None:
                raise HTTPException(
                    status_code=400, detail="colore non valido: usare #RRGGBB"
                )
            branding["primary_color"] = color
        payload = render_report_pdf(
            settings, snapshot_head(row), json.loads(row["payload"]), branding
        )
        return Response(
            content=payload,
            media_type="application/pdf",
            headers={"Content-Disposition": "inline; filename=anteprima-report.pdf"},
        )

    @app.get("/branding")
    def read_branding(user: dict = Depends(current_user)) -> dict:
        key = branding_key(user)
        row = store.tenant_branding(key) or {}
        bg_mode = str(row.get("bg_mode") or "default")
        return {
            "tenant_key": key,
            "display_name": row.get("display_name") or settings.company,
            "primary_color": row.get("primary_color") or DEFAULT_COLOR,
            "has_logo": bool(row.get("logo")),
            "logo_mime": row.get("logo_mime"),
            "bg_mode": bg_mode,
            "bg_image": row.get("bg_image") or "",
            "has_bg_file": bool(row.get("bg_data")),
            "bg_url": background_url(key),
            "has_saved_bg": bool(row.get("bg_image") or row.get("bg_data")),
            "bg_default": settings.custom_bg_image if bg_mode == "default" else "",
        }

    @app.post("/branding")
    def update_branding(
        payload: dict, user: dict = Depends(current_user)
    ) -> dict:
        """Nome e colore del report per il cliente dell'utente."""
        require_branding_role(user)
        key = branding_key(user)
        name = str(payload.get("display_name") or "").strip()[:80] or None
        raw_color = str(payload.get("primary_color") or "").strip()
        color = normalize_color(raw_color) if raw_color else None
        if raw_color and color is None:
            raise HTTPException(
                status_code=400, detail="colore non valido: usare #RRGGBB"
            )
        store.save_tenant_branding(key, name, color, user["username"])
        store.record_admin_action(
            user["username"], "branding_update", key or "globale", color or "-"
        )
        return {
            "status": "success",
            "display_name": name or settings.company,
            "primary_color": color or DEFAULT_COLOR,
        }

    @app.post("/branding/logo")
    async def upload_branding_logo(
        request: Request, user: dict = Depends(current_user)
    ) -> dict:
        """Logo del report: PNG o JPEG, fino a 512 KB, inviato come corpo."""
        require_branding_role(user)
        data = await request.body()
        if len(data) > MAX_LOGO_BYTES:
            raise HTTPException(
                status_code=413, detail="logo troppo grande: massimo 512 KB"
            )
        mime = (request.headers.get("content-type") or "").split(";")[0].strip()
        error = check_logo(data, mime)
        if error:
            raise HTTPException(status_code=400, detail=error)
        key = branding_key(user)
        store.save_tenant_logo(key, data, mime, user["username"])
        store.record_admin_action(
            user["username"], "branding_logo", key or "globale", mime
        )
        return {"status": "success", "bytes": len(data), "mime": mime}

    @app.delete("/branding/logo")
    def delete_branding_logo(user: dict = Depends(current_user)) -> dict:
        require_branding_role(user)
        key = branding_key(user)
        store.save_tenant_logo(key, None, None, user["username"])
        store.record_admin_action(
            user["username"], "branding_logo", key or "globale", "rimosso"
        )
        return {"status": "success", "has_logo": False}

    @app.post("/branding/background")
    def update_branding_background(
        payload: dict, user: dict = Depends(current_user)
    ) -> dict:
        """Modalita' dello sfondo: URL del cliente, predefinito del server o nessuno."""
        require_branding_role(user)
        key = branding_key(user)
        raw_url = str(payload.get("url") or "").strip()
        mode = str(
            payload.get("mode") or ("custom" if raw_url else "default")
        ).strip().lower()
        if mode not in ("custom", "default", "none"):
            raise HTTPException(
                status_code=400, detail="modalita' non valida: usare custom, default o none"
            )
        if raw_url and not custom_bg_url(raw_url):
            raise HTTPException(
                status_code=400,
                detail="URL non valido: usare http(s), un percorso o data:image",
            )
        try:
            # 'none' e 'default' spengono soltanto: URL e file restano salvati.
            store.set_tenant_background(
                key,
                mode,
                url=raw_url or None,
                updated_by=user["username"],
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        store.record_admin_action(
            user["username"],
            "branding_background",
            key or "globale",
            mode + (" " + raw_url[:60] if raw_url else ""),
        )
        row = store.tenant_branding(key) or {}
        return {
            "status": "success",
            "bg_mode": row.get("bg_mode") or mode,
            "bg_image": row.get("bg_image") or "",
            "bg_url": background_url(key),
            "has_saved_bg": bool(row.get("bg_image") or row.get("bg_data")),
        }

    @app.post("/branding/background/file")
    async def upload_branding_background(
        request: Request, user: dict = Depends(current_user)
    ) -> dict:
        """Sfondo caricato: PNG, JPEG o WebP fino a 1,5 MB, inviato come corpo."""
        require_branding_role(user)
        data = await request.body()
        if len(data) > MAX_BG_BYTES:
            raise HTTPException(
                status_code=413, detail="immagine troppo grande: massimo 1,5 MB"
            )
        mime = (request.headers.get("content-type") or "").split(";")[0].strip()
        error = check_background(data, mime)
        if error:
            raise HTTPException(status_code=400, detail=error)
        key = branding_key(user)
        store.set_tenant_background(
            key,
            "custom",
            data=data,
            mime=mime,
            updated_by=user["username"],
        )
        store.record_admin_action(
            user["username"], "branding_background", key or "globale", mime
        )
        return {
            "status": "success",
            "bg_mode": "custom",
            "bytes": len(data),
            "mime": mime,
            "bg_url": background_url(key),
        }

    @app.delete("/branding/background")
    def delete_branding_background(user: dict = Depends(current_user)) -> dict:
        """Torna al predefinito del server; per il tema pulito usare mode=none."""
        require_branding_role(user)
        key = branding_key(user)
        store.set_tenant_background(key, "default", updated_by=user["username"])
        store.record_admin_action(
            user["username"], "branding_background", key or "globale", "default"
        )
        return {
            "status": "success",
            "bg_mode": "default",
            "bg_url": background_url(key),
        }

    @app.get("/report/{snapshot_id}", response_class=HTMLResponse)
    def report_page(snapshot_id: int) -> str:
        """Report mensile congelato, stampabile."""
        row = store.esg_snapshot(snapshot_id)
        key = str(row["tenant_key"]) if row else ""
        return render_report_page(settings, snapshot_id, background_url(key))

    # --- aggiornamenti della piattaforma --------------------------------

    @app.get("/updates")
    def update_status(user: dict = Depends(current_user)) -> dict:
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        return updates.status(settings)

    @app.post("/updates/check")
    def check_updates(user: dict = Depends(current_user)) -> dict:
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        try:
            result = updates.check(settings)
        except updates.UpdateError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        store.record_admin_action(
            user["username"],
            "update_check",
            result.get("latest") or "-",
            f"disponibile={result['available']}",
        )
        return result

    @app.post("/updates/apply")
    def apply_update(
        payload: dict | None = None, user: dict = Depends(current_user)
    ) -> dict:
        """Installa il pacchetto verificato e, se richiesto, riavvia il servizio."""
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        try:
            manifest = updates.check(settings)
            if not manifest["available"]:
                raise HTTPException(
                    status_code=409, detail="nessun aggiornamento disponibile"
                )
            result = updates.install(settings, manifest)
        except updates.UpdateError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        store.record_admin_action(
            user["username"],
            "update_apply",
            result["version"],
            f"file={result['installed']} target={result['target']}"
            f" backup={result['backup'] or '-'}",
        )
        restart = True
        if isinstance(payload, dict) and "restart" in payload:
            restart = bool(payload.get("restart"))
        result["restart"] = restart
        if restart:
            updates.restart_later()
        return {"status": "success", **result}

    @app.get("/audit/admin")
    def admin_audit(
        limit: int = Query(default=100, ge=1, le=500),
        user: dict = Depends(current_user),
    ) -> dict:
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        rows = store.admin_actions(limit)
        return {"count": len(rows), "actions": rows}

    # --- SOC --------------------------------------------------------------

    @app.get("/alerts")
    def list_alerts(
        open_only: bool = Query(default=False),
        limit: int = Query(default=100, ge=1, le=1000),
        user: dict = Depends(current_user),
    ) -> dict:
        rows = store.alerts(limit, open_only, tenant_scope(user))
        return {"count": len(rows), "alerts": rows}

    @app.post("/alerts/{alert_id}/ack")
    def acknowledge(
        alert_id: int,
        by: str | None = Query(default=None),
        user: dict = Depends(current_user),
    ) -> dict:
        alert = store.alert(alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="Allarme inesistente")
        tenant = tenant_scope(user)
        if tenant is not None and alert.get("tenant_id") != tenant:
            raise HTTPException(status_code=403, detail="Allarme di un altro cliente")
        operator = by or user["username"]
        if not store.acknowledge_alert(alert_id, operator):
            raise HTTPException(status_code=409, detail="Allarme gia' preso in carico")
        return {"status": "success", "id": alert_id, "acknowledged_by": operator}

    # --- zone, regole di notifica, manutenzione, export ------------------

    def tenant_key(user: dict) -> str:
        tenant = tenant_scope(user)
        return "" if tenant is None else str(tenant)

    @app.get("/geofences")
    def list_geofences(user: dict = Depends(current_user)) -> dict:
        zones = store.geofences(tenant_key(user))
        return {"count": len(zones), "geofences": zones}

    @app.post("/geofences")
    def create_geofence(payload: dict, user: dict = Depends(current_user)) -> dict:
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        name = str(payload.get("name") or "").strip()[:60]
        if not name:
            raise HTTPException(status_code=400, detail="nome zona obbligatorio")
        shape = str(payload.get("shape") or "circle").strip().lower()
        if shape not in SHAPES:
            raise HTTPException(status_code=400, detail="tipo area non valido")
        try:
            schedule = normalize_schedule(payload.get("schedule"))
            timezone_name = normalize_timezone(payload.get("timezone"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if shape == "circle":
            try:
                latitude = float(payload.get("latitude"))
                longitude = float(payload.get("longitude"))
                radius_m = int(payload.get("radius_m") or 500)
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=400, detail="coordinate o raggio non validi"
                ) from exc
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise HTTPException(
                    status_code=400, detail="coordinate fuori intervallo"
                )
            if not 25 <= radius_m <= 50000:
                raise HTTPException(
                    status_code=400, detail="raggio tra 25 e 50000 metri"
                )
            geometry = []
        else:
            try:
                geometry = normalize_geometry(shape, payload.get("geometry"))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            latitude, longitude, radius_m = 0.0, 0.0, 0
        zone_id = store.create_geofence(
            tenant_key(user),
            name,
            latitude,
            longitude,
            radius_m,
            user["username"],
            shape=shape,
            geometry=geometry,
            schedule=schedule,
            timezone_name=timezone_name,
        )
        store.record_admin_action(
            user["username"], "geofence_create", str(zone_id),
            f"{name} shape={shape}",
        )
        return {"status": "success", "id": zone_id, "shape": shape}

    @app.delete("/geofences/{geofence_id}")
    def delete_geofence(
        geofence_id: int, user: dict = Depends(current_user)
    ) -> dict:
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        if not store.delete_geofence(geofence_id, tenant_key(user)):
            raise HTTPException(status_code=404, detail="zona inesistente")
        store.record_admin_action(
            user["username"], "geofence_delete", str(geofence_id), ""
        )
        return {"status": "success", "id": geofence_id}

    @app.get("/alert-rules")
    def read_alert_rules(user: dict = Depends(current_user)) -> dict:
        rules = store.alert_rules(tenant_key(user))
        return {"tenant_key": tenant_key(user), "rules": rules}

    @app.post("/alert-rules")
    def save_alert_rule(payload: dict, user: dict = Depends(current_user)) -> dict:
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        kind = str(payload.get("kind") or "")
        if kind not in ("speed", "theft"):
            raise HTTPException(status_code=400, detail="tipo regola non valido")
        try:
            threshold = float(payload.get("threshold"))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="soglia non valida") from exc
        if not 1 <= threshold <= 300:
            raise HTTPException(status_code=400, detail="soglia tra 1 e 300")
        enabled = bool(payload.get("enabled", True))
        store.save_alert_rule(
            tenant_key(user), kind, threshold, enabled, user["username"]
        )
        store.record_admin_action(
            user["username"],
            "alert_rule_update",
            kind,
            f"soglia={threshold:.0f} attiva={enabled}",
        )
        return {
            "status": "success",
            "kind": kind,
            "threshold": threshold,
            "enabled": enabled,
        }

    @app.get("/work-hours")
    def read_work_hours(user: dict = Depends(current_user)) -> dict:
        return {
            "tenant_key": tenant_key(user),
            "work_hours": store.work_hours(tenant_key(user)),
        }

    @app.post("/work-hours")
    def save_work_hours(payload: dict, user: dict = Depends(current_user)) -> dict:
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        enabled = bool(payload.get("enabled", True))
        try:
            schedule = normalize_schedule(payload.get("schedule"))
            timezone_name = normalize_timezone(payload.get("timezone"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if enabled and not schedule:
            raise HTTPException(
                status_code=400, detail="serve almeno una fascia oraria"
            )
        store.save_work_hours(
            tenant_key(user), enabled, schedule, timezone_name, user["username"]
        )
        store.record_admin_action(
            user["username"],
            "work_hours_update",
            str(enabled),
            f"finestre={len(schedule)} fuso={timezone_name}",
        )
        return {
            "status": "success",
            "enabled": enabled,
            "schedule": schedule,
            "timezone": timezone_name,
        }

    @app.get("/maintenance")
    def list_maintenance(
        imei: str | None = Query(default=None),
        open_only: bool = Query(default=False),
        user: dict = Depends(current_user),
    ) -> dict:
        if imei:
            require_device(user, imei)
        items = store.maintenance(tenant_scope(user), imei, open_only)
        return {"count": len(items), "items": items}

    @app.post("/maintenance")
    def create_maintenance(payload: dict, user: dict = Depends(current_user)) -> dict:
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        imei = str(payload.get("imei") or "")
        require_device(user, imei)
        kind = str(payload.get("kind") or "").strip()[:40]
        if not kind:
            raise HTTPException(status_code=400, detail="tipo intervento obbligatorio")
        due_date = str(payload.get("due_date") or "").strip() or None
        if due_date:
            try:
                datetime.fromisoformat(due_date)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="data non valida (YYYY-MM-DD)"
                ) from exc
        raw_km = payload.get("due_odometer_km")
        due_km = None
        if raw_km not in (None, ""):
            try:
                due_km = float(raw_km)
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=400, detail="chilometraggio non valido"
                ) from exc
            if due_km < 0:
                raise HTTPException(status_code=400, detail="chilometraggio negativo")
        if not due_date and due_km is None:
            raise HTTPException(
                status_code=400, detail="serve una data o un chilometraggio"
            )
        repeat_km = payload.get("repeat_km")
        if repeat_km not in (None, ""):
            try:
                repeat_km = float(repeat_km)
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=400, detail="ripetizione km non valida"
                ) from exc
            if repeat_km <= 0:
                raise HTTPException(
                    status_code=400, detail="ripetizione km positiva"
                )
        else:
            repeat_km = None
        repeat_months = payload.get("repeat_months")
        if repeat_months not in (None, ""):
            try:
                repeat_months = int(repeat_months)
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=400, detail="ripetizione mesi non valida"
                ) from exc
            if repeat_months <= 0:
                raise HTTPException(
                    status_code=400, detail="ripetizione mesi positiva"
                )
        else:
            repeat_months = None
        item_id = store.create_maintenance(
            imei,
            kind,
            due_date,
            due_km,
            str(payload.get("note") or "").strip()[:200] or None,
            user["username"],
            repeat_km,
            repeat_months,
        )
        store.record_admin_action(
            user["username"], "maintenance_create", imei, f"{kind} id={item_id}"
        )
        return {"status": "success", "id": item_id}

    @app.post("/maintenance/{maintenance_id}/complete")
    def complete_maintenance(
        maintenance_id: int, user: dict = Depends(current_user)
    ) -> dict:
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        result = store.complete_maintenance(
            maintenance_id, user["username"], tenant_scope(user)
        )
        if result is None:
            raise HTTPException(status_code=404, detail="intervento inesistente")
        store.record_admin_action(
            user["username"],
            "maintenance_complete",
            str(maintenance_id),
            f"next={result.get('next_id') or '-'}",
        )
        return {"status": "success", **result}

    @app.get("/solutions")
    def read_solution(user: dict = Depends(current_user)) -> dict:
        row = store.tenant_solution(tenant_key(user))
        return {
            "tenant_key": tenant_key(user),
            "vertical": row["vertical"],
            "connectivity": row["connectivity"],
            "maps": row["maps"],
            "verticals": sorted(VERTICAL_IDS),
            "vertical_details": vertical_details(),
            "connectivities": ["4g", "2g", "swiss_global"],
            "maps_options": ["osm", "google", "swiss"],
        }

    @app.post("/solutions")
    def save_solution(
        payload: dict, user: dict = Depends(current_user)
    ) -> dict:
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        vertical = str(payload.get("vertical") or "")
        connectivity = str(payload.get("connectivity") or "")
        maps = str(payload.get("maps") or "")
        allowed = {
            "vertical": VERTICAL_IDS,
            "connectivity": {"4g", "2g", "swiss_global"},
            "maps": {"osm", "google", "swiss"},
        }
        for field, value in (
            ("vertical", vertical),
            ("connectivity", connectivity),
            ("maps", maps),
        ):
            if value not in allowed[field]:
                raise HTTPException(status_code=400, detail=f"{field} non valido")
        store.save_tenant_solution(
            tenant_key(user), vertical, connectivity, maps, user["username"]
        )
        return {"status": "success"}

    @app.get("/tenants")
    def list_tenants(user: dict = Depends(current_user)) -> dict:
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        return {"tenants": store.tenants()}

    @app.post("/devices/{imei}/driver")
    def assign_driver(
        imei: str, payload: dict, user: dict = Depends(current_user)
    ) -> dict:
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        row = store.device(imei)
        if not row or (
            user["role"] == "manager" and row.get("tenant_id") != tenant_scope(user)
        ):
            raise HTTPException(status_code=404, detail="mezzo non trovato")
        badge = str(payload.get("badge") or "").strip() or None
        if badge and badge not in {
            item["badge"] for item in store.drivers(row.get("tenant_id"))
        }:
            raise HTTPException(status_code=400, detail="badge non valido")
        store.set_device_driver(imei, badge)
        return {"status": "success", "badge": badge}

    @app.post("/devices/{imei}/trailer")
    def assign_trailer(
        imei: str, payload: dict, user: dict = Depends(current_user)
    ) -> dict:
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        row = store.device(imei)
        if not row or (
            user["role"] == "manager" and row.get("tenant_id") != tenant_scope(user)
        ):
            raise HTTPException(status_code=404, detail="mezzo non trovato")
        plate = str(payload.get("plate") or "").strip() or None
        kind = str(payload.get("type") or "").strip() or None
        if plate and len(plate) > 32:
            raise HTTPException(status_code=400, detail="targa rimorchio troppo lunga")
        if kind and len(kind) > 40:
            raise HTTPException(status_code=400, detail="tipo rimorchio troppo lungo")
        store.set_device_trailer(imei, plate, kind)
        return {"status": "success", "plate": plate, "type": kind}

    @app.get("/drivers")
    def list_drivers(user: dict = Depends(current_user)) -> dict:
        return {"drivers": store.drivers(tenant_scope(user))}

    @app.post("/drivers")
    def create_driver(
        payload: dict, user: dict = Depends(current_user)
    ) -> dict:
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        name = str(payload.get("name") or "").strip()
        badge = str(payload.get("badge") or "").strip()
        if not name or not badge:
            raise HTTPException(status_code=400, detail="nome e badge obbligatori")
        tenant = tenant_scope(user)
        if user["role"] == "admin" and payload.get("tenant_id") not in (None, ""):
            tenant = int(payload["tenant_id"])
            if not any(item["id"] == tenant for item in store.tenants()):
                raise HTTPException(status_code=400, detail="cliente inesistente")
        row = store.add_driver(name, badge, tenant)
        return {"status": "success", "driver": row}

    @app.get("/driving")
    def driving(
        hours: int = Query(default=24, ge=1, le=168),
        points: int = Query(default=5000, ge=100, le=20000),
        user: dict = Depends(current_user),
    ) -> dict:
        scope = tenant_scope(user)
        records = store.driving_positions(hours, scope, points)
        registered = store.drivers(scope)
        names = {item["badge"]: item["name"] for item in registered}
        result = analyse(
            records,
            settings.driver_io_id,
            names,
            settings.harsh_accel_kmh_s,
            settings.harsh_brake_kmh_s,
        )
        known = {item["badge"] for item in result["drivers"]}
        for item in registered:
            if item["badge"] not in known:
                result["drivers"].append(
                    {
                        "badge": item["badge"],
                        "name": item["name"],
                        "accel": 0,
                        "brake": 0,
                        "events": 0,
                        "score": 100,
                    }
                )
        return result

    def notification_channels() -> dict:
        """Stato dei canali senza esporre credenziali o token."""
        return {
            "email": {
                "enabled": settings.smtp_enabled,
                "mode": settings.smtp_mode,
                "configured": bool(
                    settings.smtp_enabled
                    and settings.smtp_host
                    and settings.report_from
                ),
                "from": settings.report_from,
            },
            "sms": {
                "enabled": settings.sms_enabled,
                "mode": settings.sms_mode,
                "provider": settings.sms_provider,
                "configured": bool(
                    settings.sms_enabled
                    and (settings.sms_mode == "simulated" or settings.sms_url)
                ),
            },
            "voice": {
                "enabled": settings.voice_enabled,
                "mode": settings.voice_mode,
                "provider": settings.voice_provider,
                "configured": bool(settings.voice_enabled),
            },
            "demo_mode": settings.demo_mode,
            "environment": settings.environment,
        }

    @app.get("/notifications")
    def read_notifications(user: dict = Depends(current_user)) -> dict:
        key = tenant_key(user)
        row = store.tenant_notification_settings(key)
        return {
            "tenant_key": key,
            "emails": row.get("emails") or "",
            "phones": row.get("phones") or "",
            "global_emails": settings.alert_emails,
            "global_phones": settings.sms_to,
            "cooldown_minutes": settings.alert_cooldown_minutes,
            "channels": notification_channels(),
        }

    @app.get("/notifications/outbox")
    def read_notification_outbox(
        limit: int = Query(default=100, ge=1, le=500),
        user: dict = Depends(current_user),
    ) -> dict:
        """Ultime notifiche; admin vede tutto, gli altri il proprio cliente."""
        if user["role"] not in ("admin", "manager", "soc"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        rows = store.notification_outbox(tenant_scope(user), limit)
        return {
            "count": len(rows),
            "items": rows,
            "channels": notification_channels(),
        }

    @app.post("/notifications")
    def save_notifications(
        payload: dict, user: dict = Depends(current_user)
    ) -> dict:
        if user["role"] not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        emails = str(payload.get("emails") or "").strip()
        phones = str(payload.get("phones") or "").strip()
        invalid = [
            item.strip()
            for item in emails.split(",")
            if item.strip() and not EMAIL_RE.match(item.strip())
        ]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"email non valide: {', '.join(invalid)}",
            )
        bad_phones = [
            item.strip()
            for item in phones.split(",")
            if item.strip() and not re.fullmatch(r"\+?[0-9][0-9 .-]{5,20}", item.strip())
        ]
        if bad_phones:
            raise HTTPException(
                status_code=400,
                detail=f"numeri non validi: {', '.join(bad_phones)}",
            )
        store.save_tenant_notification_settings(
            tenant_key(user), emails, phones, user["username"]
        )
        store.record_admin_action(
            user["username"],
            "notification_settings",
            tenant_key(user) or "globale",
            f"email={len(emails.split(',')) if emails else 0}",
        )
        return {"status": "success", "emails": emails, "phones": phones}

    @app.post("/sms/receipts")
    async def sms_receipt(request: Request) -> dict:
        """Webhook del gateway SMS (token condiviso, nessuna sessione)."""
        if not settings.sms_receipt_token:
            raise HTTPException(
                status_code=503, detail="ricevute SMS non configurate"
            )
        provided = request.headers.get("x-receipt-token") or request.query_params.get(
            "token"
        )
        if not hmac.compare_digest(
            str(provided or ""), settings.sms_receipt_token
        ):
            raise HTTPException(status_code=403, detail="token ricevuta non valido")
        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="JSON non valido") from exc
        provider_id = str(
            payload.get("id") or payload.get("message_id") or ""
        ) or None
        recipient = str(payload.get("to") or payload.get("recipient") or "") or None
        status = str(payload.get("status") or payload.get("state") or "") or None
        receipt_id = store.record_sms_receipt(
            provider_id,
            recipient,
            status,
            json.dumps(payload)[:2000],
        )
        return {"status": "success", "id": receipt_id}

    @app.get("/webhooks/status")
    def webhook_status(user: dict = Depends(current_user)) -> dict:
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        return {
            "configured": bool(settings.webhook_url and settings.webhook_secret),
            "outbox": store.webhook_stats(),
        }

    @app.get("/sms/receipts")
    def list_sms_receipts(
        limit: int = Query(default=200, ge=1, le=1000),
        user: dict = Depends(current_user),
    ) -> dict:
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Solo amministratore")
        rows = store.sms_receipts(limit)
        return {"count": len(rows), "receipts": rows}

    @app.get("/safety/checks")
    def list_safety_checks(
        limit: int = Query(default=200, ge=1, le=1000),
        user: dict = Depends(current_user),
    ) -> dict:
        checks = store.safety_checks(tenant_scope(user), limit)
        return {
            "count": len(checks),
            "checks": checks,
            "summary": store.safety_summary(tenant_scope(user)),
        }

    @app.post("/safety/checks")
    def create_safety_check(
        payload: dict, user: dict = Depends(current_user)
    ) -> dict:
        """Registra un controllo; una non conformita' apre un allarme SAFETY."""
        if user["role"] not in ("admin", "manager", "soc"):
            raise HTTPException(status_code=403, detail="Permesso insufficiente")
        imei = str(payload.get("imei") or "")
        require_device(user, imei)
        kind = str(payload.get("kind") or "").strip()[:60]
        if not kind:
            raise HTTPException(status_code=400, detail="tipo controllo obbligatorio")
        compliant = bool(payload.get("compliant", True))
        note = str(payload.get("note") or "").strip()[:300] or None
        check_id = store.create_safety_check(
            imei, kind, compliant, note, user["username"]
        )
        if not compliant:
            detail = note or f"Controllo non conforme: {kind}"
            store.raise_alert(imei, "SAFETY", "HIGH", detail, None)
        store.record_admin_action(
            user["username"],
            "safety_check",
            imei,
            f"{kind} conforme={compliant}",
        )
        return {
            "status": "success",
            "id": check_id,
            "compliant": compliant,
        }

    @app.get("/activity/{imei}")
    def vehicle_activity(
        imei: str,
        hours: int = Query(default=24, ge=1, le=24 * 30),
        stop_minutes: int = Query(default=5, ge=1, le=180),
        user: dict = Depends(current_user),
    ) -> dict:
        """Tragitti e soste ricavati dalle posizioni delle ultime ore."""
        require_device(user, imei)
        since_ms = int(
            (datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp() * 1000
        )
        return store.activity(imei, since_ms, stop_minutes)

    @app.get("/fuel/report")
    def fuel_report(
        month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
        user: dict = Depends(current_user),
    ) -> dict:
        """Km, litri stimati, costo, minimo e cali anomali del mese."""
        now = datetime.now(timezone.utc)
        if month is None:
            month = previous_period(now, settings.report_timezone)
        try:
            since_ms, until_ms, period = month_window(
                month, now, settings.report_timezone
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="mese non valido") from exc
        report = store.fuel_report(
            since_ms,
            until_ms,
            tenant_scope(user),
            settings.fuel_price_eur,
            settings.idle_l_per_hour,
            settings.fuel_l_per_100km,
            settings.fuel_theft_liters,
        )
        return {"month": period, **report}

    @app.get("/export/{dataset}")
    def export_dataset(
        dataset: str,
        format: str = Query(default="csv", pattern="^(csv|xlsx)$"),
        imei: str | None = Query(default=None),
        hours: int = Query(default=24, ge=1, le=24 * 90),
        user: dict = Depends(current_user),
    ) -> Response:
        """Esporta dispositivi, posizioni, manutenzione o allarmi in CSV o XLSX."""
        tenant = tenant_scope(user)
        if dataset == "devices":
            headers = [
                "mezzo", "imei", "cliente", "stato", "ultimo_contatto",
                "latitudine", "longitudine", "velocita_kmh", "km",
                "carburante_l", "temperatura_c", "rpm",
            ]
            rows = [
                [
                    device.get("plate") or device.get("model") or device["imei"],
                    device["imei"],
                    device.get("tenant_name") or "",
                    device.get("status") or "",
                    device.get("last_seen") or "",
                    device.get("latitude"),
                    device.get("longitude"),
                    device.get("speed"),
                    round(device["odometer_m"] / 1000, 1)
                    if device.get("odometer_m") is not None
                    else None,
                    device.get("can_fuel_liters"),
                    device.get("engine_temp"),
                    device.get("can_rpm"),
                ]
                for device in store.devices(tenant)
            ]
        elif dataset == "positions":
            if not imei:
                raise HTTPException(
                    status_code=400, detail="imei obbligatorio per le posizioni"
                )
            require_device(user, imei)
            since_ms = int(
                (datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp()
                * 1000
            )
            headers = [
                "timestamp_ms", "latitudine", "longitudine", "velocita_kmh",
                "accensione", "km", "carburante_l", "temperatura_c", "rpm",
            ]
            rows = [
                [
                    point["ts_ms"],
                    point["latitude"],
                    point["longitude"],
                    point["speed"],
                    point["ignition"],
                    round(point["odometer_m"] / 1000, 1)
                    if point.get("odometer_m") is not None
                    else None,
                    point.get("can_fuel_liters"),
                    point.get("engine_temp"),
                    point.get("can_rpm"),
                ]
                for point in store.positions_range(imei, since_ms)
            ]
        elif dataset == "trips":
            since_ms = int(
                (datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp()
                * 1000
            )
            zone = report_zone(settings.report_timezone)
            headers = [
                "mezzo", "imei", "inizio", "fine", "durata_min", "km",
                "velocita_max_kmh", "partenza_lat", "partenza_lon",
                "arrivo_lat", "arrivo_lon",
            ]

            def local_stamp(ts_ms: int) -> str:
                return datetime.fromtimestamp(ts_ms / 1000, zone).strftime(
                    "%d/%m/%Y %H:%M"
                )

            rows = []
            for device in store.devices(tenant):
                hidden = bool(device.get("privacy_mode"))
                report = store.activity(device["imei"], since_ms)
                for trip in report["trips"]:
                    rows.append(
                        [
                            device.get("plate") or device["imei"],
                            device["imei"],
                            local_stamp(trip["start_ms"]),
                            local_stamp(trip["end_ms"]),
                            trip.get("duration_min"),
                            round((trip.get("distance_m") or 0) / 1000, 2),
                            round(trip.get("max_speed") or 0, 1),
                            None if hidden else trip.get("start_latitude"),
                            None if hidden else trip.get("start_longitude"),
                            None if hidden else trip.get("end_latitude"),
                            None if hidden else trip.get("end_longitude"),
                        ]
                    )
        elif dataset == "maintenance":
            headers = [
                "mezzo", "imei", "tipo", "scadenza", "km_previsti",
                "km_attuali", "stato", "note", "completato_il", "completato_da",
            ]
            state_labels = {
                "planned": "pianificato",
                "overdue": "scaduto",
                "completed": "completato",
            }
            rows = [
                [
                    item.get("plate") or item["imei"],
                    item["imei"],
                    item["kind"],
                    item.get("due_date") or "",
                    item.get("due_odometer_km"),
                    item.get("odometer_km"),
                    state_labels.get(item.get("status") or "", item.get("status") or ""),
                    item.get("note") or "",
                    item.get("completed_at") or "",
                    item.get("completed_by") or "",
                ]
                for item in store.maintenance(tenant)
            ]
        elif dataset == "fuel":
            now = datetime.now(timezone.utc)
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            following = (
                start.replace(year=start.year + 1, month=1)
                if start.month == 12
                else start.replace(month=start.month + 1)
            )
            report = store.fuel_report(
                int(start.timestamp() * 1000),
                int(following.timestamp() * 1000) - 1,
                tenant,
                settings.fuel_price_eur,
                settings.idle_l_per_hour,
                settings.fuel_l_per_100km,
                settings.fuel_theft_liters,
            )
            headers = [
                "mezzo", "imei", "km", "consumo_l_100km", "litri_stimati",
                "costo_eur", "ore_minimo", "litri_minimo", "calo_carburante_l",
                "furto_sospetto",
            ]
            rows = [
                [
                    item["plate"] or item["imei"],
                    item["imei"],
                    item["km"],
                    item["consumption_l_per_100km"],
                    item["liters"],
                    item["cost_eur"],
                    item["idle_hours"],
                    item["idle_liters"],
                    item["fuel_drop_liters"],
                    "si" if item["theft_suspected"] else "no",
                ]
                for item in report["items"]
            ]
        elif dataset == "alerts":
            headers = [
                "id", "imei", "mezzo", "tipo", "gravita", "dettaglio",
                "creato", "preso_in_carico_da",
            ]
            rows = [
                [
                    alert["id"],
                    alert["imei"],
                    alert.get("plate") or "",
                    alert["kind"],
                    alert["severity"],
                    alert.get("detail") or "",
                    alert.get("created_at") or "",
                    alert.get("acknowledged_by") or "",
                ]
                for alert in store.alerts(1000, False, tenant)
            ]
        else:
            raise HTTPException(status_code=404, detail="dataset non disponibile")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        filename = f"{dataset}-{stamp}.{format}"
        if format == "xlsx":
            payload = xlsx_bytes(dataset, headers, rows)
            media = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            payload = csv_bytes(headers, rows)
            media = "text/csv; charset=utf-8"
        return Response(
            content=payload,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # --- provisioning -----------------------------------------------------

    @app.get("/provisioning/{imei}")
    def provisioning(
        imei: str,
        host: str | None = Query(default=None),
        port: int | None = Query(default=None),
        apn: str | None = Query(default=None),
        codec: int | None = Query(default=None),
        user: dict = Depends(current_user),
    ) -> dict:
        try:
            plan = teltonika_plan(
                imei=imei,
                host=host or settings.public_host,
                port=port or settings.public_port,
                apn=apn or settings.apn or "inserire.apn",
                codec=codec or settings.codec,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return plan.as_dict()

    @app.get("/provisioning/{imei}/sms.txt", response_class=PlainTextResponse)
    def provisioning_text(
        imei: str,
        host: str | None = Query(default=None),
        port: int | None = Query(default=None),
        apn: str | None = Query(default=None),
        codec: int | None = Query(default=None),
        user: dict = Depends(current_user),
    ) -> str:
        try:
            plan = teltonika_plan(
                imei=imei,
                host=host or settings.public_host,
                port=port or settings.public_port,
                apn=apn or settings.apn or "inserire.apn",
                codec=codec or settings.codec,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return plan.as_text()

    if settings.webhook_url and settings.webhook_secret:
        def webhook_worker() -> None:
            while True:
                try:
                    flush_outbox(store, settings)
                except WebhookNotConfigured:
                    pass
                except Exception:  # pragma: no cover - difesa del worker
                    pass
                time.sleep(5)

        threading.Thread(target=webhook_worker, daemon=True).start()

    return app
