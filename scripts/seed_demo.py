"""Crea un database demo completo: utenti, flotta, storico e autista."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devicehub.config import Settings
from devicehub.profiles import DeviceProfile
from devicehub.store import TelemetryStore
from devicehub.teltonika import AvlRecord

PASSWORD = os.getenv("DEVICEHUB_ADMIN_PASSWORD", "Demo-Cliente-2026")
MANAGER_PASSWORD = os.getenv("DEVICEHUB_DEMO_MANAGER_PASSWORD", "Manager-Demo-2026")
TENANT = os.getenv("DEVICEHUB_DEMO_TENANT", "Cliente Demo")

DEVICES = [
    ("352093086403655", "DEMO-01", "FMC150"),
    ("352093086403656", "DEMO-02", "FMC150"),
    ("352093086403657", "DEMO-03", "FMC150"),
]


def main() -> None:
    settings = Settings.from_env()
    store = TelemetryStore(
        settings.db_path, DeviceProfile.from_file("profiles/fmc150.json")
    )
    tenant = store.ensure_tenant(TENANT)

    store.create_user(
        "demo", PASSWORD, "admin", None, "Demo Admin", must_change=False
    )
    store.create_user(
        "demo.manager",
        MANAGER_PASSWORD,
        "manager",
        tenant,
        "Demo Manager",
        must_change=False,
    )

    now = int(time.time() * 1000)
    for index, (imei, plate, model) in enumerate(DEVICES):
        store.register_device(imei, "127.0.0.1")
        store.activate(imei, plate, model)
        store.set_device_tenant(imei, tenant)
        records = []
        odometer_base = 1_250_000 + index * 180_000
        for step in range(40):
            speed = [0, 18, 38, 52, 46, 22, 0, 30, 48, 15][step % 10]
            records.append(
                AvlRecord(
                    timestamp_ms=now - (40 - step) * 60000 - index * 5000,
                    priority=1,
                    longitude=14.08 + step * 0.001 + index * 0.01,
                    latitude=42.31 + step * 0.0008 + index * 0.01,
                    altitude=100,
                    angle=45,
                    satellites=9,
                    speed=float(speed),
                    event_id=239,
                    io={
                        1: 1,
                        239: 1 if speed else 0,
                        10: "A1",
                        84: 4200 - step * 3 - index * 200,   # litri CAN
                        89: 68 - step // 10,                  # percentuale CAN
                        115: 850 + (step % 4) * 5,            # temperatura CAN
                        87: odometer_base + step * 800,       # odometro CAN
                    },
                )
            )
        store.save_records(imei, records, 8)

    store.add_driver("Mario Rossi", "A1", tenant)
    store.add_driver("Giulia Bianchi", "A2", tenant)
    store.add_driver("Luca Verdi", "A3", tenant)
    for index, (imei, _, _) in enumerate(DEVICES):
        store.set_device_driver(imei, ["A1", "A2", "A3"][index])
    store.set_device_trailer("352093086403655", "TR-01", "Semirimorchio")
    store.set_device_trailer("352093086403656", "TR-02", "Cassone")
    for key in (str(tenant), ""):
        store.save_tenant_solution(key, "trasporti_pesanti", "4g", "osm")

    print(f"Demo pronta: cliente={TENANT}, mezzi={len(DEVICES)}")
    print(f"  demo / {PASSWORD} (admin)")
    print(f"  demo.manager / {MANAGER_PASSWORD} (manager)")


if __name__ == "__main__":
    main()
