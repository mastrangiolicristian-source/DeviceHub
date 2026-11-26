#!/usr/bin/env python3
"""Test di carico dell'ingestione Teltonika.

Apre N connessioni, ognuna come un tracker diverso, e invia un pacchetto
Codec 8E con `records` record ogni `interval` secondi, per `duration`
secondi. Misura il tempo tra invio e ACK e quanti record il server accetta.

Non scrive nel database del servizio: usa solo il protocollo TCP.

    python3 scripts/load_test.py --devices 200 --records 1 --interval 1 --duration 10
    python3 scripts/load_test.py --devices 50 --records 5 --interval 1 --duration 20 --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devicehub.teltonika import (  # noqa: E402
    CODEC_8E,
    AvlRecord,
    encode_avl_packet,
    encode_imei_handshake,
)

IMEI_BASE = 352099000000000


def make_record(timestamp_ms: int, odometer_m: int) -> AvlRecord:
    return AvlRecord(
        timestamp_ms=timestamp_ms,
        priority=1,
        longitude=14.0809,
        latitude=42.3169,
        altitude=110,
        angle=0,
        satellites=9,
        speed=30.0,
        event_id=239,
        io={1: 1, 239: 1, 87: odometer_m},
    )


async def run_device(
    host: str,
    port: int,
    imei: str,
    batch: int,
    interval: float,
    deadline: float,
    latencies: list[float],
    errors: list[str],
    accepted: list[int],
) -> None:
    writer = None
    try:
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(encode_imei_handshake(imei))
        await writer.drain()
        verdict = await reader.readexactly(1)
        if verdict != b"\x01":
            errors.append(f"{imei}: handshake rifiutato")
            return
        odometer = 1_000_000
        while time.monotonic() < deadline:
            started = time.perf_counter()
            now_ms = int(time.time() * 1000)
            records = [
                make_record(now_ms, odometer + index * 100)
                for index in range(batch)
            ]
            writer.write(encode_avl_packet(records, codec_id=CODEC_8E))
            await writer.drain()
            ack = await asyncio.wait_for(reader.readexactly(4), timeout=15)
            latencies.append((time.perf_counter() - started) * 1000)
            accepted[0] += struct.unpack(">I", ack)[0]
            odometer += batch * 100
            if interval:
                await asyncio.sleep(interval)
    except Exception as exc:  # rete, timeout, connessione chiusa
        errors.append(f"{imei}: {type(exc).__name__}: {exc}")
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


async def measure(args: argparse.Namespace) -> dict:
    latencies: list[float] = []
    errors: list[str] = []
    accepted = [0]
    started = time.monotonic()
    deadline = started + args.duration
    tasks = [
        run_device(
            args.host,
            args.port,
            str(IMEI_BASE + index),
            args.records,
            args.interval,
            deadline,
            latencies,
            errors,
            accepted,
        )
        for index in range(args.devices)
    ]
    await asyncio.gather(*tasks)
    elapsed = time.monotonic() - started
    packets = len(latencies)
    return {
        "devices": args.devices,
        "records_per_packet": args.records,
        "interval_seconds": args.interval,
        "duration_seconds": round(elapsed, 2),
        "packets": packets,
        "records_accepted": accepted[0],
        "records_per_second": round(accepted[0] / elapsed, 1) if elapsed else 0.0,
        "packets_per_second": round(packets / elapsed, 1) if elapsed else 0.0,
        "errors": errors[:20],
        "error_count": len(errors),
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(percentile(latencies, 0.95), 2),
            "p99": round(percentile(latencies, 0.99), 2),
            "max": round(max(latencies), 2) if latencies else 0.0,
            "mean": round(statistics.fmean(latencies), 2) if latencies else 0.0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Test di carico dell'ingestione")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5027)
    parser.add_argument("--devices", type=int, default=100)
    parser.add_argument("--records", type=int, default=1, help="record per pacchetto")
    parser.add_argument("--interval", type=float, default=1.0, help="secondi tra pacchetti")
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--json", action="store_true", help="solo JSON")
    args = parser.parse_args()

    result = asyncio.run(measure(args))
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["error_count"] == 0 else 1

    latency = result["latency_ms"]
    print(f"device: {result['devices']}, {result['records_per_packet']} record"
          f" ogni {result['interval_seconds']} s per {result['duration_seconds']} s")
    print(f"pacchetti inviati: {result['packets']}")
    print(f"record accettati: {result['records_accepted']}"
          f" ({result['records_per_second']} record/s,"
          f" {result['packets_per_second']} pacchetti/s)")
    print(f"latenza ACK: p50 {latency['p50']} ms, p95 {latency['p95']} ms,"
          f" p99 {latency['p99']} ms, max {latency['max']} ms")
    if result["error_count"]:
        print(f"errori: {result['error_count']}")
        for line in result["errors"]:
            print("  ", line)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
