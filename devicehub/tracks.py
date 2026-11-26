"""Storico percorsi: semplificazione, statistiche e soste prolungate.

Le posizioni arrivano dal database gia' ordinate per timestamp. Il payload
destinato alla mappa viene alleggerito con Ramer-Douglas-Peucker in metri,
cosi' i segmenti rettilinei non consumano punti e il playback resta fluido.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

EARTH_RADIUS_M = 6_371_008.8
DEFAULT_EPSILON_M = 8.0
DEFAULT_STOP_SECONDS = 300
DEFAULT_STOP_MAX_GAP_SECONDS = 900
MAX_PLAUSIBLE_KMH = 220.0


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _project(points: list[dict], latitude: float) -> list[tuple[float, float]]:
    """Proiezione locale equirettangolare, sufficiente per pochi km."""
    scale = math.cos(math.radians(latitude)) * 111_320.0
    return [(_number(p.get("longitude")) * scale, _number(p.get("latitude")) * 110_540.0)
            for p in points]


def _distance_to_segment(point: tuple[float, float], start: tuple[float, float],
                         end: tuple[float, float]) -> float:
    px, py = point
    ax, ay = start
    bx, by = end
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(rows: list[dict], epsilon_m: float = DEFAULT_EPSILON_M) -> list[dict]:
    """Ramer-Douglas-Peucker iterativo; mantiene primo e ultimo punto."""
    if len(rows) < 3 or epsilon_m <= 0:
        return list(rows)
    lat = sum(_number(p.get("latitude")) for p in rows) / len(rows)
    projected = _project(rows, lat)
    keep = [False] * len(rows)
    keep[0] = keep[-1] = True
    stack = [(0, len(rows) - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        farthest = -1.0
        index = -1
        for i in range(start + 1, end):
            distance = _distance_to_segment(projected[i], projected[start], projected[end])
            if distance > farthest:
                farthest, index = distance, i
        if index >= 0 and farthest > epsilon_m:
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))
    return [row for row, selected in zip(rows, keep) if selected]


def detect_stops(rows: list[dict], min_seconds: int = DEFAULT_STOP_SECONDS,
                 speed_threshold: float = 1.0,
                 max_gap_seconds: int = DEFAULT_STOP_MAX_GAP_SECONDS) -> list[dict]:
    """Soste prolungate: gruppi consecutivi con velocita' sotto soglia."""
    stops: list[dict] = []
    run: list[dict] = []

    def close_run() -> None:
        if len(run) < 2:
            return
        start_ms = int(_number(run[0].get("ts_ms")))
        end_ms = int(_number(run[-1].get("ts_ms")))
        duration = max(0, round((end_ms - start_ms) / 1000))
        if duration < min_seconds:
            return
        lat = sum(_number(p.get("latitude")) for p in run) / len(run)
        lon = sum(_number(p.get("longitude")) for p in run) / len(run)
        stops.append({
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "started_ms": start_ms,
            "ended_ms": end_ms,
            "duration_s": duration,
        })

    previous_ts: int | None = None
    max_gap_ms = max_gap_seconds * 1000
    for row in rows:
        timestamp = int(_number(row.get("ts_ms")))
        if run and previous_ts is not None and timestamp - previous_ts > max_gap_ms:
            close_run()
            run = []
        if _number(row.get("speed")) <= speed_threshold:
            run.append(row)
        else:
            close_run()
            run = []
        previous_ts = timestamp
    close_run()
    return stops


def build_history(rows: list[dict], epsilon_m: float = DEFAULT_EPSILON_M,
                  min_stop_seconds: int = DEFAULT_STOP_SECONDS) -> dict:
    """Payload per il player: punti semplificati, statistiche e soste."""
    rows = sorted(rows, key=lambda row: int(_number(row.get("ts_ms"))))
    if not rows:
        return {
            "count": 0, "raw_count": 0, "positions": [], "stops": [],
            "total_km": 0.0, "duration_s": 0, "max_speed_kmh": 0.0,
        }

    distance_m = 0.0
    previous = rows[0]
    for row in rows[1:]:
        segment = haversine_m(
            _number(previous.get("latitude")), _number(previous.get("longitude")),
            _number(row.get("latitude")), _number(row.get("longitude")),
        )
        elapsed_s = (int(_number(row.get("ts_ms"))) - int(_number(previous.get("ts_ms")))) / 1000
        # Salta i salti impossibili (teleport tra sessioni o fix GPS errati).
        if elapsed_s > 0 and segment / elapsed_s * 3.6 <= MAX_PLAUSIBLE_KMH:
            distance_m += segment
        previous = row
    duration_s = max(0, round((int(_number(rows[-1].get("ts_ms"))) -
                               int(_number(rows[0].get("ts_ms")))) / 1000))
    max_speed = max(_number(row.get("speed")) for row in rows)
    simplified = simplify(rows, epsilon_m)
    return {
        "count": len(simplified),
        "raw_count": len(rows),
        "positions": simplified,
        "stops": detect_stops(rows, min_stop_seconds),
        "total_km": round(distance_m / 1000, 2),
        "duration_s": duration_s,
        "max_speed_kmh": round(max_speed, 1),
    }


def day_bounds(day: str, tz_offset_minutes: int = 0) -> tuple[int, int]:
    """Mezzanotte locale convertita in UTC; offset JavaScript getTimezoneOffset."""
    try:
        parsed = datetime.combine(date.fromisoformat(day), datetime.min.time(), tzinfo=timezone.utc)
    except ValueError as error:
        raise ValueError("Data non valida: attesa YYYY-MM-DD") from error
    start = parsed + timedelta(minutes=tz_offset_minutes)
    end = start + timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)
