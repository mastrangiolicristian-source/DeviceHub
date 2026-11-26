"""Stile di guida: eventi bruschi e punteggio per autista.

Il calcolo usa le posizioni gia' registrate: nessun dato inventato. La soglia
e' in km/h al secondo, quindi non dipende dall'intervallo del tracker.
"""

from __future__ import annotations

ACCEL = "HARSH_ACCEL"
BRAKE = "HARSH_BRAKE"


def detect(
    previous_speed: float,
    previous_ts_ms: int,
    speed: float,
    ts_ms: int,
    accel_threshold: float = 8.0,
    brake_threshold: float = 10.0,
) -> str | None:
    """Ritorna l'evento se la variazione supera la soglia, altrimenti None."""
    seconds = (ts_ms - previous_ts_ms) / 1000.0
    if seconds <= 0 or seconds > 15:
        return None
    delta = speed - previous_speed
    rate = delta / seconds
    if delta >= 15 and rate >= accel_threshold:
        return ACCEL
    if delta <= -15 and rate <= -brake_threshold:
        return BRAKE
    return None


def analyse(
    records: list[dict],
    driver_io_id: int = 0,
    driver_names: dict[str, str] | None = None,
    accel_threshold: float = 8.0,
    brake_threshold: float = 10.0,
) -> dict:
    """Eventi e punteggio (0-100) per autista a partire dalle posizioni."""
    names = driver_names or {}
    events: list[dict] = []
    previous: dict[str, tuple[float, int]] = {}
    for record in records:
        imei = str(record["imei"])
        speed = float(record.get("speed") or 0)
        ts_ms = int(record["ts_ms"])
        badge = ""
        if driver_io_id:
            try:
                raw = record.get("io") or {}
                # Dopo il passaggio in JSON le chiavi numeriche diventano stringhe.
                badge = str(
                    raw.get(driver_io_id) or raw.get(str(driver_io_id)) or ""
                )
            except AttributeError:
                badge = ""
        before = previous.get(imei)
        if before is not None:
            kind = detect(
                before[0], before[1], speed, ts_ms, accel_threshold, brake_threshold
            )
            if kind:
                events.append(
                    {
                        "imei": imei,
                        "plate": record.get("plate") or "",
                        "badge": badge,
                        "driver": names.get(badge, badge),
                        "kind": kind,
                        "speed_before": round(before[0], 1),
                        "speed_after": round(speed, 1),
                        "ts_ms": ts_ms,
                    }
                )
        previous[imei] = (speed, ts_ms)

    events.sort(key=lambda item: item["ts_ms"], reverse=True)
    accel = sum(1 for event in events if event["kind"] == ACCEL)
    brake = sum(1 for event in events if event["kind"] == BRAKE)

    drivers: dict[str, dict] = {}
    for event in events:
        key = event["badge"] or "unknown"
        entry = drivers.setdefault(
            key,
            {
                "badge": event["badge"],
                "name": event["driver"] or "Non identificato",
                "accel": 0,
                "brake": 0,
            },
        )
        entry["accel" if event["kind"] == ACCEL else "brake"] += 1
    for entry in drivers.values():
        penalty = entry["accel"] * 3 + entry["brake"] * 5
        entry["events"] = entry["accel"] + entry["brake"]
        entry["score"] = max(0, min(100, 100 - penalty))
    return {
        "count": len(events),
        "accel": accel,
        "brake": brake,
        "events": events,
        "drivers": sorted(
            drivers.values(), key=lambda item: item["events"], reverse=True
        ),
    }
