# Caricamento del codice esistente

Cosa caricare, cosa lasciare fuori, e cosa succede dopo.

## Dove

Nel **pannello Files del progetto** (a destra), non come allegato in chat: gli
allegati arrivano come testo estratto, i file caricati nel progetto arrivano
come file veri, eseguibili e modificabili.

## Formato

1. **Preferito**: uno zip della cartella di progetto. Se il pannello lo
   accetta, lo estraggo nel workspace con `unzip` (verificato disponibile).
2. In alternativa: i singoli file, mantenendo nomi e sottocartelle originali.

## Da includere

- Tutti i `.py` (compreso `run_fleet_test.py`)
- Template e frontend: `.html`, `.css`, `.js`
- Dipendenze: `requirements.txt`, `pyproject.toml`, `Pipfile`, `package.json`
- Configurazioni non segrete: `.json`, `.yaml`, `.toml`, `.ini`, `.sql`
- Documentazione e note eventuali (`.md`, `.txt`)

## Da NON includere

| Cosa | Perché |
| --- | --- |
| `.env`, file con chiavi o token | i segreti non entrano nel repository: si passano come variabili d'ambiente |
| Database con dati reali (`.db`) | targhe e posizioni sono dati personali: se serve, esportare solo lo schema |
| `.venv`, `node_modules`, `__pycache__`, `*.pyc` | ricostruibili, appesantiscono e non servono |
| Backup, log, file temporanei | rumore |

Se vuoi che parta dai dati reali, esporta solo la struttura:

```bash
sqlite3 mastranglee_fleet_visionos_ultimate.db .schema > schema.sql
```

## Cosa faccio appena arrivano

1. **Inventario**: elenco dei file con dimensioni, così vediamo subito se manca qualcosa.
2. **Integrità**: compilazione di tutti i `.py` e controllo dei riferimenti rotti.
3. **Mappa dei moduli**: chi importa chi, quali tabelle tocca, dove sono i duplicati.
4. **Unificazione**: rimozione della seconda app duplicata e del doppio database,
   dashboard collegata al servizio di ingestione, live update sul loop corretto.
5. **Verifica**: suite di test, avvio del servizio, pagina di controllo con i
   dati che arrivano dal simulatore.

## Prima di caricare

Copia di sicurezza della cartella originale sul PC: il caricamento non tocca
nulla sul tuo disco, ma è buona norma averla prima di qualunque refactoring.
