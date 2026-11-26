# Soluzioni e servizi: cosa è attivo

Confronto con TOPFLY e Runic al 12 novembre 2026. Distingue ciò che il
software fa davvero da ciò che richiede hardware o un servizio esterno.

| Richiesta | Stato | Dove |
|---|---|---|
| Localizzazione in tempo reale | Attivo | Dashboard, mappa, aggiornamento 15 s |
| Storico e analisi percorso | Attivo | Replay, tragitti, soste, export |
| Geofence e notifiche | Attivo | SOC, regole, email/SMS |
| Report archiviabili | Attivo | PDF/ESG firmato, snapshot, export |
| Pacchetto 4G | Configurazione | Scheda Soluzioni; SIM/hardware del cliente |
| Pacchetto Svizzera e mappe globali | Configurazione | Scheda Soluzioni; OpenStreetMap è già globale |
| Carrelli elevatori | Verticale | Profilo cliente; telemetria ore/km e manutenzione |
| Agricoltura e movimento terra | Verticale | Profilo cliente; ore motore, km, geofence |
| Tachigrafo digitale | Non attivo | Scheda segnaposto: serve scarico `.DDD` |
| Controllo carburante | Attivo (stima) | Consumi, costi, cali a motore spento |
| Anti-jammer | Attivo | Allarme `JAMMING` dal dispositivo |
| Dashcam | Non attivo | Scheda Video segnaposto: serve hardware |
| Stile di guida autisti | Attivo | Scheda Guida, punteggio, SOC |
| Identificazione autista | Attivo con lettore | Badge iButton/RFID, `DEVICEHUB_DRIVER_IO_ID` |
| API e webhook | Parziale | API REST e chiave; webhook in uscita assente |
| App mobile | No | Solo portale web responsive |

## Runic: spunti utili

- **Semplicità di attivazione**: hardware OBD plug-in, SIM inclusa, prezzi chiari.
- **Webhook firmati con retry**: da aggiungere per integrazioni cliente.
- **Sandbox con dispositivi simulati**: abbiamo il simulatore, va reso un ambiente
  demo separato e documentato.
- **Verticali molto espliciti** (auto, furgoni, barche, attrezzature): noi abbiamo
  un profilo verticale per cliente, non dashboard dedicate.

## Altre soluzioni di mercato

- **Wialon**: ecosistema multi-dispositivo, white-label per partner, API estese.
  Spunto: catalogo hardware e programmi partner.
- **Samsara**: video AI, sensori, diagnostica e report di sicurezza.
  Spunto: eventi video collegati agli allarmi.
- **Webfleet**: tachigrafo, gestione EV, integrazioni OEM.
  Spunto: stato batteria/ricarica e conformità tachigrafica.
- **Motive**: dashcam e workflow autista/app.
  Spunto: checklist e chat autista.
- **Runic**: attivazione semplice, SIM inclusa, sandbox e webhook firmati.
  Spunto: esperienza di onboarding e self-service.

Nuove funzioni da valutare: stato batteria/EV, app autista con checklist,
integrazioni OEM, catalogo hardware, portale partner white-label, conformità
e certificazioni, report programmati via webhook.

## Cosa manca per essere competitivi

1. Webhook in uscita firmati e con retry: **fatto**, con coda persistente.
2. Dashboard dedicate per carrelli/agricoltura (ore, manutenzione, utilizzo):
   prima versione con KPI per verticale; servono colonne e flussi dedicati.
3. Tachigrafo e dashcam con partner hardware.
4. App autista e missioni.
5. Backup, monitoraggio e staging per l'esercizio.
