# Deploy su un cloud Linux (VPS)

Procedura per portare la piattaforma su un server Linux pubblico, quello che
i GPS devono raggiungere sulla porta **5027**.

Per l'esecuzione operativa, con i controlli da fare dopo ogni passo, usare la
[checklist di deploy](deploy-checklist.md): questo documento spiega il perche',
la checklist dice cosa digitare e cosa deve rispondere.

Questa guida riguarda il *tuo* server di produzione. Il workspace di lavoro in
cui sviluppiamo e' un'altra macchina: si lavora li', si pubblica qui.

## 1. Requisiti

| Voce | Minimo | Note |
| --- | --- | --- |
| VPS | 1 vCPU, 1 GB RAM, 20 GB SSD | Ubuntu 24.04 LTS o Debian 12 |
| IP pubblico | statico | i tracker devono poterlo raggiungere |
| DNS | record A `gps.tuodominio.it` → IP | meglio dell'IP nudo: si puo' cambiare server senza toccare i GPS |
| Porte | 5027/tcp, 80, 443, 22 | 8010 **non** va aperta: resta su loopback |

I tracker Teltonika non usano TLS: la 5027 e' traffico binario in chiaro. Non
esiste un modo per metterla dietro HTTPS, quindi va esposta direttamente.

## 2. Preparazione del server

```bash
# utente di servizio senza login
sudo adduser --system --group --home /opt/devicehub devicehub

sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx
```

## 3. Codice e dipendenze

Dal workspace di sviluppo, il codice va trasferito sul server. Due strade:

```bash
# A) da repository git
sudo -u devicehub git clone <repo> /opt/devicehub

# B) da locale con SFTP (FileZilla), poi sul server:
sudo chown -R devicehub:devicehub /opt/devicehub
```

```bash
cd /opt/devicehub
sudo -u devicehub python3 -m venv .venv
sudo -u devicehub ./.venv/bin/pip install -r requirements.txt
```

## 4. Configurazione

```bash
sudo -u devicehub tee /opt/devicehub/.env >/dev/null <<'EOF'
DEVICEHUB_DB=/opt/devicehub/devicehub.db
DEVICEHUB_TCP_HOST=0.0.0.0
DEVICEHUB_TCP_PORT=5027
DEVICEHUB_API_HOST=127.0.0.1
DEVICEHUB_API_PORT=8010
DEVICEHUB_API_TOKEN=cambiare-questo-token
DEVICEHUB_ADMIN_PASSWORD=cambiare-questa-password
DEVICEHUB_ADMIN_TENANT=Cliente Uno
DEVICEHUB_SESSION_SECRET=generare-con-secrets
DEVICEHUB_SESSION_TTL_HOURS=12
DEVICEHUB_MAX_LOGIN_ATTEMPTS=5
DEVICEHUB_LOCK_MINUTES=15
DEVICEHUB_FUEL_L_PER_100KM=8.0
DEVICEHUB_CO2_KG_PER_LITER=2.65
DEVICEHUB_SIGNING_KEY=/opt/devicehub/esg-signing-key.pem
DEVICEHUB_PUBLIC_URL=https://api.tuodominio.it
DEVICEHUB_REPORT_FROM=report@tuodominio.it
DEVICEHUB_REPORT_TO=cliente@esempio.it
DEVICEHUB_SMTP_HOST=smtp.tuodominio.it
DEVICEHUB_SMTP_PORT=587
DEVICEHUB_SMTP_USER=report@tuodominio.it
DEVICEHUB_SMTP_PASSWORD=password-della-casella
DEVICEHUB_SMTP_STARTTLS=1
DEVICEHUB_MONTHLY_AUTO=1
DEVICEHUB_MONTHLY_HOUR=3
DEVICEHUB_MONTHLY_EMAIL=1
DEVICEHUB_LINK_HOURS=72
DEVICEHUB_LINK_MAX_USES=25
DEVICEHUB_LINK_ATTEMPT_LIMIT=10
DEVICEHUB_LINK_BLOCK_MINUTES=15
DEVICEHUB_PUBLIC_HOST=gps.tuodominio.it
DEVICEHUB_PUBLIC_PORT=5027
DEVICEHUB_APN=inserire.apn
DEVICEHUB_CODEC=142
DEVICEHUB_PROFILE=/opt/devicehub/profiles/fmc150.json
DEVICEHUB_REJECT_UNKNOWN=1
DEVICEHUB_LOG_IO=0
DEVICEHUB_IDLE_TIMEOUT=120
EOF
sudo chmod 600 /opt/devicehub/.env
sudo chown devicehub:devicehub /opt/devicehub/.env
```

Con `DEVICEHUB_REJECT_UNKNOWN=1` solo i dispositivi abilitati possono inviare
dati. Al primo collegamento il GPS viene comunque registrato come `pending`,
poi si abilita cosi' (con il token dell'API):

```bash
curl -s -X POST -H "X-Api-Key: <token>" \
  "https://api.tuodominio.it/devices/<IMEI>/activate?plate=AB123CD&model=FMC150"
```

Il token va generato, non scelto a mano:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 4.1 Accesso, ruoli e clienti

`DEVICEHUB_ADMIN_PASSWORD` serve **solo al primo avvio**: se nel database non
c'e' nessun utente, il servizio crea `admin` nel cliente indicato da
`DEVICEHUB_ADMIN_TENANT`. Va generata, non scelta, e cambiata subito.

**Senza `DEVICEHUB_ADMIN_PASSWORD` e senza utenti il servizio resta in
"primo avvio": chiunque raggiunga l'API entra come amministratore.** Su un
server pubblico e' un errore di configurazione, non una comodita': `/health`
lo dichiara con `"auth": "open"`.

- Accesso: `https://api.tuodominio.it/login`; cookie `dh_session` HttpOnly,
  SameSite=Lax, scadenza `DEVICEHUB_SESSION_TTL_HOURS` (default 12).
- Ruoli: `admin` (tutti i clienti, gestisce utenti), `manager` (solo il
  proprio cliente, abilita e comanda), `soc` (comanda e prende in carico gli
  allarmi), `viewer` (sola lettura).
- Un cliente nuovo con il suo utente, da amministratore:

  ```bash
  curl -s -X POST -H "X-Api-Key: <token>" -H "Content-Type: application/json" \
    -d '{"username":"mario","password":"<password-lunga>","role":"manager","tenant":"Trasporti Rossi"}' \
    "https://api.tuodominio.it/users"
  ```

- Dopo `DEVICEHUB_MAX_LOGIN_ATTEMPTS` tentativi falliti l'account si blocca
  per `DEVICEHUB_LOCK_MINUTES`. Reset da amministratore:
  `POST /users/<utente>/password` con `{"password":"..."}` nel body (obbliga
  il cambio al prossimo accesso); sblocco: `POST /users/<utente>/unlock`.
  Anche la creazione utente vuole il body JSON: la password non va mai
  nell'URL, che finisce nei log del server e dei proxy.
- Cambio password personale: `POST /auth/password` con `{"current":...,"new":...}`.
  Il cambio invalida i cookie gia' emessi sugli altri dispositivi.
- Disattivazione: `POST /users/<utente>/active?active=false` chiude subito le
  sessioni aperte (il controllo avviene a ogni richiesta). Non si puo'
  disattivare il proprio utente ne' l'ultimo amministratore attivo.
- `DEVICEHUB_SESSION_SECRET` va impostato a un valore casuale: senza, la
  chiave e' generata all'avvio e tutti gli accessi cadono a ogni riavvio.
- La chiave `X-Api-Key` resta per gli script e vale come un amministratore:
  non va mai messa nel browser di un cliente.
- Il cookie di sessione e' `HttpOnly` ma non `Secure`: diventa protetto perche'
  il traffico passa da HTTPS tramite nginx. Se un giorno l'API viene esposta
  in chiaro, il cookie viaggia in chiaro.

## 5. Servizio systemd

```bash
sudo cp deploy/devicehub.service /etc/systemd/system/devicehub.service
sudo systemctl daemon-reload
sudo systemctl enable --now devicehub
sudo systemctl status devicehub
journalctl -u devicehub -f
```

## 6. Reverse proxy e TLS per l'API

```bash
sudo cp deploy/nginx-devicehub.conf /etc/nginx/sites-available/devicehub
sudo ln -s /etc/nginx/sites-available/devicehub /etc/nginx/sites-enabled/
sudo sed -i 's/api.example.com/api.tuodominio.it/g' /etc/nginx/sites-available/devicehub
sudo nginx -t && sudo systemctl reload nginx
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.tuodominio.it
```

## 7. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp
sudo ufw allow 5027/tcp comment 'tracker Teltonika'
sudo ufw enable
sudo ufw status numbered
```

Verificare dall'esterno che la 5027 risponda (da un'altra macchina):

```bash
nc -vz gps.tuodominio.it 5027
```

## 8. Collaudo dal server

```bash
# la catena interna funziona?
sudo -u devicehub ./.venv/bin/python -m devicehub.simulator \
  --host 127.0.0.1 --port 5027 --packets 2

curl -s -H "X-Api-Key: <token>" https://api.tuodominio.it/devices
```

Poi con il GPS vero: comandi SMS generati da
`https://api.tuodominio.it/provisioning/<IMEI>/sms.txt?apn=<APN>`.

## 9. Backup

SQLite in modalita' WAL: copiare il file a caldo con `.backup`, non con `cp`.

```bash
sudo -u devicehub tee /opt/devicehub/backup.sh >/dev/null <<'EOF'
#!/bin/sh
set -eu
cd /opt/devicehub
sqlite3 devicehub.db ".backup '/opt/devicehub/backup/devicehub-$(date +%F).db'"
find /opt/devicehub/backup -name 'devicehub-*.db' -mtime +14 -delete
EOF
sudo -u devicehub chmod +x /opt/devicehub/backup.sh
sudo -u devicehub mkdir -p /opt/devicehub/backup

# ogni notte alle 3:15
( crontab -u devicehub -l 2>/dev/null; echo "15 3 * * * /opt/devicehub/backup.sh" ) | sudo crontab -u devicehub -
```

Serve il pacchetto `sqlite3` (`sudo apt install -y sqlite3`).

Nel backup va inclusa anche la chiave privata degli snapshot
(`esg-signing-key.pem`): senza, gli snapshot gia' firmati restano verificabili
solo con la chiave pubblica conservata a parte, ma non se ne possono firmare
nuovi con la stessa identita'.

```bash
sudo -u devicehub cp /opt/devicehub/esg-signing-key.pem /opt/devicehub/backup/
```

La chiave pubblica, da consegnare al cliente per la verifica indipendente:

```bash
curl -s -H "X-Api-Key: <token>" https://api.tuodominio.it/esg/public-key
```

Rotazione della chiave di firma (solo amministratore):

```bash
curl -s -X POST -H "X-Api-Key: <token>" https://api.tuodominio.it/esg/signing-key/rotate
curl -s -H "X-Api-Key: <token>" https://api.tuodominio.it/esg/signing-keys
```

La chiave precedente viene rinominata `esg-signing-key-<impronta>-<data>.pem`
accanto alla nuova: va conservata, e va conservata anche la chiave pubblica
corrispondente perche' gli snapshot gia' chiusi restano verificabili ma non
firmabili di nuovo con quella identita'.

## 10. Aggiornamenti

```bash
cd /opt/devicehub
sudo -u devicehub git pull
sudo -u devicehub ./.venv/bin/pip install -r requirements.txt
sudo systemctl restart devicehub
```

## Note operative

- Il database cresce con le posizioni: con 10 mezzi a un record ogni 30 s sono
  ~29 000 righe al giorno. Pianificare una pulizia o una partizione per mese
  quando si supera il milione di righe.
- `DEVICEHUB_POSITION_RETENTION_DAYS` e `DEVICEHUB_ALERT_RETENTION_DAYS` (default
  `0`, storico illimitato) cancellano a lotti con il servizio attivo. La
  cancellazione libera pagine interne a SQLite, non il file: per ridurre il
  disco serve `VACUUM` a servizio fermo, con spazio libero temporaneo pari
  circa alla dimensione del database. La procedura e' al passo 12 della
  checklist.
- L'indice `idx_positions_ts` viene creato all'avvio solo se manca. Su una
  tabella `positions` gia' grande va creato prima, a servizio fermo: la
  creazione blocca le scritture per tutta la sua durata.
- Un solo processo puo' essere in ascolto sulla 5027: non avviare due istanze
  ne' in sviluppo ne' in produzione.
- Se il server cambia IP, aggiornare il record DNS: i GPS continuano a
  funzionare senza riconfigurazione.
- Tenere l'orologio in UTC sul server: i timestamp dei record sono epoch ms.
- Gli allarmi jamming arrivano dall'AVL 249: il tracker li trasmette al primo
  contatto utile dopo l'interferenza, quindi un allarme puo' comparire in
  ritardo rispetto al disturbatore. `GET /alerts?open_only=true` e
  `POST /alerts/<id>/ack` sono gli endpoint della scheda SOC.
