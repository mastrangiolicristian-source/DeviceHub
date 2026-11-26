# FMC150 — acquisto, cablaggio e collaudo

Riferimento per configurare il dispositivo scelto: **Teltonika FMC150**
(4G Cat 1, GNSS, Bluetooth LE, processore CAN integrato, 10–30 V DC).

Fonti: datasheet FMC150, quick manual (pinout) e wiki FMC150 AVL ID list.

## 1. Cosa comprare

| Voce | Perché | Note |
| --- | --- | --- |
| FMC150 **QKIB0** | 3 uscite digitali: 2 relè + sirena | la variante QJIB0 ha solo 2 DOUT |
| 2 × relè auto 12/24 V con zoccolo | blocco motore su due circuiti distinti | contatti adatti alla corrente del circuito interrotto |
| 2 × diodo 1N4007 | protezione del DOUT dalla extracorrente del relè | catodo verso +12 V, in parallelo alla bobina |
| 1 × sirena/buzzer 12 V | avviso locale anti-jammer | pilotata via relè, non diretta sul DOUT |
| Micro-SIM M2M dati | connettività del tracker | APN noto, traffico incluso, meglio se con IP statico non necessario |
| Portafusibili + fusibili | protezione linea | alimentazione e circuiti relè |
| Alimentatore 12 V da banco | configurazione e prova in laboratorio | 1–2 A sono sufficienti senza relè |
| Cavo micro-USB | configurazione con Configurator | più comodo del Bluetooth in laboratorio |

Non serve comprare LV-CAN200/ALL-CAN300: **FMC150 ha il CAN integrato**. Per
i veicoli pesanti valutare comunque la lista di compatibilità del programma
CAN prima dell'ordine.

Opzionali utili: iButton per l'identificazione autista (scenario Immobilizer),
sensore LLS analogico se il veicolo non espone il livello carburante su CAN.

## 2. Pinout (connettore 2×6)

| Pin | Nome | Uso |
| --- | --- | --- |
| 1 | VCC 10–30 V | positivo permanente, fusibile |
| 2 | DIN3 / AIN2 | ingresso configurabile |
| 3 | DIN2-N / AIN1 | ingresso con ground sense |
| 4 | DIN1 | **quadro/ignizione** |
| 5 | CAN2L | CAN secondaria |
| 6 | CAN1L | **CAN primaria (low)** |
| 7 | GND | massa |
| 8 | DOUT1 | relè 1 (open collector, verso massa) |
| 9 | DOUT2 | relè 2 (open collector, verso massa) |
| 10 | 1-WIRE DATA | iButton / sensori temperatura |
| 11 | CAN2H | CAN secondaria |
| 12 | CAN1H | **CAN primaria (high)** |

## 3. Cablaggio relè (doppio blocco)

```
        +12V (fusibile)
           │
           ├─────────── bobina relè 1 ─────── DOUT1 (pin 8)
           │                 │
           │              1N4007 (catodo a +12V)
           │
           └─────────── bobina relè 2 ─────── DOUT2 (pin 9)
                             │
                          1N4007
```

Il DOUT è un open collector: **chiude verso massa**, non fornisce +12 V. La
bobina va quindi tra positivo (fusibilato) e DOUT. Corrente massima
raccomandata 0,5 A per uscita: qualsiasi carico reale passa da relè.

Contatti del relè in serie al circuito da interrompere, in ordine di
preferenza:

1. **consenso all'avviamento** (filo del solenoidino dello starter): blocca
   l'avviamento ma non spegne un motore già in moto;
2. **alimentazione della pompa carburante** o elettrovalvola: più invasivo,
   spegne il motore anche in marcia — da usare solo con la logica di sicurezza
   del punto 5.

Due relè su due circuiti sono la ridondanza richiesta, ma vanno comandati
dallo stesso stato logico: se uno dei due non scatta, il blocco resta
parziale e va segnalato alla piattaforma.

## 4. Sirena anti-jammer

- Sirena 12 V pilotata da **DOUT3** (pin 3 sulla QKIB0) tramite relè.
- In Configurator abilitare lo scenario **Jamming detection** con azione su
  DOUT3: il device rileva la perdita anomala di segnale GNSS/GSM e attiva
  l'uscita.
- Verità da mettere in chiaro con il cliente: durante il jamming il tracker
  **non ha rete**, quindi l'allarme arriva alla piattaforma quando la
  connettività torna (i record restano in memoria: 128 MB, ~422 000 posizioni).
  La sirena è deterrente locale, non notifica in tempo reale.
- Evento disponibile anche come AVL ID **249** (jamming start/stop): la
  piattaforma lo riceve e apre l'alert.

## 5. Regole di sicurezza sul blocco motore

1. **Mai bloccare con veicolo in movimento.** Il blocco va attivato solo con
   velocità 0 e quadro spento; la piattaforma deve rifiutare il comando se
   l'ultima posizione ha `speed > 0`.
2. Preferire lo **scenario Immobilizer del device** (blocco automatico quando
   l'iButton autorizzato non è presente) al comando remoto: agisce in locale,
   anche senza rete.
3. Prevedere sempre un **ripristino manuale** (interruttore nascosto o
   sequenza autorizzata), altrimenti un guasto di rete lascia il mezzo fermo.
4. Installazione da elettrauto qualificato, con documentazione fotografica:
   serve per validare l'antifurto presso l'assicurazione.
5. Attenzione alle normative del veicolo (impianto frenante, ADAS): non
   interrompere linee diverse da avviamento e pompa carburante.

## 6. Configurazione del dispositivo

La piattaforma genera i comandi SMS (endpoint `/provisioning/{imei}/sms.txt`):

```
setparam 2001:<APN>
setparam 2004:<host>
setparam 2005:5027
setparam 2006:0          # TCP
setparam 113:1           # Codec 8 Extended
```

Poi, da Configurator (USB o Bluetooth):

1. selezionare il **programma CAN** del veicolo (marca/modello/anno);
2. in **CAN → Send data to server** abilitare gli elementi da ricevere:
   **84** carburante (L, ×0,1), **89** carburante (%), **87** km totali,
   **115** temperatura motore (×0,1), **102** ore motore (minuti);
3. verificare che DIN1 sia configurato come **ignizione**;
4. salvare e riavviare il device.

Senza il passo 2 il tracker invia solo posizione e IO elettrici: il
carburante non compare anche se il CAN è collegato.

## 7. Collaudo in 6 passi

```bash
# 1. server con log degli IO grezzi
DEVICEHUB_DB=./devicehub.db DEVICEHUB_LOG_IO=1 \
DEVICEHUB_PROFILE=profiles/fmc150.json python3 -m devicehub

# 2. verifica catena senza hardware
python3 -m devicehub.simulator --packets 3

# 3. stato dispositivi
curl -s http://127.0.0.1:8010/devices
```

4. Alimentare il tracker con l'alimentatore da banco, inserire la SIM,
   inviare gli SMS di configurazione e attendere la connessione al server.
5. Controllare nei log gli AVL ID ricevuti: devono comparire 84/89/87/115/102
   solo con CAN collegato e programma veicolo corretto. Se il carburante non
   arriva, il problema è nel programma CAN o nel passo 6.2, non nel decoder.
6. Provare i relè a banco (senza veicolo): comando di blocco → i due relè
   scattano, la sirena suona con lo scenario jamming.

## 8. Blocco motore remoto (implementato)

Il comando passa sulla connessione TCP già aperta dal device, in Codec 12:

```bash
# blocco (rifiutato se l'ultima posizione indica movimento)
curl -s -X POST -H "X-Api-Key: <token>" \
  "https://api.tuodominio.it/devices/<IMEI>/engine_block?block=true&requested_by=operatore"

# sblocco (sempre consentito)
curl -s -X POST -H "X-Api-Key: <token>" \
  "https://api.tuodominio.it/devices/<IMEI>/engine_block?block=false"

# chi ha comandato cosa
curl -s -H "X-Api-Key: <token>" \
  "https://api.tuodominio.it/devices/<IMEI>/commands"
```

Cosa fa il server:

- con quadro spento usa `setigndigout`, altrimenti `setdigout` (il device
  ignora `setdigout` a quadro spento: è il motivo per cui esiste la variante);
- con 3 uscite comanda `setdigout 11?`: relè 1 e 2 ON, sirena ignorata;
- rifiuta il blocco se la velocità supera 1 km/h, se non c'è una posizione o
  se l'ultimo fix GPS è più vecchio di 2 minuti;
- scrive ogni tentativo in `command_audit` (accettato o rifiutato, con motivo).

## 9. Cosa manca per chiudere il cerchio

- **Pulsante in interfaccia**: l'API c'è, la dashboard no.
- **Percentuale carburante** in tabella: l'ID 89 è già salvato in `io_json`,
  manca la colonna dedicata per il cruscotto.
- **RPM da CAN**: ID da confermare sul veicolo con `DEVICEHUB_LOG_IO=1`.
- **Scenario Immobilizer sul device** (iButton): blocco automatico in locale,
  da configurare in Configurator, indipendente dalla piattaforma.
