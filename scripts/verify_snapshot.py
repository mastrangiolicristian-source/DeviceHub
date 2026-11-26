#!/usr/bin/env python3
"""Verifica offline di uno snapshot ESG esportato da DeviceHub.

Non contatta il server e non apre il database: controlla il documento con la
sola chiave pubblica, quindi funziona anche su una macchina diversa.
Richiede soltanto `cryptography`.

    python3 scripts/verify_snapshot.py snapshot-2026-10.json
    python3 scripts/verify_snapshot.py snapshot-2026-10.json --public-key chiave.pem

Senza `--public-key` la firma viene controllata con la chiave contenuta nel
documento: prova che il file non e' stato alterato, non che provenga da noi.
Con `--public-key` si verifica anche che a firmarlo sia stata la chiave attesa.
Esito 0 = verificato, 1 = non verificato, 2 = documento illeggibile.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization

FORMAT = "devicehub-esg-snapshot/1"


def fingerprint(public_key_pem: str) -> str:
    public = serialization.load_pem_public_key(public_key_pem.encode())
    der = public.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()[:32]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verifica impronta e firma di uno snapshot ESG esportato."
    )
    parser.add_argument("document", type=Path, help="file esportato (JSON)")
    parser.add_argument(
        "--public-key",
        type=Path,
        help="chiave pubblica attesa in PEM (consigliata, presa fuori dal server)",
    )
    args = parser.parse_args()

    try:
        document = json.loads(args.document.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Documento illeggibile: {exc}")
        return 2
    if document.get("format") != FORMAT:
        print(f"Formato non riconosciuto: {document.get('format')!r}")
        return 2

    snapshot = document.get("snapshot") or {}
    payload = document.get("payload")
    if not isinstance(payload, str) or not snapshot.get("digest"):
        print("Documento incompleto: mancano payload o impronta.")
        return 2

    digest_ok = hashlib.sha256(payload.encode()).hexdigest() == snapshot["digest"]
    signature = snapshot.get("signature") or ""
    expected_fp = snapshot.get("fingerprint") or ""
    public_pem = snapshot.get("public_key") or ""
    if args.public_key:
        try:
            public_pem = args.public_key.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Chiave pubblica illeggibile: {exc}")
            return 2

    key_fp = ""
    key_ok = False
    if public_pem:
        try:
            key_fp = fingerprint(public_pem)
            key_ok = key_fp == expected_fp
        except ValueError:
            print("La chiave pubblica non e' un PEM valido.")
            return 2

    signature_ok = False
    if public_pem and signature:
        try:
            serialization.load_pem_public_key(public_pem.encode()).verify(
                base64.b64decode(signature), payload.encode()
            )
            signature_ok = True
        except Exception:
            signature_ok = False

    print(
        f"Snapshot {snapshot.get('period')} (id {snapshot.get('id')}), "
        f"creato {snapshot.get('created_at')} da "
        f"{snapshot.get('created_by') or 'sconosciuto'}"
    )
    print("Impronta SHA-256:", "integra" if digest_ok else "ALTERATA")
    if not signature:
        print("Firma Ed25519: assente")
    else:
        print("Firma Ed25519:", "valida" if signature_ok else "NON valida")
    if public_pem:
        print(
            "Chiave:",
            key_fp or "illeggibile",
            f"(attesa {expected_fp or 'non indicata'})",
            "ok" if key_ok else "DIVERSA",
        )
    verified = digest_ok and signature_ok and key_ok
    print("Esito:", "VERIFICATO" if verified else "NON VERIFICATO")
    return 0 if verified else 1


if __name__ == "__main__":
    sys.exit(main())
