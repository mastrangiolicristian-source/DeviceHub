"""Persistenza su SQLite dell'ingestione, con ponte verso la dashboard esistente.

Tabelle proprie (devices, positions) + aggiornamento best-effort della tabella
`vehicles` dell'applicazione FastAPI, se il database la contiene: cosi' i mezzi
gia' censiti iniziano a muoversi sulla mappa senza modificare l'app.
"""

from __future__ import annotations

import json
import math
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .branding import content_digest
from .profiles import VEHICLE_FIELD_MAP, DeviceProfile
from .geofence import (
    DEFAULT_TIMEZONE,
    line_crossed,
    point_in_polygon,
    polygon_crossed,
    schedule_active,
)
from .teltonika import AvlRecord


_WEEKDAYS_IT = (
    "lunedi",
    "martedi",
    "mercoledi",
    "giovedi",
    "venerdi",
    "sabato",
    "domenica",
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    imei        TEXT PRIMARY KEY,
    model       TEXT,
    plate       TEXT,
    tenant      TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',
    first_seen  TEXT NOT NULL,
    last_seen   TEXT,
    last_ip     TEXT,
    note        TEXT,
    driver_badge  TEXT,
    trailer_plate TEXT,
    trailer_type  TEXT,
    privacy_mode  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS positions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    imei                 TEXT NOT NULL,
    ts_ms                INTEGER NOT NULL,
    received_at          TEXT NOT NULL,
    latitude             REAL,
    longitude            REAL,
    speed                REAL,
    altitude             INTEGER,
    angle                INTEGER,
    satellites           INTEGER,
    ignition             INTEGER,
    odometer_m           INTEGER,
    battery_voltage      REAL,
    can_fuel_liters      REAL,
    can_fuel_pct         REAL,
    engine_temp          REAL,
    can_rpm              INTEGER,
    engine_hours         REAL,
    codec_id             INTEGER,
    io_json              TEXT,
    UNIQUE(imei, ts_ms)
);

CREATE INDEX IF NOT EXISTS idx_positions_imei_ts
    ON positions (imei, ts_ms DESC);
-- Retention: ricerca globale per data, non per singolo mezzo.
CREATE INDEX IF NOT EXISTS idx_positions_ts ON positions (ts_ms);

CREATE TABLE IF NOT EXISTS command_audit (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    imei         TEXT NOT NULL,
    action       TEXT NOT NULL,
    command      TEXT NOT NULL,
    requested_by TEXT,
    accepted     INTEGER NOT NULL,
    detail       TEXT,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_command_audit_imei
    ON command_audit (imei, id DESC);

CREATE TABLE IF NOT EXISTS tenants (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'manager',
    tenant_id     INTEGER,
    full_name     TEXT,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    imei            TEXT NOT NULL,
    kind            TEXT NOT NULL,
    severity        TEXT NOT NULL DEFAULT 'HIGH',
    detail          TEXT,
    ts_ms           INTEGER,
    latitude        REAL,
    longitude       REAL,
    created_at      TEXT NOT NULL,
    acknowledged_at TEXT,
    acknowledged_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_alerts_imei ON alerts (imei, id DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_open ON alerts (acknowledged_at);

-- Storia dei parametri ESG: un cambio vale dalla sua decorrenza in avanti,
-- cosi' un report gia' calcolato non cambia retroattivamente.
CREATE TABLE IF NOT EXISTS vehicle_esg_params (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    imei            TEXT NOT NULL,
    fuel_l_per_100km REAL,
    co2_kg_per_liter REAL,
    valid_from_ms   INTEGER NOT NULL,
    created_at      TEXT NOT NULL,
    created_by      TEXT
);

CREATE INDEX IF NOT EXISTS idx_esg_params_imei
    ON vehicle_esg_params (imei, valid_from_ms DESC);

-- Azioni amministrative: chi ha fatto cosa e quando.
CREATE TABLE IF NOT EXISTS admin_audit (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    actor      TEXT,
    action     TEXT NOT NULL,
    target     TEXT,
    detail     TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_id ON admin_audit (id DESC);

-- Registro delle chiavi di firma: le ritirate restano per verificare gli
-- snapshot firmati prima della rotazione.
CREATE TABLE IF NOT EXISTS signing_keys (
    fingerprint  TEXT PRIMARY KEY,
    public_key   TEXT NOT NULL,
    private_path TEXT,
    created_at   TEXT NOT NULL,
    created_by   TEXT,
    retired_at   TEXT,
    active       INTEGER NOT NULL DEFAULT 1
);

-- Link con token per i report: si conserva solo l'impronta del token.
CREATE TABLE IF NOT EXISTS report_tokens (
    token_hash   TEXT PRIMARY KEY,
    snapshot_id  INTEGER NOT NULL,
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    created_by   TEXT,
    revoked      INTEGER NOT NULL DEFAULT 0,
    used_count   INTEGER NOT NULL DEFAULT 0,
    last_used_at TEXT,
    max_uses     INTEGER NOT NULL DEFAULT 25
);

-- Branding del report per cliente (tenant vuoto = globale).
CREATE TABLE IF NOT EXISTS tenant_branding (
    tenant_key    TEXT PRIMARY KEY,
    display_name  TEXT,
    primary_color TEXT,
    logo          BLOB,
    logo_mime     TEXT,
    -- Sfondo della dashboard: 'default' (usa il server), 'custom' (URL o
    -- file del cliente) o 'none' (nessuno, senza risalire al predefinito).
    bg_mode       TEXT,
    bg_image      TEXT,
    bg_data       BLOB,
    bg_mime       TEXT,
    -- Impronta del contenuto: firma l'URL pubblico e cambia solo quando
    -- cambia l'immagine, non quando cambia la modalita'.
    bg_stamp      TEXT,
    updated_at    TEXT,
    updated_by    TEXT
);

-- Tentativi falliti sui link, per indirizzo: serve al blocco temporaneo.
CREATE TABLE IF NOT EXISTS link_attempts (
    ip            TEXT PRIMARY KEY,
    failures      INTEGER NOT NULL DEFAULT 0,
    first_at      TEXT NOT NULL,
    blocked_until TEXT
);

-- Tentativi di accesso falliti per indirizzo, separati dai link pubblici.
CREATE TABLE IF NOT EXISTS auth_attempts (
    ip            TEXT PRIMARY KEY,
    failures      INTEGER NOT NULL DEFAULT 0,
    first_at      TEXT NOT NULL,
    blocked_until TEXT
);

-- Snapshot mensili ESG: payload congelato + impronta per verifica.
CREATE TABLE IF NOT EXISTS esg_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period          TEXT NOT NULL,
    tenant_key      TEXT NOT NULL DEFAULT '',
    payload         TEXT NOT NULL,
    digest          TEXT NOT NULL,
    signature       TEXT,
    public_key      TEXT,
    key_fingerprint TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT,
    UNIQUE (period, tenant_key)
);

-- Zone geografiche per cliente ('' = valgono per tutti i mezzi).
CREATE TABLE IF NOT EXISTS geofences (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_key    TEXT NOT NULL DEFAULT '',
    name          TEXT NOT NULL,
    latitude      REAL NOT NULL,
    longitude     REAL NOT NULL,
    radius_m      INTEGER NOT NULL,
    shape         TEXT NOT NULL DEFAULT 'circle',
    geometry_json TEXT NOT NULL DEFAULT '[]',
    schedule_json TEXT NOT NULL DEFAULT '[]',
    timezone      TEXT NOT NULL DEFAULT 'Europe/Rome',
    created_at    TEXT NOT NULL,
    created_by    TEXT
);

-- Ultimo stato dentro/fuori per mezzo e zona: serve a rilevare i passaggi.
CREATE TABLE IF NOT EXISTS geofence_states (
    imei        TEXT NOT NULL,
    geofence_id INTEGER NOT NULL,
    inside      INTEGER NOT NULL DEFAULT 0,
    last_lat    REAL,
    last_lon    REAL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (imei, geofence_id)
);

-- Regole di notifica per cliente: velocita' e furto (movimento a motore spento).
CREATE TABLE IF NOT EXISTS alert_rules (
    tenant_key  TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL,
    threshold   REAL NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT NOT NULL,
    updated_by  TEXT,
    PRIMARY KEY (tenant_key, kind)
);

-- Fascia lavorativa per cliente ('' = globale): base per l'allarme di
-- accensione fuori orario. Resta spenta finche' non viene configurata.
CREATE TABLE IF NOT EXISTS tenant_work_hours (
    tenant_key    TEXT PRIMARY KEY,
    enabled       INTEGER NOT NULL DEFAULT 0,
    schedule_json TEXT NOT NULL DEFAULT '[]',
    timezone      TEXT NOT NULL DEFAULT 'Europe/Rome',
    updated_at    TEXT,
    updated_by    TEXT
);

-- Interventi di manutenzione con scadenza a data o chilometraggio.
CREATE TABLE IF NOT EXISTS maintenance (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    imei             TEXT NOT NULL,
    kind             TEXT NOT NULL,
    due_date         TEXT,
    due_odometer_km  REAL,
    note             TEXT,
    repeat_km        REAL,
    repeat_months    INTEGER,
    created_at       TEXT NOT NULL,
    created_by       TEXT,
    completed_at     TEXT,
    completed_by     TEXT
);

-- Destinatari degli allarmi per cliente ('' = globale).
CREATE TABLE IF NOT EXISTS tenant_notifications (
    tenant_key TEXT PRIMARY KEY,
    emails     TEXT NOT NULL DEFAULT '',
    phones     TEXT NOT NULL DEFAULT '',
    updated_at TEXT,
    updated_by TEXT
);

-- Ultimo invio per mezzo/allarme/canale: evita raffiche di email e SMS.
CREATE TABLE IF NOT EXISTS alert_dispatches (
    imei         TEXT NOT NULL,
    kind         TEXT NOT NULL,
    channel      TEXT NOT NULL,
    last_sent_at TEXT NOT NULL,
    PRIMARY KEY (imei, kind, channel)
);

-- Pacchetto, verticale e mappe scelti dal cliente (metadata di servizio).
CREATE TABLE IF NOT EXISTS tenant_solutions (
    tenant_key   TEXT PRIMARY KEY,
    vertical     TEXT NOT NULL DEFAULT 'trasporti_pesanti',
    connectivity TEXT NOT NULL DEFAULT '4g',
    maps         TEXT NOT NULL DEFAULT 'osm',
    updated_at   TEXT,
    updated_by   TEXT
);

-- Autisti identificati dal badge iButton/RFID del dispositivo.
CREATE TABLE IF NOT EXISTS drivers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id  INTEGER,
    name       TEXT NOT NULL,
    badge      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(tenant_id, badge)
);

-- Coda persistente dei webhook in uscita (sopravvive al riavvio).
CREATE TABLE IF NOT EXISTS webhook_outbox (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event         TEXT NOT NULL,
    payload       TEXT NOT NULL,
    attempts      INTEGER NOT NULL DEFAULT 0,
    next_attempt  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    last_error    TEXT,
    created_at    TEXT NOT NULL
);

-- Outbox delle notifiche: email, SMS e voce, anche simulate.
CREATE TABLE IF NOT EXISTS notification_outbox (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_key  TEXT NOT NULL DEFAULT '',
    imei        TEXT,
    channel     TEXT NOT NULL,
    provider    TEXT,
    mode        TEXT,
    recipients  TEXT NOT NULL DEFAULT '',
    subject     TEXT,
    body        TEXT NOT NULL,
    status      TEXT NOT NULL,
    detail      TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notification_outbox_tenant
    ON notification_outbox (tenant_key, id DESC);

-- Ricevute dei gateway SMS (webhook del fornitore).
CREATE TABLE IF NOT EXISTS sms_receipts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT,
    recipient   TEXT,
    status      TEXT,
    raw         TEXT,
    received_at TEXT NOT NULL
);

-- Controlli di sicurezza sul lavoro: procedure e non conformita'.
CREATE TABLE IF NOT EXISTS safety_checks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    imei        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    compliant   INTEGER NOT NULL,
    note        TEXT,
    checked_at  TEXT NOT NULL,
    checked_by  TEXT
);
"""


def _haversine_m(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Distanza in metri tra due punti (formula dell'emisenoverso)."""
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


# In WAL un solo scrittore alla volta tiene il lock e le connessioni nascono per
# frame, richieste HTTP e report: l'attesa evita il "database is locked".
SQLITE_TIMEOUT_SECONDS = 30.0


class TelemetryStore:
    def __init__(self, db_path: str | Path, profile: DeviceProfile | None = None) -> None:
        self.db_path = str(db_path)
        self.profile = profile or DeviceProfile("default")
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        # isolation_level resta quello predefinito (transazione implicita per
        # _session): con None ogni istruzione sarebbe autocommit.
        conn = sqlite3.connect(self.db_path, timeout=SQLITE_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(f"PRAGMA busy_timeout={int(SQLITE_TIMEOUT_SECONDS * 1000)}")
        return conn

    @contextmanager
    def _session(self):
        """Connessione con commit/rollback e chiusura garantita.

        `with sqlite3.connect(...)` esegue il commit ma non chiude la
        connessione: in un server sempre attivo sarebbe un leak per ogni frame.
        """
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._session() as conn:
            conn.executescript(SCHEMA)
            self._add_missing_columns(conn)
            conn.execute(
                "UPDATE tenant_solutions SET vertical = 'trasporti_pesanti'"
                " WHERE vertical = 'trasporti'"
            )
            # Righe create prima della modalita' esplicita: chi aveva URL o
            # file diventa 'custom', gli altri restano sul predefinito.
            conn.execute(
                "UPDATE tenant_branding SET bg_mode = CASE"
                " WHEN bg_data IS NOT NULL"
                " OR (bg_image IS NOT NULL AND bg_image <> '') THEN 'custom'"
                " ELSE 'default' END"
                " WHERE bg_mode IS NULL"
            )
            # Impronta delle righe salvate prima che esistesse: calcolata dal
            # contenuto, cosi' gli URL firmati restano gli stessi.
            for row in conn.execute(
                "SELECT tenant_key, bg_image, bg_data FROM tenant_branding"
                " WHERE bg_stamp IS NULL"
                " AND (bg_data IS NOT NULL OR bg_image IS NOT NULL)"
            ).fetchall():
                conn.execute(
                    "UPDATE tenant_branding SET bg_stamp = ? WHERE tenant_key = ?",
                    (content_digest(row["bg_data"], row["bg_image"]), row["tenant_key"]),
                )

    def _add_missing_columns(self, conn: sqlite3.Connection) -> None:
        """Migrazioni idempotenti per i database creati da versioni precedenti."""
        migrations = {
            "tenant_branding": {
                "bg_mode": "TEXT",
                "bg_image": "TEXT",
                "bg_data": "BLOB",
                "bg_mime": "TEXT",
                "bg_stamp": "TEXT",
            },
            "geofences": {
                "shape": "TEXT NOT NULL DEFAULT 'circle'",
                "geometry_json": "TEXT NOT NULL DEFAULT '[]'",
                "schedule_json": "TEXT NOT NULL DEFAULT '[]'",
                "timezone": "TEXT NOT NULL DEFAULT 'Europe/Rome'",
            },
            "geofence_states": {
                "last_lat": "REAL",
                "last_lon": "REAL",
            },
            "positions": {
                "can_fuel_liters": "REAL",
                "can_fuel_pct": "REAL",
                "engine_temp": "REAL",
                "can_rpm": "INTEGER",
                "engine_hours": "REAL",
            },
            "devices": {
                "tenant_id": "INTEGER",
                "fuel_l_per_100km": "REAL",
                "co2_kg_per_liter": "REAL",
                "driver_badge": "TEXT",
                "trailer_plate": "TEXT",
                "trailer_type": "TEXT",
                "privacy_mode": "INTEGER NOT NULL DEFAULT 0",
            },
            "alerts": {
                "latitude": "REAL",
                "longitude": "REAL",
            },
            "esg_snapshots": {
                "signature": "TEXT",
                "public_key": "TEXT",
                "key_fingerprint": "TEXT",
            },
            "report_tokens": {
                "used_count": "INTEGER NOT NULL DEFAULT 0",
                "last_used_at": "TEXT",
                "max_uses": "INTEGER NOT NULL DEFAULT 25",
            },
            "maintenance": {
                "repeat_km": "REAL",
                "repeat_months": "INTEGER",
            },
            "users": {
                "must_change": "INTEGER NOT NULL DEFAULT 0",
                "failed_attempts": "INTEGER NOT NULL DEFAULT 0",
                "locked_until": "TEXT",
                "password_changed_at": "TEXT",
                "password_version": "INTEGER NOT NULL DEFAULT 0",
                "last_login_at": "TEXT",
            },
        }
        for table, columns in migrations.items():
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column, kind in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")

    # --- ingestione -------------------------------------------------------

    def register_device(self, imei: str, ip: str | None = None) -> bool:
        """Registra l'IMEI al primo contatto. Ritorna True se e' nuovo."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._session() as conn:
            row = conn.execute(
                "SELECT imei FROM devices WHERE imei = ?", (imei,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE devices SET last_seen = ?, last_ip = ? WHERE imei = ?",
                    (now, ip, imei),
                )
                return False
            conn.execute(
                "INSERT INTO devices (imei, status, first_seen, last_seen, last_ip)"
                " VALUES (?, 'pending', ?, ?, ?)",
                (imei, now, now, ip),
            )
            return True

    def save_records(self, imei: str, records: list[AvlRecord], codec_id: int) -> int:
        """Salva i record non ancora visti. Ritorna quanti ne ha inseriti."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        inserted = 0
        with self._session() as conn:
            # Un dispositivo che invia dati esiste, anche se l'handshake non e'
            # stato registrato (import, migrazioni, DB ricostruito).
            conn.execute(
                "INSERT OR IGNORE INTO devices (imei, status, first_seen)"
                " VALUES (?, 'pending', ?)",
                (imei, now),
            )
            privacy = conn.execute(
                "SELECT privacy_mode FROM devices WHERE imei = ?", (imei,)
            ).fetchone()
            hide_position = bool(privacy and privacy["privacy_mode"])
            for record in records:
                normalized = self.profile.normalize(record)
                # Modalita' privacy: si salva tutto tranne la posizione, cosi'
                # odometro e CAN continuano a contare per km e report ESG.
                latitude = None if hide_position else normalized["latitude"]
                longitude = None if hide_position else normalized["longitude"]
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO positions ("
                    " imei, ts_ms, received_at, latitude, longitude, speed, altitude,"
                    " angle, satellites, ignition, odometer_m, battery_voltage,"
                    " can_fuel_liters, can_fuel_pct, engine_temp, can_rpm, engine_hours,"
                    " codec_id, io_json"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        imei,
                        record.timestamp_ms,
                        now,
                        latitude,
                        longitude,
                        normalized["speed"],
                        record.altitude,
                        record.angle,
                        record.satellites,
                        normalized["ignition"],
                        normalized["odometer_m"],
                        normalized["battery_voltage"],
                        normalized["can_fuel_liters"],
                        normalized["fuel_level_pct"],
                        normalized["engine_temp"],
                        normalized["can_rpm"],
                        normalized["engine_hours"],
                        codec_id,
                        json.dumps(record.io, sort_keys=True),
                    ),
                )
                inserted += cursor.rowcount
            conn.execute(
                "UPDATE devices SET last_seen = ? WHERE imei = ?", (now, imei)
            )
            self._push_to_vehicles(conn, imei, records, hide_position)
        return inserted

    def _push_to_vehicles(
        self,
        conn: sqlite3.Connection,
        imei: str,
        records: list[AvlRecord],
        hide_position: bool = False,
    ) -> None:
        """Aggiorna la riga del mezzo nella tabella usata dalla dashboard."""
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(vehicles)").fetchall()
        }
        if not columns or "device_imei" not in columns:
            return

        latest = max(records, key=lambda item: item.timestamp_ms)
        normalized = self.profile.normalize(latest)

        updates: dict[str, object] = {}
        if not hide_position:
            updates["latitude"] = normalized["latitude"]
            updates["longitude"] = normalized["longitude"]
        if normalized["battery_voltage"] is not None:
            updates["battery_voltage"] = normalized["battery_voltage"]
        if normalized["odometer_m"] is not None:
            updates["total_km"] = round(normalized["odometer_m"] / 1000, 1)
        for field_name, column in VEHICLE_FIELD_MAP.items():
            value = normalized.get(field_name)
            if value is not None and column in columns:
                updates[column] = value

        if "health_status" in columns:
            updates["health_status"] = "Telemetria GPS ricevuta"
        if "status" in columns:
            updates["status"] = "active"

        assignments = [f"{column} = ?" for column in updates]
        conn.execute(
            f"UPDATE vehicles SET {', '.join(assignments)} WHERE device_imei = ?",
            (*updates.values(), imei),
        )

    # --- lettura ----------------------------------------------------------

    def devices(self, tenant_id: int | None = None) -> list[dict]:
        query = (
            "SELECT d.*, t.name AS tenant_name,"
            # Con la privacy attiva la posizione del mezzo e' NULL anche se
            # l'ultima registrazione precedente al cambio la conteneva.
            " CASE WHEN d.privacy_mode = 1 THEN NULL ELSE p.latitude END AS latitude,"
            " CASE WHEN d.privacy_mode = 1 THEN NULL ELSE p.longitude END AS longitude,"
            " p.speed,"
            " p.ignition, p.angle, p.ts_ms, p.odometer_m, p.battery_voltage, p.can_fuel_liters,"
            " p.can_fuel_pct, p.engine_temp, p.can_rpm, p.engine_hours,"
            " d.driver_badge, d.trailer_plate, d.trailer_type,"
            " dr.name AS driver_name"
            " FROM devices d"
            " LEFT JOIN tenants t ON t.id = d.tenant_id"
            " LEFT JOIN drivers dr ON dr.tenant_id = d.tenant_id"
            " AND dr.badge = d.driver_badge"
            " LEFT JOIN positions p ON p.imei = d.imei"
            " AND p.ts_ms = (SELECT MAX(ts_ms) FROM positions WHERE imei = d.imei)"
        )
        params: tuple = ()
        if tenant_id is not None:
            query += " WHERE d.tenant_id = ?"
            params = (tenant_id,)
        query += " ORDER BY d.imei"
        with self._session() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    # --- tenant, utenti, allarmi -----------------------------------------

    def count_users(self) -> int:
        with self._session() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def ensure_tenant(self, name: str) -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._session() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO tenants (name, created_at) VALUES (?, ?)",
                (name, now),
            )
            row = conn.execute("SELECT id FROM tenants WHERE name = ?", (name,)).fetchone()
        return int(row["id"])

    def tenants(self) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute("SELECT * FROM tenants ORDER BY name").fetchall()
        return [dict(row) for row in rows]

    def create_user(
        self,
        username: str,
        password: str,
        role: str = "manager",
        tenant_id: int | None = None,
        full_name: str | None = None,
        must_change: bool = False,
    ) -> bool:
        from .auth import hash_password

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with self._session() as conn:
                conn.execute(
                    "INSERT INTO users (username, password_hash, role, tenant_id,"
                    " full_name, created_at, password_changed_at, must_change,"
                    " password_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                    (
                        username,
                        hash_password(password),
                        role,
                        tenant_id,
                        full_name,
                        now,
                        now,
                        1 if must_change else 0,
                    ),
                )
        except sqlite3.IntegrityError:
            return False
        return True

    def get_user(self, username: str) -> dict | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT u.*, t.name AS tenant_name FROM users u"
                " LEFT JOIN tenants t ON t.id = u.tenant_id WHERE u.username = ?",
                (username,),
            ).fetchone()
        return dict(row) if row else None

    def device(self, imei: str) -> dict | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT imei, status, model, plate, tenant_id, driver_badge,"
                " trailer_plate, trailer_type FROM devices WHERE imei = ?",
                (imei,),
            ).fetchone()
        return dict(row) if row else None

    def set_vehicle_esg(
        self,
        imei: str,
        fuel_l_per_100km: float | None,
        co2_kg_per_liter: float | None,
        valid_from_ms: int | None = None,
        created_by: str | None = None,
    ) -> bool:
        """Parametri ESG del mezzo, con decorrenza (None = valore di flotta).

        Oltre allo stato corrente si registra la storia: il calcolo dei
        periodi passati usa i parametri in vigore allora, non quelli di oggi.
        """
        start = valid_from_ms if valid_from_ms is not None else int(time.time() * 1000)
        with self._session() as conn:
            cursor = conn.execute(
                "UPDATE devices SET fuel_l_per_100km = ?, co2_kg_per_liter = ?"
                " WHERE imei = ?",
                (fuel_l_per_100km, co2_kg_per_liter, imei),
            )
            if cursor.rowcount == 0:
                return False
            conn.execute(
                "INSERT INTO vehicle_esg_params (imei, fuel_l_per_100km,"
                " co2_kg_per_liter, valid_from_ms, created_at, created_by)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    imei,
                    fuel_l_per_100km,
                    co2_kg_per_liter,
                    start,
                    _utcnow(),
                    created_by,
                ),
            )
        return True

    def esg_param_history(self) -> dict[str, list[dict]]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT imei, fuel_l_per_100km, co2_kg_per_liter, valid_from_ms"
                " FROM vehicle_esg_params ORDER BY imei, valid_from_ms"
            ).fetchall()
        history: dict[str, list[dict]] = {}
        for row in rows:
            history.setdefault(row["imei"], []).append(dict(row))
        return history

    def record_admin_action(
        self,
        actor: str | None,
        action: str,
        target: str | None = None,
        detail: str | None = None,
    ) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO admin_audit (actor, action, target, detail, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (actor, action, target, detail, _utcnow()),
            )

    def admin_actions(self, limit: int = 100) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM admin_audit ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def save_esg_snapshot(
        self,
        period: str,
        tenant_key: str,
        payload: str,
        digest: str,
        signature: str | None,
        public_key: str | None,
        key_fingerprint: str | None,
        created_by: str | None,
    ) -> int | None:
        """Salva lo snapshot del mese. None se esiste gia' per quel periodo."""
        try:
            with self._session() as conn:
                cursor = conn.execute(
                    "INSERT INTO esg_snapshots (period, tenant_key, payload, digest,"
                    " signature, public_key, key_fingerprint, created_at, created_by)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        period,
                        tenant_key,
                        payload,
                        digest,
                        signature,
                        public_key,
                        key_fingerprint,
                        _utcnow(),
                        created_by,
                    ),
                )
                return int(cursor.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def register_signing_key(
        self,
        fingerprint: str,
        public_key: str,
        private_path: str | None,
        created_by: str | None = None,
        active: bool = True,
    ) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO signing_keys (fingerprint, public_key,"
                " private_path, created_at, created_by, retired_at, active)"
                " VALUES (?, ?, ?, ?, ?, NULL, ?)",
                (
                    fingerprint,
                    public_key,
                    private_path,
                    _utcnow(),
                    created_by,
                    1 if active else 0,
                ),
            )

    def retire_signing_key(self, fingerprint: str) -> bool:
        with self._session() as conn:
            cursor = conn.execute(
                "UPDATE signing_keys SET active = 0, retired_at = ?"
                " WHERE fingerprint = ? AND active = 1",
                (_utcnow(), fingerprint),
            )
        return cursor.rowcount > 0

    def signing_keys(self) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT k.*, (SELECT COUNT(*) FROM esg_snapshots s"
                " WHERE s.key_fingerprint = k.fingerprint) AS snapshots"
                " FROM signing_keys k ORDER BY k.created_at DESC, k.fingerprint"
            ).fetchall()
        return [dict(row) for row in rows]

    def snapshots_without_key_fingerprint(self) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT id, public_key FROM esg_snapshots"
                " WHERE key_fingerprint IS NULL AND public_key IS NOT NULL"
            ).fetchall()
        return [dict(row) for row in rows]

    def set_snapshot_key_fingerprint(self, snapshot_id: int, fingerprint: str) -> None:
        with self._session() as conn:
            conn.execute(
                "UPDATE esg_snapshots SET key_fingerprint = ? WHERE id = ?",
                (fingerprint, snapshot_id),
            )

    def active_signing_key(self) -> dict | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT * FROM signing_keys WHERE active = 1"
                " ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def create_report_token(
        self,
        token_hash: str,
        snapshot_id: int,
        expires_at: str,
        created_by: str | None,
        max_uses: int = 25,
    ) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO report_tokens (token_hash, snapshot_id, created_at,"
                " expires_at, created_by, revoked, max_uses)"
                " VALUES (?, ?, ?, ?, ?, 0, ?)",
                (
                    token_hash,
                    snapshot_id,
                    _utcnow(),
                    expires_at,
                    created_by,
                    max(1, int(max_uses)),
                ),
            )

    def report_token(self, token_hash: str) -> dict | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT * FROM report_tokens WHERE token_hash = ? AND revoked = 0",
                (token_hash,),
            ).fetchone()
        if row is None or row["expires_at"] <= _utcnow():
            return None
        return dict(row)

    def report_tokens(self, snapshot_id: int) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT token_hash, created_at, expires_at, created_by, revoked,"
                " used_count, last_used_at, max_uses FROM report_tokens"
                " WHERE snapshot_id = ? ORDER BY created_at DESC, token_hash",
                (snapshot_id,),
            ).fetchall()
        now = _utcnow()
        items = []
        for row in rows:
            item = dict(row)
            item["expired"] = item["expires_at"] <= now
            items.append(item)
        return items

    def revoke_report_token(self, token_hash: str) -> bool:
        with self._session() as conn:
            cursor = conn.execute(
                "UPDATE report_tokens SET revoked = 1"
                " WHERE token_hash = ? AND revoked = 0",
                (token_hash,),
            )
        return cursor.rowcount > 0

    # --- blocco per indirizzo: link pubblici e accessi ---------------------

    def _ip_blocked(self, table: str, ip: str) -> str | None:
        with self._session() as conn:
            row = conn.execute(
                f"SELECT blocked_until FROM {table} WHERE ip = ?", (ip,)
            ).fetchone()
        if row is None or not row["blocked_until"]:
            return None
        return row["blocked_until"] if row["blocked_until"] > _utcnow() else None

    def _register_ip_failure(
        self, table: str, ip: str, limit: int, block_minutes: int
    ) -> bool:
        """Registra un tentativo fallito; True se l'indirizzo va bloccato."""
        now = _utcnow()
        blocked_until = (
            datetime.now(timezone.utc) + timedelta(minutes=block_minutes)
        ).isoformat(timespec="seconds")
        with self._session() as conn:
            row = conn.execute(
                f"SELECT failures, first_at FROM {table} WHERE ip = ?", (ip,)
            ).fetchone()
            if row is None:
                conn.execute(
                    f"INSERT INTO {table} (ip, failures, first_at, blocked_until)"
                    " VALUES (?, 1, ?, NULL)",
                    (ip, now),
                )
                return False
            window_start = datetime.fromisoformat(row["first_at"])
            if datetime.now(timezone.utc) - window_start > timedelta(
                minutes=block_minutes
            ):
                conn.execute(
                    f"UPDATE {table} SET failures = 1, first_at = ?,"
                    " blocked_until = NULL WHERE ip = ?",
                    (now, ip),
                )
                return False
            failures = row["failures"] + 1
            if failures >= max(1, limit):
                conn.execute(
                    f"UPDATE {table} SET failures = ?, blocked_until = ?"
                    " WHERE ip = ?",
                    (failures, blocked_until, ip),
                )
                return True
            conn.execute(
                f"UPDATE {table} SET failures = ? WHERE ip = ?", (failures, ip)
            )
            return False

    def _clear_ip_failures(self, table: str, ip: str) -> None:
        with self._session() as conn:
            conn.execute(f"DELETE FROM {table} WHERE ip = ?", (ip,))

    def link_blocked(self, ip: str) -> str | None:
        return self._ip_blocked("link_attempts", ip)

    def register_link_failure(
        self, ip: str, limit: int, block_minutes: int
    ) -> bool:
        return self._register_ip_failure("link_attempts", ip, limit, block_minutes)

    def clear_link_failures(self, ip: str) -> None:
        self._clear_ip_failures("link_attempts", ip)

    def login_blocked(self, ip: str) -> str | None:
        """Blocco temporaneo dopo troppi accessi falliti dallo stesso indirizzo."""
        return self._ip_blocked("auth_attempts", ip)

    def register_login_failure(
        self, ip: str, limit: int, block_minutes: int
    ) -> bool:
        return self._register_ip_failure("auth_attempts", ip, limit, block_minutes)

    def clear_login_failures(self, ip: str) -> None:
        self._clear_ip_failures("auth_attempts", ip)

    def link_blocks(self) -> list[dict]:
        """Indirizzi con tentativi registrati, bloccati o in osservazione."""
        now = _utcnow()
        with self._session() as conn:
            rows = conn.execute(
                "SELECT ip, failures, first_at, blocked_until FROM link_attempts"
                " ORDER BY blocked_until DESC, ip"
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["blocked"] = bool(
                item["blocked_until"] and item["blocked_until"] > now
            )
            items.append(item)
        return items

    def tenant_branding(self, tenant_key: str) -> dict | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT * FROM tenant_branding WHERE tenant_key = ?", (tenant_key,)
            ).fetchone()
        return dict(row) if row else None

    def save_tenant_branding(
        self,
        tenant_key: str,
        display_name: str | None,
        primary_color: str | None,
        updated_by: str | None,
    ) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO tenant_branding (tenant_key, display_name,"
                " primary_color, updated_at, updated_by) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(tenant_key) DO UPDATE SET"
                " display_name = COALESCE(excluded.display_name,"
                " tenant_branding.display_name),"
                " primary_color = COALESCE(excluded.primary_color,"
                " tenant_branding.primary_color),"
                " updated_at = excluded.updated_at,"
                " updated_by = excluded.updated_by",
                (
                    tenant_key,
                    display_name,
                    primary_color,
                    _utcnow(),
                    updated_by,
                ),
            )

    def save_tenant_logo(
        self,
        tenant_key: str,
        logo: bytes | None,
        mime: str | None,
        updated_by: str | None,
    ) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO tenant_branding (tenant_key, logo, logo_mime,"
                " updated_at, updated_by) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(tenant_key) DO UPDATE SET"
                " logo = excluded.logo, logo_mime = excluded.logo_mime,"
                " updated_at = excluded.updated_at,"
                " updated_by = excluded.updated_by",
                (tenant_key, logo, mime, _utcnow(), updated_by),
            )

    def set_tenant_background(
        self,
        tenant_key: str,
        mode: str,
        url: str | None = None,
        data: bytes | None = None,
        mime: str | None = None,
        updated_by: str | None = None,
    ) -> None:
        """Spegne, riaccende o sostituisce lo sfondo del cliente.

        ``mode`` e' sempre aggiornata ('custom', 'none' o 'default'), mentre il
        contenuto cambia solo quando arrivano ``url`` o ``data``. Cosi' 'none'
        lascia intatti URL e file: scegliere di nuovo 'custom' senza nuovi byte
        riattiva quello che c'era, senza un nuovo caricamento.
        """
        if mode not in ("custom", "default", "none"):
            raise ValueError("modalita' sfondo non valida: " + mode)
        new_content = url is not None or data is not None
        with self._session() as conn:
            if mode == "custom" and not new_content:
                row = conn.execute(
                    "SELECT bg_image, bg_data FROM tenant_branding WHERE tenant_key = ?",
                    (tenant_key,),
                ).fetchone()
                if row is None or not (row["bg_image"] or row["bg_data"]):
                    raise ValueError("nessuno sfondo salvato da riattivare")
            conn.execute(
                "INSERT INTO tenant_branding (tenant_key, bg_mode, updated_at,"
                " updated_by) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(tenant_key) DO UPDATE SET"
                " bg_mode = excluded.bg_mode,"
                " updated_at = excluded.updated_at,"
                " updated_by = excluded.updated_by",
                (tenant_key, mode, _utcnow(), updated_by),
            )
            if new_content:
                conn.execute(
                    "UPDATE tenant_branding SET bg_image = ?, bg_data = ?,"
                    " bg_mime = ?, bg_stamp = ? WHERE tenant_key = ?",
                    (url, data, mime, content_digest(data, url), tenant_key),
                )

    def touch_report_token(self, token_hash: str) -> None:
        with self._session() as conn:
            conn.execute(
                "UPDATE report_tokens SET used_count = used_count + 1,"
                " last_used_at = ? WHERE token_hash = ?",
                (_utcnow(), token_hash),
            )

    def revoke_report_tokens(self, snapshot_id: int) -> int:
        with self._session() as conn:
            cursor = conn.execute(
                "UPDATE report_tokens SET revoked = 1"
                " WHERE snapshot_id = ? AND revoked = 0",
                (snapshot_id,),
            )
        return cursor.rowcount

    def esg_snapshots(
        self, limit: int = 24, tenant_key: str | None = None
    ) -> list[dict]:
        query = (
            "SELECT id, period, tenant_key, digest, created_at, created_by"
            " FROM esg_snapshots"
        )
        params: tuple = ()
        if tenant_key is not None:
            query += " WHERE tenant_key = ?"
            params = (tenant_key,)
        query += " ORDER BY period DESC LIMIT ?"
        params += (limit,)
        with self._session() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def esg_snapshot(self, snapshot_id: int) -> dict | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT * FROM esg_snapshots WHERE id = ?", (snapshot_id,)
            ).fetchone()
        return dict(row) if row else None

    def set_user_active(self, username: str, active: bool) -> bool:
        """Attiva o disattiva un utente. La disattivazione chiude la sessione."""
        with self._session() as conn:
            cursor = conn.execute(
                "UPDATE users SET active = ? WHERE username = ?",
                (1 if active else 0, username),
            )
        return cursor.rowcount > 0

    def count_active_admins(self) -> int:
        with self._session() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1"
                ).fetchone()[0]
            )

    def set_device_tenant(self, imei: str, tenant_id: int) -> None:
        with self._session() as conn:
            conn.execute("UPDATE devices SET tenant_id = ? WHERE imei = ?", (tenant_id, imei))

    def set_device_driver(self, imei: str, badge: str | None) -> None:
        with self._session() as conn:
            conn.execute(
                "UPDATE devices SET driver_badge = ? WHERE imei = ?",
                (badge or None, imei),
            )

    def set_device_trailer(
        self, imei: str, plate: str | None, kind: str | None = None
    ) -> None:
        with self._session() as conn:
            conn.execute(
                "UPDATE devices SET trailer_plate = ?, trailer_type = ?"
                " WHERE imei = ?",
                (plate or None, kind or None, imei),
            )

    def geofences(self, tenant_key: str) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM geofences WHERE tenant_key = ? ORDER BY name",
                (tenant_key,),
            ).fetchall()
        zones = []
        for row in rows:
            item = dict(row)
            try:
                item["geometry"] = json.loads(item.pop("geometry_json") or "[]")
            except ValueError:
                item["geometry"] = []
            try:
                item["schedule"] = json.loads(item.pop("schedule_json") or "[]")
            except ValueError:
                item["schedule"] = []
            zones.append(item)
        return zones

    def create_geofence(
        self,
        tenant_key: str,
        name: str,
        latitude: float,
        longitude: float,
        radius_m: int,
        created_by: str | None = None,
        shape: str = "circle",
        geometry: list | None = None,
        schedule: list | None = None,
        timezone_name: str = DEFAULT_TIMEZONE,
    ) -> int:
        vertices = geometry or []
        if shape in ("polygon", "line") and vertices:
            latitude = sum(float(point[0]) for point in vertices) / len(vertices)
            longitude = sum(float(point[1]) for point in vertices) / len(vertices)
            radius_m = 0
        with self._session() as conn:
            cursor = conn.execute(
                "INSERT INTO geofences (tenant_key, name, latitude, longitude,"
                " radius_m, shape, geometry_json, schedule_json, timezone,"
                " created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant_key,
                    name,
                    latitude,
                    longitude,
                    int(radius_m),
                    shape,
                    json.dumps(vertices, separators=(",", ":")),
                    json.dumps(schedule or [], separators=(",", ":")),
                    timezone_name,
                    _utcnow(),
                    created_by,
                ),
            )
            return int(cursor.lastrowid)

    def delete_geofence(self, geofence_id: int, tenant_key: str) -> bool:
        with self._session() as conn:
            cursor = conn.execute(
                "DELETE FROM geofences WHERE id = ? AND tenant_key = ?",
                (geofence_id, tenant_key),
            )
            conn.execute(
                "DELETE FROM geofence_states WHERE geofence_id = ?", (geofence_id,)
            )
        return cursor.rowcount > 0

    def alert_rules(self, tenant_key: str) -> dict[str, dict]:
        """Regole effettive: prima i valori globali, poi quelli del cliente."""
        rules: dict[str, dict] = {
            "speed": {"threshold": 90.0, "enabled": 1},
            "theft": {"threshold": 5.0, "enabled": 1},
        }
        with self._session() as conn:
            rows = conn.execute(
                "SELECT tenant_key, kind, threshold, enabled FROM alert_rules"
                " WHERE tenant_key = ? OR tenant_key = ''",
                (tenant_key,),
            ).fetchall()
        for row in sorted(rows, key=lambda item: item["tenant_key"] != ""):
            rules[row["kind"]] = {
                "threshold": float(row["threshold"]),
                "enabled": int(row["enabled"]),
            }
        return rules

    def save_alert_rule(
        self,
        tenant_key: str,
        kind: str,
        threshold: float,
        enabled: bool,
        updated_by: str | None = None,
    ) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO alert_rules (tenant_key, kind, threshold, enabled,"
                " updated_at, updated_by) VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(tenant_key, kind) DO UPDATE SET"
                " threshold = excluded.threshold, enabled = excluded.enabled,"
                " updated_at = excluded.updated_at, updated_by = excluded.updated_by",
                (
                    tenant_key,
                    kind,
                    float(threshold),
                    1 if enabled else 0,
                    _utcnow(),
                    updated_by,
                ),
            )

    def work_hours(self, tenant_key: str) -> dict:
        """Fascia lavorativa effettiva: prima i valori globali, poi il cliente.

        Senza configurazione la regola resta spenta: nessun allarme di
        accensione fuori orario finche' il cliente non la imposta.
        """
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM tenant_work_hours WHERE tenant_key = ? OR tenant_key = ''",
                (tenant_key,),
            ).fetchall()
        chosen = None
        for row in sorted(rows, key=lambda item: item["tenant_key"] != ""):
            chosen = row
        if chosen is None:
            return {
                "enabled": False,
                "schedule": [],
                "timezone": DEFAULT_TIMEZONE,
                "configured": False,
            }
        try:
            schedule = json.loads(chosen["schedule_json"] or "[]")
        except ValueError:
            schedule = []
        return {
            "enabled": bool(chosen["enabled"]),
            "schedule": schedule if isinstance(schedule, list) else [],
            "timezone": chosen["timezone"] or DEFAULT_TIMEZONE,
            "configured": True,
        }

    def save_work_hours(
        self,
        tenant_key: str,
        enabled: bool,
        schedule: list[dict],
        timezone_name: str = DEFAULT_TIMEZONE,
        updated_by: str | None = None,
    ) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO tenant_work_hours (tenant_key, enabled, schedule_json,"
                " timezone, updated_at, updated_by) VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(tenant_key) DO UPDATE SET"
                " enabled = excluded.enabled, schedule_json = excluded.schedule_json,"
                " timezone = excluded.timezone, updated_at = excluded.updated_at,"
                " updated_by = excluded.updated_by",
                (
                    tenant_key,
                    1 if enabled else 0,
                    json.dumps(schedule or [], separators=(",", ":")),
                    timezone_name,
                    _utcnow(),
                    updated_by,
                ),
            )

    def evaluate_notifications(
        self,
        imei: str,
        latitude: float,
        longitude: float,
        speed: float,
        ignition: int,
        ts_ms: int,
        fuel_theft_liters: float = 15.0,
    ) -> list[str]:
        """Valuta regole e zone su un record; ritorna i tipi di allarme aperti."""
        created: list[str] = []
        with self._session() as conn:
            row = conn.execute(
                "SELECT tenant_id FROM devices WHERE imei = ?", (imei,)
            ).fetchone()
        tenant_key = str(row["tenant_id"]) if row and row["tenant_id"] else ""
        rules = self.alert_rules(tenant_key)

        speed_rule = rules.get("speed", {})
        if speed_rule.get("enabled") and speed >= float(speed_rule["threshold"]):
            if self.raise_alert(
                imei,
                "SPEED",
                "HIGH",
                f"Velocita {speed:.0f} km/h oltre la soglia di "
                f"{float(speed_rule['threshold']):.0f} km/h",
                ts_ms,
            ):
                created.append("SPEED")

        theft_rule = rules.get("theft", {})
        if (
            theft_rule.get("enabled")
            and not int(ignition or 0)
            and speed >= float(theft_rule["threshold"])
        ):
            if self.raise_alert(
                imei,
                "THEFT",
                "CRITICAL",
                f"Movimento a motore spento: {speed:.0f} km/h "
                f"(soglia {float(theft_rule['threshold']):.0f} km/h)",
                ts_ms,
            ):
                created.append("THEFT")

        with self._session() as conn:
            fuel_rows = conn.execute(
                "SELECT can_fuel_liters, ignition FROM positions"
                " WHERE imei = ? AND can_fuel_liters IS NOT NULL"
                " ORDER BY ts_ms DESC LIMIT 2",
                (imei,),
            ).fetchall()
        if len(fuel_rows) == 2:
            latest_fuel = fuel_rows[0]["can_fuel_liters"]
            older_fuel = fuel_rows[1]["can_fuel_liters"]
            if (
                not int(fuel_rows[0]["ignition"] or 0)
                and older_fuel - latest_fuel >= fuel_theft_liters
            ):
                if self.raise_alert(
                    imei,
                    "FUEL_THEFT",
                    "HIGH",
                    f"Calo di carburante a motore spento: "
                    f"{older_fuel - latest_fuel:.0f} L",
                    ts_ms,
                ):
                    created.append("FUEL_THEFT")

        # Accensione fuori orario: serve la transizione 0 -> 1, quindi si
        # confronta con la posizione precedente dello stesso mezzo. Senza
        # registro precedente (primo contatto) non c'e' transizione da contare.
        if int(ignition or 0):
            with self._session() as conn:
                previous_ignition = conn.execute(
                    "SELECT ignition FROM positions WHERE imei = ? AND ts_ms < ?"
                    " ORDER BY ts_ms DESC LIMIT 1",
                    (imei, int(ts_ms)),
                ).fetchone()
            if previous_ignition is not None and not int(
                previous_ignition["ignition"] or 0
            ):
                hours = self.work_hours(tenant_key)
                if hours["enabled"] and not schedule_active(
                    hours["schedule"], int(ts_ms), hours["timezone"]
                ):
                    try:
                        zone = ZoneInfo(hours["timezone"] or DEFAULT_TIMEZONE)
                    except ZoneInfoNotFoundError:
                        zone = ZoneInfo("UTC")
                    moment = datetime.fromtimestamp(int(ts_ms) / 1000, zone)
                    if self.raise_alert(
                        imei,
                        "IGNITION_OUT_OF_HOURS",
                        "HIGH",
                        f"Motore acceso alle {moment:%H:%M} di "
                        f"{_WEEKDAYS_IT[moment.weekday()]} fuori fascia lavorativa",
                        ts_ms,
                    ):
                        created.append("IGNITION_OUT_OF_HOURS")

        zones = self.geofences(tenant_key)
        if tenant_key:
            known = {zone["id"] for zone in zones}
            zones += [zone for zone in self.geofences("") if zone["id"] not in known]
        for zone in zones:
            shape = str(zone.get("shape") or "circle").lower()
            vertices = zone.get("geometry") or []
            with self._session() as conn:
                state = conn.execute(
                    "SELECT inside, last_lat, last_lon FROM geofence_states"
                    " WHERE imei = ? AND geofence_id = ?",
                    (imei, zone["id"]),
                ).fetchone()
            previous = None if state is None else bool(state["inside"])
            previous_point = (
                (state["last_lat"], state["last_lon"])
                if state is not None
                and state["last_lat"] is not None
                and state["last_lon"] is not None
                else None
            )
            boundary_crossed = False
            if shape == "line":
                inside = 0
                boundary_crossed = line_crossed(
                    previous_point, [latitude, longitude], vertices
                )
            elif shape == "polygon":
                inside = 1 if point_in_polygon(latitude, longitude, vertices) else 0
                boundary_crossed = polygon_crossed(
                    previous_point, [latitude, longitude], vertices
                )
            else:
                distance = _haversine_m(
                    latitude, longitude, zone["latitude"], zone["longitude"]
                )
                inside = 1 if distance <= zone["radius_m"] else 0
            with self._session() as conn:
                conn.execute(
                    "INSERT INTO geofence_states (imei, geofence_id, inside,"
                    " last_lat, last_lon, updated_at) VALUES (?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(imei, geofence_id) DO UPDATE SET"
                    " inside = excluded.inside, last_lat = excluded.last_lat,"
                    " last_lon = excluded.last_lon, updated_at = excluded.updated_at",
                    (imei, zone["id"], inside, latitude, longitude, _utcnow()),
                )
            if previous is None:
                continue
            if shape == "line":
                if not boundary_crossed:
                    continue
                kind = "GEOFENCE_CROSS"
                detail = f"Attraversamento del confine {zone['name']}"
                severity = "CRITICAL"
            elif previous != bool(inside):
                kind = "GEOFENCE_ENTER" if inside else "GEOFENCE_EXIT"
                detail = f"{'Ingresso in' if inside else 'Uscita da'} {zone['name']}"
                severity = "HIGH" if inside else "INFO"
            elif boundary_crossed:
                kind = "GEOFENCE_CROSS"
                detail = f"Attraversamento dell'area {zone['name']}"
                severity = "CRITICAL"
            else:
                continue
            if not schedule_active(
                zone.get("schedule") or [],
                int(ts_ms),
                zone.get("timezone") or DEFAULT_TIMEZONE,
            ):
                continue
            if self.raise_alert(
                imei,
                kind,
                severity,
                detail,
                ts_ms,
                dedupe=False,
            ):
                created.append(kind)

        return created

    def detect_power_cut(
        self,
        imei: str,
        io: dict,
        ts_ms: int,
        min_voltage: float = 8.0,
        drop_voltage: float = 3.0,
    ) -> bool:
        """Rileva la rimozione dell'alimentazione esterna dall'FMC150.

        AVL 66 e' la tensione esterna in mV, AVL 67 quella della batteria
        interna. Un valore sotto la soglia, un calo netto o la scomparsa del
        66 mentre il 67 e' ancora presente aprono un allarme UNPLUG.
        """
        current_raw = io.get(66) if 66 in io else None
        with self._session() as conn:
            rows = conn.execute(
                "SELECT io_json FROM positions WHERE imei = ? AND ts_ms < ?"
                " ORDER BY ts_ms DESC LIMIT 8",
                (imei, int(ts_ms)),
            ).fetchall()
        previous_raw = None
        for row in rows:
            try:
                previous_io = json.loads(row["io_json"] or "{}")
            except ValueError:
                continue
            if 66 in previous_io or "66" in previous_io:
                previous_raw = previous_io.get(66, previous_io.get("66"))
                break
        if previous_raw is None:
            return False
        try:
            previous_v = float(previous_raw) / 1000
        except (TypeError, ValueError):
            return False
        if previous_v < max(0.0, min_voltage):
            return False
        current_v = None
        if current_raw is not None:
            try:
                current_v = float(current_raw) / 1000
            except (TypeError, ValueError):
                current_v = None
        external_missing = current_v is None and 67 in io
        below_minimum = current_v is not None and current_v <= min_voltage
        sharp_drop = (
            current_v is not None
            and current_v < previous_v
            and previous_v - current_v >= drop_voltage
        )
        if not (external_missing or below_minimum or sharp_drop):
            return False
        shown = "assente" if current_v is None else f"{current_v:.1f} V"
        return self.raise_alert(
            imei,
            "UNPLUG",
            "CRITICAL",
            f"Alimentazione esterna interrotta: {previous_v:.1f} V -> {shown}",
            ts_ms,
        )

    def create_maintenance(
        self,
        imei: str,
        kind: str,
        due_date: str | None = None,
        due_odometer_km: float | None = None,
        note: str | None = None,
        created_by: str | None = None,
        repeat_km: float | None = None,
        repeat_months: int | None = None,
    ) -> int:
        with self._session() as conn:
            cursor = conn.execute(
                "INSERT INTO maintenance (imei, kind, due_date, due_odometer_km,"
                " note, repeat_km, repeat_months, created_at, created_by)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    imei,
                    kind,
                    due_date,
                    due_odometer_km,
                    note,
                    repeat_km,
                    repeat_months,
                    _utcnow(),
                    created_by,
                ),
            )
            return int(cursor.lastrowid)

    def maintenance(
        self,
        tenant_id: int | None = None,
        imei: str | None = None,
        open_only: bool = False,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list = []
        if tenant_id is not None:
            clauses.append("d.tenant_id = ?")
            params.append(tenant_id)
        if imei:
            clauses.append("m.imei = ?")
            params.append(imei)
        if open_only:
            clauses.append("m.completed_at IS NULL")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._session() as conn:
            rows = conn.execute(
                "SELECT m.*, d.plate, d.model, d.tenant_id,"
                " (SELECT MAX(odometer_m) FROM positions p WHERE p.imei = m.imei)"
                " AS odometer_m FROM maintenance m"
                " LEFT JOIN devices d ON d.imei = m.imei"
                f"{where} ORDER BY m.completed_at IS NOT NULL, m.due_date, m.id DESC",
                tuple(params),
            ).fetchall()
        today = datetime.now(timezone.utc).date().isoformat()
        items: list[dict] = []
        for row in rows:
            item = dict(row)
            odo = item.get("odometer_m")
            item["odometer_km"] = round(odo / 1000, 1) if odo is not None else None
            if item.get("completed_at"):
                item["status"] = "completed"
            elif (item.get("due_date") and item["due_date"] < today) or (
                item.get("due_odometer_km") is not None
                and item["odometer_km"] is not None
                and item["odometer_km"] >= item["due_odometer_km"]
            ):
                item["status"] = "overdue"
            else:
                item["status"] = "planned"
            items.append(item)
        return items

    def complete_maintenance(
        self,
        maintenance_id: int,
        completed_by: str | None = None,
        tenant_id: int | None = None,
    ) -> dict | None:
        """Chiude un intervento; se ricorrente ne pianifica il successivo."""
        with self._session() as conn:
            row = conn.execute(
                "SELECT m.* FROM maintenance m WHERE m.id = ?", (maintenance_id,)
            ).fetchone()
            if row is None or row["completed_at"]:
                return None
            if tenant_id is not None:
                owner = conn.execute(
                    "SELECT tenant_id FROM devices WHERE imei = ?", (row["imei"],)
                ).fetchone()
                if owner is None or owner["tenant_id"] != tenant_id:
                    return None
            cursor = conn.execute(
                "UPDATE maintenance SET completed_at = ?, completed_by = ?"
                " WHERE id = ? AND completed_at IS NULL",
                (_utcnow(), completed_by, maintenance_id),
            )
            if cursor.rowcount == 0:
                return None
            next_id = None
            repeat_km = row["repeat_km"]
            repeat_months = row["repeat_months"]
            if repeat_km or repeat_months:
                next_date = None
                if repeat_months and row["due_date"]:
                    base = datetime.fromisoformat(row["due_date"])
                    next_date = (base + timedelta(days=30 * int(repeat_months))).date().isoformat()
                elif repeat_months:
                    next_date = (
                        datetime.now(timezone.utc)
                        + timedelta(days=30 * int(repeat_months))
                    ).date().isoformat()
                next_km = None
                if repeat_km:
                    if row["due_odometer_km"] is not None:
                        next_km = float(row["due_odometer_km"]) + float(repeat_km)
                    else:
                        latest = conn.execute(
                            "SELECT MAX(odometer_m) FROM positions WHERE imei = ?",
                            (row["imei"],),
                        ).fetchone()[0]
                        if latest is not None:
                            next_km = round(latest / 1000 + float(repeat_km), 1)
                if next_date or next_km:
                    next_id = conn.execute(
                        "INSERT INTO maintenance (imei, kind, due_date,"
                        " due_odometer_km, note, repeat_km, repeat_months,"
                        " created_at, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            row["imei"],
                            row["kind"],
                            next_date,
                            next_km,
                            row["note"],
                            repeat_km,
                            repeat_months,
                            _utcnow(),
                            completed_by,
                        ),
                    ).lastrowid
        return {"id": maintenance_id, "next_id": next_id}

    def maintenance_due(self, tenant_id: int | None = None) -> list[dict]:
        return [
            item
            for item in self.maintenance(tenant_id, open_only=True)
            if item["status"] == "overdue"
        ]

    def positions_window(
        self, imei: str, start_ms: int, end_ms: int
    ) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM positions WHERE imei = ? AND ts_ms BETWEEN ? AND ?"
                " ORDER BY ts_ms ASC LIMIT 50000",
                (imei, start_ms, end_ms),
            ).fetchall()
        return [dict(row) for row in rows]

    def activity(
        self, imei: str, since_ms: int, stop_minutes: int = 5
    ) -> dict:
        """Tragitti e soste ricavati dalle posizioni (soglia 3 km/h)."""
        points = self.positions_range(imei, since_ms)
        trips: list[dict] = []
        stops: list[dict] = []
        trip: dict | None = None
        stop: dict | None = None
        previous: dict | None = None

        for point in points:
            moving = (point.get("speed") or 0) > 3
            stamp = point["ts_ms"]
            if moving:
                if stop is not None:
                    minutes = (stamp - stop["start_ms"]) / 60000
                    if minutes >= stop_minutes:
                        stops.append(
                            {
                                **stop,
                                "end_ms": stop["end_ms"],
                                "duration_min": round(minutes, 1),
                            }
                        )
                    stop = None
                if trip is None:
                    trip = {
                        "start_ms": stamp,
                        "start_latitude": point["latitude"],
                        "start_longitude": point["longitude"],
                        "end_ms": stamp,
                        "end_latitude": point["latitude"],
                        "end_longitude": point["longitude"],
                        "max_speed": point.get("speed") or 0,
                        "distance_m": 0.0,
                        "odometer_start": point.get("odometer_m"),
                        "_last": point,
                    }
                else:
                    trip["end_ms"] = stamp
                    trip["end_latitude"] = point["latitude"]
                    trip["end_longitude"] = point["longitude"]
                    trip["max_speed"] = max(
                        trip["max_speed"], point.get("speed") or 0
                    )
                    last = trip["_last"]
                    # Con la modalita' privacy le coordinate sono assenti:
                    # la distanza resta quella dell'odometro, senza geometria.
                    if (
                        last.get("latitude") is not None
                        and point.get("latitude") is not None
                    ):
                        trip["distance_m"] += _haversine_m(
                            last["latitude"],
                            last["longitude"],
                            point["latitude"],
                            point["longitude"],
                        )
                    trip["_last"] = point
            else:
                if trip is not None:
                    start_odo = trip.get("odometer_start")
                    end_odo = point.get("odometer_m")
                    if start_odo is not None and end_odo is not None:
                        trip["distance_m"] = max(0, end_odo - start_odo)
                    trip["duration_min"] = round(
                        (stamp - trip["start_ms"]) / 60000, 1
                    )
                    trip.pop("_last", None)
                    trips.append(trip)
                    trip = None
                if stop is None:
                    stop = {
                        "start_ms": stamp,
                        "end_ms": stamp,
                        "latitude": point["latitude"],
                        "longitude": point["longitude"],
                    }
                else:
                    stop["end_ms"] = stamp
            previous = point

        if trip is not None:
            start_odo = trip.get("odometer_start")
            end_odo = previous.get("odometer_m") if previous else None
            if start_odo is not None and end_odo is not None:
                trip["distance_m"] = max(0, end_odo - start_odo)
            trip["duration_min"] = round(
                (trip["end_ms"] - trip["start_ms"]) / 60000, 1
            )
            trip.pop("_last", None)
            trips.append(trip)
        if stop is not None:
            minutes = (stop["end_ms"] - stop["start_ms"]) / 60000
            if minutes >= stop_minutes:
                stops.append({**stop, "duration_min": round(minutes, 1)})

        return {
            "imei": imei,
            "trips": trips,
            "stops": stops,
            "counts": {"trips": len(trips), "stops": len(stops)},
        }

    def fuel_report(
        self,
        start_ms: int,
        end_ms: int,
        tenant_id: int | None = None,
        price_eur: float = 1.75,
        idle_l_per_hour: float = 2.0,
        default_consumption: float = 8.0,
        theft_liters: float = 15.0,
    ) -> dict:
        """Costi stimati: km, consumo, ore di minimo e cali anomali a motore spento."""
        items: list[dict] = []
        for device in self.devices(tenant_id):
            points = self.positions_window(device["imei"], start_ms, end_ms)
            if not points:
                continue
            odometers = [
                point["odometer_m"]
                for point in points
                if point.get("odometer_m") is not None
            ]
            km = round((max(odometers) - min(odometers)) / 1000, 1) if len(odometers) > 1 else 0.0
            idle_hours = 0.0
            dropped = 0.0
            previous = None
            previous_fuel = None
            for point in points:
                if previous is not None:
                    delta_h = (point["ts_ms"] - previous["ts_ms"]) / 3_600_000
                    if (
                        0 < delta_h <= 0.5
                        and int(previous.get("ignition") or 0)
                        and (previous.get("speed") or 0) < 1
                    ):
                        idle_hours += delta_h
                fuel = point.get("can_fuel_liters")
                if previous_fuel is not None and fuel is not None:
                    delta = previous_fuel - fuel
                    if delta >= theft_liters and not int(point.get("ignition") or 0):
                        dropped += delta
                if fuel is not None:
                    previous_fuel = fuel
                previous = point
            consumption = device.get("fuel_l_per_100km") or default_consumption
            liters = km * consumption / 100 + idle_hours * idle_l_per_hour
            items.append(
                {
                    "imei": device["imei"],
                    "plate": device.get("plate"),
                    "km": km,
                    "consumption_l_per_100km": consumption,
                    "idle_hours": round(idle_hours, 2),
                    "idle_liters": round(idle_hours * idle_l_per_hour, 1),
                    "fuel_drop_liters": round(dropped, 1),
                    "theft_suspected": dropped > 0,
                    "liters": round(liters, 1),
                    "cost_eur": round(liters * price_eur, 2),
                }
            )
        totals = {
            "km": round(sum(item["km"] for item in items), 1),
            "liters": round(sum(item["liters"] for item in items), 1),
            "cost_eur": round(sum(item["cost_eur"] for item in items), 2),
            "idle_hours": round(sum(item["idle_hours"] for item in items), 2),
            "fuel_drop_liters": round(
                sum(item["fuel_drop_liters"] for item in items), 1
            ),
        }
        return {"items": items, "totals": totals, "price_eur": price_eur}

    def notification_targets(self, imei: str) -> dict:
        """Destinatari del cliente, con i valori globali come riserva."""
        with self._session() as conn:
            row = conn.execute(
                "SELECT d.tenant_id FROM devices d WHERE d.imei = ?", (imei,)
            ).fetchone()
            tenant_key = (
                str(row["tenant_id"])
                if row and row["tenant_id"] is not None
                else ""
            )
            own = conn.execute(
                "SELECT emails, phones FROM tenant_notifications"
                " WHERE tenant_key = ?",
                (tenant_key,),
            ).fetchone()
            fallback = None
            if tenant_key:
                fallback = conn.execute(
                    "SELECT emails, phones FROM tenant_notifications"
                    " WHERE tenant_key = ''"
                ).fetchone()
        emails = (own["emails"] if own else "") or ""
        phones = (own["phones"] if own else "") or ""
        if fallback is not None:
            emails = emails or (fallback["emails"] or "")
            phones = phones or (fallback["phones"] or "")
        return {"tenant_key": tenant_key, "emails": emails, "phones": phones}

    def record_notification_outbox(
        self,
        *,
        imei: str | None,
        channel: str,
        provider: str | None,
        mode: str | None,
        recipients: str,
        subject: str | None,
        body: str,
        status: str,
        detail: str | None = None,
    ) -> int:
        """Registra una notifica; il tenant e' ricavato dal mezzo."""
        tenant_key = ""
        if imei:
            with self._session() as conn:
                row = conn.execute(
                    "SELECT tenant_id FROM devices WHERE imei = ?", (imei,)
                ).fetchone()
            if row and row["tenant_id"] is not None:
                tenant_key = str(row["tenant_id"])
        with self._session() as conn:
            cursor = conn.execute(
                "INSERT INTO notification_outbox (tenant_key, imei, channel,"
                " provider, mode, recipients, subject, body, status, detail,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant_key,
                    imei,
                    channel,
                    provider,
                    mode,
                    recipients[:1000],
                    subject[:500] if subject else None,
                    body[:4000],
                    status,
                    detail[:1000] if detail else None,
                    _utcnow(),
                ),
            )
            return int(cursor.lastrowid)

    def notification_outbox(
        self, tenant_id: int | None = None, limit: int = 200
    ) -> list[dict]:
        query = "SELECT * FROM notification_outbox"
        params: tuple[object, ...] = ()
        if tenant_id is not None:
            query += " WHERE tenant_key = ?"
            params = (str(tenant_id),)
        query += " ORDER BY id DESC LIMIT ?"
        params += (max(1, min(1000, int(limit))),)
        with self._session() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def tenant_notification_settings(self, tenant_key: str) -> dict:
        with self._session() as conn:
            row = conn.execute(
                "SELECT * FROM tenant_notifications WHERE tenant_key = ?",
                (tenant_key,),
            ).fetchone()
        return dict(row) if row else {
            "tenant_key": tenant_key,
            "emails": "",
            "phones": "",
        }

    def save_tenant_notification_settings(
        self,
        tenant_key: str,
        emails: str,
        phones: str,
        updated_by: str | None = None,
    ) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO tenant_notifications (tenant_key, emails, phones,"
                " updated_at, updated_by) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(tenant_key) DO UPDATE SET"
                " emails = excluded.emails, phones = excluded.phones,"
                " updated_at = excluded.updated_at,"
                " updated_by = excluded.updated_by",
                (tenant_key, emails, phones, _utcnow(), updated_by),
            )

    def tenant_solution(self, tenant_key: str) -> dict:
        with self._session() as conn:
            row = conn.execute(
                "SELECT * FROM tenant_solutions WHERE tenant_key = ?",
                (tenant_key,),
            ).fetchone()
        if row:
            return dict(row)
        return {
            "tenant_key": tenant_key,
            "vertical": "trasporti_pesanti",
            "connectivity": "4g",
            "maps": "osm",
        }

    def save_tenant_solution(
        self, tenant_key: str, vertical: str, connectivity: str, maps: str,
        updated_by: str | None = None,
    ) -> None:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO tenant_solutions (tenant_key, vertical, connectivity,"
                " maps, updated_at, updated_by) VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(tenant_key) DO UPDATE SET"
                " vertical = excluded.vertical,"
                " connectivity = excluded.connectivity, maps = excluded.maps,"
                " updated_at = excluded.updated_at,"
                " updated_by = excluded.updated_by",
                (tenant_key, vertical, connectivity, maps, _utcnow(), updated_by),
            )

    def add_driver(self, name: str, badge: str, tenant_id: int | None) -> dict:
        with self._session() as conn:
            conn.execute(
                "INSERT INTO drivers (tenant_id, name, badge, created_at)"
                " VALUES (?, ?, ?, ?) ON CONFLICT(tenant_id, badge)"
                " DO UPDATE SET name = excluded.name",
                (tenant_id, name, badge, _utcnow()),
            )
            row = conn.execute(
                "SELECT * FROM drivers WHERE tenant_id IS ? AND badge = ?",
                (tenant_id, badge),
            ).fetchone()
        return dict(row) if row else {}

    def drivers(self, tenant_id: int | None = None) -> list[dict]:
        with self._session() as conn:
            if tenant_id is None:
                rows = conn.execute("SELECT * FROM drivers ORDER BY name").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM drivers WHERE tenant_id = ? ORDER BY name",
                    (tenant_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    def tenants(self) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT id, name, active FROM tenants ORDER BY name"
            ).fetchall()
        return [dict(row) for row in rows]

    def driving_positions(
        self, hours: int, tenant_id: int | None = None, limit: int = 5000
    ) -> list[dict]:
        cutoff = int((time.time() - max(1, hours) * 3600) * 1000)
        with self._session() as conn:
            if tenant_id is None:
                rows = conn.execute(
                    "SELECT p.imei, p.ts_ms, p.speed, p.io_json, d.plate"
                    " FROM positions p JOIN devices d ON d.imei = p.imei"
                    " WHERE p.ts_ms >= ? ORDER BY p.ts_ms DESC LIMIT ?",
                    (cutoff, max(1, limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT p.imei, p.ts_ms, p.speed, p.io_json, d.plate"
                    " FROM positions p JOIN devices d ON d.imei = p.imei"
                    " WHERE p.ts_ms >= ? AND d.tenant_id = ?"
                    " ORDER BY p.ts_ms DESC LIMIT ?",
                    (cutoff, tenant_id, max(1, limit)),
                ).fetchall()
        # La query limita prendendo le piu' recenti; il calcolo vuole l'ordine
        # cronologico per confrontare ogni posizione con la precedente.
        rows = list(reversed(rows))
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["io"] = json.loads(item.get("io_json") or "{}")
            except ValueError:
                item["io"] = {}
            result.append(item)
        return result

    def can_dispatch(
        self, imei: str, kind: str, channel: str, cooldown_minutes: int
    ) -> bool:
        """True se il canale e' libero; non registra nulla."""
        now = datetime.now(timezone.utc)
        with self._session() as conn:
            row = conn.execute(
                "SELECT last_sent_at FROM alert_dispatches"
                " WHERE imei = ? AND kind = ? AND channel = ?",
                (imei, kind, channel),
            ).fetchone()
        if not row:
            return True
        last = datetime.fromisoformat(row["last_sent_at"])
        return now - last >= timedelta(minutes=max(0, cooldown_minutes))

    def mark_dispatched(self, imei: str, kind: str, channel: str) -> None:
        """Registra l'invio riuscito: solo dopo il successo del canale."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._session() as conn:
            conn.execute(
                "INSERT INTO alert_dispatches (imei, kind, channel, last_sent_at)"
                " VALUES (?, ?, ?, ?) ON CONFLICT(imei, kind, channel) DO UPDATE"
                " SET last_sent_at = excluded.last_sent_at",
                (imei, kind, channel, now),
            )

    def enqueue_webhook(
        self, event: str, payload: str, max_pending: int = 1000
    ) -> int:
        now = _utcnow()
        with self._session() as conn:
            pending = conn.execute(
                "SELECT COUNT(*) FROM webhook_outbox WHERE status = 'pending'"
            ).fetchone()[0]
            # Coda piena: l'evento va in overflow, non viene perso.
            status = (
                "overflow"
                if int(pending) >= max(1, max_pending)
                else "pending"
            )
            cursor = conn.execute(
                "INSERT INTO webhook_outbox (event, payload, attempts,"
                " next_attempt, status, created_at) VALUES (?, ?, 0, ?, ?, ?)",
                (event, payload, now, status, now),
            )
            return int(cursor.lastrowid)

    def promote_overflow(self, max_pending: int = 1000) -> int:
        """Riporta in consegna gli eventi in overflow, senza perderli."""
        with self._session() as conn:
            pending = conn.execute(
                "SELECT COUNT(*) FROM webhook_outbox WHERE status = 'pending'"
            ).fetchone()[0]
            free = max(0, max(1, max_pending) - int(pending))
            if not free:
                return 0
            cursor = conn.execute(
                "UPDATE webhook_outbox SET status = 'pending' WHERE id IN ("
                "SELECT id FROM webhook_outbox WHERE status = 'overflow'"
                " ORDER BY id LIMIT ?)",
                (free,),
            )
            return int(cursor.rowcount or 0)

    def due_webhooks(self, limit: int = 20) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM webhook_outbox WHERE status = 'pending'"
                " AND next_attempt <= ? ORDER BY id LIMIT ?",
                (_utcnow(), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def webhook_delivered(self, webhook_id: int) -> None:
        with self._session() as conn:
            conn.execute(
                "UPDATE webhook_outbox SET status = 'delivered', last_error = NULL"
                " WHERE id = ?",
                (webhook_id,),
            )

    def webhook_failed(
        self, webhook_id: int, error: str, max_attempts: int,
        permanent: bool = False,
    ) -> None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT attempts FROM webhook_outbox WHERE id = ?", (webhook_id,)
            ).fetchone()
            attempts = int(row["attempts"]) + 1 if row else 1
            status = (
                "failed" if permanent or attempts >= max_attempts else "pending"
            )
            delay = min(300, 5 * (2 ** min(attempts, 6)))
            next_attempt = (
                datetime.now(timezone.utc) + timedelta(seconds=delay)
            ).isoformat(timespec="seconds")
            conn.execute(
                "UPDATE webhook_outbox SET attempts = ?, status = ?, last_error = ?,"
                " next_attempt = ? WHERE id = ?",
                (attempts, status, error[:500], next_attempt, webhook_id),
            )

    def prune_webhooks(self, days: int = 7) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=max(1, days))
        ).isoformat(timespec="seconds")
        with self._session() as conn:
            cursor = conn.execute(
                "DELETE FROM webhook_outbox WHERE status IN ('delivered','failed')"
                " AND created_at < ?",
                (cutoff,),
            )
            return int(cursor.rowcount or 0)

    def webhook_stats(self) -> dict:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS total FROM webhook_outbox GROUP BY status"
            ).fetchall()
        stats = {
            "pending": 0, "overflow": 0, "delivered": 0, "failed": 0
        }
        for row in rows:
            stats[row["status"]] = row["total"]
        return stats

    def record_sms_receipt(
        self,
        provider_id: str | None,
        recipient: str | None,
        status: str | None,
        raw: str,
    ) -> int:
        with self._session() as conn:
            cursor = conn.execute(
                "INSERT INTO sms_receipts (provider_id, recipient, status, raw,"
                " received_at) VALUES (?, ?, ?, ?, ?)",
                (provider_id, recipient, status, raw, _utcnow()),
            )
            return int(cursor.lastrowid)

    def sms_receipts(self, limit: int = 200) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM sms_receipts ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def create_safety_check(
        self,
        imei: str,
        kind: str,
        compliant: bool,
        note: str | None,
        checked_by: str | None,
    ) -> int:
        with self._session() as conn:
            cursor = conn.execute(
                "INSERT INTO safety_checks (imei, kind, compliant, note,"
                " checked_at, checked_by) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    imei,
                    kind,
                    1 if compliant else 0,
                    note,
                    _utcnow(),
                    checked_by,
                ),
            )
            return int(cursor.lastrowid)

    def safety_checks(
        self, tenant_id: int | None = None, limit: int = 200
    ) -> list[dict]:
        where = ""
        params: list = []
        if tenant_id is not None:
            where = " WHERE d.tenant_id = ?"
            params.append(tenant_id)
        params.append(limit)
        with self._session() as conn:
            rows = conn.execute(
                "SELECT s.*, d.plate, d.tenant_id FROM safety_checks s"
                " LEFT JOIN devices d ON d.imei = s.imei"
                f"{where} ORDER BY s.id DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def safety_summary(self, tenant_id: int | None = None) -> dict:
        checks = self.safety_checks(tenant_id, 5000)
        compliant = sum(1 for item in checks if item["compliant"])
        return {
            "total": len(checks),
            "compliant": compliant,
            "non_compliant": len(checks) - compliant,
        }

    def raise_alert(
        self,
        imei: str,
        kind: str,
        severity: str,
        detail: str,
        ts_ms: int | None = None,
        dedupe: bool = True,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> bool:
        """Apre un allarme; con dedupe evita doppioni finche' quello resta aperto.

        Le coordinate sono opzionali e servono all'eccezione SOS: con la
        modalita' privacy attiva il dettaglio dell'allarme resta l'unico
        posto in cui la posizione istantanea viene conservata.
        """
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._session() as conn:
            if dedupe:
                existing = conn.execute(
                    "SELECT id FROM alerts WHERE imei = ? AND kind = ?"
                    " AND acknowledged_at IS NULL LIMIT 1",
                    (imei, kind),
                ).fetchone()
                if existing:
                    return False
            conn.execute(
                "INSERT INTO alerts (imei, kind, severity, detail, ts_ms,"
                " latitude, longitude, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (imei, kind, severity, detail, ts_ms, latitude, longitude, now),
            )
        return True

    def alert_details(
        self, imei: str, kinds: list[str], ts_ms: int | None = None
    ) -> list[dict]:
        """Dettagli degli allarmi appena aperti, per email e webhook."""
        if not kinds:
            return []
        with self._session() as conn:
            if ts_ms is None:
                rows = conn.execute(
                    "SELECT id, kind, severity, detail, latitude, longitude"
                    " FROM alerts WHERE imei = ? ORDER BY id DESC LIMIT 20",
                    (imei,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, kind, severity, detail, latitude, longitude"
                    " FROM alerts WHERE imei = ? AND ts_ms = ?"
                    " ORDER BY id DESC LIMIT 20",
                    (imei, int(ts_ms)),
                ).fetchall()
        wanted = set(kinds)
        return [dict(row) for row in rows if row["kind"] in wanted]

    def alerts(
        self,
        limit: int = 100,
        open_only: bool = False,
        tenant_id: int | None = None,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list = []
        if open_only:
            clauses.append("a.acknowledged_at IS NULL")
        if tenant_id is not None:
            clauses.append("d.tenant_id = ?")
            params.append(tenant_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._session() as conn:
            rows = conn.execute(
                "SELECT a.*, d.plate, d.tenant_id FROM alerts a"
                " LEFT JOIN devices d ON d.imei = a.imei"
                f"{where} ORDER BY a.id DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def alert(self, alert_id: int) -> dict | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT a.*, d.tenant_id, d.plate FROM alerts a"
                " LEFT JOIN devices d ON d.imei = a.imei WHERE a.id = ?",
                (alert_id,),
            ).fetchone()
        return dict(row) if row else None

    def acknowledge_alert(self, alert_id: int, acknowledged_by: str) -> bool:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._session() as conn:
            cursor = conn.execute(
                "UPDATE alerts SET acknowledged_at = ?, acknowledged_by = ?"
                " WHERE id = ? AND acknowledged_at IS NULL",
                (now, acknowledged_by, alert_id),
            )
        return cursor.rowcount > 0

    def list_users(self) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT u.username, u.role, u.tenant_id, u.full_name, u.active,"
                " u.created_at, u.must_change, u.locked_until, u.last_login_at,"
                " t.name AS tenant_name FROM users u"
                " LEFT JOIN tenants t ON t.id = u.tenant_id ORDER BY u.username"
            ).fetchall()
        return [dict(row) for row in rows]

    def register_success(self, username: str) -> None:
        now = _utcnow()
        with self._session() as conn:
            conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL,"
                " last_login_at = ? WHERE username = ?",
                (now, username),
            )

    def register_failure(
        self, username: str, max_attempts: int, lock_minutes: int
    ) -> dict:
        """Conta il tentativo fallito e blocca l'account al limite."""
        with self._session() as conn:
            row = conn.execute(
                "SELECT failed_attempts FROM users WHERE username = ?", (username,)
            ).fetchone()
            if row is None:
                return {"attempts": 0, "remaining": max_attempts, "locked_until": None}
            attempts = int(row["failed_attempts"] or 0) + 1
            locked_until = None
            if attempts >= max_attempts:
                locked_until = (
                    datetime.now(timezone.utc) + timedelta(minutes=lock_minutes)
                ).isoformat(timespec="seconds")
                attempts = 0
            conn.execute(
                "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE username = ?",
                (attempts, locked_until, username),
            )
        return {
            "attempts": attempts,
            "remaining": max(0, max_attempts - attempts),
            "locked_until": locked_until,
        }

    def set_password(
        self, username: str, password: str, must_change: bool = False
    ) -> bool:
        """Imposta una nuova password e invalida le sessioni esistenti."""
        from .auth import hash_password

        with self._session() as conn:
            cursor = conn.execute(
                "UPDATE users SET password_hash = ?, password_changed_at = ?,"
                " must_change = ?, failed_attempts = 0, locked_until = NULL,"
                " password_version = COALESCE(password_version, 0) + 1"
                " WHERE username = ?",
                (hash_password(password), _utcnow(), 1 if must_change else 0, username),
            )
        return cursor.rowcount > 0

    def unlock(self, username: str) -> bool:
        with self._session() as conn:
            cursor = conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL"
                " WHERE username = ?",
                (username,),
            )
        return cursor.rowcount > 0

    def last_command(self, imei: str) -> dict | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT action, command, accepted, created_at FROM command_audit"
                " WHERE imei = ? ORDER BY id DESC LIMIT 1",
                (imei,),
            ).fetchone()
        return dict(row) if row else None

    def esg_daily(
        self,
        since_ms: int,
        tenant_id: int | None = None,
        until_ms: int | None = None,
    ) -> list[dict]:
        """Chilometri al giorno per mezzo, dall'odometro CAN."""
        clauses = ["p.odometer_m IS NOT NULL", "p.ts_ms >= ?"]
        params: list = [since_ms]
        if until_ms is not None:
            clauses.append("p.ts_ms <= ?")
            params.append(until_ms)
        if tenant_id is not None:
            clauses.append("d.tenant_id = ?")
            params.append(tenant_id)
        with self._session() as conn:
            rows = conn.execute(
                "SELECT p.imei, d.plate, d.fuel_l_per_100km, d.co2_kg_per_liter,"
                " date(p.ts_ms / 1000, 'unixepoch') AS day,"
                " MAX(p.odometer_m) - MIN(p.odometer_m) AS meters, COUNT(*) AS samples"
                " FROM positions p LEFT JOIN devices d ON d.imei = p.imei"
                f" WHERE {' AND '.join(clauses)}"
                " GROUP BY p.imei, day ORDER BY day, p.imei",
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_commands(
        self, limit: int = 100, tenant_id: int | None = None
    ) -> list[dict]:
        params: list = []
        where = ""
        if tenant_id is not None:
            where = " WHERE d.tenant_id = ?"
            params.append(tenant_id)
        params.append(limit)
        with self._session() as conn:
            rows = conn.execute(
                "SELECT c.*, d.plate FROM command_audit c"
                " LEFT JOIN devices d ON d.imei = c.imei"
                f"{where} ORDER BY c.id DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def positions(self, imei: str, limit: int = 100) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM positions WHERE imei = ? ORDER BY ts_ms DESC LIMIT ?",
                (imei, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def positions_day(self, imei: str, start_ms: int, end_ms: int) -> list[dict]:
        """Posizioni di una giornata, dalla piu' vecchia alla piu' nuova."""
        with self._session() as conn:
            rows = conn.execute(
                "SELECT imei, ts_ms, latitude, longitude, speed, angle, ignition"
                " FROM positions WHERE imei = ? AND ts_ms >= ? AND ts_ms < ?"
                " ORDER BY ts_ms ASC LIMIT 20000",
                (imei, start_ms, end_ms),
            ).fetchall()
        return [dict(row) for row in rows]

    def positions_range(self, imei: str, since_ms: int) -> list[dict]:
        """Posizioni dall'istante indicato, dalla piu' vecchia alla piu' nuova."""
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM positions WHERE imei = ? AND ts_ms >= ?"
                " ORDER BY ts_ms ASC LIMIT 50000",
                (imei, since_ms),
            ).fetchall()
        return [dict(row) for row in rows]

    def prune_positions(self, retention_days: int, batch_size: int = 5000) -> int:
        """Elimina a lotti le posizioni piu' vecchie di N giorni.

        Ogni lotto e' una transazione breve: il lock di scrittura non resta
        aperto per tutta la cancellazione. Gli snapshot ESG sono payload gia'
        congelati e non vengono toccati. Con 0 giorni non cancella nulla.
        """
        if retention_days <= 0:
            return 0
        cutoff_ms = int(
            (
                datetime.now(timezone.utc) - timedelta(days=retention_days)
            ).timestamp()
            * 1000
        )
        size = max(1, batch_size)
        deleted = 0
        while True:
            with self._session() as conn:
                cursor = conn.execute(
                    "DELETE FROM positions WHERE id IN ("
                    " SELECT id FROM positions WHERE ts_ms < ?"
                    " ORDER BY ts_ms LIMIT ?)",
                    (cutoff_ms, size),
                )
                removed = cursor.rowcount
            deleted += removed
            if removed < size:
                return deleted

    def prune_alerts(self, retention_days: int, batch_size: int = 5000) -> int:
        """Elimina gli allarmi piu' vecchi di N giorni (retention separata).

        Le posizioni SOS vivono nel record dell'allarme: questa retention
        decide per quanto restano consultabili. Con 0 giorni non cancella.
        """
        if retention_days <= 0:
            return 0
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=retention_days)
        ).isoformat(timespec="seconds")
        size = max(1, batch_size)
        deleted = 0
        while True:
            with self._session() as conn:
                cursor = conn.execute(
                    "DELETE FROM alerts WHERE id IN ("
                    " SELECT id FROM alerts WHERE created_at < ?"
                    " ORDER BY created_at LIMIT ?)",
                    (cutoff, size),
                )
                removed = cursor.rowcount
            deleted += removed
            if removed < size:
                return deleted

    def last_position(self, imei: str) -> dict | None:
        """Ultima posizione nota: serve alla guardia sul blocco motore."""
        with self._session() as conn:
            row = conn.execute(
                "SELECT imei, ts_ms, latitude, longitude, speed, ignition"
                " FROM positions WHERE imei = ? ORDER BY ts_ms DESC LIMIT 1",
                (imei,),
            ).fetchone()
        return dict(row) if row else None

    def record_command(
        self,
        imei: str,
        action: str,
        command: str,
        requested_by: str | None,
        accepted: bool,
        detail: str = "",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._session() as conn:
            conn.execute(
                "INSERT INTO command_audit"
                " (imei, action, command, requested_by, accepted, detail, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (imei, action, command, requested_by, int(accepted), detail, now),
            )

    def commands(self, imei: str, limit: int = 50) -> list[dict]:
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM command_audit WHERE imei = ? ORDER BY id DESC LIMIT ?",
                (imei, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def is_active(self, imei: str) -> bool:
        with self._session() as conn:
            row = conn.execute(
                "SELECT status FROM devices WHERE imei = ?", (imei,)
            ).fetchone()
        return bool(row and row["status"] == "active")

    def activate(self, imei: str, plate: str | None, model: str | None) -> bool:
        with self._session() as conn:
            cursor = conn.execute(
                "UPDATE devices SET status = 'active',"
                " plate = COALESCE(?, plate), model = COALESCE(?, model)"
                " WHERE imei = ?",
                (plate, model, imei),
            )
        return cursor.rowcount > 0

    def privacy_enabled(self, imei: str) -> bool:
        """True se il mezzo e' in modalita' privacy (coordinate non salvate)."""
        with self._session() as conn:
            row = conn.execute(
                "SELECT privacy_mode FROM devices WHERE imei = ?", (imei,)
            ).fetchone()
        return bool(row and row["privacy_mode"])

    def set_privacy_mode(
        self, imei: str, enabled: bool, updated_by: str | None = None
    ) -> bool:
        """Accende o spegne la privacy; ritorna False se l'IMEI non esiste."""
        with self._session() as conn:
            cursor = conn.execute(
                "UPDATE devices SET privacy_mode = ? WHERE imei = ?",
                (1 if enabled else 0, imei),
            )
            if cursor.rowcount == 0:
                return False
            if enabled and conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table'"
                " AND name = 'vehicles'"
            ).fetchone():
                # La dashboard non deve continuare a mostrare l'ultima
                # posizione nota del mezzo finita in modalita' privacy.
                conn.execute(
                    "UPDATE vehicles SET latitude = NULL, longitude = NULL"
                    " WHERE device_imei = ?",
                    (imei,),
                )
            conn.execute(
                "INSERT INTO admin_audit (actor, action, target, detail,"
                " created_at) VALUES (?, 'privacy_mode', ?, ?, ?)",
                (
                    updated_by or "sistema",
                    imei,
                    "on" if enabled else "off",
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
        return True

    def update_device(
        self,
        imei: str,
        plate: str | None,
        model: str | None,
        note: str | None = None,
    ) -> bool:
        """Aggiorna i dati anagrafici del mezzo. Targa e modello vuoti = assenti."""
        with self._session() as conn:
            cursor = conn.execute(
                "UPDATE devices SET plate = ?, model = ?, note = ? WHERE imei = ?",
                (plate or None, model or None, note or None, imei),
            )
        return cursor.rowcount > 0

    # Dati figli del mezzo: senza questi un IMEI eliminato resterebbe presente
    # in storico, allarmi e coda notifiche.
    DEVICE_CHILD_TABLES = (
        "positions",
        "command_audit",
        "alerts",
        "vehicle_esg_params",
        "geofence_states",
        "alert_dispatches",
        "maintenance",
        "safety_checks",
        "notification_outbox",
    )

    def delete_device(self, imei: str) -> dict:
        """Elimina il mezzo e i dati che gli appartengono, in una transazione."""
        with self._session() as conn:
            row = conn.execute(
                "SELECT imei FROM devices WHERE imei = ?", (imei,)
            ).fetchone()
            if row is None:
                return {"removed": 0, "tables": {}}
            removed = 0
            tables: dict[str, int] = {}
            for table in self.DEVICE_CHILD_TABLES:
                cursor = conn.execute(
                    f"DELETE FROM {table} WHERE imei = ?", (imei,)
                )
                tables[table] = cursor.rowcount
                removed += cursor.rowcount
            conn.execute("DELETE FROM devices WHERE imei = ?", (imei,))
        return {"removed": removed + 1, "tables": tables}
