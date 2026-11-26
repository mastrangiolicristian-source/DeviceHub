"""PDF del report mensile, generato sul server con ReportLab.

Il documento e' autonomo: contiene i numeri congelati, il dettaglio per mezzo,
il grafico giornaliero e i dati per la verifica della firma. Serve anche come
allegato dell'email, cosi' il cliente conserva il report dopo la scadenza del
link.
"""

from __future__ import annotations

import io
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .config import Settings

INK = colors.HexColor("#12202f")
MUTED = colors.HexColor("#5b6b7c")
LINE = colors.HexColor("#dde4ec")
ACCENT = colors.HexColor("#0e7490")
SOFT = colors.HexColor("#f4f7fa")

LEFT = 18 * mm


def _brand_color(value, fallback=ACCENT):
    if isinstance(value, str) and re.match(r"^#[0-9a-fA-F]{6}$", value):
        return colors.HexColor(value)
    return fallback


def _number(value, digits: int = 1) -> str:
    if value is None:
        return "-"
    text = f"{float(value):,.{digits}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def _fit(pdf: canvas.Canvas, text, font: str, size: float, width: float) -> str:
    text = str(text)
    if pdf.stringWidth(text, font, size) <= width:
        return text
    while text and pdf.stringWidth(text + "...", font, size) > width:
        text = text[:-1]
    return text + "..."


def _footer(
    pdf: canvas.Canvas, settings: Settings, page: int, name: str | None = None
) -> None:
    width, _ = A4
    pdf.setStrokeColor(LINE)
    pdf.setLineWidth(0.6)
    pdf.line(LEFT, 16 * mm, width - LEFT, 16 * mm)
    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(MUTED)
    pdf.drawString(LEFT, 11 * mm, name or settings.company)
    pdf.drawRightString(width - LEFT, 11 * mm, f"pagina {page}")


def _kpis(
    pdf: canvas.Canvas, totals: dict, right: float, y: float, primary=ACCENT
) -> float:
    boxes = [
        ("Km", _number(totals.get("km"))),
        ("Litri stimati", _number(totals.get("liters"))),
        ("CO2 kg", _number(totals.get("co2_kg"))),
        ("CO2 per km", _number(totals.get("grams_per_km"), 0) + " g"),
    ]
    gap = 3 * mm
    width = (right - LEFT - gap * 3) / 4
    height = 16 * mm
    for index, (label, value) in enumerate(boxes):
        x = LEFT + index * (width + gap)
        pdf.setFillColor(SOFT)
        pdf.setStrokeColor(LINE)
        pdf.roundRect(x, y - height, width, height, 2 * mm, stroke=1, fill=1)
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 7)
        pdf.drawString(x + 3 * mm, y - 5 * mm, label.upper())
        pdf.setFillColor(primary)
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(
            x + 3 * mm, y - 12 * mm, _fit(pdf, value, "Helvetica-Bold", 13, width - 6 * mm)
        )
    return y - height - 7 * mm


def _chart(
    pdf: canvas.Canvas, daily: list[dict], right: float, y: float, primary=ACCENT
) -> float:
    points = (daily or [])[-31:]
    if not points:
        return y
    values = [float(point.get("co2_kg") or 0) for point in points]
    peak = max(values) or 1.0
    width = right - LEFT
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(LEFT, y, "Emissioni per giorno (kg CO2)")
    base = y - 5 * mm - 22 * mm
    slot = width / len(points)
    bar_width = max(1.5, slot * 0.62)
    pdf.setFillColor(primary)
    for index, value in enumerate(values):
        bar_height = 22 * mm * (value / peak)
        x = LEFT + index * slot + (slot - bar_width) / 2
        pdf.rect(x, base, bar_width, bar_height, stroke=0, fill=1)
    pdf.setStrokeColor(LINE)
    pdf.setLineWidth(0.6)
    pdf.line(LEFT, base, right, base)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 6.5)
    pdf.drawString(LEFT, base - 4 * mm, str(points[0].get("date") or ""))
    pdf.drawRightString(right, base - 4 * mm, str(points[-1].get("date") or ""))
    return base - 9 * mm


def _paragraph(
    pdf: canvas.Canvas,
    text: str,
    right: float,
    y: float,
    size: float = 8,
    leading: float = 4 * mm,
) -> float:
    width = right - LEFT
    pdf.setFont("Helvetica", size)
    pdf.setFillColor(MUTED)
    line = ""
    for word in str(text).split():
        candidate = (line + " " + word).strip()
        if pdf.stringWidth(candidate, "Helvetica", size) <= width:
            line = candidate
        else:
            if line:
                pdf.drawString(LEFT, y, line)
                y -= leading
            line = word
    if line:
        pdf.drawString(LEFT, y, line)
        y -= leading
    return y


def render_report_pdf(
    settings: Settings,
    snapshot: dict,
    report: dict,
    branding: dict | None = None,
) -> bytes:
    """Costruisce il PDF del report congelato e ne restituisce i byte."""
    name = (branding or {}).get("display_name") or settings.company
    primary = _brand_color((branding or {}).get("primary_color"))
    logo = (branding or {}).get("logo")
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    period = str(snapshot.get("period") or "")
    pdf.setTitle(f"Report mensile {period} - {name}")
    pdf.setAuthor(name)
    pdf.setSubject(f"Report congelato {period}")

    width, height = A4
    right = width - LEFT
    content = right - LEFT
    page = 1
    y = height - 20 * mm

    def new_page() -> None:
        nonlocal page, y
        _footer(pdf, settings, page, name)
        pdf.showPage()
        page += 1
        y = height - 20 * mm

    # Intestazione
    text_left = LEFT
    if logo:
        try:
            reader = ImageReader(io.BytesIO(logo))
            image_width, image_height = reader.getSize()
            scale = min((36 * mm) / image_width, (13 * mm) / image_height)
            draw_width, draw_height = image_width * scale, image_height * scale
            pdf.drawImage(
                reader,
                LEFT,
                y - 2 * mm,
                width=draw_width,
                height=draw_height,
                mask="auto",
                preserveAspectRatio=True,
            )
            text_left = LEFT + draw_width + 5 * mm
        except Exception:
            text_left = LEFT
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(
        text_left, y, _fit(pdf, name, "Helvetica-Bold", 15, right - text_left - 28 * mm)
    )
    pdf.setFont("Helvetica-Bold", 13)
    pdf.setFillColor(primary)
    pdf.drawRightString(right, y, period)
    pdf.setFillColor(INK)
    y -= 6 * mm
    pdf.setFont("Helvetica", 9.5)
    pdf.setFillColor(MUTED)
    pdf.drawString(LEFT, y, "Report mensile congelato")
    y -= 5 * mm
    pdf.setStrokeColor(LINE)
    pdf.setLineWidth(0.8)
    pdf.line(LEFT, y, right, y)
    y -= 8 * mm

    pdf.setFont("Helvetica", 8.5)
    pdf.setFillColor(MUTED)
    meta = (
        f"Snapshot {snapshot.get('id')} - creato "
        f"{str(snapshot.get('created_at') or '').replace('T', ' ')}"
        f" da {snapshot.get('created_by') or 'sistema'}"
    )
    pdf.drawString(LEFT, y, _fit(pdf, meta, "Helvetica", 8.5, content))
    y -= 7 * mm

    y = _kpis(pdf, report.get("totals") or {}, right, y, primary)

    # Dettaglio per mezzo
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(LEFT, y, "Dettaglio per mezzo")
    y -= 6 * mm

    headers = [
        ("Mezzo", 0.26),
        ("IMEI", 0.26),
        ("Km", 0.11),
        ("Litri", 0.13),
        ("CO2 kg", 0.12),
        ("g/km", 0.12),
    ]

    def table_header() -> None:
        nonlocal y
        x = LEFT
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.setFillColor(MUTED)
        for label, fraction in headers:
            pdf.drawString(x, y, label)
            x += fraction * content
        y -= 2 * mm
        pdf.setStrokeColor(LINE)
        pdf.setLineWidth(0.6)
        pdf.line(LEFT, y, right, y)
        y -= 5 * mm

    table_header()
    devices = report.get("devices") or []
    for device in devices:
        if y < 32 * mm:
            new_page()
            pdf.setFillColor(INK)
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawString(LEFT, y, "Dettaglio per mezzo (continua)")
            y -= 6 * mm
            table_header()
        values = [
            device.get("plate") or device.get("imei") or "-",
            device.get("imei") or "-",
            _number(device.get("km")),
            _number(device.get("liters")),
            _number(device.get("co2_kg")),
            _number(device.get("grams_per_km"), 0),
        ]
        x = LEFT
        pdf.setFont("Helvetica", 8)
        pdf.setFillColor(INK)
        for value, (_, fraction) in zip(values, headers):
            pdf.drawString(
                x, y, _fit(pdf, value, "Helvetica", 8, fraction * content - 2 * mm)
            )
            x += fraction * content
        y -= 5 * mm
    if not devices:
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(LEFT, y, "Nessun chilometraggio nel periodo.")
        y -= 6 * mm
    y -= 3 * mm

    if y < 60 * mm:
        new_page()
    y = _chart(pdf, report.get("daily") or [], right, y, primary)

    # Integrita
    if y < 48 * mm:
        new_page()
    box_height = 26 * mm
    pdf.setFillColor(SOFT)
    pdf.setStrokeColor(LINE)
    pdf.roundRect(LEFT, y - box_height, content, box_height, 2 * mm, stroke=1, fill=1)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(LEFT + 3 * mm, y - 6 * mm, "Integrita del documento")
    pdf.setFont("Helvetica", 7.5)
    pdf.setFillColor(MUTED)
    pdf.drawString(
        LEFT + 3 * mm,
        y - 11 * mm,
        _fit(
            pdf,
            "Impronta SHA-256: " + (snapshot.get("digest") or "-"),
            "Helvetica",
            7.5,
            content - 8 * mm,
        ),
    )
    pdf.drawString(
        LEFT + 3 * mm,
        y - 15 * mm,
        "Chiave di firma: " + (snapshot.get("fingerprint") or "non firmato"),
    )
    pdf.drawString(
        LEFT + 3 * mm,
        y - 19 * mm,
        "La firma Ed25519 si verifica anche senza accesso, dalla pagina /verify.",
    )
    y -= box_height + 6 * mm

    assumptions = report.get("assumptions") or {}
    note = (
        "Distanza da odometro CAN (AVL 87). Consumo "
        f"{_number(assumptions.get('fuel_l_per_100km'))} L/100 km e fattore "
        f"{_number(assumptions.get('co2_kg_per_liter'), 2)} kg CO2/L, salvo "
        "parametri propri del mezzo. Indicatore dichiarato, non un report "
        "certificato da un ente."
    )
    y = _paragraph(pdf, note, right, y)

    _footer(pdf, settings, page, name)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
