# Checklist di deploy

Da seguire in ordine su un VPS Ubuntu 24.04. Ogni passo ha il comando e il
controllo che deve passare prima di andare avanti. Dettagli e motivazioni:
[deploy-vps.md](deploy-vps.md).

Segnare le caselle man mano; se un controllo non passa, fermarsi li'.

## 0. Prima di toccare il server

- [ ] Dominio con record A `api.tuodominio.it` che punta all'IP del VPS (gia' propagato: `dig +short api.tuodominio.it`).
- [ ] Dominio con record A `gps.tuodominio.it` che punta allo stesso IP.
- [ ] IP statico e console del provider a portata di mano.
- [ ] Archivio del codice `devicehub-release.zip` (dalla cartella `dist/`), con il suo `devicehub-release.zip.sha256` per il controllo d'integrità: si genera **solo** con lo script standard, da un albero Git pulito.

```bash
./scripts/build-release.sh
```

Lo script rifiuta un albero sporco, verifica che l'archivio contenga `devicehub/__main__.py`, `requirements.txt`, `profiles/fmc150.json` e `deploy/devicehub.service` (se ne manca anche uno solo lo scarta e termina in errore), scrive il pacchetto con il suo `.sha256` e fallisce se trova `.env`, `.pem`, `.key`, database `.db`, `artifacts/` o `.venv/`. Il report finale stampa percorso, dimensione e hash.
- [ ] Password e chiavi generate, non scelte a mano:

```bash
python3 -c "import secrets; print('password:', secrets.token_urlsafe(24))"
python3 -c "import secrets; print('segreto:  ', secrets.token_urlsafe(32))"
python3 -c "import secrets; print('token:    ', secrets.token_urlsafe(32))"
```

- [ ] Valori salvati in un gestore di password, non in chat ne' nel repository.

## 1. Server base

```bash
sudo adduser --system --group --home /opt/devicehub devicehub
sudo apt update && sudo apt install -y python3 python3-venv python3-pip nginx sqlite3
```

- [ ] `python3 --version` mostra 3.10 o superiore.
- [ ] `systemctl is-active nginx` risponde `active`.

## 2. Codice e dipendenze

```bash
cd /opt/devicehub
# copiare qui l'archivio generato da ./scripts/build-release.sh (scp o SFTP), poi:
sudo -u devicehub unzip -o devicehub-release.zip -d /opt/devicehub
sudo chown -R devicehub:devicehub /opt/devicehub
sudo -u devicehub python3 -m venv .venv
sudo -u devicehub ./.venv/bin/pip install -r requirements.txt
```

- [ ] `./.venv/bin/python -c "import cryptography, fastapi; print('ok')"` stampa `ok`.
- [ ] `ls profiles/fmc150.json deploy/ nginx` (i file di supporto sono presenti).
- [ ] Nessun database di verifica temporaneo nell'installazione (`artifacts/verify.db`, `.db` di prova o copie locali): l'istanza di produzione deve partire solo dal DB definitivo indicato in `DEVICEHUB_DB`.

```bash
# deve elencare solo /opt/devicehub/devicehub.db (i backup stanno in backup/)
sudo -u devicehub find /opt/devicehub -maxdepth 2 -name '*.db' -not -path '*/backup/*'
```

- [ ] L'archivio distribuito non contiene `artifacts/`: se c'e', rimuoverlo prima del primo avvio (`rm -rf /opt/devicehub/artifacts`).
- [ ] L'archivio non contiene segreti ne' chiavi: il comando seguente non deve stampare nulla.

```bash
unzip -l /opt/devicehub/devicehub-release.zip | grep -E '\.env$|\.pem$|devicehub\.db$'
```

## 3. Configurazione

Lo schema di riferimento e' `.env.example`, incluso nell'archivio: si copia e si
compilano i segnaposto, senza inventare nomi di variabile. Il database e' un
percorso di file (`DEVICEHUB_DB`), non una URL: `sqlite:///...` non e' supportato;
con `DEVICEHUB_UPDATE_URL` vuoto gli aggiornamenti restano manuali (archivio zip).

```bash
cd /opt/devicehub
sudo -u devicehub cp .env.example .env
sudo -u devicehub nano .env
sudo chmod 600 .env
sudo chown devicehub:devicehub .env
```

- [ ] `sudo -u devicehub stat -c '%a %U' /opt/devicehub/.env` mostra `600 devicehub`.
- [ ] Le tre stringhe `sostituire-...` non compaiono piu': `grep -c sostituire /opt/devicehub/.env` risponde `0`.
- [ ] Anche gli altri segnaposto del template sono compilati: `grep -nE 'Nome del cliente|inserire\.apn|password-della-casella|tuodominio\.it' /opt/devicehub/.env` non stampa nulla.
- [ ] `grep -E '^(ENVIRONMENT|DEVICEHUB_DB|DEVICEHUB_API_TOKEN|DEVICEHUB_SESSION_SECRET|DEVICEHUB_SIGNING_KEY)=' /opt/devicehub/.env` elenca tutte e cinque le variabili.

## 4. Primo avvio e accesso

```bash
cd /opt/devicehub
sudo -u devicehub env $(grep -v '^#' .env | xargs) ./.venv/bin/python -m devicehub
```

In un secondo terminale:

```bash
curl -s http://127.0.0.1:8010/health
```

- [ ] Risponde `"auth": "required"` e `"users": 1` (se risponde `"open"`, `.env` non e' stato caricato).
- [ ] `sqlite3 /opt/devicehub/devicehub.db "select username, role from users"` mostra `admin|admin`.
- [ ] Login dal browser (dopo il passo 6): utente `admin`, password del `.env`, cambio password obbligatorio al primo accesso.
- [ ] Dopo il cambio password, `DEVICEHUB_ADMIN_PASSWORD` puo' restare nel `.env` senza effetto (l'utente esiste gia').

Fermare il processo manuale con `Ctrl+C` prima del passo 5.

## 5. Servizio systemd

```bash
sudo cp /opt/devicehub/deploy/devicehub.service /etc/systemd/system/devicehub.service
sudo systemctl daemon-reload
sudo systemctl enable --now devicehub
```

- [ ] `systemctl status devicehub` mostra `active (running)`.
- [ ] `journalctl -u devicehub -n 20 --no-pager` non mostra traceback.
- [ ] `curl -s http://127.0.0.1:8010/health` risponde `ok`.
- [ ] `ss -ltnp | grep 5027` mostra `0.0.0.0:5027`: i tracker esterni devono raggiungerlo.
- [ ] `ss -ltnp | grep 8010` mostra `127.0.0.1:8010`: l'API non e' esposta direttamente; l'accesso pubblico passa solo dal proxy al passo 6.
- [ ] `systemctl is-enabled devicehub` risponde `enabled` (riavvio automatico dopo crash o reboot).

## 6. HTTPS con nginx

```bash
sudo cp /opt/devicehub/deploy/nginx-devicehub.conf /etc/nginx/sites-available/devicehub
sudo ln -sf /etc/nginx/sites-available/devicehub /etc/nginx/sites-enabled/devicehub
sudo sed -i 's/api.example.com/api.tuodominio.it/g' /etc/nginx/sites-available/devicehub
sudo nginx -t && sudo systemctl reload nginx
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.tuodominio.it
```

- [ ] `curl -sI https://api.tuodominio.it/health | head -1` risponde `HTTP/2 200`.
- [ ] `curl -s https://api.tuodominio.it/health` dichiara `"auth": "required"`.
- [ ] Nel browser: `https://api.tuodominio.it/login` mostra la pagina di accesso, senza avvisi di certificato.
- [ ] Login riuscito e dashboard visibile.
- [ ] `curl -s https://api.tuodominio.it/verify` risponde 200 (pagina pubblica di verifica).

## 7. Firewall e porta dei GPS

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp
sudo ufw allow 5027/tcp comment 'tracker Teltonika'
sudo ufw enable
sudo ufw status numbered
```

Da un'altra macchina (non dal server):

```bash
nc -vz gps.tuodominio.it 5027
```

- [ ] La connessione si apre.
- [ ] `curl https://api.tuodominio.it:5027` **non** risponde HTTP: e' normale, la 5027 e' binaria.
- [ ] `sudo ufw status` non mostra la 8010 aperta.
- [ ] nginx inoltra `X-Real-IP` e `X-Forwarded-For`; il rate limit login usa quell'indirizzo (con la 8010 su loopback l'header non e' falsificabile dall'esterno).

## 8. Collaudo della catena

```bash
cd /opt/devicehub
sudo -u devicehub env $(grep -v '^#' .env | xargs) \
  ./.venv/bin/python -m devicehub.simulator --host 127.0.0.1 --port 5027 --packets 2
curl -s -H "X-Api-Key: <token>" https://api.tuodominio.it/devices
```

- [ ] Il simulatore riceve l'handshake e gli ACK.
- [ ] `/devices` elenca l'IMEI simulato con `"connected": true`.
- [ ] Nel browser la dashboard mostra il mezzo nella scheda Flotta.

## 9. Primo GPS reale

- [ ] Comandi SMS generati da `/provisioning/<IMEI>/sms.txt?apn=<APN>` e inviati al tracker.
- [ ] Il GPS compare in `/devices` come `pending`.
- [ ] Abilitazione con targa e modello:

```bash
curl -s -X POST -H "X-Api-Key: <token>" \
  "https://api.tuodominio.it/devices/<IMEI>/activate?plate=AB123CD&model=FMC150"
```

- [ ] Posizione e odometro visibili nella scheda Flotta.
- [ ] Blocco e sblocco motore provati a mezzo fermo, con voce nell'audit comandi.

## 10. Chiave di firma

- [ ] `ls -l /opt/devicehub/esg-signing-key.pem` mostra `-rw-------`.
- [ ] La chiave privata e' stata **generata su questo server** (al primo avvio o con `POST /esg/signing-key/rotate`) e non copiata dall'ambiente di prova: `DEVICEHUB_SIGNING_KEY` punta a un file che non esisteva nell'archivio distribuito.
- [ ] `DEVICEHUB_SESSION_SECRET` e' il segreto generato al passo 0, diverso da quello della demo: dopo un riavvio la sessione resta valida.
- [ ] Chiave privata inclusa nel backup (vedi passo 13).
- [ ] Chiave pubblica esportata e consegnata al cliente:

```bash
curl -s -H "X-Api-Key: <token>" https://api.tuodominio.it/esg/public-key
```

- [ ] Impronta annotata nel contratto o nell'ordine di servizio.

## 11. Snapshot, report e verifica

- [ ] Dalla scheda ESG: mese precedente, "Chiudi mese", snapshot creato con firma.
- [ ] Pulsante Report: pagina stampabile con i totali e la scritta "firma valida".
- [ ] Export del documento:

```bash
curl -s -H "X-Api-Key: <token>" \
  https://api.tuodominio.it/esg/snapshots/<id>/export > snapshot.json
python3 scripts/verify_snapshot.py snapshot.json --public-key chiave-cliente.pem
```

- [ ] Esito `VERIFICATO`, uscita `0`.
- [ ] Con un file modificato a mano: `NON VERIFICATO`, uscita `1`.
- [ ] Pagina `https://api.tuodominio.it/verify`: caricando lo stesso file, esito `VERIFICATO`.

## 11.1 Invio del report per email

- [ ] Casella mittente esistente e autorizzata a inviare (`DEVICEHUB_REPORT_FROM`).
- [ ] Credenziali SMTP nel `.env`, con `DEVICEHUB_SMTP_STARTTLS=1` sulla 587.
- [ ] `DEVICEHUB_PUBLIC_URL` punta all'indirizzo HTTPS pubblico, non a `localhost`.
- [ ] Invio di prova dalla scheda ESG, pulsante Invia, con il proprio indirizzo come destinatario.
- [ ] Email ricevuta: oggetto con il mese, link che apre il report, impronta e chiave.
- [ ] Il link apre il report solo dopo il login (i dati non sono pubblici).
- [ ] Riga `esg_report_sent` nell'audit amministrativo, con i destinatari.
- [ ] Senza configurazione, l'endpoint risponde 503 con il nome delle variabili mancanti: e' il comportamento atteso, non un errore da aggirare.

## 11.1.1 Canali di allarme

- [ ] `APP_NAME`, `ENVIRONMENT=demo` e `DEMO_MODE=true` presenti nel `.env` della demo.
- [ ] `DEMO_TRIGGER_TOKEN` presente nel `.env`: lo script demo lo usa come `X-Demo-Token`; senza header il trigger risponde `401`.
- [ ] `GET /health` mostra `app_name`, `environment` e `demo_mode` attesi.
- [ ] `GET /notifications` mostra i canali senza token: email `local_preview` o `live`, SMS `simulated` o `live`, voce `simulated` o spenta.
- [ ] Con Mailpit/MailHog su `127.0.0.1:1025`, un allarme di prova compare nella casella; senza server, la riga email resta `preview` nell'outbox SOC.
- [ ] Con `SMS_MODE=simulated` e `VOICE_MODE=simulated`, l'outbox SOC mostra una riga per canale, con testo e destinatari demo, senza traffico esterno.
- [ ] Con `SMS_MODE=live`, `DEVICEHUB_SMS_URL` e i destinatari sono configurati; un errore del gateway produce una riga `failed`, non un crash del servizio.
- [ ] Il provider vocale live non è configurato: la voce resta `simulated` finché non si integra un adattatore.

## 11.1.2 Passaggio ai canali reali prima del go-live

Con `SMTP_MODE=local_preview` e `SMS_MODE=simulated` i messaggi restano
nell'outbox: è corretto in demo, non in produzione.

- [ ] `GET /notifications` mostra email `live` e SMS `live`; se un canale resta spento è una scelta esplicita del cliente, annotata nell'ordine di servizio.
- [ ] `DEVICEHUB_SMTP_MODE=live`, host, porta e credenziali reali: un allarme di prova arriva nella casella del cliente e nell'outbox la riga è `sent`, non `preview`.
- [ ] `DEVICEHUB_SMS_MODE=live` con `DEVICEHUB_SMS_URL` e token del gateway: l'SMS di prova arriva e la riga è `sent`.
- [ ] `DEVICEHUB_ALERT_TO` e i destinatari per cliente sono indirizzi e numeri reali, non quelli demo.
- [ ] Con `DEVICEHUB_SMS_RECEIPT_TOKEN` impostato, `POST /sms/receipts` accetta una ricevuta del gateway e la si vede in `GET /sms/receipts`.
- [ ] Un invio fallito lascia la riga `failed` e non blocca il tentativo successivo (il cooldown parte solo dopo un invio riuscito).

## 11.2 Chiusura automatica e link

- [ ] `DEVICEHUB_MONTHLY_AUTO=1` e `DEVICEHUB_MONTHLY_HOUR=3` nel `.env`.
- [ ] Riavvio del servizio e riga nel log: `chiusura mensile all'avvio: {...}`.
- [ ] Secondo avvio: lo snapshot esiste, l'esito e' `exists` e non parte una seconda email.
- [ ] Link creato dalla scheda ESG (pulsante Link): si apre da un browser senza accesso.
- [ ] Il link scade all'ora indicata e si puo' revocare: dopo la revoca risponde 404.
- [ ] `DEVICEHUB_LINK_HOURS` allineato alla policy commerciale (default 72 ore).
- [ ] Pannello "Link dei report": link attivo con apertura contata, revoca singola che porta a 404.
- [ ] Pulsante PDF: file valido, con totali, tabella per mezzo e riquadro integrita.
- [ ] Email con allegato `report-<mese>.pdf` ricevuta e aperta.
- [ ] PDF apribile anche dal link con token, senza accesso.

## 11.3 Branding e protezione dei link

- [ ] Nome e colore salvati dal pannello Branding: il PDF cambia intestazione e accenti.
- [ ] Logo PNG/JPEG caricato (max 512 KB): compare nel PDF; "Rimuovi logo" lo toglie.
- [ ] Un cliente diverso ha branding proprio e non vede quello degli altri.
- [ ] Link creato con 1 apertura: il secondo accesso risponde 410 e la pagina dice "link esaurito".
- [ ] Con `DEVICEHUB_LINK_ATTEMPT_LIMIT=3`: tre token inventati dallo stesso indirizzo portano al blocco 429, che dura `DEVICEHUB_LINK_BLOCK_MINUTES`.
- [ ] Dopo un accesso valido il contatore dei tentativi falliti riparte da zero.
- [ ] "Anteprima PDF" apre il report con nome e colore non ancora salvati; il PDF salvato resta invariato.
- [ ] Un indirizzo bloccato compare nella scheda Utenti e "Sblocca" lo riammette subito.

## 11.4 Zone, notifiche, manutenzione, export

- [ ] Zona creata con raggio: uscita e ingresso generano un allarme nella scheda SOC.
- [ ] Regole velocità e furto salvate; un superamento apre un solo allarme finché resta aperto.
- [ ] Fasce lavorative configurate nella scheda SOC (pannello Regole: giorni, dalle/alle, fuso) e salvate: con il motore spento e poi acceso fuori fascia compare un solo `Accensione fuori orario`, senza duplicati finché l'allarme resta aperto.
- [ ] Senza fasce configurate (o con la regola disattivata) l'accensione non genera alcun allarme: è il default atteso.
- [ ] Riga SOC con Street View: il link apre Google Street View per un allarme del mezzo; con privacy attiva la riga mostra "posizione oscurata (privacy)" e nessun link.
- [ ] Email in `local_preview` ripetuta entro `DEVICEHUB_ALERT_COOLDOWN_MINUTES`: nell'outbox SOC resta una sola riga, come per SMS e voce simulati.
- [ ] Intervento con data passata risulta "scaduto"; "Completa" lo chiude e resta nello storico.
- [ ] CSV e XLSX scaricati per flotta, posizioni, tragitti, manutenzione e allarmi; il CSV si apre in Excel con gli accenti corretti.
- [ ] Pulsante "Tragitti XLSX" nella scheda Mappa: il file contiene inizio, fine, durata, km, velocita' massima e coordinate di partenza/arrivo.
- [ ] Badge manutenzione: rosso per scaduto, arancione entro 30 giorni o 1000 km, verde per pianificato.
- [ ] Un manager di un altro cliente non vede zone, interventi o righe di export del cliente estraneo.
- [ ] Modalita' privacy attivata dal portale (switch nella sidebar) o da ingresso DIN: nelle nuove posizioni `latitude`/`longitude` sono NULL, mentre odometro e CAN continuano a crescere.
- [ ] Con privacy attiva un SOS apre l'allarme con la posizione nel record; gli altri allarmi non inviano coordinate nelle notifiche.
- [ ] Con privacy attiva l'accensione fuori orario non viene valutata (come velocità, furto e calo carburante): nessun `Accensione fuori orario` finché il mezzo resta in privacy.

## 11.5 SMS, sicurezza e interfaccia

- [ ] Con `DEVICEHUB_SMS_URL` e `DEVICEHUB_SMS_TO` un allarme arriva al gateway; senza configurazione resta in dashboard senza errori bloccanti.
- [ ] Un controllo non conforme apre `SAFETY` nella scheda SOC e compare nel riepilogo.
- [ ] La scheda Sicurezza elenca i controlli del solo cliente dell'utente.
- [ ] Google Maps in embed e i link 3D/Street View si aprono dal mezzo selezionato.
- [ ] Tema chiaro su desktop e telefono: tabelle leggibili, dock scorrevole, nessun testo chiaro su fondo chiaro.

## 12. Manutenzione del database SQLite

L'indice su `positions(ts_ms)` viene creato all'avvio con `CREATE INDEX IF
NOT EXISTS`. Su un database gia' grande va creato a servizio fermo, altrimenti
il primo avvio blocca le scritture per tutta la durata della creazione.

```bash
sudo systemctl stop devicehub
sudo -u devicehub sqlite3 /opt/devicehub/devicehub.db \
  "CREATE INDEX IF NOT EXISTS idx_positions_ts ON positions (ts_ms);"
sudo -u devicehub sqlite3 /opt/devicehub/devicehub.db \
  "PRAGMA index_list(positions);"
sudo systemctl start devicehub
```

- [ ] `PRAGMA index_list(positions)` elenca `idx_positions_ts`.
- [ ] `/health` torna 200 dopo il riavvio.

La retention elimina righe e libera pagine interne a SQLite, ma **non riduce
il file**. Con `DEVICEHUB_POSITION_RETENTION_DAYS=0` (default) non cancella
nulla; `DEVICEHUB_ALERT_RETENTION_DAYS=0` fa lo stesso per gli allarmi e le
posizioni SOS. Per recuperare spazio su disco pianificare un `VACUUM` a
servizio fermo, dopo aver verificato lo spazio libero (serve circa la
dimensione del database, piu' il margine del filesystem):

```bash
sudo systemctl stop devicehub
sudo -u devicehub sqlite3 /opt/devicehub/devicehub.db \
  "PRAGMA wal_checkpoint(TRUNCATE); VACUUM;"
sudo systemctl start devicehub
```

- [ ] `du -h /opt/devicehub/devicehub.db` mostra la dimensione attesa dopo il `VACUUM`.
- [ ] Backup notturno gia' eseguito prima dell'operazione.

## 13. Backup e ripristino

```bash
sudo -u devicehub mkdir -p /opt/devicehub/backup
sudo -u devicehub tee /opt/devicehub/backup.sh >/dev/null <<'EOF'
#!/bin/sh
set -eu
cd /opt/devicehub
sqlite3 devicehub.db ".backup '/opt/devicehub/backup/devicehub-$(date +%F).db'"
cp esg-signing-key.pem /opt/devicehub/backup/
find /opt/devicehub/backup -name 'devicehub-*.db' -mtime +14 -delete
EOF
sudo -u devicehub chmod +x /opt/devicehub/backup.sh
( crontab -u devicehub -l 2>/dev/null; echo "15 3 * * * /opt/devicehub/backup.sh" ) | sudo crontab -u devicehub -
sudo -u devicehub /opt/devicehub/backup.sh
```

- [ ] `ls /opt/devicehub/backup` mostra un `.db` e `esg-signing-key.pem`.
- [ ] Prova di ripristino su una copia: aprire il backup con `sqlite3` e contare le posizioni, senza toccare il database in uso.
- [ ] Prova di verifica di uno snapshot usando la chiave pubblica del backup.

## 14. Monitoraggio

- [ ] `systemctl is-enabled devicehub` risponde `enabled`.
- [ ] Controllo periodico di `/health` (uptime robot o cron con curl) e allarme se non risponde 200.
- [ ] `df -h /opt` sotto il 70%: il database cresce con le posizioni.
- [ ] Rotazione dei log di systemd configurata dal sistema (`journalctl --disk-usage`).

## 15. Aggiornamento e ripristino

```bash
cd /opt/devicehub
sudo -u devicehub ./.venv/bin/pip install -r requirements.txt
sudo systemctl restart devicehub
```

- [ ] `/health` di nuovo 200 e login funzionante.
- [ ] Se qualcosa non torna: `sudo systemctl stop devicehub`, ripristinare il `.db` dal backup, riavviare, verificare `/health` e almeno uno snapshot.

## 16. Igiene finale

- [ ] `.env` mai nel repository ne' in chat.
- [ ] Chiave `X-Api-Key` solo negli script, mai nel browser di un cliente.
- [ ] Ruoli minimi: `viewer` per chi guarda, `manager` per chi comanda, `admin` solo dove serve.
- [ ] Clienti diversi con tenant diversi.
- [ ] Utente demo o di prova rimosso o disattivato.
- [ ] Password dell'amministratore cambiata e salvata nel gestore.
