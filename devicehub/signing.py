"""Firma Ed25519 degli snapshot ESG.

La chiave privata resta sul server, in un file con permessi 600 (percorso in
`DEVICEHUB_SIGNING_KEY`, altrimenti accanto al database). La chiave pubblica
si esporta per la verifica indipendente: chi la conserva puo' controllare uno
snapshot anche se il database viene riscritto, perche' non contiene la
chiave privata necessaria a rifare la firma.
"""

from __future__ import annotations

import base64
import hashlib
import os
import stat
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def load_or_create_private_key(path: str) -> Ed25519PrivateKey:
    """Carica la chiave privata, creandola al primo avvio."""
    file = Path(path)
    if file.exists():
        key = serialization.load_pem_private_key(file.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError(f"{path} non e' una chiave Ed25519")
        return key
    key = Ed25519PrivateKey.generate()
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    os.chmod(file, stat.S_IRUSR | stat.S_IWUSR)
    return key


def public_pem(key: Ed25519PrivateKey) -> str:
    return (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )


def fingerprint(public_key_pem: str) -> str:
    """Impronta corta della chiave pubblica, da comunicare al cliente."""
    der = (
        serialization.load_pem_public_key(public_key_pem.encode())
        .public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return hashlib.sha256(der).hexdigest()[:32]


def sign(key: Ed25519PrivateKey, payload: str) -> str:
    return base64.b64encode(key.sign(payload.encode())).decode()


def verify(public_key_pem: str, payload: str, signature_b64: str) -> bool:
    try:
        public: Ed25519PublicKey = serialization.load_pem_public_key(
            public_key_pem.encode()
        )
        public.verify(base64.b64decode(signature_b64), payload.encode())
    except Exception:
        return False
    return True
