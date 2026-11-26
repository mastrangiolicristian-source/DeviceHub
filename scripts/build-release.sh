#!/usr/bin/env bash
# Costruisce l'archivio di rilascio dal commit corrente: verifica l'albero
# Git, controlla i file indispensabili, calcola il checksum e scarta il
# pacchetto se contiene segreti, database o cartelle di lavoro locali.
#
# Uso: ./scripts/build-release.sh   (da qualsiasi directory)
# Esito 0 = pacchetto pronto in dist/; esito 1 = albero sporco, file
# indispensabili mancanti o controllo d'igiene fallito (in quei casi
# l'archivio viene rimosso).
#
# Dipendenze: git, bash 4+, coreutils (sha256sum, mktemp, wc, tr, awk) e,
# per leggere lo zip, unzip oppure python3 (Ubuntu 24.04: pacchetti git,
# coreutils, unzip; python3 e' gia' richiesto dalla checklist di deploy).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DIST="dist"
ARCHIVE="$DIST/devicehub-release.zip"
CHECKSUM="$ARCHIVE.sha256"
NAME="$(basename "$ARCHIVE")"

# File senza i quali il pacchetto non e' avviabile.
REQUIRED_FILES=(
    "devicehub/__main__.py"
    "requirements.txt"
    "profiles/fmc150.json"
    "deploy/devicehub.service"
)

# Nomi che non devono mai entrare nel pacchetto (ancorati: niente falsi
# positivi su nomi che contengono ".db" o ".env" come sottostringa).
FORBIDDEN='(^|/)\.env($|\.)|\.pem$|\.key$|\.db$|\.db-wal$|\.db-shm$|(^|/)artifacts/|(^|/)\.venv/|(^|/)__pycache__/|(^|/)dist/|(^|/)\.pytest_cache/'

# Template delle variabili d'ambiente: sono esempi senza valori, quindi
# possono essere distribuiti. Ogni altra variante (.env, .env.local,
# .env.production, .env.example.bak) resta bloccata.
ENV_TEMPLATES='(^|/)\.env\.(example|sample|template)$'

if [ -t 2 ] && [ -z "${NO_COLOR:-}" ]; then
    RED=$'\033[31m'
    BOLD=$'\033[1m'
    RESET=$'\033[0m'
else
    RED=''
    BOLD=''
    RESET=''
fi

say() { printf '%s\n' "$*"; }
fail() { printf '%sERRORE: %s%s\n' "$RED" "$*" "$RESET" >&2; exit 1; }

# 1. Dipendenze e albero Git pulito: si rilascia solo cio' che e' committato.
say "[1/7] Controllo di dipendenze e albero Git..."
command -v git >/dev/null 2>&1 || fail "git non trovato nel PATH"
if [ -n "$(git status --porcelain)" ]; then
    git status --short >&2
    fail "l'albero Git non e' pulito: committare o ripristinare le modifiche"
fi
COMMIT="$(git rev-parse --short HEAD)"
say "      albero pulito, commit $COMMIT"

# 2. Cartella di uscita.
say "[2/7] Preparazione di $DIST/..."
mkdir -p "$DIST"

# 3. Archivio dal commit corrente (solo file tracciati).
say "[3/7] Creazione di $ARCHIVE..."
rm -f "$ARCHIVE" "$CHECKSUM"
git archive --format=zip -o "$ARCHIVE" HEAD
[ -s "$ARCHIVE" ] || fail "archivio vuoto: $ARCHIVE"

# Elenco delle voci, usato dai controlli successivi.
ENTRIES="$(mktemp)"
CHECKABLE="$(mktemp)"
trap 'rm -f "$ENTRIES" "$ENTRIES.lf" "$CHECKABLE"' EXIT
if command -v unzip >/dev/null 2>&1; then
    unzip -Z1 "$ARCHIVE" > "$ENTRIES"
elif command -v python3 >/dev/null 2>&1; then
    python3 - "$ARCHIVE" > "$ENTRIES" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as archive:
    for name in archive.namelist():
        print(name)
PY
else
    fail "serve unzip oppure python3 per leggere l'archivio"
fi
# Normalizza i fine riga: su Windows python3 scrive CRLF e il match esatto
# dei nomi fallirebbe.
tr -d '\r' < "$ENTRIES" > "$ENTRIES.lf" && mv "$ENTRIES.lf" "$ENTRIES"
COUNT="$(wc -l < "$ENTRIES" | tr -d ' ')"
[ "$COUNT" -gt 0 ] || fail "archivio senza voci"

# 4. Controllo preventivo: i file indispensabili devono essere nell'archivio.
say "[4/7] Verifica dei file indispensabili..."
MISSING_FILES=()
for entry in "${REQUIRED_FILES[@]}"; do
    grep -Fxq "$entry" "$ENTRIES" || MISSING_FILES+=("$entry")
done
if [ "${#MISSING_FILES[@]}" -ne 0 ]; then
    printf '%s%sERRORE: archivio incompleto, file indispensabili mancanti:%s\n' \
        "$BOLD" "$RED" "$RESET" >&2
    for entry in "${MISSING_FILES[@]}"; do
        printf '%s  - %s%s\n' "$RED" "$entry" "$RESET" >&2
    done
    printf '%sPacchetto scartato: verificare che i file siano tracciati da Git.%s\n' \
        "$RED" "$RESET" >&2
    rm -f "$ARCHIVE" "$CHECKSUM"
    exit 1
fi
say "      presenti: ${REQUIRED_FILES[*]}"

# 5. Checksum SHA-256 accanto all'archivio.
say "[5/7] Calcolo del checksum SHA-256..."
if command -v sha256sum >/dev/null 2>&1; then
    HASH="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
    HASH="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"
else
    fail "serve sha256sum oppure shasum"
fi
printf '%s  %s\n' "$HASH" "$NAME" > "$CHECKSUM"
if command -v sha256sum >/dev/null 2>&1; then
    ( cd "$DIST" && sha256sum -c "$NAME.sha256" >/dev/null ) \
        || fail "il checksum non corrisponde all'archivio appena creato"
fi

# 6. Igiene: nessun segreto, database o cartella locale nell'archivio.
say "[6/7] Controlli di igiene sull'archivio..."
# Si escludono solo i template espliciti, non i file di configurazione reali.
grep -Ev "$ENV_TEMPLATES" "$ENTRIES" > "$CHECKABLE" || true
if OFFENDERS="$(grep -Ei "$FORBIDDEN" "$CHECKABLE")"; then
    printf "%s%sERRORE: l'archivio contiene file che non vanno distribuiti:%s\n" \
        "$BOLD" "$RED" "$RESET" >&2
    printf '%s\n' "$OFFENDERS" | while IFS= read -r entry; do
        printf '%s  - %s%s\n' "$RED" "$entry" "$RESET" >&2
    done
    rm -f "$ARCHIVE" "$CHECKSUM"
    printf '%sPacchetto rimosso.%s\n' "$RED" "$RESET" >&2
    exit 1
fi
say "      nessun .env reale, .pem, .key, .db/-wal/-shm, artifacts/, .venv/, dist/ o __pycache__"
say "      ammessi i template .env.example, .env.sample, .env.template"

# 7. Report finale.
BYTES="$(wc -c < "$ARCHIVE" | tr -d ' ')"
say "[7/7] Pacchetto pronto."
say ""
say "  commit    : $COMMIT"
say "  archivio  : $ROOT/$ARCHIVE"
say "  checksum  : $ROOT/$CHECKSUM"
say "  voci      : $COUNT"
say "  dimensione: $BYTES byte"
say "  sha256    : $HASH"
say ""
say "Sul VPS, dalla cartella dell'archivio: sha256sum -c $NAME.sha256"
