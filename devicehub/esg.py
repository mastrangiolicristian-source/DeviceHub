"""Calcolo del report ESG, condiviso tra endpoint live e snapshot mensili.

La distanza e' misurata (odometro CAN); consumo e fattore di emissione sono
assunzioni dichiarate, per flotta o per singolo mezzo, con storia e decorrenza.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Settings
from .store import TelemetryStore


def build_report(
    store: TelemetryStore,
    settings: Settings,
    tenant_id: int | None,
    since_ms: int,
    until_ms: int,
    now_ms: int | None = None,
) -> dict:
    """Aggregato ESG per la finestra [since_ms, until_ms]."""
    reference = now_ms if now_ms is not None else int(time.time() * 1000)
    fuel = settings.fuel_l_per_100km
    factor = settings.co2_kg_per_liter
    history = store.esg_param_history()
    fleet_rows = {device["imei"]: device for device in store.devices(tenant_id)}

    def params_at(
        imei: str, ts_ms: int, fallback: tuple[float | None, float | None]
    ) -> tuple[float | None, float | None]:
        """Parametri in vigore in quell'istante, non quelli di oggi."""
        rows = history.get(imei)
        if not rows:
            # Database precedente alla storia: valgono i valori correnti.
            return fallback
        chosen: tuple[float | None, float | None] = (None, None)
        for row in rows:
            if int(row["valid_from_ms"]) <= ts_ms:
                chosen = (row["fuel_l_per_100km"], row["co2_kg_per_liter"])
            else:
                break
        # Prima della prima decorrenza: valori di flotta, non quelli odierni.
        return chosen

    def day_end_ms(day: str) -> int:
        start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int((start + timedelta(days=1)).timestamp() * 1000) - 1

    per_device: dict[str, dict] = {}
    daily: dict[str, dict[str, dict]] = {}
    for row in store.esg_daily(since_ms, tenant_id, until_ms):
        imei = row["imei"]
        km = max(0.0, int(row["meters"] or 0) / 1000.0)
        legacy = (row.get("fuel_l_per_100km"), row.get("co2_kg_per_liter"))
        fuel_p, factor_p = params_at(imei, day_end_ms(row["day"]), legacy)
        liters = km * (fuel_p if fuel_p is not None else fuel) / 100.0
        co2 = liters * (factor_p if factor_p is not None else factor)
        entry = per_device.setdefault(
            imei,
            {
                "imei": imei,
                "plate": row.get("plate"),
                "km": 0.0,
                "liters": 0.0,
                "co2": 0.0,
                "days": 0,
                "samples": 0,
            },
        )
        entry["km"] += km
        entry["liters"] += liters
        entry["co2"] += co2
        entry["days"] += 1
        entry["samples"] += int(row["samples"] or 0)
        daily.setdefault(row["day"], {})[imei] = {
            "km": km,
            "liters": liters,
            "co2": co2,
        }

    devices = []
    for entry in sorted(per_device.values(), key=lambda item: -item["km"]):
        device_row = fleet_rows.get(entry["imei"]) or {}
        current_fuel, current_factor = params_at(
            entry["imei"],
            reference,
            (device_row.get("fuel_l_per_100km"), device_row.get("co2_kg_per_liter")),
        )
        devices.append(
            {
                "imei": entry["imei"],
                "plate": entry["plate"],
                "km": round(entry["km"], 2),
                "liters": round(entry["liters"], 2),
                "co2_kg": round(entry["co2"], 2),
                "grams_per_km": round(entry["co2"] * 1000 / entry["km"], 1)
                if entry["km"]
                else 0.0,
                "days": entry["days"],
                "samples": entry["samples"],
                "fuel_l_per_100km": round(current_fuel, 2)
                if current_fuel is not None
                else fuel,
                "co2_kg_per_liter": round(current_factor, 2)
                if current_factor is not None
                else factor,
                "params_source": "veicolo"
                if current_fuel is not None or current_factor is not None
                else "flotta",
            }
        )

    total_km = sum(item["km"] for item in devices)
    total_liters = sum(item["liters"] for item in devices)
    total_co2 = sum(item["co2_kg"] for item in devices)
    known = {item["imei"] for item in devices}
    series = [
        {
            "date": day,
            "km": round(sum(item["km"] for item in by_vehicle.values()), 2),
            "liters": round(sum(item["liters"] for item in by_vehicle.values()), 2),
            "co2_kg": round(sum(item["co2"] for item in by_vehicle.values()), 2),
        }
        for day, by_vehicle in sorted(daily.items())
    ]
    return {
        "assumptions": {
            "fuel_l_per_100km": fuel,
            "co2_kg_per_liter": factor,
            "distance": "odometro CAN (AVL 87), metri",
        },
        "totals": {
            "km": round(total_km, 2),
            "liters": round(total_liters, 2),
            "co2_kg": round(total_co2, 2),
            "grams_per_km": round(total_co2 * 1000 / total_km, 1) if total_km else 0.0,
        },
        "devices": devices,
        "daily": series,
        "devices_without_data": [
            imei for imei in fleet_rows if imei not in known
        ],
    }


DEFAULT_REPORT_TIMEZONE = "Europe/Rome"


def report_zone(timezone_name: str | None) -> ZoneInfo:
    """Fuso del cliente, con un errore chiaro se il nome non esiste."""
    try:
        return ZoneInfo(timezone_name or DEFAULT_REPORT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("fuso orario non valido") from exc


def month_window(
    month: str,
    now: datetime | None = None,
    timezone_name: str = DEFAULT_REPORT_TIMEZONE,
) -> tuple[int, int, str]:
    """Confini del mese civile nel fuso del cliente, in millisecondi UTC.

    Un report di novembre per un cliente italiano parte dal 1° novembre alle
    00:00 locali (31 ottobre 23:00 UTC) e non dalla mezzanotte UTC: cosi' i
    viaggi notturni finiscono nel mese giusto anche quando l'ora legale cambia.
    """
    now = now or datetime.now(timezone.utc)
    zone = report_zone(timezone_name)
    start = datetime.strptime(month, "%Y-%m").replace(tzinfo=zone)
    following = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    start_utc = start.astimezone(timezone.utc)
    end_utc = following.astimezone(timezone.utc) - timedelta(milliseconds=1)
    if start_utc > now:
        raise ValueError("mese futuro")
    return (
        int(start_utc.timestamp() * 1000),
        int(min(end_utc, now).timestamp() * 1000),
        start.strftime("%Y-%m"),
    )


def previous_period(
    now: datetime | None = None,
    timezone_name: str = DEFAULT_REPORT_TIMEZONE,
) -> str:
    """Mese da chiudere quando non ne viene indicato uno: quello precedente."""
    zone = report_zone(timezone_name)
    local = (now or datetime.now(timezone.utc)).astimezone(zone)
    return (local.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
