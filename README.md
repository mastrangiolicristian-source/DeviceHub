# DeviceHub — ingestione GPS e provisioning

Modulo di ingestione per la piattaforma flotta: riceve i dati dai tracker
Teltonika via TCP, li decodifica (Codec 8 / 8E), li salva e aggiorna la tabella
`vehicles` della dashboard esistente. Include il generatore dei comandi di
configurazione da inviare al GPS e un simulatore per provare tutto senza
hardware.

Hardware di riferimento: **Teltonika FMC150** (CAN integrato).
Guida di acquisto, cablaggio e collaudo: [docs/fmc150-commissioning.md](docs/fmc150-commissioning.md).

## Installazione

```bash
python3 -m pip install -r requirements.txt
```

## Avvio

```bash
# ingestione TCP su 5027 + API su 8010
DEVICEHUB_DB=./devicehub.db python3 -m devicehub
```

Prova completa senza GPS (device simulato che invia 5 posizioni):

```bash
python3 -m devicehub.simulator --packets 5 --interval 2
```

## Accesso da un altro browser

L'anteprima di questo workspace e' privata e temporanea: non e' un indirizzo
pubblico. Per aprire la piattaforma da un browser qualsiasi servono un server
raggiungibile e un nome con HTTPS.

1. **Produzione (consigliato)**: seguire la checklist [docs/deploy-checklist.md](docs/deploy-checklist.md),
   con i dettagli in [docs/deploy-vps.md](docs/deploy-vps.md).
   Al termine la dashboard risponde su `https://api.tuodominio.it/`, il login
   su `/login`, i GPS sulla porta 5027; qualsiasi browser vede la stessa
   interfaccia.
2. **Prova temporanea con tunnel**, da una macchina dove gira il servizio:

   ```bash
   cloudflared tunnel --url http://127.0.0.1:8010
   # oppure: ngrok http 8010
   ```

   Il tunnel stampa un indirizzo `https://...` valido finche' il processo resta
   acceso. Prima di condividerlo impostare `DEVICEHUB_ADMIN_PASSWORD` e
   `DEVICEHUB_SESSION_SECRET`: senza utenti il servizio e' in primo avvio e
   chiunque abbia l'indirizzo entra come amministratore.
3. **Anteprima del workspace**: la scheda Browser qui accanto mostra il
   servizio in esecuzione, ma l'indirizzo e' riservato a chi sta lavorando e
   non e' adatto a un cliente.

Con dati veri (targhe, posizioni) servono login attivo, HTTPS e una password
per ogni utente: sono dati personali.

## Verifica offline degli snapshot

Lo snapshot esportato si controlla senza server e senza database:

```bash
curl -s -H "X-Api-Key: <token>" \
  https://api.tuodominio.it/esg/snapshots/3/export > snapshot-3.json

python3 scripts/verify_snapshot.py snapshot-3.json
python3 scripts/verify_snapshot.py snapshot-3.json --public-key chiave-cliente.pem
```

Con `--public-key` (la chiave pubblica consegnata al cliente, tenuta fuori dal
server) si verifica anche l'identita' del firmatario: senza, la firma prova
solo che il file non e' stato modificato. Esito 0 = verificato, 1 = non
verificato.

Chi non ha Python puo' usare la pagina pubblica `/verify`: si trascina il file
esportato (e, se disponibile, la chiave pubblica in formato PEM) e il
controllo avviene nel browser, senza inviare nulla al server. Il file non
lascia la macchina.

## Endpoint

`/` e' la dashboard VisionOS (sedici schede: dashboard, mappa con replay,
flotta, censimento, SOC funzionanti; le altre dichiarano cosa manca, senza dati
inventati). `/controllo` resta la pagina operativa essenziale. `/login` apre la
sessione: cookie `dh_session` HttpOnly, ruoli `admin` / `manager` / `soc` /
`viewer` e isolamento per cliente (tenant). Il cookie si rinnova mentre la
dashboard e' in uso; alla scadenza la pagina riporta al login.

Finche' non esiste un utente e non e' impostata una chiave API il servizio
resta in **primo avvio** (accesso aperto, `/health` risponde `"auth": "open"`):
serve a installare, non va lasciato cosi' su un server pubblico.

| Metodo | Percorso | Descrizione |
| --- | --- | --- |
| GET | `/health` | stato del servizio (dichiara se l'accesso e' aperto) |
| POST | `/auth/login` | accesso, imposta il cookie di sessione |
| POST | `/auth/logout` | chiude la sessione |
| GET | `/auth/me` | utente corrente e modalita' di accesso |
| GET | `/users` | utenti e clienti (solo amministratore) |
| POST | `/users` | crea utente/cliente con body JSON (solo amministratore) |
| POST | `/auth/password` | cambio password dell'utente collegato |
| POST | `/users/{username}/password` | reset da amministratore (body JSON), obbliga il cambio |
| POST | `/users/{username}/unlock` | sblocca un account bloccato |
| POST | `/users/{username}/active?active=false` | disattiva o riattiva un utente (chiude subito le sessioni) |
| PATCH | `/devices/{imei}` | modifica targa, modello e nota del mezzo (admin o manager) |
| DELETE | `/devices/{imei}` | elimina il mezzo e i dati collegati (admin o manager) |
| GET | `/updates` | versione installata e canale di rilascio (admin) |
| POST | `/updates/check` | confronta il manifest con la versione installata (admin) |
| POST | `/updates/apply` | scarica, verifica lo SHA-256 e installa il pacchetto; poi riavvia (admin) |
| GET | `/esg?days=30` | km, litri e CO2 stimati nel periodo |
| POST | `/devices/{imei}/esg?fuel_l_per_100km=&co2_kg_per_liter=` | consumo e fattore del singolo mezzo (senza parametri torna ai valori di flotta) |
| POST | `/esg/snapshot?month=YYYY-MM` | congela e sigilla i numeri di un mese (solo admin) |
| GET | `/esg/snapshots` | snapshot disponibili, con impronta |
| GET | `/esg/snapshots/{id}` | report congelato + verifica dell'impronta |
| GET | `/esg/snapshots/{id}/export` | documento autonomo da verificare offline |
| GET | `/audit/admin` | azioni amministrative con autore e momento (solo admin) |
| GET | `/esg/public-key` | chiave pubblica Ed25519 per verificare gli snapshot |
| GET | `/esg/signing-keys` | registro delle chiavi, con stato e snapshot firmati (admin) |
| POST | `/esg/signing-key/rotate` | genera una nuova chiave e archivia la precedente (admin) |
| GET | `/report/{id}` | report mensile congelato, stampabile |
| GET | `/verify` | pagina pubblica: verifica un file esportato nel browser |
| POST | `/esg/snapshots/{id}/send?to=` | invia il report per email con link (admin o manager) |
| POST | `/esg/snapshots/{id}/link?hours=` | crea un link con scadenza, senza account (admin o manager) |
| POST | `/esg/snapshots/{id}/link/revoke` | revoca i link attivi dello snapshot |
| GET | `/esg/snapshots/{id}/links` | link creati, con scadenza e aperture (admin o manager) |
| GET | `/esg/snapshots/{id}/pdf` | PDF del report (sessione) |
| GET | `/r/{token}` | report aperto dal link del cliente |
| GET | `/public/report/{token}` | dati del report per il link con token |
| GET | `/public/report/{token}/pdf` | PDF del report da un link con token |
| GET | `/branding` | nome, colore e logo del report del proprio cliente |
| POST | `/branding` | imposta nome e colore (admin o manager) |
| POST | `/branding/logo` | carica un logo PNG/JPEG fino a 512 KB (corpo della richiesta) |
| DELETE | `/branding/logo` | rimuove il logo |
| GET | `/branding/preview.pdf` | anteprima PDF con nome e colore non ancora salvati |
| GET | `/links/blocked` | indirizzi con tentativi falliti sui link (admin) |
| POST | `/links/unblock?ip=` | azzera tentativi e blocco di un indirizzo (admin) |
| GET | `/geofences` | zone del cliente (o globali per l'amministratore), con geometria e fasce orarie |
| POST | `/geofences` | crea cerchio, poligono o linea di confine; `geometry`, `schedule`, `timezone` |
| DELETE | `/geofences/{id}` | elimina una zona |
| GET | `/positions/{imei}/history?date=` | percorso del giorno semplificato per il player |
| GET | `/positions/{imei}/history/export?date=&format=gpx\|kml` | scarica il tracciato grezzo del giorno in GPX o KML |
| GET | `/alert-rules` | soglie di velocita' e furto effettive |
| POST | `/alert-rules` | salva soglia e attivazione (`speed`, `theft`) |
| GET | `/work-hours` | lettura delle fasce orarie lavorative del cliente (base dell'accensione fuori orario) |
| POST | `/work-hours` | configura fascia, fuso e attivazione (admin o manager) |
| GET | `/maintenance` | interventi con stato e chilometraggio attuale |
| POST | `/maintenance` | pianifica un intervento (data o km) |
| POST | `/maintenance/{id}/complete` | chiude un intervento |
| GET | `/export/{dataset}` | CSV o XLSX di `devices`, `positions`, `trips`, `maintenance`, `alerts`, `fuel` |
| POST | `/devices/{imei}/privacy?enabled=true\|false` | modalita' privacy GDPR: coordinate oscurate, odometro e CAN conservati |
| GET | `/activity/{imei}` | tragitti e soste delle ultime ore |
| GET | `/fuel/report` | km, litri stimati, costo, minimo e cali del mese |
| GET | `/safety/checks` | controlli di sicurezza con riepilogo |
| POST | `/safety/checks` | registra un controllo; una non conformita' apre `SAFETY` |
| GET | `/notifications` | destinatari email/SMS e stato dei canali (senza credenziali) |
| GET | `/notifications/outbox` | ultime notifiche email/SMS/voce; admin tutto, manager/SOC il proprio cliente |
| POST | `/notifications` | salva i destinatari del cliente |
| POST | `/api/v1/demo/trigger-alarm` | simula un allarme su un mezzo della flotta; attivo solo con `DEMO_MODE=true`, token opzionale |
| POST | `/sms/receipts` | webhook ricevute del gateway (token condiviso) |
| GET | `/sms/receipts` | ultime ricevute SMS (admin) |
| GET | `/devices` | dispositivi visti, con ultima posizione |
| POST | `/devices/{imei}/activate?plate=&model=` | abilita un IMEI |
| POST | `/devices/{imei}/engine_block?block=true` | blocco/sblocco relè (rifiutato se in movimento o senza fix GPS recente) |
| GET | `/devices/{imei}/commands` | audit dei comandi inviati |
| GET | `/commands?limit=` | audit di tutti i mezzi visibili |
| GET | `/alerts?open_only=true` | allarmi SOC (jamming, presa in carico) |
| POST | `/alerts/{id}/ack` | prende in carico un allarme |
| GET | `/positions/{imei}?limit=` | storico posizioni |
| GET | `/provisioning/{imei}?host=&port=&apn=&codec=` | piano di configurazione in JSON |
| GET | `/provisioning/{imei}/sms.txt` | comandi SMS pronti da inviare |

Esempio:

```bash
curl -s "http://127.0.0.1:8010/provisioning/352093086403655/sms.txt?host=gps.example.com&apn=internet.m2m"
```

## Variabili d'ambiente

| Variabile | Default | Note |
| --- | --- | --- |
| `DEVICEHUB_DB` | `devicehub.db` | usare lo stesso file della dashboard per il ponte su `vehicles` |
| `DEVICEHUB_TCP_HOST` / `DEVICEHUB_TCP_PORT` | `0.0.0.0` / `5027` | porta di ascolto dei tracker |
| `DEVICEHUB_API_HOST` / `DEVICEHUB_API_PORT` | `127.0.0.1` / `8010` | con `DEVICEHUB_API_TOKEN` assente resta su loopback |
| `DEVICEHUB_API_TOKEN` | vuoto | se impostato, richiede header `X-Api-Key` |
| `DEVICEHUB_PUBLIC_HOST` / `DEVICEHUB_PUBLIC_PORT` | `127.0.0.1` / `5027` | indirizzo scritto nei comandi di provisioning |
| `DEVICEHUB_APN` | vuoto | APN della SIM M2M |
| `DEVICEHUB_CODEC` | `142` (`0x8E`) | 8 = Codec 8, 142 = Codec 8E |
| `DEVICEHUB_DOUTS` | `3` | uscite digitali del modello (QKIB0 = 3, QJIB0 = 2) |
| `DEVICEHUB_PROFILE` | vuoto | es. `profiles/fmc150.json` |
| `DEVICEHUB_LOG_IO` | `0` | logga gli AVL ID grezzi: serve a mappare i CAN |
| `DEVICEHUB_REJECT_UNKNOWN` | `0` | `1` = rifiuta IMEI non abilitati |
| `DEVICEHUB_ADMIN_PASSWORD` | vuoto | solo primo avvio: crea `admin`; senza, login disattivato |
| `DEVICEHUB_ADMIN_TENANT` | `Default` | cliente dell'amministratore iniziale |
| `DEVICEHUB_SESSION_SECRET` | casuale | firma dei cookie; `scripts/demo.sh` la salva in `.env`, senza la sessione cade a ogni riavvio |
| `DEVICEHUB_SESSION_TTL_HOURS` | `12` | durata della sessione |
| `DEVICEHUB_MAX_LOGIN_ATTEMPTS` | `5` | tentativi falliti prima del blocco |
| `DEVICEHUB_LOCK_MINUTES` | `15` | durata del blocco dell'account |
| `DEVICEHUB_FUEL_L_PER_100KM` | `8.0` | consumo usato dalla stima ESG |
| `DEVICEHUB_CO2_KG_PER_LITER` | `2.65` | fattore di emissione del gasolio |
| `DEVICEHUB_COMPANY` / `APP_NAME` | `CM FleetHUD VisionOS` | nome mostrato nella dashboard |
| `DEVICEHUB_CUSTOM_BG_IMAGE` | vuoto | sfondo predefinito del server; ogni cliente puo' impostarne uno proprio in Branding (URL o immagine fino a 1,5 MB) |
| `DEVICEHUB_UPDATE_URL` | vuoto | manifest JSON del canale di rilascio (`http(s)` o `file://`) |
| `DEVICEHUB_UPDATE_DIR` | cartella dell'app | destinazione dei file del pacchetto, per installazioni separate |
| `DEVICEHUB_SIGNING_KEY` | accanto al database | chiave privata Ed25519 per firmare gli snapshot: va salvata nei backup |
| `DEVICEHUB_SMTP_ENABLED` / `SMTP_ENABLED` | host presente | spegne tutti gli invii email se `false` |
| `DEVICEHUB_SMTP_MODE` / `SMTP_MODE` | `live` | `local_preview` usa Mailpit/MailHog; se non raggiungibile il messaggio resta in anteprima nell'outbox |
| `DEVICEHUB_SMTP_HOST` / `SMTP_HOST` | vuoto | server SMTP per report e allarmi: senza host l'invio resta spento |
| `DEVICEHUB_SMTP_PORT` / `SMTP_PORT` | `587` | per Mailpit/MailHog in demo usare `1025` |
| `DEVICEHUB_SMTP_USER` / `SMTP_USER` | vuoto | credenziali della casella: restano nel `.env`, mai nel codice |
| `DEVICEHUB_SMTP_PASSWORD` / `SMTP_PASS` | vuoto | password SMTP; in demo locale può restare vuota |
| `DEVICEHUB_SMTP_STARTTLS` / `SMTP_STARTTLS` | `1` (`0` in `local_preview`) | STARTTLS sulla porta 587; mettere `0` solo su un relay interno |
| `DEVICEHUB_REPORT_FROM` / `SMTP_FROM` | vuoto | mittente del report; accetta `Nome <indirizzo@dominio>` |
| `DEVICEHUB_REPORT_TO` | vuoto | destinatari predefiniti, separati da virgola |
| `DEVICEHUB_PUBLIC_URL` | vuoto | indirizzo pubblico per i link nelle email, es. `https://api.esempio.it` |
| `DEVICEHUB_MONTHLY_AUTO` | `0` | `1` = chiude il mese precedente da sola e invia il report |
| `DEVICEHUB_MONTHLY_HOUR` | `3` | ora UTC del controllo giornaliero di chiusura |
| `DEVICEHUB_MONTHLY_EMAIL` | `1` | invia il report se SMTP e destinatari sono configurati |
| `DEVICEHUB_LINK_HOURS` | `72` | validita dei link con token creati per email o a mano |
| `DEVICEHUB_LINK_MAX_USES` | `25` | aperture massime di un link con token |
| `DEVICEHUB_LINK_ATTEMPT_LIMIT` | `10` | tentativi falliti prima del blocco temporaneo |
| `DEVICEHUB_LINK_BLOCK_MINUTES` | `15` | durata del blocco per indirizzo |
| `DEVICEHUB_REPORT_TIMEZONE` | `Europe/Rome` | fuso del mese civile: i confini di report e report carburante vengono convertiti in UTC |
| `DEVICEHUB_POSITION_RETENTION_DAYS` | `0` | elimina a lotti le posizioni più vecchie di N giorni (`0` = storico completo) |
| `DEVICEHUB_ALERT_RETENTION_DAYS` | `0` | retention separata di allarmi e posizioni SOS (`0` = nessuna scadenza) |
| `DEVICEHUB_PRIVACY_IO_ID` | `0` | ingresso digitale che attiva la modalita' privacy dal tracker (`0` = disabilitato) |
| `DEVICEHUB_LOGIN_IP_ATTEMPT_LIMIT` | `20` | accessi falliti dallo stesso indirizzo prima del blocco del login |
| `DEVICEHUB_LOGIN_IP_BLOCK_MINUTES` | `15` | durata del blocco login per indirizzo |
| `DEVICEHUB_ALERT_TO` / `ALERT_TO` | vuoto | email per geofence, velocita', furto, SOS e manutenzione; in `local_preview` senza destinatari usa il mittente come casella demo |
| `DEVICEHUB_SOS_IO_ID` | `251` | AVL ID del pulsante SOS, da confermare sul dispositivo |
| `DEVICEHUB_FUEL_PRICE_EUR` | `1.75` | prezzo al litro per il report costi |
| `DEVICEHUB_IDLE_L_PER_HOUR` | `2.0` | litri al minimo per ora |
| `DEVICEHUB_FUEL_THEFT_LITERS` | `15` | calo di carburante che apre un allarme |
| `DEVICEHUB_UNPLUG_ENABLED` | `1` | rileva il taglio dell'alimentazione esterna (AVL 66) |
| `DEVICEHUB_UNPLUG_MIN_VOLTAGE` | `8.0` | tensione esterna sotto la quale apre `UNPLUG` |
| `DEVICEHUB_UNPLUG_DROP_VOLTAGE` | `3.0` | calo minimo rispetto al record precedente |
| `DEVICEHUB_SMS_ENABLED` / `SMS_ENABLED` | URL presente o modalità simulata | abilita il canale SMS |
| `DEVICEHUB_SMS_MODE` / `SMS_MODE` | `live` | `simulated` registra nell'outbox senza chiamare il gateway |
| `DEVICEHUB_SMS_PROVIDER` / `SMS_PROVIDER` | vuoto | etichetta del fornitore mostrata nell'outbox (`twilio`, `infobip`, ...) |
| `DEVICEHUB_SMS_URL` / `SMS_URL` | vuoto | gateway HTTP che accetta `POST` JSON `{to, text}`; serve in modalità `live` |
| `DEVICEHUB_SMS_TOKEN` / `SMS_TOKEN` | vuoto | bearer token per il gateway |
| `DEVICEHUB_SMS_TO` / `SMS_TO` | vuoto | numeri separati da virgola |
| `DEVICEHUB_SMS_FROM` / `SMS_FROM` / `SMS_SENDER_ID` | vuoto | mittente opzionale |
| `DEVICEHUB_SMS_TEMPLATE_CRITICAL` / `SMS_TEMPLATE_CRITICAL` | template integrato | supporta `{{app_name}}`, `{{plate}}`, `{{alarm_type}}`, `{{time}}`, `{{maps_link}}` |
| `DEVICEHUB_SMS_RETRIES` / `SMS_RETRIES` | `2` | tentativi aggiuntivi sugli errori di rete o 5xx |
| `DEVICEHUB_SMS_RECEIPT_TOKEN` / `SMS_RECEIPT_TOKEN` | vuoto | token per il webhook delle ricevute |
| `DEVICEHUB_VOICE_ENABLED` / `VOICE_ENABLED` | `0` | abilita il canale vocale per le emergenze massime |
| `DEVICEHUB_VOICE_MODE` / `VOICE_MODE` | `simulated` | `simulated` registra la chiamata nell'outbox; il provider live non è incluso |
| `DEVICEHUB_VOICE_PROVIDER` / `VOICE_PROVIDER` | vuoto | etichetta del provider (`twilio_voice`, ...) |
| `DEVICEHUB_VOICE_CALLER_ID` / `VOICE_CALLER_ID` | vuoto | numero chiamante previsto dal provider |
| `DEVICEHUB_VOICE_LANGUAGE` / `VOICE_LANGUAGE` | `it-IT` | lingua del messaggio TTS |
| `DEVICEHUB_VOICE_TTS_TEMPLATE` / `VOICE_TTS_TEMPLATE` | template integrato | stessi segnaposto del template SMS |
| `ENVIRONMENT` | `production` | ambiente dichiarato in `/health` |
| `DEMO_MODE` | `false` (vero se `ENVIRONMENT=demo`) | in demo consente il sink SMS/voce senza destinatari reali |
| `DEVICEHUB_DEMO_TRIGGER_TOKEN` / `DEMO_TRIGGER_TOKEN` | vuoto | se impostato, il trigger demo richiede `X-Demo-Token` |
| `DEVICEHUB_ALERT_COOLDOWN_MINUTES` | `10` | intervallo minimo tra due messaggi dello stesso allarme |
| `DEVICEHUB_DRIVER_IO_ID` | `0` | IO del badge iButton/RFID (0 = disattivo) |
| `DEVICEHUB_HARSH_ACCEL_KMH_S` | `8` | soglia accelerazione brusca in km/h al secondo |
| `DEVICEHUB_HARSH_BRAKE_KMH_S` | `10` | soglia frenata brusca in km/h al secondo |
| `DEVICEHUB_WEBHOOK_URL` | vuoto | destinatario degli eventi in uscita |
| `DEVICEHUB_WEBHOOK_SECRET` | vuoto | segreto HMAC per la firma dei webhook |
| `DEVICEHUB_WEBHOOK_RETRIES` | `2` | tentativi aggiuntivi sui webhook 5xx/rete |

### Configurazione demo dei canali

Il file `.env` nella directory di avvio viene caricato automaticamente, senza
sovrascrivere le variabili già presenti nella shell. I test lo ignorano per
restare isolati; per disattivarlo esplicitamente usare
`DEVICEHUB_SKIP_DOTENV=1`. In demo:

```dotenv
APP_NAME="Fleet & Security Platform"
ENVIRONMENT=demo
DEMO_MODE=true
DEMO_TRIGGER_TOKEN="sostituire-con-un-token-casuale"

SMTP_ENABLED=true
SMTP_MODE=local_preview
SMTP_HOST=127.0.0.1
SMTP_PORT=1025
SMTP_FROM="Fleet Alert Center <alert@localhost>"

SMS_ENABLED=true
SMS_MODE=simulated
SMS_PROVIDER=twilio
SMS_SENDER_ID=AlertCenter

VOICE_ENABLED=true
VOICE_MODE=simulated
VOICE_PROVIDER=twilio_voice
VOICE_CALLER_ID="+390000000000"
VOICE_LANGUAGE=it-IT
```

Non inserire token o password reali nel repository: `.env` è già ignorato da
Git. Con `SMTP_MODE=local_preview` il servizio prova il server su
`SMTP_HOST:SMTP_PORT` (Mailpit/MailHog); se non è in ascolto, il messaggio
resta come `preview` nell'outbox e viene comunque mostrato nel SOC. In
`SMS_MODE=simulated` e `VOICE_MODE=simulated` non parte nessun traffico
esterno: la notifica viene registrata nell'outbox. Il provider vocale live non
è incluso: per una chiamata reale serve un adattatore al fornitore.

Per far partire la demo con il file `.env`:

```bash
./scripts/demo.sh
```

### Simulazione allarme commerciale

Con la demo attiva, lo script invia un evento all'endpoint senza sessione:

```bash
./scripts/trigger_demo_alarm.sh
# targa o evento diversi:
VEHICLE_PLATE=DEMO-02 ALARM_TYPE=JAMMING ./scripts/trigger_demo_alarm.sh
```

Lo script legge `DEMO_TRIGGER_TOKEN` dal `.env` (o dall'ambiente) e, se presente,
lo invia come header `X-Demo-Token`. Script ed esempio leggono
`DEVICEHUB_API_PORT`, la stessa porta del server (3000 nella demo, 8010
dell'installazione). Per una chiamata manuale:

```bash
set -a; . ./.env; set +a
curl -sS -X POST "http://127.0.0.1:${DEVICEHUB_API_PORT:-3000}/api/v1/demo/trigger-alarm" \
  -H "Content-Type: application/json" \
  -H "X-Demo-Token: $DEMO_TRIGGER_TOKEN" \
  -d '{"plate":"DEMO-01","alarm_type":"SOS_PANIC_BUTTON","channels":["email","sms","voice_tts"]}'
```

Per ruotare il token basta modificare `DEMO_TRIGGER_TOKEN` nel `.env` e
riavviare il servizio: non viene scritto nei log né restituito dalle API.

`POST /api/v1/demo/trigger-alarm` accetta `plate`, `alarm_type`, `severity`,
`lat`, `lng`, `speed_kmh` e `channels` (`email`, `sms`, `voice_tts`). Crea un
allarme, lo mostra nel SOC e alimenta l'outbox. L'endpoint risponde `404` fuori
da `DEMO_MODE=true`, `401` se il token è configurato e non coincide, e non crea
mezzi o posizioni: la targa deve esistere nella flotta demo. Il token è
facoltativo, ma consigliato se la demo è raggiungibile da altri: senza token
l'endpoint resta aperto a chiunque conosca l'URL. Non va esposto in produzione.

## Struttura

```
devicehub/teltonika.py     Codec 8 / 8E: parser, encoder, CRC-16
devicehub/profiles.py      AVL ID -> campi di dominio, per modello
devicehub/store.py         SQLite (tenants, users, devices, positions, alerts) + ponte su vehicles
devicehub/ingest.py        server TCP asyncio (handshake IMEI, ACK, allarmi)
devicehub/notifications.py composizione email/SMS/voce e outbox dei canali
devicehub/api.py           API HTTP: dispositivi, comandi, SOC, accesso, trigger demo
devicehub/updates.py       verifica e installa i rilasci (manifest + SHA-256)
devicehub/version.py       versione corrente della piattaforma
devicehub/auth.py          password PBKDF2 e cookie di sessione firmati
devicehub/dashboard.py     dashboard VisionOS
devicehub/web.py           pagina di controllo e pagina di accesso
devicehub/codec12.py       comandi in discesa (blocco relè) e risposte
devicehub/provisioning.py  comandi SMS di configurazione
devicehub/simulator.py     device simulato per i test
scripts/load_test.py       generatore di carico per l'ingestione
scripts/verify_snapshot.py verifica offline di uno snapshot esportato
profiles/fmc150.json       profilo FMC150 con ID verificati sul wiki
```

## Aggiornamenti

La scheda **Sistema** (solo amministratore) mostra la versione installata e il
canale di rilascio. `Verifica aggiornamenti` legge il manifest configurato in
`DEVICEHUB_UPDATE_URL`:

```json
{
  "version": "1.4.2",
  "notes": "Correzioni e nuove funzioni",
  "url": "https://esempio.it/dist/devicehub-src-1.4.2.zip",
  "sha256": "<64 caratteri esadecimali>",
  "published_at": "2026-11-20"
}
```

`Aggiorna piattaforma` scarica il pacchetto, rifiuta checksum non corrispondenti
e percorsi non sicuri e compila in memoria i file Python del pacchetto: un file
non valido viene rifiutato prima di toccare l'installazione. Poi salva in
`updates/backups/<versione>-<data>/` i file che sta per sostituire, copia i nuovi
nella cartella dell'app (`.env`, database, `.git`, `updates/`, `artifacts/` e
`dist/` non vengono toccati) e riavvia il servizio. Il pacchetto deve contenere
la cartella `devicehub/`; per le demo offline il manifest e lo zip possono stare
su `file://`.

Se la copia fallisce a metà, i file precedenti vengono ripristinati
automaticamente, quelli nuovi rimossi e l'API risponde 400 senza riavviare: la
piattaforma resta alla versione in uso. Restano gli ultimi 5 backup, utilizzabili
per un ripristino manuale.

## Test

```bash
python3 -m pytest -q
```

I test usano i pacchetti di esempio pubblicati sul wiki Teltonika (Codec 8,
Codec 8E, multi-record) oltre a un end-to-end TCP con il simulatore.

## Capacità misurata (ingestione)

Misura con `scripts/load_test.py` su questa macchina di sviluppo (una vCPU
condivisa, SQLite in WAL, un solo processo Python, nessun TLS):

| Device connessi | Record/s | Latenza ACK p95 | CPU del servizio |
| --- | --- | --- | --- |
| 100 | ~97 | 54 ms | 13% |
| 300 | ~279 | 110 ms | 30% |
| 600 | ~536 | 274 ms | 58% |
| 300, 2 record per pacchetto | ~564 | 161 ms | 34% |

Ogni connessione apre il database in WAL con `synchronous=NORMAL` e un
`busy_timeout` di 30 secondi: una scrittura che trova il lock dell'ingestione o
di una richiesta HTTP attende invece di fallire con `database is locked`.

Nessun errore e nessun record perso: 12 831 posizioni scritte nelle quattro
prove. Una flotta reale di 10-50 mezzi con un record ogni 30 s sta sotto i
2 record/s, quindi una singola istanza ha un margine di due ordini di
grandezza. Il limite pratico arriva prima dalla latenza (a 600 connessioni il
p95 supera i 250 ms) che dal throughput. Misurare sul proprio VPS prima di
dimensionare: CPU e disco disponibili contano piu' del numero di device.

```bash
python3 scripts/load_test.py --port 5027 --devices 300 --records 1 --interval 1 --duration 10
```

## Stato e limiti noti

- Fatto: ingestione e dashboard nello stesso servizio, blocco motore con
  guardia (rifiuto se velocità > 1 km/h o ultimo fix GPS più vecchio di 2
  minuti) e audit con operatore, login a
  sessione, isolamento per cliente, allarmi jamming con presa in carico,
  cambio e reset password con blocco dopo N tentativi, stima ESG dal CAN.
- Manca: fascicolo documentale, video, logistica, tachigrafo, chat autisti,
  routing per tablet. Lo stile di guida (frenate/accelerazioni, punteggio,
  badge iButton) e' attivo. Le schede dichiarano il requisito
  invece di mostrare zeri. La verifica funzione per funzione e' in
  [docs/copertura-funzioni.md](docs/copertura-funzioni.md).
- L'ESG e' un indicatore, non un report certificato: la distanza e' misurata
  (odometro CAN), il consumo e' un'assunzione dichiarata
  (`DEVICEHUB_FUEL_L_PER_100KM`) e il fattore di emissione e' configurabile
  (`DEVICEHUB_CO2_KG_PER_LITER`). I valori di flotta si possono sovrascrivere
  per singolo mezzo: la scheda mostra se il dato e' "proprio" o "flotta".
- Gli snapshot mensili sono **firmati Ed25519**: la chiave privata resta sul
  server (`DEVICEHUB_SIGNING_KEY`), la pubblica si esporta per la verifica
  indipendente. La firma prova che il contenuto non e' cambiato dopo la
  chiusura; non dimostra che i dati ricevuti dal GPS fossero corretti.
- La chiave si puo' **ruotare** (`POST /esg/signing-key/rotate`): la privata
  precedente viene archiviata accanto alla nuova, e ogni snapshot conserva la
  chiave pubblica che lo ha firmato, quindi i report gia' chiusi restano
  verificabili. Consegnare al cliente la chiave pubblica usata, o l'impronta,
  per il controllo indipendente.
- L'invio del report per email usa **SMTP** (la casella che il cliente ha gia',
  nessun fornitore aggiuntivo) e resta spento finche' non sono impostati
  `DEVICEHUB_SMTP_HOST`, `DEVICEHUB_REPORT_FROM` e un destinatario: senza
  configurazione l'endpoint risponde 503 invece di simulare un invio.
- Con `DEVICEHUB_MONTHLY_AUTO=1` il servizio chiude da solo il mese precedente
  all'avvio e ogni giorno all'ora indicata: se lo snapshot esiste gia' non lo
  ricrea e non invia un secondo messaggio.
- **Taglio alimentazione**: il calo o la scomparsa della tensione esterna
  (AVL 66) con batteria interna ancora presente apre `UNPLUG`; soglie e
  attivazione sono configurabili con `DEVICEHUB_UNPLUG_*`.
- I link con token (`/r/{token}`) aprono un singolo report senza account, con
  scadenza e revoca. Nel database resta solo l'impronta SHA-256 del token:
  chi ha un backup non ottiene link utilizzabili. Il pannello "Link dei report"
  mostra stato e numero di aperture, e revoca un singolo link.
- Il report si scarica anche in **PDF** (`/esg/snapshots/{id}/pdf` o dal link
  con token) e viene allegato all'email: il cliente conserva il documento
  anche dopo la scadenza del link. Il PDF contiene totali, dettaglio per
  mezzo, grafico giornaliero e dati di verifica della firma.
- Nome, colore e logo del PDF sono **branding per cliente** (`tenant_branding`):
  il logo e' PNG o JPEG fino a 512 KB, salvato nel database. Il cliente senza
  branding usa il nome aziendale e il colore predefinito.
- Lo **sfondo** e' anch'esso per cliente, con tre stati espliciti
  (`tenant_branding.bg_mode`): `default` eredita `DEVICEHUB_CUSTOM_BG_IMAGE`,
  `custom` usa l'URL o l'immagine PNG/JPEG/WebP fino a 1,5 MB caricata dalla
  scheda Branding, `none` lascia il tema pulito e blocca il predefinito del
  server senza cancellare niente: il pulsante "Riattiva sfondo" rimette quello
  salvato senza un nuovo caricamento. L'ultimo salvataggio fra URL e file vince
  e sostituisce l'altro. L'immagine caricata e' servita da `/bg/...` solo con
  modalita' `custom` (404 con `none` o `default`), con `Cache-Control:
  private, max-age=0, must-revalidate` perche' nessun proxy conservi l'asset;
  l'`ETag` sul contenuto evita di ritrasmettere l'immagine a ogni refresh.
  La firma dell'URL dipende dal contenuto, quindi cambiare modalita' non
  invalida la cache del browser. Viene
  reso dal server nel `<body>` di dashboard, report e verifica del cliente,
  con un velo del tema che tiene il contrasto dei testi sopra 4.5:1 su
  qualunque foto.
- I link hanno un **limite di aperture** (`DEVICEHUB_LINK_MAX_USES`, 25 per
  impostazione) e un **blocco temporaneo** per indirizzo dopo troppi tentativi
  falliti (`DEVICEHUB_LINK_ATTEMPT_LIMIT` in `DEVICEHUB_LINK_BLOCK_MINUTES`).
  L'amministratore vede gli indirizzi bloccati nella scheda Utenti e li
  sblocca subito (`GET /links/blocked`, `POST /links/unblock`).
- La scheda Branding ha **Anteprima PDF**: apre il report con nome e colore
  scritti nei campi senza salvarli, cosi' si controlla il risultato prima di
  applicarlo a tutti i report del cliente.
- Le **zone geografiche** generano allarmi di ingresso e uscita nella scheda
  SOC. Le regole di notifica coprono velocita' e furto (movimento con
  accensione spenta); sono per cliente, con valori globali di riserva. Gli
  allarmi possono partire via email e SMS verso i destinatari del cliente
  (scheda Branding) e restano in dashboard finche' non vengono presi in carico;
  un intervallo minimo per mezzo, allarme e canale evita le raffiche.
- **Accensione fuori orario** (`IGNITION_OUT_OF_HOURS`, priorita' HIGH): la
  fascia lavorativa del cliente (`GET/POST /work-hours`, pannello Regole della
  scheda SOC) definisce giorni, orari e fuso con la stessa logica dei geofence.
  La transizione del motore da spento ad acceso (ignition `0 -> 1`) fuori fascia
  apre l'allarme, con deduplicazione attiva: resta un solo allarme aperto per
  mezzo finche' non viene preso in carico, quindi nessuna raffica di eventi.
  Senza configurazione la regola resta spenta; un cliente senza fascia propria
  eredita quella globale. Con la modalita' privacy attiva la regola non viene
  valutata, come velocita', furto e calo carburante: nessun allarme finche' il
  mezzo resta in privacy.
- Le righe del **SOC** mostrano Street View come fallback sicuro sull'ultima
  posizione nota del veicolo: la posizione dell'allarme vale per l'SOS, per gli
  altri tipi si usa quella del mezzo. In modalita' privacy GDPR il
  mascheramento e' automatico (coordinate NULL anche se l'ultima registrazione
  precede il cambio) e la riga dice "posizione oscurata (privacy)", senza
  generare link rotti.
- L'email in `local_preview` e' una consegna registrata come l'SMS simulato:
  entra nell'outbox, marca l'invio e rispetta il timer di cooldown
  `DEVICEHUB_ALERT_COOLDOWN_MINUTES` (default 10 minuti) senza accumulare lo
  stesso allarme a ogni record.
- La scheda **Manutenzione** pianifica interventi con scadenza a data o a
  chilometraggio, mostra lo stato (pianificato, scaduto, completato) e conserva
  chi ha chiuso l'intervento. Un controllo periodico apre `MAINTENANCE_DUE`
  per gli interventi scaduti; il promemoria email parte se `DEVICEHUB_ALERT_TO`
  e SMTP sono configurati.
- **Export CSV e XLSX** per flotta, posizioni, tragitti, manutenzione, allarmi
  e carburante (`GET /export/{dataset}?format=csv|xlsx`), con isolamento per
  cliente. Il CSV usa il punto e virgola e la codifica UTF-8 con BOM, per
  aprirsi in Excel con gli accenti corretti. `trips` accetta `hours` e
  restituisce inizio, fine, durata, km, velocita' massima e coordinate di
  partenza/arrivo; la dashboard lo scarica dalla scheda Mappa.
- **Modalita' privacy (GDPR)**: si attiva dal portale o da un ingresso DIN del
  tracker (`DEVICEHUB_PRIVACY_IO_ID`). Le posizioni continuano a registrare
  odometro e dati CAN, ma `latitude` e `longitude` restano NULL; geofence,
  velocita', furto e carburante non vengono valutati. Il pulsante SOS fa
  eccezione: la posizione finisce nel record dell'allarme, con la sua
  retention (`DEVICEHUB_ALERT_RETENTION_DAYS`).
- La scheda Mappa mostra **tragitti e soste** delle ultime ore (soglia 3 km/h,
  soste da 5 minuti) e ogni mezzo ha i link a Google Maps e Street View.
- **Costi e carburante**: km da odometro, litri stimati (consumo del mezzo o di
  flotta, ore di minimo), costo al prezzo configurato e cali di carburante a
  motore spento come possibile furto (`FUEL_THEFT`). E' una stima dichiarata.
- **SOS**: il pulsante del dispositivo (AVL ID configurabile) apre un allarme
  critico con la posizione. Gli allarmi possono essere inviati via email con
  `DEVICEHUB_ALERT_TO` e via SMS con `DEVICEHUB_SMS_URL`; senza canali restano
  solo in dashboard. I destinatari per cliente si impostano in Branding; i
  valori globali fanno da riserva. Gli invii SMS ritentano sugli errori di
  rete/5xx e le ricevute del gateway si raccolgono su `POST /sms/receipts`.
  L'intervallo anti-raffica parte solo dopo un invio riuscito: un errore non
  blocca il tentativo successivo. Nella preview in iframe il cookie di sessione
  diventa `SameSite=None; Secure`, altrimenti il browser non lo rimanda.
- **Sicurezza sul lavoro**: controlli registrati per mezzo (cinture, carico,
  documenti, dispositivi di protezione), riepilogo conformi/non conformi e
  allarme `SAFETY` per ogni non conformita. E' una registrazione operatore, non
  una lettura automatica del mezzo.
- **Mappa Google**: link a Google Maps 3D e Street View per ogni mezzo e
  pannello Google in embed; la mappa principale resta OpenStreetMap. L'embed
  e' stato verificato in browser (documento Google caricato); la mappa 3D
  navigabile dentro la dashboard richiederebbe una chiave API.
- La **manutenzione ricorrente** pianifica il prossimo intervento alla chiusura
  (ogni N km o N mesi) e un controllo periodico apre `MAINTENANCE_DUE` per gli
  interventi scaduti, con riepilogo email se configurato.
- I parametri ESG per mezzo hanno una **storia con decorrenza**
  (`vehicle_esg_params`): un cambio vale da quel momento in avanti, quindi un
  report di un mese chiuso non cambia se a giugno correggi un consumo. Per i
  giorni precedenti alla prima decorrenza valgono i valori di flotta.
- Il profilo FMC150 mappa gli ID verificati (carburante in litri e percentuale,
  temperatura, ore, km). L'ID CAN dei giri motore va confermato sul veicolo con
  `DEVICEHUB_LOG_IO=1`.
- Il vecchio `run_fleet_test.py` non e' stato importato: la dashboard e' stata
  ricostruita nel servizio nuovo, quindi l'import non serve piu' per andare
  avanti.
