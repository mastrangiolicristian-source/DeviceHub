"""Branding del report per cliente: nome, colore e logo.

I valori stanno in `tenant_branding`, una riga per cliente. Il tenant vuoto e'
il branding globale (amministratore senza cliente).
"""

from __future__ import annotations

import hashlib
import re

DEFAULT_COLOR = "#0e7490"
MAX_LOGO_BYTES = 512 * 1024
MAX_BG_BYTES = 1536 * 1024
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
LOGO_MAGIC = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8",
}
BG_MAGIC = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8",
}
# Estensione usata nell'URL pubblico dell'immagine caricata.
BG_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def content_digest(data: bytes | None, url: str | None) -> str:
    """Impronta del contenuto dello sfondo.

    Dipende solo dall'immagine o dall'URL: cambiare modalita' non la tocca,
    quindi la firma dell'URL resta valida e la cache del browser non cade.
    """
    if data:
        return hashlib.sha256(data).hexdigest()
    if url:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()
    return ""


def normalize_color(value: str | None) -> str | None:
    if value and COLOR_RE.match(value.strip()):
        return value.strip().lower()
    return None


def check_background(data: bytes, mime: str) -> str | None:
    """Restituisce un messaggio di errore, oppure None se lo sfondo va bene."""
    if not data:
        return "immagine vuota"
    if len(data) > MAX_BG_BYTES:
        return "immagine troppo grande: massimo 1,5 MB"
    if mime == "image/webp":
        if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
            return "il contenuto del file non corrisponde al formato dichiarato"
        return None
    magic = BG_MAGIC.get(mime)
    if magic is None:
        return "formato non supportato: usare PNG, JPEG o WebP"
    if not data.startswith(magic):
        return "il contenuto del file non corrisponde al formato dichiarato"
    return None


def check_logo(data: bytes, mime: str) -> str | None:
    """Restituisce un messaggio di errore, oppure None se il logo va bene."""
    if not data:
        return "logo vuoto"
    if len(data) > MAX_LOGO_BYTES:
        return "logo troppo grande: massimo 512 KB"
    magic = LOGO_MAGIC.get(mime)
    if magic is None:
        return "formato non supportato: usare PNG o JPEG"
    if not data.startswith(magic):
        return "il contenuto del file non corrisponde al formato dichiarato"
    return None
