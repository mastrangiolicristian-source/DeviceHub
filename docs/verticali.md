# Verticali e copertura funzioni

Catalogo esposto da `GET /solutions` (`vertical_details`) e mostrato nella
dashboard verticale. Ogni funzione ha uno stato:

- **Attivo** (`live`): disponibile con la telemetria attuale.
- **Parziale** (`partial`): disponibile con limiti o solo con il sensore giusto.
- **Hardware** (`hardware`): richiede tachigrafo, dashcam o sensori dedicati.
- **Da sviluppare** (`planned`): non implementato, nessun dato simulato.

## Verticali

| Verticale | Focus | Funzioni mancanti principali |
|---|---|---|
| Trasporti pesanti | km, costi, rimorchi, merci | tachigrafo, dashcam |
| Bus e trasporto persone | corse, passeggeri, scuolabus | passeggeri, scuolabus, tachigrafo |
| Rifiuti e igiene urbana | raccolta, cassoni | sensori cassone |
| Corrieri e logistica | consegne, merci | protezione merci, dashcam |
| Noleggio e car sharing | utilizzo, EV, antifurto | rental, auto elettriche |
| Macchine operatrici | utilizzo, manutenzione | lavorabilità calcestruzzo, dashcam |
| Sgombero neve | interventi, costi | tachigrafo, dashcam |
| Moto e bici | localizzazione, antifurto | — |
| Imbarcazioni | localizzazione in acqua | sensoristica dedicata |
| Persone e scuolabus | sicurezza persone | scuolabus, dispositivi indossabili |
| Carrelli elevatori | utilizzo, urti | sensori urto |
| Agricoltura | mezzi, manutenzione | sensoristica ISOBUS |
| Movimento terra | utilizzo, manutenzione | sensori idraulici |

## Funzioni core già attive

Tempo reale e storico, geofence e allarmi, blocco motore, autisti e badge,
manutenzione e costi, carburante con sensore, report PDF/ESG, export CSV/XLSX,
webhook firmati, API, mappe globali (OSM/Google embed/SwissTopo).

Tachigrafo, dashcam, passeggeri e sensoristica avanzata restano segnaposto
finché non c'è hardware: la piattaforma non inventa i relativi dati.
