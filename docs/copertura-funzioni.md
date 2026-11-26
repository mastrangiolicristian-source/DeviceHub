# Copertura delle funzioni richieste

Verifica fatta sul codice del servizio al **11 novembre 2026**, non sul
materiale commerciale. Per ogni voce: cosa esiste davvero, cosa manca e come
controllarla. Le funzioni assenti non hanno dati finti: la scheda dichiara il
requisito.

Legenda: **Fatto** = usabile e coperto da test; **Parziale** = una parte
funziona, il resto no; **No** = non implementato.

| # | Funzione richiesta | Stato | Cosa c'è oggi | Cosa manca |
|---|---|---|---|---|
| 1 | Controllo mezzi in tempo reale | Fatto (web) | Ingestione TCP Teltonika, ultima posizione per IMEI, mappa con Google Maps/Street View, dashboard ogni 15 s, tragitti e soste recenti | Frequenza dipende dal tracker; nessun websocket/push e nessuna app mobile |
| 2 | Tracciati storici completi e replay | Fatto | Storico posizioni, Replay su mappa, tragitti e soste con durata/km/velocità massima; export delle posizioni in CSV/XLSX e del singolo giorno in GPX/KML | Il replay è visivo e non include gli allarmi nel tracciato |
| 3 | Notifiche e allarmi geografici | Fatto (software) | Zone con ingresso/uscita, velocità, furto e carburante, SOS, jamming, email e SMS con destinatari per cliente, presa in carico SOC | Serve un gateway SMS del cliente (nessun fornitore incluso); nessuna push; il furto è un'euristica |
| 4 | Blocco avviamento da remoto | Fatto (web) | Blocco/sblocco motore Codec 12 da dashboard e pagina controllo, guardia velocità > 1 km/h e fix GPS più vecchio di 2 minuti, audit operatore, ruoli | Solo browser, nessuna app mobile |
| 5 | Indicatori, costi e report | Parziale | Snapshot mensile firmato, PDF con branding, export JSON, verifica indipendente, email e link, CSV/XLSX di flotta, posizioni, manutenzione, allarmi e carburante; report costi per mese | Nessun builder di report personalizzati; consumi e costi sono stime dichiarate |
| 6 | Multiutenze e accesso di terze parti | Parziale | Quattro ruoli (admin, manager, soc, viewer), isolamento per cliente, creazione utenti, blocco, audit | I permessi sono per ruolo, non per singola funzione; nessun portale self-service per sottoutenze |
| 7 | Integrazione con altri software via API | Fatto | API REST JSON con sessione o `X-Api-Key`, OpenAPI su `/docs` | Nessun webhook in uscita |
| 8 | Controllo centralina veicolo | Parziale | Carburante, temperatura, ore motore, km CAN letti e mostrati; RPM previsto dal profilo | L'ID CAN dei giri motore va confermato sul veicolo (`DEVICEHUB_LOG_IO=1`) |
| 9 | Scarico tachigrafo da remoto | No | Scheda segnaposto | Integrazione tachigrafo e archiviazione a norma |
| 10 | Analisi tachigrafiche | No | Scheda segnaposto | Lettura file conducente, analisi, lettere di richiamo |
| 11 | Gestione scadenze manutentive | Fatto (web) | Interventi con scadenza a data o km, ricorrenza (km/mesi), stato, storico, allarme `MAINTENANCE_DUE` e riepilogo email | Nessuna pianificazione per singolo componente (es. gomme anteriori) |
| 12 | Stile di guida e chat autisti | Parziale | Scheda Guida con frenate/accelerazioni dalle posizioni, punteggio per autista e anagrafica badge iButton (`GET/POST /drivers`, `GET /driving`) | Manca il canale chat con l'autista; il curving richiede accelerometro laterale |
| 13 | Tablet autisti e percorsi | No | Scheda Logistica segnaposto | Calcolo percorsi per sagoma, app autista, invio su telefono/tablet |
| 14 | Centrale operativa 24/7 | No (servizio) | Allarmi e presa in carico nel software | È un servizio organizzativo: turni, reperibilità, contratto |
| 15 | Video control room | No | Scheda segnaposto | Stream telecamere e registrazione |
| 16 | Fascicolo documentale | No | Scheda segnaposto | Storage file per tenant, scadenze documenti |
| 17 | Sicurezza sul lavoro | Fatto (web) | Controlli per mezzo con esito, note e operatore; riepilogo conformi/non conformi; allarme `SAFETY` e notifica email/SMS | E' una registrazione operatore, non una verifica automatica delle procedure |

## Funzioni legate all'hardware

Queste voci non si possono completare solo con il software: dipendono dal
cablaggio e dagli accessori installati sul mezzo. Il servizio le supporta solo
nella parte disponibile.

- **Immobilizer**: richiede un relè di avviamento dedicato e, per
  l'identificazione del conducente, un lettore iButton/RFID. Oggi esiste il
  blocco da remoto via DOUT, non l'immobilizer autonomo.
- **Sirena anti-jammer e antisollevamento**: sono accessori fisici. Il servizio
  rileva il jamming e il movimento a motore spento, ma non pilota la sirena;
  l'uscita DOUT va cablata e configurata sul dispositivo.
- **Mappa Google 3D/Street View**: i link per mezzo sono presenti e il
  pannello Google in embed è stato verificato in browser; i tili Google 3D
  incorporati richiedono una chiave API e un provider a pagamento.
- **SMS**: invio via gateway HTTP generico configurato dal cliente
  (`DEVICEHUB_SMS_URL`), con retry su errori di rete/5xx e webhook delle
  ricevute (`POST /sms/receipts`). Non è incluso un fornitore né un credito.
  I destinatari sono per cliente (fallback globale) e l'invio è limitato da un
  intervallo per mezzo, allarme e canale. Con `SMS_MODE=simulated` il messaggio
  viene registrato nell'outbox senza traffico esterno.
- **Voce**: il canale è predisposto per le emergenze massime (SOS, jamming,
  taglio alimentazione, furto) con `VOICE_ENABLED=true`. In demo
  `VOICE_MODE=simulated` registra testo e destinatari nell'outbox; non è
  incluso un adattatore vocale live verso Twilio o altri provider.

## Dettaglio delle voci mancanti

- **Tachigrafo (9, 10)**: richiede un dispositivo/centralina che esponga lo
  scarico del tachigrafo e un archivio conforme. Il servizio oggi riceve solo
  telemetria AVL: nessun file `.DDD`, nessuna firma o conservazione a norma.
- **Manutenzione (11)**: la tabella e la scadenza esistono; mancano i
  promemoria automatici e la pianificazione ricorrente (es. ogni 20.000 km).
- **Stile di guida (12)**: il dispositivo ha un accelerometro, ma il servizio
  non ne ricava eventi. Mancano soglie, punteggio per autista e report.
- **Chat autisti (12)**: richiede un'app lato autista e la consegna dei
  messaggi; non c'è alcun canale nel servizio.
- **Percorsi e tablet (13)**: servono un motore di routing con vincoli di
  sagoma, un'app autista e l'invio. Oggi non c'è nulla oltre la scheda.
- **Notifiche (3)**: geofence (cerchi, poligoni, linee, fasce orarie), velocità,
  furto e taglio alimentazione sono attivi e possono partire
  via email, SMS e voce verso i destinatari del cliente, con un intervallo
  minimo per canale; l'outbox in SOC mostra stato e testo di ogni invio, anche
  simulato. Non c'è push né invio per singolo destinatario oltre alla lista del
  cliente. L'allarme vive anche nella dashboard finché non viene preso in
  carico. Il furto è un'euristica: movimento sopra soglia con accensione spenta.
- **Report (5)**: il PDF è completo per l'ESG mensile, ma non è un builder:
  non si scelgono colonne, periodi arbitrari o formati oltre PDF e JSON.
- **Multiutenze (6)**: l'isolamento per cliente è reale e testato; manca la
  personalizzazione fine dei diritti e l'accesso di terze parti con permessi
  limitati a singole schede.
- **Posizione in tempo reale (1)**: la dashboard si aggiorna ogni 15 secondi,
  ma la frequenza dei dati è quella configurata sul tracker; non c'è una
  spinta in tempo reale al browser.

## Come verificare

```bash
# suite completa
./.venv/bin/python -m pytest -q

# posizione e storico (con sessione)
curl -s -b cookie.txt http://127.0.0.1:3000/devices | head
curl -s -b cookie.txt "http://127.0.0.1:3000/positions/352093086403655?hours=24" | head

# blocco motore e audit
curl -s -b cookie.txt -X POST "http://127.0.0.1:3000/devices/352093086403655/engine_block" | head
curl -s -b cookie.txt http://127.0.0.1:3000/audit/commands | head

# branding: anteprima senza salvare, poi PDF salvato
curl -s -b cookie.txt -o /tmp/anteprima.pdf \
  "http://127.0.0.1:3000/branding/preview.pdf?display_name=Prova&primary_color=%23b91c1c"
curl -s -b cookie.txt -o /tmp/report.pdf http://127.0.0.1:3000/esg/snapshots/1/pdf

# link: limite aperture e blocco/sblocco
curl -s -b cookie.txt -X POST "http://127.0.0.1:3000/esg/snapshots/1/link?max_uses=1"
curl -s -b cookie.txt http://127.0.0.1:3000/links/blocked
```

Le voci **No** non hanno endpoint: la verifica è l'assenza della scheda
funzionante e la nota nella dashboard.
