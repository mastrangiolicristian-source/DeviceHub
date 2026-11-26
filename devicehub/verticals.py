"""Catalogo dei verticali e stato reale delle funzioni.

Status:
  live     = disponibile con la telemetria attuale
  partial  = disponibile con limiti o solo se il dispositivo invia il dato
  hardware = richiede hardware/sensore dedicato
  planned  = non implementato
"""

from __future__ import annotations

LIVE = "live"
PARTIAL = "partial"
HARDWARE = "hardware"
PLANNED = "planned"

STATUS_LABELS = {
    LIVE: "Attivo",
    PARTIAL: "Parziale",
    HARDWARE: "Hardware",
    PLANNED: "Da sviluppare",
}


def f(fid: str, label: str, status: str, note: str = "") -> dict:
    if status == PARTIAL and not note:
        note = "Disponibile solo con il dato o il sensore corrispondente."
    return {"id": fid, "label": label, "status": status, "note": note}


_CORE = [
    f("realtime", "Tempo reale e storico", LIVE),
    f(
        "diagnostics",
        "Centralina e anomalie",
        PARTIAL,
        "Mostra gli allarmi e i codici inviati dal dispositivo.",
    ),
    f(
        "tachograph",
        "Tachigrafo e infrazioni",
        HARDWARE,
        "Richiede tachigrafo digitale integrato.",
    ),
    f("fuel", "Carburante", PARTIAL, "Con sensore carburante o lettura CAN."),
    f("drivers", "Autisti", LIVE),
    f("missions", "Missioni", PARTIAL, "Basate su geofence e storico."),
    f("costs", "Costi e manutenzione", LIVE),
    f(
        "alarm",
        "Antifurto completo",
        PARTIAL,
        "Blocco motore, SOS, geofence e taglio alimentazione; manca la sirena.",
    ),
    f("maps", "Connessioni e mappe globali", LIVE),
    f(
        "support",
        "Assistenza",
        PARTIAL,
        "Contatti e diagnostica, senza ticketing/SLA integrato.",
    ),
    f(
        "dashcam",
        "Dashcam intelligenti",
        HARDWARE,
        "Richiede dashcam compatibile.",
    ),
]

VERTICALS = [
    {
        "id": "trasporti_pesanti",
        "label": "Trasporti pesanti",
        "note": "Km, movimenti, allarmi e costi della flotta pesante",
        "functions": _CORE + [
            f("trailers", "Cassoni e rimorchi", PARTIAL, "Con sensori su rimorchio."),
            f("savings", "Risparmi e incentivi", PARTIAL, "Punteggio di guida."),
            f("safety", "Sicurezza mezzi e persone", PARTIAL),
            f("cargo", "Protezione merci", PARTIAL, "Con sensori porte/portelloni."),
            f("sensors", "Sensoristica aggiuntiva", PARTIAL),
            f("integration", "Integrazione e condivisione", LIVE, "API e webhook."),
        ],
    },
    {
        "id": "bus",
        "label": "Bus e trasporto persone",
        "note": "Servizio, passeggeri, corse e sicurezza",
        "functions": _CORE + [
            f("passengers", "Passeggeri", PLANNED),
            f("trips", "Corse e fermate", PARTIAL, "Fermate da geofence."),
            f("school", "Scuolabus sicuro", PLANNED),
            f("safety", "Sicurezza mezzi e persone", PARTIAL),
            f("integration", "Integrazione e condivisione", LIVE),
        ],
    },
    {
        "id": "rifiuti",
        "label": "Rifiuti e igiene urbana",
        "note": "Raccolta, cassoni e percorsi",
        "functions": _CORE + [
            f("bins", "Cassoni e rimorchi", PARTIAL, "Con sensori di carico."),
            f("savings", "Risparmi e incentivi", PARTIAL),
            f("sensors", "Sensoristica aggiuntiva", PARTIAL),
            f("integration", "Integrazione e condivisione", LIVE),
        ],
    },
    {
        "id": "corrieri",
        "label": "Corrieri e logistica",
        "note": "Consegne, merci e sicurezza",
        "functions": _CORE + [
            f("safety", "Sicurezza mezzi e persone", PARTIAL),
            f("cargo", "Protezione merci", PARTIAL),
            f("sensors", "Sensoristica aggiuntiva", PARTIAL),
            f("integration", "Integrazione e condivisione", LIVE),
        ],
    },
    {
        "id": "noleggio",
        "label": "Noleggio e car sharing",
        "note": "Utilizzo, costi, antifurto e flotte elettriche",
        "functions": [
            f("realtime", "Tempo reale e storico", LIVE),
            f("diagnostics", "Centralina e anomalie", PARTIAL),
            f("fuel", "Carburante", PARTIAL),
            f("costs", "Costi e manutenzione", LIVE),
            f("alarm", "Antifurto completo", LIVE),
            f("maps", "Connessioni e mappe globali", LIVE),
            f("integration", "Integrazione e condivisione", LIVE),
            f("support", "Assistenza", LIVE),
            f("rental", "Car rental / car sharing", PLANNED),
            f("ev", "Auto elettriche", PLANNED),
        ],
    },
    {
        "id": "macchine_operatrici",
        "label": "Macchine operatrici",
        "note": "Utilizzo, manutenzione e sensori",
        "functions": [
            f("realtime", "Tempo reale e storico", LIVE),
            f("diagnostics", "Centralina e anomalie", PARTIAL),
            f("fuel", "Carburante", PARTIAL),
            f("drivers", "Autisti", LIVE),
            f("costs", "Costi e manutenzione", LIVE),
            f("alarm", "Antifurto completo", LIVE),
            f("maps", "Connessioni e mappe globali", LIVE),
            f("savings", "Risparmi e incentivi", PARTIAL),
            f("integration", "Integrazione e condivisione", LIVE),
            f("support", "Assistenza", LIVE),
            f("dashcam", "Dashcam intelligenti", HARDWARE),
            f("concrete", "Lavorabilità calcestruzzo", PLANNED),
        ],
    },
    {
        "id": "sgombero_neve",
        "label": "Sgombero neve",
        "note": "Interventi, mezzi e costi",
        "functions": _CORE + [
            f("savings", "Risparmi e incentivi", PARTIAL),
            f("integration", "Integrazione e condivisione", LIVE),
        ],
    },
    {
        "id": "moto_bici",
        "label": "Moto e bici",
        "note": "Localizzazione, antifurto e manutenzione",
        "functions": [
            f("realtime", "Tempo reale e storico", LIVE),
            f("costs", "Costi e manutenzione", LIVE),
            f("alarm", "Antifurto completo", LIVE),
            f("maps", "Connessioni e mappe globali", LIVE),
            f("integration", "Integrazione e condivisione", LIVE),
            f("support", "Assistenza", LIVE),
        ],
    },
    {
        "id": "imbarcazioni",
        "label": "Imbarcazioni",
        "note": "Localizzazione e antifurto in acqua",
        "functions": [
            f("realtime", "Tempo reale e storico", LIVE),
            f("alarm", "Antifurto completo", LIVE),
            f("maps", "Connessioni e mappe globali", LIVE),
            f("sensors", "Sensoristica aggiuntiva", PARTIAL),
            f("integration", "Integrazione e condivisione", LIVE),
            f("support", "Assistenza", LIVE),
        ],
    },
    {
        "id": "persone",
        "label": "Persone e scuolabus",
        "note": "Sicurezza persone e dispositivi indossabili",
        "functions": [
            f("realtime", "Tempo reale e storico", LIVE),
            f("maps", "Connessioni e mappe globali", LIVE),
            f("school", "Scuolabus sicuro", PLANNED),
            f("safety", "Sicurezza mezzi e persone", PARTIAL),
            f("sensors", "Sensoristica aggiuntiva", PARTIAL),
            f("integration", "Integrazione e condivisione", LIVE),
            f("support", "Assistenza", LIVE),
        ],
    },
    {
        "id": "carrelli",
        "label": "Carrelli elevatori",
        "note": "Utilizzo, urti e manutenzione",
        "functions": [
            f("realtime", "Tempo reale e storico", LIVE),
            f("diagnostics", "Centralina e anomalie", PARTIAL),
            f("drivers", "Autisti", LIVE),
            f("costs", "Costi e manutenzione", LIVE),
            f("alarm", "Antifurto completo", LIVE),
            f("maps", "Connessioni e mappe globali", LIVE),
            f("safety", "Sicurezza mezzi e persone", PARTIAL),
            f("sensors", "Sensoristica aggiuntiva", PARTIAL),
            f("integration", "Integrazione e condivisione", LIVE),
            f("support", "Assistenza", LIVE),
        ],
    },
    {
        "id": "agricoltura",
        "label": "Agricoltura",
        "note": "Mezzi, utilizzo e manutenzione",
        "functions": [
            f("realtime", "Tempo reale e storico", LIVE),
            f("drivers", "Autisti", LIVE),
            f("costs", "Costi e manutenzione", LIVE),
            f("alarm", "Antifurto completo", LIVE),
            f("maps", "Connessioni e mappe globali", LIVE),
            f("sensors", "Sensoristica aggiuntiva", PARTIAL),
            f("integration", "Integrazione e condivisione", LIVE),
            f("support", "Assistenza", LIVE),
        ],
    },
    {
        "id": "movimento_terra",
        "label": "Movimento terra",
        "note": "Utilizzo, manutenzione e sensori",
        "functions": [
            f("realtime", "Tempo reale e storico", LIVE),
            f("diagnostics", "Centralina e anomalie", PARTIAL),
            f("fuel", "Carburante", PARTIAL),
            f("drivers", "Autisti", LIVE),
            f("costs", "Costi e manutenzione", LIVE),
            f("alarm", "Antifurto completo", LIVE),
            f("maps", "Connessioni e mappe globali", LIVE),
            f("integration", "Integrazione e condivisione", LIVE),
            f("support", "Assistenza", LIVE),
        ],
    },
]

VERTICAL_IDS = {item["id"] for item in VERTICALS}


def vertical_details() -> list[dict]:
    return VERTICALS
