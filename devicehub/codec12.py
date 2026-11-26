"""Codec 12: comandi e risposte fra server e device (canale GPRS/TCP).

Struttura del frame (wiki Teltonika, "Codec for communication over GPRS
messages"):

    preambolo 4B | data size 4B | 0x0C | qty1 1B | tipo 1B | size 4B |
    testo XB | qty2 1B | CRC-16 4B

`data size` va calcolato dal Codec ID fino a qty2, quindi esclude il CRC.
Tipo 0x05 = comando dal server, 0x06 = risposta del device.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass

from .teltonika import PREAMBLE, ProtocolError, crc16_ibm

CODEC_12 = 0x0C
TYPE_COMMAND = 0x05
TYPE_RESPONSE = 0x06

MAX_FRAME = 4096
MAX_TEXT = 1024

#: I relè si comandano solo con il mezzo fermo. Il limite è in km/h e tollera
#: il rumore del GPS alla sosta.
MAX_BLOCK_SPEED_KMH = 1.0


@dataclass
class Codec12Message:
    type: int
    text: str
    quantity: int
    crc_ok: bool
    crc_received: int
    crc_computed: int

    @property
    def is_response(self) -> bool:
        return self.type == TYPE_RESPONSE


def _frame(text: str, message_type: int) -> bytes:
    payload = text.encode("ascii")
    if not payload:
        raise ValueError("comando vuoto")
    if len(payload) > MAX_TEXT:
        raise ValueError(f"comando troppo lungo: {len(payload)} byte")

    field = (
        bytes([CODEC_12, 0x01, message_type])
        + struct.pack(">I", len(payload))
        + payload
        + b"\x01"
    )
    return (
        PREAMBLE
        + struct.pack(">I", len(field))
        + field
        + struct.pack(">I", crc16_ibm(field))
    )


def encode_command(text: str) -> bytes:
    return _frame(text, TYPE_COMMAND)


def encode_response(text: str) -> bytes:
    return _frame(text, TYPE_RESPONSE)


def parse_frame(data: bytes) -> tuple[Codec12Message, int]:
    if len(data) < 13:
        raise ProtocolError("frame codec 12 troppo corto")
    if data[:4] != PREAMBLE:
        raise ProtocolError(f"preambolo inatteso: {data[:4].hex()}")

    length = struct.unpack_from(">I", data, 4)[0]
    if not 8 <= length <= MAX_FRAME:
        raise ProtocolError(f"data size codec 12 fuori range: {length}")
    total = 8 + length + 4
    if len(data) < total:
        raise ProtocolError("frame codec 12 troncato")

    field = data[8 : 8 + length]
    crc_received = struct.unpack_from(">I", data, 8 + length)[0] & 0xFFFF
    crc_computed = crc16_ibm(field)

    if field[0] != CODEC_12:
        raise ProtocolError(f"codec atteso 0x0C, trovato 0x{field[0]:02X}")

    payload_size = struct.unpack_from(">I", field, 3)[0]
    if 7 + payload_size + 1 != len(field):
        raise ProtocolError(
            f"dimensione payload incoerente: {payload_size} per {len(field)} byte di campo"
        )

    payload = field[7 : 7 + payload_size]
    return (
        Codec12Message(
            type=field[2],
            text=payload.decode("ascii", errors="replace"),
            quantity=field[7 + payload_size],
            crc_ok=crc_received == crc_computed,
            crc_received=crc_received,
            crc_computed=crc_computed,
        ),
        total,
    )


def relay_command(dout_count: int = 3, on: bool = True, ignition_off: bool = False) -> str:
    """Comando per i due relè del blocco motore.

    Con 3 uscite il terzo stato resta `?` (ignorato): la sirena non deve essere
    toccata dal comando di blocco. Con il quadro spento serve `setigndigout`,
    altrimenti il device ignora `setdigout`.
    """
    if dout_count < 2:
        raise ValueError("servono almeno 2 uscite digitali per il doppio relè")

    states = ("1" if on else "0") * 2 + "?" * (dout_count - 2)
    verb = "setigndigout" if ignition_off else "setdigout"
    return f"{verb} {states}"


def block_allowed(
    last_position: dict | None, max_age_seconds: float = 120.0
) -> tuple[bool, str]:
    """Guardia di sicurezza: si blocca solo un mezzo fermo, noto e con fix recente.

    Senza un fix GPS fresco la velocita' e' quella dell'ultimo contatto e non
    dice nulla sull'istante del comando: il blocco viene rifiutato.
    """
    if not last_position:
        return False, "nessuna posizione ricevuta: stato del veicolo sconosciuto"

    ts_ms = last_position.get("ts_ms")
    if ts_ms:
        age_seconds = (time.time() * 1000 - float(ts_ms)) / 1000.0
        if age_seconds > max_age_seconds:
            return False, (
                f"ultimo fix GPS vecchio di {age_seconds:.0f}s"
                f" (limite {max_age_seconds:.0f}s): blocco rifiutato"
            )

    speed = float(last_position.get("speed") or 0)
    if speed > MAX_BLOCK_SPEED_KMH:
        return False, f"veicolo in movimento ({speed:.0f} km/h): blocco rifiutato"

    return True, ""
