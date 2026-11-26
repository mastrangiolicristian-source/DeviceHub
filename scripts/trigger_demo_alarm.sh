#!/usr/bin/env bash
# Simulazione live per demo commerciale: usa il server già avviato.
set -euo pipefail

cd "$(dirname "$0")/.."
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# Stessa porta della demo: DEVICEHUB_API_PORT (3000 se non impostata).
API_URL="${DEMO_API_URL:-${API_URL:-http://127.0.0.1:${DEVICEHUB_API_PORT:-3000}/api/v1/demo/trigger-alarm}}"
VEHICLE_PLATE="${VEHICLE_PLATE:-DEMO-01}"
ALARM_TYPE="${ALARM_TYPE:-SOS_PANIC_BUTTON}"
DEMO_TRIGGER_TOKEN="${DEVICEHUB_DEMO_TRIGGER_TOKEN:-${DEMO_TRIGGER_TOKEN:-}}"

echo "Avvio simulazione evento critico su mezzo $VEHICLE_PLATE..."

payload=$(cat <<JSON
{
  "plate": "$VEHICLE_PLATE",
  "alarm_type": "$ALARM_TYPE",
  "severity": "CRITICAL",
  "lat": 41.9028,
  "lng": 12.4964,
  "speed_kmh": 0,
  "channels": ["email", "sms", "voice_tts"]
}
JSON
)

headers=(-H "Content-Type: application/json")
if [ -n "$DEMO_TRIGGER_TOKEN" ]; then
  headers+=(-H "X-Demo-Token: $DEMO_TRIGGER_TOKEN")
fi

body=$(mktemp)
trap 'rm -f "$body"' EXIT

if ! status=$(curl -sS -o "$body" -w '%{http_code}' -X POST "$API_URL" \
  "${headers[@]}" -d "$payload"); then
  echo "Richiesta non riuscita: server demo raggiungibile su $API_URL?" >&2
  exit 1
fi

if ! python3 -m json.tool < "$body"; then
  cat "$body"
fi

if [ "$status" -lt 200 ] || [ "$status" -ge 300 ]; then
  echo "Trigger rifiutato (HTTP $status)." >&2
  exit 1
fi

echo "Evento registrato. Controlla la scheda SOC e la coda Outbox."
