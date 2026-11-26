# Inventario codice esistente (porzione 1)

Stato: ricevuta in chat la prima parte di `run_fleet_test.py`. Il testo si
interrompe **dentro `html_template`**, al campo Telegram del tab Branding
(`value="__TELEGRAM_WEBHOOK__">`). Mancano: chiusura del template, parti finali
della dashboard, `__main__` e la seconda app presente nel file.

## Stack

FastAPI + SQLAlchemy/SQLite (`mastranglee_fleet_visionos_ultimate.db`), JWT
HS256, passlib pbkdf2, frontend inline con Leaflet + Leaflet.draw + Chart.js.

## Tabelle (16)

| Tabella | Ruolo |
| --- | --- |
| `users` | utenti con ruolo e `tenant_company` |
| `tenant_config` | branding (nome, logo, telefono, webhook Telegram) |
| `module_toggles` | accensione moduli (Security, Eco-Driving, …) |
| `vehicles` | mezzo: IMEI (PK), targa, CAN, curfew, `engine_blocked` |
| `vehicle_documents` | solo metadati documenti (`file_reference` fisso) |
| `maintenance` | scadenze interventi |
| `alerts` | allarmi + `soc_dispatched` |
| `geofences` | cerchi e poligoni (coordinate JSON) |
| `cameras` | telecamere con `stream_url` |
| `pois` | punti di interesse |
| `fuel_logs` | rifornimenti |
| `tachograph` | file .DDD |
| `tachograph_remote_archive` | download OTA |
| `car_sharing` | prenotazioni |
| `pre_trip_inspections` | check-list pre-partenza |
| `anti_jamming_alerts` | eventi jamming |

## Endpoint

- **Auth**: `POST /api/auth/login`, `POST /api/auth/logout`, `POST /api/user/update_profile`
- **Dati flotta**: `GET /api/map_data`, `GET /api/history/route/{imei}`, `GET /api/history/export`
- **Comandi**: `POST /command/engine_lock/{imei}`
- **Mezzi**: `POST /vehicles/`, `PUT /vehicles/{imei}`, `DELETE /vehicles/{imei}`
- **Config**: `POST /api/tenant/update`, `POST /api/modules/toggle`
- **Geofence e POI**: `POST /geofence/add`, `POST /api/save_geofence`, `POST /api/poi/add`
- **Video**: `POST /camera/add`, `DELETE /camera/{cam_id}`
- **SOC**: `POST /api/soc/dispatch/{alert_id}`
- **Varie**: `POST /api/fuel/add`, `POST /api/documents/add`,
  `POST /api/security/anti_jamming_check`, `POST /api/tachograph/remote_download`
- **Driver PWA**: `POST /api/driver/set_trip_mode`, `/book_car`,
  `/pretrip_check`, `/panic_sos`
- **Pagine**: `GET /`, `GET /login`, `GET /driver`
- **Realtime**: `WS /ws`

## Frontend

12 schede nel dock: Dashboard, Mappa, Flotta, Censimento, ESG, Manutenzione,
Fascicolo, SOC, Video, Logistica, Tachigrafo, Branding.

## Difetti confermati in questa porzione

1. **`/command/engine_lock` non manda nulla al GPS**: cambia solo
   `vehicles.engine_blocked` nel database. Il blocco motore, oggi, è cosmetico.
2. **Logout**: il JS rimuove solo `localStorage.token`, ma `get_current_user`
   legge prima il cookie `access_token` → la sessione resta valida 2 ore.
3. **Modifica mezzo impossibile**: `registerVehicle()` fa sempre
   `POST /vehicles/`, quindi su un IMEI esistente risponde "IMEI già presente".
   `PUT /vehicles/{imei}` esiste ma non è chiamato da nessuna parte.
4. **Replay sempre vuoto**: `/api/history/route/{imei}` restituisce `points: []`.
5. **Curfew errata** se `start < end`: `hour >= start or hour < end` protegge la
   fascia sbagliata.
6. **500 su input non numerico**: `int(vehicle.get("curfew_start_hour"))` senza
   try; `plate` unica genera IntegrityError non gestita.
7. **WebSocket senza autenticazione** e `broadcast` chiamato da un thread con
   `asyncio.run(...)`: loop diverso da quello di uvicorn, eccezione inghiottita
   dal `except Exception: pass` → nessun `GPS_UPDATE` arriva ai client.
8. **`SECRET_KEY` hardcoded** nel sorgente.
9. **Password di default** precompilate nel login e suggerite nell'alert
   (`admin / mastranglee2026`).
10. **Cookie `httponly=False`**, nessun `SameSite`, nessuna protezione CSRF.
11. **Documenti senza file**: `add_document` salva solo metadati, il file
    caricato non viene mai letto (`UploadFile` importato e inutilizzato).
12. **Riduci a icona rotto** sulle card telecamera: `closest('.vision-window').id`
    è vuoto perché il contenitore non ha `id`.
13. **Grafici mai popolati**: `initCharts` crea dataset vuoti e nessuna fetch li
    riempie; `speed` è sempre `0.0` in `/api/map_data`.
14. **Isolamento tenant parziale**: solo su `map_data`, `/` e `engine_lock`,
    per confronto di stringhe libere (`tenant_company` senza tabella tenant).
15. **XSS**: valori dal DB interpolati in f-string HTML (targhe, nomi camera,
    descrizioni allarmi) senza escape.
16. **Import inutilizzati**: `requests`, `File`, `Form`, `UploadFile`,
    `Response`, `Header`.

## Da ricevere per completare

- Dal punto `value="__TELEGRAM_WEBHOOK__">` fino alla fine del file.
