"""Verifica e installazione dei rilasci della piattaforma.

Il canale di aggiornamento e' un manifest JSON raggiungibile dall'installazione
(HTTP/HTTPS o `file://` per le demo offline):

    {
      "version": "1.4.1",
      "notes": "Correzioni e nuove funzioni",
      "url": "https://esempio.it/dist/devicehub-src-1.4.1.zip",
      "sha256": "…64 caratteri esadecimali…",
      "published_at": "2026-11-20"
    }

Il pacchetto deve contenere la cartella `devicehub/`. L'installazione copia i
file nella directory dell'applicazione senza toccare dati e configurazione:
`.env`, database SQLite, `.git`, `updates/`, `artifacts/` e `dist/` restano
quelli dell'installazione. Il riavvio del servizio e' a carico del chiamante.

Prima di copiare qualunque file viene salvata una copia di quelli che stanno per
essere sostituiti in `updates/backups/`. Se la copia fallisce a meta' strada i
file vengono rimessi a posto automaticamente e i file nuovi rimossi, cosi' una
release difettosa non lascia la piattaforma in uno stato misto. Il codice del
pacchetto viene inoltre compilato in memoria prima della copia: un file Python
non valido viene rifiutato senza toccare l'installazione.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from .config import Settings
from .version import __version__

MAX_MANIFEST_BYTES = 1_000_000
MAX_PACKAGE_BYTES = 100 * 1024 * 1024
CHECKSUM_RE = re.compile(r"^[0-9a-f]{64}$")
BACKUP_KEEP = 5

# Cartelle e file dell'installazione che non arrivano mai dal pacchetto.
SKIP_TOP = {
    ".env",
    ".git",
    ".venv",
    "venv",
    "updates",
    "artifacts",
    "dist",
    "node_modules",
}
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache"}
SKIP_SUFFIXES = (".pyc", ".db", ".db-wal", ".db-shm")


class UpdateError(RuntimeError):
    """Errore leggibile di verifica o installazione."""


def parse_version(text: str) -> tuple[int, ...]:
    raw = str(text).strip().lower()
    if raw.startswith("v"):
        raw = raw[1:]
    match = re.match(r"^(\d+(?:\.\d+)*)", raw)
    if not match:
        raise UpdateError(f"versione non valida: {text}")
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(latest: str, current: str = __version__) -> bool:
    left = parse_version(latest)
    right = parse_version(current)
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) > right + (0,) * (width - len(right))


def install_dir(settings: Settings) -> Path:
    if settings.update_dir:
        return Path(settings.update_dir).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def status(settings: Settings) -> dict:
    """Configurazione corrente, senza contattare il canale di rilascio."""
    return {
        "current": __version__,
        "configured": bool(settings.update_url),
        "source": settings.update_url,
        "install_dir": str(install_dir(settings)),
    }


def _read_url(url: str, timeout: float = 10.0) -> bytes:
    if url.startswith("file://"):
        path = Path(urllib.request.url2pathname(url[len("file://"):]))
        try:
            data = path.read_bytes()
        except OSError as error:
            raise UpdateError(f"manifest non leggibile: {error}") from error
    elif url.startswith(("http://", "https://")):
        request = urllib.request.Request(
            url, headers={"User-Agent": f"devicehub/{__version__}"}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read(MAX_MANIFEST_BYTES + 1)
        except (urllib.error.URLError, OSError) as error:
            raise UpdateError(f"verifica non riuscita: {error}") from error
    else:
        raise UpdateError("DEVICEHUB_UPDATE_URL deve essere http(s) o file://")
    if len(data) > MAX_MANIFEST_BYTES:
        raise UpdateError("manifest troppo grande")
    return data


def check(settings: Settings, timeout: float = 10.0) -> dict:
    """Legge il manifest e dice se esiste una versione piu' recente."""
    result = {
        **status(settings),
        "available": False,
        "latest": "",
        "notes": "",
        "published_at": "",
        "package_url": "",
        "sha256": "",
    }
    if not settings.update_url:
        return result
    try:
        manifest = json.loads(_read_url(settings.update_url, timeout).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UpdateError("manifest non valido: non e' JSON") from error
    if not isinstance(manifest, dict):
        raise UpdateError("manifest non valido: serve un oggetto JSON")
    version = str(manifest.get("version") or "").strip()
    package = str(manifest.get("url") or "").strip()
    checksum = str(manifest.get("sha256") or "").strip().lower()
    if not version or not package:
        raise UpdateError("manifest incompleto: servono version e url")
    if not CHECKSUM_RE.match(checksum):
        raise UpdateError("manifest incompleto: serve lo sha256 del pacchetto")
    parse_version(version)
    result.update(
        {
            "latest": version,
            "available": is_newer(version),
            "notes": str(manifest.get("notes") or ""),
            "published_at": str(manifest.get("published_at") or ""),
            "package_url": urllib.parse.urljoin(settings.update_url, package),
            "sha256": checksum,
        }
    )
    return result


def _download(url: str, destination: Path, timeout: float = 30.0) -> None:
    if url.startswith("file://"):
        source = Path(urllib.request.url2pathname(url[len("file://"):]))
        try:
            if source.stat().st_size > MAX_PACKAGE_BYTES:
                raise UpdateError("pacchetto troppo grande")
            shutil.copyfile(source, destination)
        except UpdateError:
            raise
        except OSError as error:
            raise UpdateError(f"pacchetto non leggibile: {error}") from error
        return
    if not url.startswith(("http://", "https://")):
        raise UpdateError("URL del pacchetto non valido")
    request = urllib.request.Request(
        url, headers={"User-Agent": f"devicehub/{__version__}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            total = 0
            with destination.open("wb") as output:
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_PACKAGE_BYTES:
                        raise UpdateError("pacchetto troppo grande")
                    output.write(chunk)
    except UpdateError:
        raise
    except (urllib.error.URLError, OSError) as error:
        raise UpdateError(f"download non riuscito: {error}") from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract(archive: Path, target: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as bundle:
            total = 0
            for member in bundle.infolist():
                name = PurePosixPath(member.filename.replace("\\", "/"))
                if name.is_absolute() or ".." in name.parts:
                    raise UpdateError("pacchetto non valido: percorso non sicuro")
                if member.file_size > MAX_PACKAGE_BYTES:
                    raise UpdateError("pacchetto non valido: file troppo grande")
                total += member.file_size
                if total > MAX_PACKAGE_BYTES:
                    raise UpdateError("pacchetto troppo grande")
                if member.is_dir():
                    target.joinpath(*name.parts).mkdir(parents=True, exist_ok=True)
                    continue
                destination = target.joinpath(*name.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
    except UpdateError:
        raise
    except zipfile.BadZipFile as error:
        raise UpdateError("pacchetto non valido: archivio zip corrotto") from error


def _package_files(source: Path) -> list[tuple[Path, Path]]:
    """File del pacchetto da installare, in ordine stabile."""
    files: list[tuple[Path, Path]] = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if not relative.parts or relative.parts[0] in SKIP_TOP:
            continue
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        if path.is_dir() or path.suffix in SKIP_SUFFIXES:
            continue
        files.append((relative, path))
    return files


def _validate(files: list[tuple[Path, Path]]) -> None:
    """Compila i file Python del pacchetto senza scrivere nulla.

    Un rilascio con un errore di sintassi farebbe morire il servizio al
    riavvio: meglio scoprirlo prima di sostituire i file installati.
    """
    for relative, source in files:
        if source.suffix != ".py":
            continue
        try:
            compile(source.read_bytes(), str(relative), "exec")
        except (OSError, SyntaxError, ValueError) as error:
            raise UpdateError(
                f"pacchetto non valido: {relative}: {error}"
            ) from error


def _backup(
    files: list[tuple[Path, Path]], target: Path, backup_root: Path
) -> list[Path]:
    """Copia i file che verranno sovrascritti, prima di toccare l'installazione."""
    saved: list[Path] = []
    for relative, _ in files:
        existing = target.joinpath(*relative.parts)
        if not existing.is_file():
            continue
        destination = backup_root.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(existing, destination)
        saved.append(relative)
    return saved


def _ensure_parent(
    parent: Path, target: Path, created: list[Path]
) -> None:
    """Crea le cartelle mancanti, ricordando quelle nuove da rimuovere."""
    pending: list[Path] = []
    current = parent
    while current != target and not current.exists():
        pending.append(current)
        current = current.parent
    for directory in reversed(pending):
        directory.mkdir()
        created.append(directory)


def _apply(
    files: list[tuple[Path, Path]], target: Path, created_files: list[Path],
    created_dirs: list[Path],
) -> int:
    """Copia i file e tiene traccia di quelli nuovi, per un eventuale ripristino."""
    copied = 0
    for relative, source in files:
        destination = target.joinpath(*relative.parts)
        _ensure_parent(destination.parent, target, created_dirs)
        existed = destination.exists()
        shutil.copy2(source, destination)
        if not existed:
            created_files.append(relative)
        copied += 1
    return copied


def _restore(
    target: Path, backup_root: Path, saved: list[Path],
    created_files: list[Path], created_dirs: list[Path],
) -> None:
    """Rimette i file precedenti e cancella quelli aggiunti dalla release."""
    for relative in reversed(created_files):
        try:
            target.joinpath(*relative.parts).unlink()
        except FileNotFoundError:
            pass
    for relative in saved:
        shutil.copy2(
            backup_root.joinpath(*relative.parts), target.joinpath(*relative.parts)
        )
    for directory in reversed(created_dirs):
        try:
            directory.rmdir()
        except OSError:
            pass


def _prune_backups(root: Path) -> None:
    """Conserva gli ultimi backup: bastano per un ripristino manuale.

    L'ordine e' quello reale di creazione (data di modifica): ordinare per nome
    metterebbe "1.10.0" prima di "1.4.0" e taglierebbe il backup sbagliato.
    """
    if not root.is_dir():
        return
    folders = sorted(
        (entry for entry in root.iterdir() if entry.is_dir()),
        key=lambda entry: entry.stat().st_mtime,
    )
    for folder in folders[:-BACKUP_KEEP]:
        shutil.rmtree(folder, ignore_errors=True)


def install(settings: Settings, manifest: dict) -> dict:
    """Scarica, verifica e copia il pacchetto nella directory dell'app."""
    version = str(manifest.get("latest") or "").strip()
    package = str(manifest.get("package_url") or "").strip()
    checksum = str(manifest.get("sha256") or "").strip().lower()
    if not version or not package or not CHECKSUM_RE.match(checksum):
        raise UpdateError("manifest non valido: versione o checksum mancanti")
    target = install_dir(settings)
    if not target.is_dir():
        raise UpdateError(f"cartella di installazione inesistente: {target}")
    with tempfile.TemporaryDirectory(prefix="devicehub-update-") as temporary:
        work = Path(temporary)
        archive = work / "release.zip"
        _download(package, archive)
        if _sha256(archive) != checksum:
            raise UpdateError("checksum del pacchetto non corrispondente")
        staging = work / "staging"
        staging.mkdir()
        _extract(archive, staging)
        root = staging
        if not (root / "devicehub").is_dir():
            entries = [
                entry for entry in staging.iterdir() if entry.name != "__MACOSX"
            ]
            if len(entries) == 1 and (entries[0] / "devicehub").is_dir():
                root = entries[0]
        if not (root / "devicehub").is_dir():
            raise UpdateError("pacchetto non valido: manca la cartella devicehub/")
        files = _package_files(root)
        if not files:
            raise UpdateError("pacchetto non valido: nessun file da installare")
        _validate(files)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup_root = target / "updates" / "backups" / f"{__version__}-{stamp}"
        try:
            saved = _backup(files, target, backup_root)
        except OSError as error:
            shutil.rmtree(backup_root, ignore_errors=True)
            raise UpdateError(
                f"backup non riuscito, installazione annullata: {error}"
            ) from error
        created_files: list[Path] = []
        created_dirs: list[Path] = []
        try:
            copied = _apply(files, target, created_files, created_dirs)
        except Exception as error:  # qualunque errore a meta' copia: si torna indietro
            try:
                _restore(target, backup_root, saved, created_files, created_dirs)
            except OSError as restore_error:
                raise UpdateError(
                    "copia non riuscita e ripristino incompleto:"
                    f" {restore_error}; backup in {backup_root}"
                ) from error
            raise UpdateError(
                f"copia non riuscita, file precedenti ripristinati: {error}"
            ) from error
        _prune_backups(backup_root.parent)
    return {
        "installed": copied,
        "version": version,
        "target": str(target),
        "backup": str(backup_root) if saved else "",
        "restart_required": True,
    }


def restart_later(delay: float = 1.0) -> None:
    """Riavvia il processo dopo la risposta HTTP, con il codice appena copiato."""

    def _restart() -> None:
        time.sleep(delay)
        os.execv(sys.executable, [sys.executable, "-m", "devicehub"])

    threading.Thread(target=_restart, daemon=True).start()
