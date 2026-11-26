# Confronto con TOPFLY

Confronto fatto il 12 novembre 2026 sul sito pubblico
topflysolutions.com e sul codice di questa piattaforma.

| Area TOPFLY | Qui | Nota |
|---|---|---|
| Tempo reale e storico, replay | Fatto | Dashboard 15 s, mappa, replay, export |
| Geofence e notifiche | Fatto | Email/SMS per cliente, throttle |
| Blocco motore | Fatto | Codec 12, guardia velocità, audit |
| Carburante e furti | Fatto (stima) | Calo a motore spento, costi |
| Manutenzione e scadenze | Fatto | Data/km, ricorrenza, allarme |
| Report, PDF, ESG | Fatto | PDF firmato, branding, export |
| API e integrazioni | Parziale | REST e chiave API; nessun webhook in uscita |
| **Stile di guida** | **Fatto (nuovo)** | Frenate/accelerazioni dalle posizioni, punteggio |
| **Identificazione autista** | **Parziale (nuovo)** | Badge iButton/RFID, anagrafica autisti; richiede lettore |
| Tachigrafo e infrazioni | No | Richiede scarico `.DDD` e centralina |
| Dashcam e video control room | No | Richiede hardware video |
| Missioni e app autista | No | Richiede app e canale verso il conducente |
| Percorsi con vincoli di sagoma | No | Richiede motore di routing dedicato |
| Sensoristica aggiuntiva | Parziale | Temperatura e IO letti; soglie/alert per sensore da configurare |
| Sottoutenze e portale terze parti | Parziale | Tenant e ruoli; manca self-service |
| Centrale 24/7 | No (servizio) | È un servizio organizzativo, non software |

## Cosa è stato integrato

- Tabella `drivers` con nome e badge, per cliente.
- Endpoint `GET/POST /drivers` e `GET /driving?hours=`.
- Calcolo di `HARSH_ACCEL` e `HARSH_BRAKE` dalle posizioni, con soglie
  `DEVICEHUB_HARSH_ACCEL_KMH_S` (default 8) e
  `DEVICEHUB_HARSH_BRAKE_KMH_S` (default 10).
- Punteggio 0-100 per autista: -3 per accelerazione, -5 per frenata.
- Scheda **Guida** con KPI, tabella eventi e anagrafica autisti.
- `DEVICEHUB_DRIVER_IO_ID` seleziona l'IO del badge (0 = disabilitato).
- La scansione è limitata alle ultime 168 ore e a 5000 punti per richiesta
  (`?points=`), così non carica tutto lo storico a ogni apertura.
- Frenate e accelerazioni brusche aprono un allarme `HARSH_BRAKE` /
  `HARSH_ACCEL` nel SOC e seguono le notifiche email/SMS configurate.

## Limiti

- Gli eventi dipendono dalla frequenza e dalla qualità della velocità GPS:
  con intervalli oltre 15 secondi non vengono calcolati.
- Il curving non è calcolato: servirebbe l'accelerometro laterale, non
  presente nei record AVL standard.
- Senza lettore iButton collegato e `DEVICEHUB_DRIVER_IO_ID` configurato,
  gli eventi restano senza autista.
- Video, tachigrafo, app autista e routing non sono stati integrati: sono
  dipendenze hardware o servizi esterni, non funzioni software mancanti.
