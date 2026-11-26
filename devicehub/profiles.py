"""Profili dispositivo: traducono gli AVL ID grezzi in campi di dominio.

Gli ID degli ingressi digitali e della tensione sono comuni a tutta la
famiglia TM2500, ma i parametri CAN dipendono dal profilo CAN caricato sul
veicolo (LV-CAN200 / ALL-CAN300 per FMB140): per questo la mappa e'
sovrascrivibile da file e gli ID non mappati restano salvati nel JSON grezzo.

Regola pratica: prima di fidarsi di un ID CAN, accendere l'auto con
DEVICEHUB_LOG_IO=1 e leggere dal log quale ID si muove.
"""

from __future__ import annotations

import json
from pathlib import Path

from .teltonika import AvlRecord

# ID documentati e stabili sulla famiglia FMB/FMC.
DEFAULT_IO_MAP: dict[int, str] = {
    1: "din1",
    16: "odometer_m",
    21: "gsm_level",
    66: "external_voltage_mv",
    67: "battery_voltage_mv",
    239: "ignition",
    240: "movement",
}

# Campi che finiscono nella tabella vehicles dell'applicazione esistente.
VEHICLE_FIELD_MAP: dict[str, str] = {
    "can_rpm": "can_rpm",
    "can_fuel_liters": "can_fuel_liters",
    "engine_temp": "engine_temp",
    "engine_hours": "engine_hours",
}


class DeviceProfile:
    def __init__(
        self,
        name: str,
        io_map: dict[int, str] | None = None,
        divisors: dict[str, float] | None = None,
    ) -> None:
        self.name = name
        self.io_map = dict(DEFAULT_IO_MAP if io_map is None else io_map)
        self.divisors = dict(divisors or {})

    @classmethod
    def from_file(cls, path: str | Path) -> "DeviceProfile":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        io_map = {int(key): value for key, value in payload.get("io", {}).items()}
        return cls(
            name=payload.get("name", Path(path).stem),
            io_map=io_map or DEFAULT_IO_MAP,
            divisors=payload.get("divisors", {}),
        )

    def normalize(self, record: AvlRecord) -> dict:
        """Restituisce i campi di dominio ricavabili dagli IO del record."""
        values: dict[str, float | int | None] = {}
        for avl_id, raw in record.io.items():
            target = self.io_map.get(avl_id)
            if not target:
                continue
            value: float = raw
            divisor = self.divisors.get(target)
            if divisor:
                value = raw / divisor
            values[target] = value

        external_mv = values.get("external_voltage_mv")
        battery_mv = values.get("battery_voltage_mv")
        source_mv = external_mv if external_mv is not None else battery_mv

        odometer_m = values.get("odometer_m")

        return {
            "ignition": int(values.get("ignition", 0) or 0),
            "speed": record.speed,
            "latitude": record.latitude,
            "longitude": record.longitude,
            "odometer_m": int(odometer_m) if odometer_m is not None else None,
            "battery_voltage": round(source_mv / 1000, 2) if source_mv else None,
            "can_rpm": _as_int(values.get("can_rpm")),
            "can_fuel_liters": _as_float(values.get("can_fuel_liters")),
            "fuel_level_pct": _as_float(values.get("fuel_level_pct")),
            "engine_temp": _as_float(values.get("engine_temp")),
            "engine_hours": _as_float(values.get("engine_hours")),
        }


def _as_int(value) -> int | None:
    return int(value) if value is not None else None


def _as_float(value) -> float | None:
    return round(float(value), 2) if value is not None else None
