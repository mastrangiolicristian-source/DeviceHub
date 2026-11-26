"""Esportazione di un tracciato giornaliero in GPX 1.1 e KML 2.2."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

GPX_NS = "http://www.topografix.com/GPX/1/1"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
KML_NS = "http://www.opengis.net/kml/2.2"
GX_NS = "http://www.google.com/kml/ext/2.2"


def _iso(ts_ms: int) -> str:
    return (
        datetime.fromtimestamp(int(ts_ms) / 1000, timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _points(rows: list[dict]) -> list[dict]:
    return [
        row
        for row in rows
        if row.get("latitude") is not None and row.get("longitude") is not None
    ]


def _tag(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def gpx_bytes(imei: str, date: str, rows: list[dict]) -> bytes:
    points = _points(rows)
    ET.register_namespace("", GPX_NS)
    ET.register_namespace("xsi", XSI_NS)
    root = ET.Element(
        _tag(GPX_NS, "gpx"),
        {
            "version": "1.1",
            "creator": "DeviceHub",
            _tag(XSI_NS, "schemaLocation"): (
                f"{GPX_NS} {GPX_NS}/gpx.xsd"
            ),
        },
    )
    metadata = ET.SubElement(root, _tag(GPX_NS, "metadata"))
    ET.SubElement(metadata, _tag(GPX_NS, "name")).text = f"{imei} - {date}"
    ET.SubElement(metadata, _tag(GPX_NS, "time")).text = (
        _iso(points[0]["ts_ms"]) if points else _iso(0)
    )
    track = ET.SubElement(root, _tag(GPX_NS, "trk"))
    ET.SubElement(track, _tag(GPX_NS, "name")).text = f"Percorso {date}"
    ET.SubElement(track, _tag(GPX_NS, "desc")).text = f"DeviceHub - IMEI {imei}"
    segment = ET.SubElement(track, _tag(GPX_NS, "trkseg"))
    for point in points:
        node = ET.SubElement(
            segment,
            _tag(GPX_NS, "trkpt"),
            {
                "lat": f"{float(point['latitude']):.7f}",
                "lon": f"{float(point['longitude']):.7f}",
            },
        )
        ET.SubElement(node, _tag(GPX_NS, "time")).text = _iso(point["ts_ms"])
        if point.get("speed") is not None:
            # GPX esprime la velocita' in metri al secondo.
            ET.SubElement(node, _tag(GPX_NS, "speed")).text = (
                f"{float(point['speed']) / 3.6:.3f}"
            )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def kml_bytes(imei: str, date: str, rows: list[dict]) -> bytes:
    points = _points(rows)
    ET.register_namespace("", KML_NS)
    ET.register_namespace("gx", GX_NS)
    root = ET.Element(_tag(KML_NS, "kml"))
    document = ET.SubElement(root, _tag(KML_NS, "Document"))
    ET.SubElement(document, _tag(KML_NS, "name")).text = (
        f"DeviceHub - {imei} - {date}"
    )
    placemark = ET.SubElement(document, _tag(KML_NS, "Placemark"))
    ET.SubElement(placemark, _tag(KML_NS, "name")).text = f"Percorso {date}"
    track = ET.SubElement(placemark, _tag(GX_NS, "Track"))
    ET.SubElement(track, _tag(KML_NS, "altitudeMode")).text = "absolute"
    for point in points:
        ET.SubElement(track, _tag(KML_NS, "when")).text = _iso(point["ts_ms"])
    for point in points:
        ET.SubElement(track, _tag(GX_NS, "coord")).text = (
            f"{float(point['longitude']):.7f} "
            f"{float(point['latitude']):.7f} 0"
        )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
