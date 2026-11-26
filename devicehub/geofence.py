"""Geometrie e orari dei recinti.

Le coordinate delle geometrie sono sempre ``[latitudine, longitudine]``.
I calcoli sono planari: per cantieri e aree di pochi chilometri l'errore e'
trascurabile e non richiede dipendenze geografiche aggiuntive.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SHAPES = {"circle", "polygon", "line"}
DEFAULT_TIMEZONE = "Europe/Rome"
MAX_VERTICES = 200


def _point(value, label: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label} deve essere [latitudine, longitudine]")
    try:
        lat = float(value[0])
        lon = float(value[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} non valida") from exc
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError(f"{label} fuori intervallo")
    return lat, lon


def normalize_geometry(shape: str, raw) -> list[list[float]]:
    """Valida e normalizza i vertici di un poligono o di una linea."""
    if raw in (None, ""):
        return []
    if not isinstance(raw, (list, tuple)):
        raise ValueError("geometry deve essere una lista di punti")
    if len(raw) > MAX_VERTICES:
        raise ValueError(f"massimo {MAX_VERTICES} vertici")
    points = [_point(value, f"vertice {index + 1}") for index, value in enumerate(raw)]
    minimum = 3 if shape == "polygon" else 2 if shape == "line" else 0
    if len(points) < minimum:
        raise ValueError(
            "servono almeno 3 vertici per un poligono" if shape == "polygon"
            else "servono almeno 2 punti per una linea"
        )
    if len({(lat, lon) for lat, lon in points}) < minimum:
        raise ValueError("i vertici devono essere distinti")
    return [[lat, lon] for lat, lon in points]


def _clock(value, label: str, allow_24: bool = False) -> int:
    if not isinstance(value, str) or ":" not in value:
        raise ValueError(f"{label} non valido (HH:MM)")
    parts = value.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(f"{label} non valido (HH:MM)")
    hours, minutes = int(parts[0]), int(parts[1])
    if hours == 24 and minutes == 0 and allow_24:
        return 24 * 60
    if not 0 <= hours <= 23 or not 0 <= minutes <= 59:
        raise ValueError(f"{label} fuori intervallo")
    return hours * 60 + minutes


def normalize_schedule(raw) -> list[dict]:
    """Accetta una lista di finestre {days, start, end} e la valida.

    Una finestra con start > end attraversa la mezzanotte. start == end
    significa tutto il giorno; end puo' essere "24:00".
    """
    if raw in (None, ""):
        return []
    if not isinstance(raw, (list, tuple)):
        raise ValueError("schedule deve essere una lista di finestre")
    if len(raw) > 8:
        raise ValueError("massimo 8 finestre orarie")
    windows: list[dict] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"finestra {index + 1} non valida")
        days = item.get("days")
        if not isinstance(days, (list, tuple)) or not days:
            raise ValueError(f"finestra {index + 1}: giorni obbligatori")
        clean_days: list[int] = []
        for day in days:
            try:
                number = int(day)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"finestra {index + 1}: giorno non valido") from exc
            if not 0 <= number <= 6:
                raise ValueError("i giorni vanno da 0 (lunedi) a 6 (domenica)")
            if number not in clean_days:
                clean_days.append(number)
        start = _clock(item.get("start"), "ora di inizio")
        end = _clock(item.get("end"), "ora di fine", allow_24=True)
        if start == end:
            end = 24 * 60
        windows.append(
            {
                "days": sorted(clean_days),
                "start": f"{start // 60:02d}:{start % 60:02d}",
                "end": "24:00" if end == 24 * 60 else f"{end // 60:02d}:{end % 60:02d}",
            }
        )
    return windows


def normalize_timezone(value: str | None) -> str:
    name = (value or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("fuso orario non valido") from exc
    return name


def schedule_active(
    windows: list[dict], ts_ms: int, timezone_name: str = DEFAULT_TIMEZONE
) -> bool:
    """True se l'istante cade in una delle finestre; lista vuota = sempre."""
    if not windows:
        return True
    try:
        zone = ZoneInfo(timezone_name or DEFAULT_TIMEZONE)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    moment = datetime.fromtimestamp(int(ts_ms) / 1000, zone)
    minute = moment.hour * 60 + moment.minute
    weekday = moment.weekday()
    for window in windows:
        if weekday not in window.get("days", []):
            continue
        start = _clock(window.get("start"), "ora di inizio")
        end = _clock(window.get("end"), "ora di fine", allow_24=True)
        if start == end:
            return True
        if start < end:
            if start <= minute < end:
                return True
        elif minute >= start or minute < end:
            return True
    return False


def point_in_polygon(latitude: float, longitude: float, vertices: list) -> bool:
    """Ray casting su un poligono semplice."""
    if len(vertices) < 3:
        return False
    inside = False
    j = len(vertices) - 1
    for i, vertex in enumerate(vertices):
        lat_i, lon_i = float(vertex[0]), float(vertex[1])
        lat_j, lon_j = float(vertices[j][0]), float(vertices[j][1])
        crosses = (lon_i > longitude) != (lon_j > longitude)
        if crosses:
            intersection = (lat_j - lat_i) * (longitude - lon_i) / (lon_j - lon_i) + lat_i
            if latitude < intersection:
                inside = not inside
        j = i
    return inside


def _orientation(a, b, c) -> float:
    return (b[1] - a[1]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[1] - a[1])


def _on_segment(a, b, c) -> bool:
    return (
        min(a[1], b[1]) <= c[1] <= max(a[1], b[1])
        and min(a[0], b[0]) <= c[0] <= max(a[0], b[0])
    )


def segments_intersect(a, b, c, d) -> bool:
    """Intersezione tra segmenti (estremi inclusi), in coordinate lat/lon."""
    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return True
    if abs(o1) < 1e-12 and _on_segment(a, b, c):
        return True
    if abs(o2) < 1e-12 and _on_segment(a, b, d):
        return True
    if abs(o3) < 1e-12 and _on_segment(c, d, a):
        return True
    if abs(o4) < 1e-12 and _on_segment(c, d, b):
        return True
    return False


def line_crossed(previous, current, vertices: list) -> bool:
    """True se il tragitto precedente->attuale attraversa la polilinea."""
    if previous is None or len(vertices) < 2:
        return False
    a = (float(previous[0]), float(previous[1]))
    b = (float(current[0]), float(current[1]))
    for index in range(len(vertices) - 1):
        c = (float(vertices[index][0]), float(vertices[index][1]))
        d = (float(vertices[index + 1][0]), float(vertices[index + 1][1]))
        if segments_intersect(a, b, c, d):
            return True
    return False


def polygon_crossed(previous, current, vertices: list) -> bool:
    """True se il tragitto attraversa il bordo senza fermarsi dentro.

    Serve per il rilevamento di un attraversamento durante un salto tra due
    posizioni: se gli estremi sono fuori ma il segmento taglia il perimetro,
    l'evento non va perso.
    """
    if previous is None or len(vertices) < 3:
        return False
    if point_in_polygon(previous[0], previous[1], vertices):
        return False
    if point_in_polygon(current[0], current[1], vertices):
        return False
    return line_crossed(previous, current, vertices + [vertices[0]])
