"""Decodifica e codifica del protocollo Teltonika Codec 8 / Codec 8 Extended.

Implementato sulla base di https://wiki.teltonika-gps.com/view/Codec
(famiglia TM2500: FMB920/FMC130/FMB140/FMB640 e simili).

Il parser e' volutamente severo: ogni lettura e' controllata sui limiti del
buffer e il CRC viene verificato, cosi' un frame corrotto non entra nel
database come posizione valida.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone

CODEC_8 = 0x08
CODEC_8E = 0x8E

PREAMBLE = b"\x00\x00\x00\x00"
# Il wiki indica massimo 1280 byte di AVL data (255 per FMB640); teniamo un
# margine per non rifiutare firmware piu' verbosi.
MAX_DATA_FIELD = 2048

IMEI_ACCEPT = b"\x01"
IMEI_REJECT = b"\x00"


class ProtocolError(ValueError):
    """Frame non valido: preambolo, lunghezza o contenuto incoerenti."""


def crc16_ibm(payload: bytes) -> int:
    """CRC-16/IBM (riflesso, poly 0xA001, init 0x0000)."""
    crc = 0
    for byte in payload:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


@dataclass
class AvlRecord:
    timestamp_ms: int
    priority: int
    longitude: float
    latitude: float
    altitude: int
    angle: int
    satellites: int
    speed: float
    event_id: int
    io: dict[int, int] = field(default_factory=dict)

    @property
    def timestamp(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp_ms / 1000, tz=timezone.utc)

    def get(self, avl_id: int, default=None):
        return self.io.get(avl_id, default)


@dataclass
class AvlPacket:
    codec_id: int
    records: list[AvlRecord]
    crc_ok: bool
    crc_received: int
    crc_computed: int


class _Reader:
    """Lettore big-endian con controllo dei limiti."""

    __slots__ = ("buf", "pos")

    def __init__(self, buf: bytes, pos: int = 0) -> None:
        self.buf = buf
        self.pos = pos

    def take(self, size: int) -> bytes:
        end = self.pos + size
        if end > len(self.buf):
            raise ProtocolError(
                f"frame troncato: servono {size} byte a offset {self.pos}, "
                f"disponibili {len(self.buf) - self.pos}"
            )
        chunk = self.buf[self.pos:end]
        self.pos = end
        return chunk

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        return struct.unpack(">H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack(">I", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack(">Q", self.take(8))[0]

    def i16(self) -> int:
        return struct.unpack(">h", self.take(2))[0]

    def i32(self) -> int:
        return struct.unpack(">i", self.take(4))[0]

    @property
    def remaining(self) -> int:
        return len(self.buf) - self.pos


def parse_imei_handshake(data: bytes) -> tuple[str, int]:
    """Primo frame del device: 2 byte di lunghezza + IMEI in ASCII."""
    reader = _Reader(data)
    length = reader.u16()
    if length == 0 or length > 32:
        raise ProtocolError(f"lunghezza IMEI non plausibile: {length}")
    raw = reader.take(length)
    try:
        imei = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProtocolError("IMEI non ASCII") from exc
    if not imei.isdigit():
        raise ProtocolError(f"IMEI non numerico: {imei!r}")
    return imei, reader.pos


def _read_record(reader: _Reader, codec_id: int) -> AvlRecord:
    extended = codec_id == CODEC_8E
    ts_ms = reader.u64()
    priority = reader.u8()
    longitude = reader.i32() / 10_000_000
    latitude = reader.i32() / 10_000_000
    altitude = reader.i16()
    angle = reader.i16()
    satellites = reader.u8()
    speed = float(reader.u16())

    event_id = reader.u16() if extended else reader.u8()
    if extended:
        reader.u16()  # N of total IO: informativo, i conteggi reali seguono
    else:
        reader.u8()

    io: dict[int, int] = {}
    for value_size, id_size in ((1, 1), (2, 1), (4, 1), (8, 1)):
        count = reader.u16() if extended else reader.u8()
        for _ in range(count):
            avl_id = reader.u16() if extended else reader.u8()
            io[avl_id] = int.from_bytes(reader.take(value_size), "big")

    if extended:
        variable_count = reader.u16()
        for _ in range(variable_count):
            avl_id = reader.u16()
            length = reader.u16()
            io[avl_id] = int.from_bytes(reader.take(length), "big")

    return AvlRecord(
        timestamp_ms=ts_ms,
        priority=priority,
        longitude=longitude,
        latitude=latitude,
        altitude=altitude,
        angle=angle,
        satellites=satellites,
        speed=speed,
        event_id=event_id,
        io=io,
    )


def parse_avl_packet(data: bytes) -> tuple[AvlPacket, int]:
    """Decodifica un AVL packet completo.

    Ritorna (pacchetto, byte consumati) per poter alimentare il parser da uno
    stream TCP senza assumere che il buffer contenga un solo frame.
    """
    if len(data) < 12:
        raise ProtocolError("pacchetto piu' corto dell'header minimo")

    reader = _Reader(data)
    prefix = reader.take(4)
    if prefix != PREAMBLE:
        raise ProtocolError(f"preambolo inatteso: {prefix.hex()}")

    data_field_length = reader.u32()
    if data_field_length < 5 or data_field_length > MAX_DATA_FIELD:
        raise ProtocolError(f"data field length fuori range: {data_field_length}")

    data_field = reader.take(data_field_length)
    crc_received = reader.u32() & 0xFFFF
    crc_computed = crc16_ibm(data_field)

    codec_id = data_field[0]
    if codec_id not in (CODEC_8, CODEC_8E):
        raise ProtocolError(f"codec non supportato: 0x{codec_id:02X}")

    field_reader = _Reader(data_field, 1)
    declared = field_reader.u8()
    records = [_read_record(field_reader, codec_id) for _ in range(declared)]
    trailing = field_reader.u8() if field_reader.remaining else None
    if trailing != declared:
        raise ProtocolError(
            f"conteggio record incoerente: {declared} in testa, {trailing} in coda"
        )
    if field_reader.remaining:
        raise ProtocolError(f"{field_reader.remaining} byte non consumati nel data field")

    return (
        AvlPacket(
            codec_id=codec_id,
            records=records,
            crc_ok=crc_received == crc_computed,
            crc_received=crc_received,
            crc_computed=crc_computed,
        ),
        reader.pos,
    )


# --- Encoder: serve per i test e per il device simulatore -------------------


def _width(value: int) -> int:
    if value < 0:
        raise ValueError("i valori IO sono interpretati come interi senza segno")
    if value <= 0xFF:
        return 1
    if value <= 0xFFFF:
        return 2
    if value <= 0xFFFFFFFF:
        return 4
    return 8


def _encode_record(record: AvlRecord, codec_id: int) -> bytes:
    extended = codec_id == CODEC_8E
    out = bytearray()
    out += struct.pack(">Q", record.timestamp_ms)
    out.append(record.priority)
    out += struct.pack(">i", round(record.longitude * 10_000_000))
    out += struct.pack(">i", round(record.latitude * 10_000_000))
    out += struct.pack(">h", record.altitude)
    out += struct.pack(">h", record.angle)
    out.append(record.satellites)
    out += struct.pack(">H", int(record.speed))

    buckets: dict[int, list[tuple[int, int]]] = {1: [], 2: [], 4: [], 8: []}
    for avl_id, value in record.io.items():
        buckets[_width(value)].append((avl_id, value))
    total = sum(len(items) for items in buckets.values())

    if extended:
        out += struct.pack(">H", record.event_id)
        out += struct.pack(">H", total)
        for size in (1, 2, 4, 8):
            items = buckets[size]
            out += struct.pack(">H", len(items))
            for avl_id, value in items:
                out += struct.pack(">H", avl_id)
                out += value.to_bytes(size, "big")
        out += struct.pack(">H", 0)  # nX: nessun elemento a lunghezza variabile
    else:
        out.append(record.event_id)
        out.append(total)
        for size in (1, 2, 4, 8):
            items = buckets[size]
            out.append(len(items))
            for avl_id, value in items:
                out.append(avl_id)
                out += value.to_bytes(size, "big")
    return bytes(out)


def encode_avl_packet(records: list[AvlRecord], codec_id: int = CODEC_8) -> bytes:
    """Costruisce un AVL packet valido (CRC incluso)."""
    if codec_id not in (CODEC_8, CODEC_8E):
        raise ValueError(f"codec non supportato: 0x{codec_id:02X}")
    if not records:
        raise ValueError("servirebbe almeno un record")

    data_field = bytearray()
    data_field.append(codec_id)
    data_field.append(len(records))
    for record in records:
        data_field += _encode_record(record, codec_id)
    data_field.append(len(records))

    crc = crc16_ibm(bytes(data_field))
    return (
        PREAMBLE
        + struct.pack(">I", len(data_field))
        + bytes(data_field)
        + struct.pack(">I", crc)
    )


def encode_imei_handshake(imei: str) -> bytes:
    payload = imei.encode("ascii")
    return struct.pack(">H", len(payload)) + payload
