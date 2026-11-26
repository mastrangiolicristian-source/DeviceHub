# Lacune e miglioramenti prioritari

Analisi sul codice al 12 novembre 2026. Le priorità tengono conto di cosa
sblocca una demo o un cliente, non solo della difficoltà tecnica.

## Lacune che contano in una trattativa

1. **Tachigrafo e infrazioni**: senza scarico `.DDD` non si copre il trasporto
   pesante. Richiede hardware/centralina e archivio a norma.
2. **Video e dashcam**: sono il principale differenziatore nelle gare su
   sicurezza. Richiede dispositivi e streaming.
3. **App autista e missioni**: consegne, chat e percorsi richiedono un'app.
   Oggi c'è solo la dashboard web.
4. **Report builder**: report ESG/PDF ci sono, ma il cliente non sceglie colonne,
   periodi e formati arbitrari.
5. **Sensori aggiuntivi con soglie**: temperatura e IO vengono letti, ma manca
   la configurazione per sensore (nome, soglia, isteresi, alert).
6. **Sottoutenze self-service**: l'isolamento per cliente è solido, ma non c'è
   un portale per far gestire autonomamente flotta e utenti.
7. **Webhook in uscita**: l'API è buona in ingresso, manca la notifica verso
   gestionali/CRM del cliente.
8. **Affidabilità e supporto**: mancano monitoraggio, backup automatici,
   ambiente di staging e procedura di ripristino documentata.

## Miglioramenti a alto impatto e basso costo

- **Coda offline** (fatto): inserzioni salvate nel browser e sincronizzate.
- **Allarmi guida nel SOC** (fatto): frenate/accelerazioni brusche.
- **Autisti per cliente** (fatto): badge e punteggio separati per tenant.
- **Filtri e ricerca** su flotte grandi: oggi le tabelle caricano tutto.
- **Notifiche push/web** per gli allarmi, senza dipendere da SMS.
- **Firma e verifica dei report** già presente: valorizzarla nella demo.
- **Backup automatico** del database e test di ripristino periodico.
- **Paginazione e indici** sulle posizioni storiche prima di flotte grandi.
- **Metriche di servizio**: latenza ingestione, dispositivi offline, errori API.

## Roadmap consigliata

1. Consolidamento: backup, staging, monitoraggio, test di carico.
2. Produttività cliente: filtri, export programmati, webhook.
3. Sensori configurabili e alert per soglia.
4. App autista/chat e missioni.
5. Tachigrafo e video solo con un partner hardware.

## Posizionamento

Non competere sulla quantità di moduli: competere su **isolamento per cliente,
tracciabilità delle operazioni, report verificabili e semplicità**. Sono punti
già solidi e difficili da copiare in una demo commerciale.
