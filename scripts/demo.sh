#!/usr/bin/env bash
# Ambiente demo isolato: database dedicato, server e simulatore.
set -euo pipefail

cd "$(dirname "$0")/.."

# Facoltativo: le variabili del file .env (non versionato) valgono anche per
# seed, server e simulatore. L'ambiente della shell ha sempre la precedenza.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# Sessione stabile tra i riavvii: senza un segreto persistente ogni riavvio
# invalida i cookie e la dashboard mostra "sessione scaduta" al primo salvataggio.
if [ -z "${DEVICEHUB_SESSION_SECRET:-}" ]; then
  DEVICEHUB_SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  export DEVICEHUB_SESSION_SECRET
  umask 077
  printf '\nDEVICEHUB_SESSION_SECRET=%s\n' "$DEVICEHUB_SESSION_SECRET" >> .env
  echo "Aggiunto DEVICEHUB_SESSION_SECRET a .env: le sessioni restano valide dopo il riavvio."
fi

DB="${DEVICEHUB_DB:-/tmp/devicehub-demo.db}"
PORT="${DEVICEHUB_API_PORT:-3000}"
TCP_PORT="${DEVICEHUB_TCP_PORT:-5098}"
ADMIN_PASSWORD="${DEVICEHUB_ADMIN_PASSWORD:-Demo-Cliente-2026}"
COMPANY="${DEVICEHUB_COMPANY:-${APP_NAME:-FleetHUD Demo}}"

if [ ! -x ./.venv/bin/python ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install -q -r requirements.txt
fi

port_busy() {
  ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1$"
}

if curl -fsS "http://127.0.0.1:$PORT/health" > /dev/null 2>&1 || port_busy "$PORT" || port_busy "$TCP_PORT"; then
  echo "Porta $PORT o $TCP_PORT già in ascolto: ferma il server demo prima di riavviare." >&2
  echo "Il database demo non è stato toccato." >&2
  exit 1
fi

echo "Database demo: $DB"
if [ "${DEVICEHUB_DEMO_RESET:-1}" = "1" ]; then
  case "$DB" in
    *demo*)
      rm -f "$DB" "$DB-wal" "$DB-shm"
      echo "Database demo azzerato (DEVICEHUB_DEMO_RESET=0 per conservarlo)."
      ;;
    *)
      echo "Reset rifiutato: il percorso non contiene 'demo'. Usa DEVICEHUB_DEMO_RESET=0 per un DB esistente." >&2
      exit 1
      ;;
  esac
fi
echo "Popolamento flotta demo ..."
DEVICEHUB_DB="$DB" DEVICEHUB_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  ./.venv/bin/python scripts/seed_demo.py

echo "Avvio server su http://127.0.0.1:$PORT ..."
DEVICEHUB_DB="$DB" \
DEVICEHUB_API_PORT="$PORT" \
DEVICEHUB_TCP_PORT="$TCP_PORT" \
DEVICEHUB_API_HOST=0.0.0.0 \
DEVICEHUB_PROFILE=profiles/fmc150.json \
DEVICEHUB_COMPANY="$COMPANY" \
DEVICEHUB_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  nohup ./.venv/bin/python -m devicehub > /tmp/devicehub-demo.log 2>&1 &
SERVER_PID=$!

sleep 4
if ! curl -fsS "http://127.0.0.1:$PORT/health" > /dev/null; then
  echo "Server non pronto: controlla /tmp/devicehub-demo.log" >&2
  exit 1
fi

echo "Avvio simulatore su TCP $TCP_PORT ..."
nohup ./.venv/bin/python -m devicehub.simulator \
  --port "$TCP_PORT" --packets 0 --interval 3 --speed 0 \
  > /tmp/devicehub-demo-sim.log 2>&1 &
SIM_PID=$!

cat <<EOF

Demo pronta.
  URL:        http://127.0.0.1:$PORT
  Admin:      demo / $ADMIN_PASSWORD
  Manager:    demo.manager / Manager-Demo-2026
  Server PID: $SERVER_PID   (log /tmp/devicehub-demo.log)
  Sim PID:    $SIM_PID      (log /tmp/devicehub-demo-sim.log)

La flotta è già popolata (3 mezzi, storico, autista).
Prossimi passi:
  1. Accedi con demo / $ADMIN_PASSWORD.
  2. Apri Soluzioni e scegli verticale/pacchetto per la demo.
  3. Apri Mappa e mostra la modalità Google o il toggle tracce.

Per fermare tutto:
  kill $SERVER_PID $SIM_PID
EOF
