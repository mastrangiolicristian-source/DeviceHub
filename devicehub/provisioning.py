"""Generazione dei comandi di configurazione da inviare al GPS.

Serve al momento dell'acquisto: si compra il dispositivo, si inserisce la SIM
M2M e gli si comunica dove mandare i dati. I parametri usati sono quelli
documentati da Teltonika (2001-2006 APN e server, 113 codec).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Parametro 113 = protocollo dati: 0 Codec 8, 1 Codec 8 Extended, 2 JSON.
CODEC_PARAM = {8: 0, 0x8E: 1}


@dataclass
class ProvisioningPlan:
    imei: str
    host: str
    port: int
    apn: str
    codec: int
    apn_user: str = ""
    apn_password: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def sms_commands(self) -> list[str]:
        commands = [f"setparam 2001:{self.apn}"]
        if self.apn_user or self.apn_password:
            commands.append(f"setparam 2002:{self.apn_user}")
            commands.append(f"setparam 2003:{self.apn_password}")
        commands += [
            f"setparam 2004:{self.host}",
            f"setparam 2005:{self.port}",
            "setparam 2006:0",  # 0 = TCP
            f"setparam 113:{CODEC_PARAM[self.codec]}",
        ]
        return commands

    def as_dict(self) -> dict:
        return {
            "imei": self.imei,
            "server": {"host": self.host, "port": self.port, "transport": "TCP"},
            "apn": {"name": self.apn, "user": self.apn_user, "password": self.apn_password},
            "codec": "8E" if self.codec == 0x8E else "8",
            "sms_commands": self.sms_commands,
            "verification": ["getinfo"],
            "notes": self.notes,
        }

    def as_text(self) -> str:
        lines = [
            f"Configurazione dispositivo Teltonika - IMEI {self.imei}",
            "",
            f"Server   : {self.host}:{self.port} (TCP)",
            f"APN      : {self.apn}",
            f"Codec    : {'8E' if self.codec == 0x8E else '8'}",
            "",
            "Comandi SMS da inviare al numero della SIM del tracker:",
        ]
        lines += [f"  {command}" for command in self.sms_commands]
        lines += [
            "",
            "Verifica: inviare 'getinfo' e controllare che il device risponda",
            "con IMEI, firmware e stato GPRS.",
            "",
            "Note:",
        ]
        lines += [f"  - {note}" for note in self.notes] or ["  - nessuna"]
        return "\n".join(lines)


def teltonika_plan(
    imei: str,
    host: str,
    port: int,
    apn: str,
    codec: int = 0x8E,
    apn_user: str = "",
    apn_password: str = "",
) -> ProvisioningPlan:
    if codec not in CODEC_PARAM:
        raise ValueError(f"codec non supportato: 0x{codec:02X}")
    if not imei.isdigit() or len(imei) < 14:
        raise ValueError("IMEI non plausibile: attesi almeno 14 caratteri numerici")

    notes = [
        "Alcuni firmware accettano la forma 'setparam 2004 :dominio' (con spazio):"
        " se il comando non viene applicato, riprovare con lo spazio.",
        "Con Codec 8 Extended verificare che il firmware del dispositivo sia"
        " aggiornato: i modelli piu' vecchi accettano solo Codec 8.",
        "La SIM deve essere M2M/dati con APN noto e traffico incluso:"
        " il tracker apre una connessione TCP verso il server e resta connesso.",
    ]
    notes.append(
        "FMC150 ha il processore CAN integrato: non serve acquistare LV-CAN200."
        " Gli elementi CAN (84 carburante in litri x0,1 - 89.% - 87 km -"
        " 115 temperatura motore x0,1 - 102 ore motore in minuti) non sono attivi"
        " di default: vanno abilitati in Configurator (CAN -> Send data to server)"
        " dopo aver selezionato il programma del veicolo."
    )

    return ProvisioningPlan(
        imei=imei,
        host=host,
        port=port,
        apn=apn,
        apn_user=apn_user,
        apn_password=apn_password,
        codec=codec,
        notes=notes,
    )
