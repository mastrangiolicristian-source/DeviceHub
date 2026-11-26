"""Device simulatore: verifica la catena completa senza avere il GPS in mano.

Utile in fase di configurazione: permette di provare dashboard e ingestione
prima che i tracker arrivino.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import random
import struct
import time

from .codec12 import encode_response, parse_frame as parse_codec12_frame
from .teltonika import AvlRecord, CODEC_8E, encode_avl_packet, encode_imei_handshake

MANOPPELLO = (42.316909, 14.080997)


def make_record(
    latitude: float, longitude: float, speed: float, odometer_m: int, ignition: int = 1
) -> AvlRecord:
    return AvlRecord(
        timestamp_ms=int(time.time() * 1000),
        priority=1,
        longitude=longitude,
        latitude=latitude,
        altitude=250,
        angle=0,
        satellites=9,
        speed=speed,
        event_id=239,
        io={
            1: ignition,
            16: odometer_m,
            21: 4,
            66: 12_150,
            # Parametri CAN come li invia un FMC150 con programma veicolo attivo.
            84: 845,        # carburante, 84,5 L (x0,1)
            89: 68,         # livello carburante, 68 %
            87: 1_234_567 + odometer_m,  # km totali da CAN (profilo FMC150)
            102: 123_456,   # ore motore in minuti
            115: 890,       # temperatura motore, 89,0 C (x0,1)
            239: ignition,
        },
    )


async def _read_ack(reader, writer) -> int:
    """Legge l'ACK dei record; se arriva un comando Codec 12, risponde."""
    head = await reader.readexactly(4)
    if head == b"\x00\x00\x00\x00":
        length = struct.unpack(">I", await reader.readexactly(4))[0]
        body = await reader.readexactly(length + 4)
        message, _ = parse_codec12_frame(
            b"\x00\x00\x00\x00" + struct.pack(">I", length) + body
        )
        print(f"[demo] comando ricevuto: {message.text!r}")
        writer.write(encode_response(f"OK:{message.text}"))
        await writer.drain()
        return await _read_ack(reader, writer)
    return struct.unpack(">I", head)[0]


async def simulate(
    host: str,
    port: int,
    imei: str,
    interval: float = 5.0,
    packets: int = 0,
    speed: float = 45.0,
) -> None:
    reader, writer = await asyncio.open_connection(host, port)
    writer.write(encode_imei_handshake(imei))
    await writer.drain()
    verdict = await reader.readexactly(1)
    if verdict != b"\x01":
        raise SystemExit("device rifiutato dal server (IMEI non abilitato)")
    print(f"[demo] connesso come {imei}, invio ogni {interval}s")

    lat, lon = MANOPPELLO
    odometer = 0
    sent = 0
    heading = random.uniform(0, 2 * math.pi)

    while packets == 0 or sent < packets:
        heading += random.uniform(-0.4, 0.4)
        step_m = speed / 3.6 * interval
        lat += (step_m * math.cos(heading)) / 111_320
        lon += (step_m * math.sin(heading)) / (111_320 * math.cos(math.radians(lat)))
        odometer += int(step_m)

        payload = encode_avl_packet(
            [make_record(lat, lon, speed, odometer)], codec_id=CODEC_8E
        )
        writer.write(payload)
        await writer.drain()
        accepted = await _read_ack(reader, writer)
        sent += 1
        print(f"[demo] #{sent} inviato, accettati {accepted} record ({lat:.5f}, {lon:.5f})")
        await asyncio.sleep(interval)

    writer.close()
    await writer.wait_closed()


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulatore device Teltonika")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5027)
    parser.add_argument("--imei", default="352093086403655")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--packets", type=int, default=5, help="0 = infinito")
    parser.add_argument("--speed", type=float, default=45.0)
    args = parser.parse_args()
    asyncio.run(
        simulate(args.host, args.port, args.imei, args.interval, args.packets, args.speed)
    )


if __name__ == "__main__":
    main()
