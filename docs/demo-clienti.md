# Demo ai clienti

## 1. Preparazione (il giorno prima)

Avvio rapido (database demo separato, server e simulatore):

```bash
./scripts/demo.sh
```

Lo script stampa URL, credenziali, PID e log. Se preferisci il controllo
manuale, segui i passaggi sotto.

Usa **un database separato**, mai quello di produzione.

```bash
export DEVICEHUB_DB=/srv/devicehub/demo.db
export DEVICEHUB_ADMIN_PASSWORD='Demo-Cliente-2026'
export DEVICEHUB_COMPANY='Nome Cliente Demo'
export DEVICEHUB_PROFILE=profiles/fmc150.json
./.venv/bin/python -m devicehub
```

Verifica che risponda:

```bash
curl -s http://127.0.0.1:3000/health
```

Avvia il simulatore per avere un mezzo in movimento:

```bash
./.venv/bin/python -m devicehub.simulator --port 5098 --packets 0 --interval 3
```

Con `./scripts/demo.sh` la flotta è già attiva e associata al cliente Demo.
Nel setup manuale abilita l'IMEI dalla scheda **Censimento** e associa targa e
cliente.

### Checklist prima della demo

1. **Dashboard**: 3 mezzi, vista Trasporti pesanti, tabella con autisti
   (Mario Rossi/A1, Giulia Bianchi/A2, Luca Verdi/A3), rimorchi
   (TR-01 semirimorchio, TR-02 cassone) e form di assegnazione
   autista/rimorchio nella stessa scheda.
2. **Tutte le tab del dock**: aprono senza errori e il dock scorre fino a Utenti.
3. **Mappa**: modalità Google e pulsante “Mostra tracce”.
4. **Soluzioni**: 13 verticali, nessun duplicato Trasporti; chip con stato.
5. **Manager**: `demo.manager` vede solo i 3 mezzi Demo; Utenti è nascosto e
   `/users` risponde 403.
6. **Webhook**: `GET /webhooks/status` mostra `pending`, `overflow`, `delivered`,
   `failed`; a coda piena gli eventi vanno in overflow e rientrano senza perdite.

### Credenziali e ruoli da mostrare

| Utente | Ruolo | Cosa dimostra |
|---|---|---|
| `demo` | admin | tutto, clienti, utenti, audit |
| `demo.manager` | manager | solo flotta del cliente Demo |
| un manager del cliente | manager | isolamento dati e destinatari |

Non usare password reali: crea utenti demo e cancellali dopo la presentazione.

## 2. Scaletta di 12 minuti

1. **Dashboard** (2 min): KPI, mezzi online, grafici, aggiornamento ogni 15 s.
2. **Mappa** (2 min): posizione, tragitto, soste, link Google Maps/Street View.
3. **SOC** (2 min): allarme velocità o geofence, presa in carico, audit.
4. **Manutenzione** (1 min): scadenza a km, ricorrenza, intervento chiuso.
5. **Sicurezza** (1 min): controllo conforme/non conforme e allarme `SAFETY`.
6. **Guida** (2 min): eventi bruschi, autista con badge, punteggio.
   Mostra anche la **Dashboard verticale** (mezzi, km, in movimento, allarmi).
7. **Report/ESG** (1 min): PDF con branding, link protetto, verifica.
8. **Chiusura** (1 min): ruoli, isolamento per cliente, API.

## 3. Pacchetti e verticale

Apri **Soluzioni** e mostra la scelta per cliente: trasporti pesanti, bus,
rifiuti, corrieri, noleggio, macchine operatrici, sgombero neve, moto/bici,
imbarcazioni, persone, carrelli,
agricoltura o movimento terra; connettività 4G/2G/Svizzera; mappe OSM, Google o
svizzere. Dopo il salvataggio, la Dashboard mostra il badge del pacchetto e una
vista verticale con mezzi, online e km; la mappa usa il provider scelto quando
è disponibile.

Con **Mappe Google** la scheda Mappa apre automaticamente l'embed Google del
mezzo selezionato; tracce e marker restano su OpenStreetMap perché i tili
Google richiedono una chiave API. Con **Svizzera** la base usa SwissTopo.

Dichiara che connettività e mappe sono configurazione di servizio: non cambiano
SIM o hardware. Tachigrafo e dashcam restano segnaposto finché non c'è hardware.

Se hai configurato i webhook, mostra `GET /webhooks/status`: riporta coda
`pending/delivered/failed`. Gli eventi sono firmati HMAC e ritentati dal worker
anche dopo un riavvio.

## 4. Dimostrare il funzionamento offline

1. Apri la scheda **Guida**.
2. Attiva offline nelle DevTools del browser (Network → Offline).
3. Compila nome e badge di un autista e premi **Aggiungi**.
4. Compare il banner giallo “Offline: le nuove inserzioni restano sul dispositivo”.
5. Disattiva Offline: il banner sparisce e l'autista viene inviato automaticamente.
6. Ricarica la pagina e verifica che l'autista ci sia ancora.

Cosa dire: le inserzioni fatte senza rete restano nel browser e partono in ordine
al ritorno della connessione. Non vengono accodate le operazioni di login né i
caricamenti di file; se la connessione cade durante l'invio, l'operazione non
viene duplicata: va ripetuta.

## 5. Cosa dichiarare come limite

- I dati GPS dipendono dalla copertura e dalla configurazione del tracker.
- Gli SMS richiedono un gateway del cliente; nella demo restano in dashboard.
- Video, tachigrafo e app autista non sono inclusi.
- Consumi e costi sono stime dichiarate, non letture dirette.
- La demo non è un ambiente di produzione: usare un DB dedicato e credenziali demo.

## 6. Dopo la demo

- Conserva il database demo per la presentazione successiva.
- Ruota le password demo e disabilita gli utenti creati per la prova.
- Se il cliente chiede una prova autonoma, pubblica la demo dietro HTTPS con
  credenziali dedicate e scadenza, senza dati reali.

## 7. Versione stabile per lavorare

```bash
git add -A
git commit -m "Base demo stabile"
git tag -a v1.0-demo -m "Versione per demo clienti"
```

Parti sempre dal tag per le modifiche successive, tieni un branch per le prove e
non mescolare il database demo con quello reale.
