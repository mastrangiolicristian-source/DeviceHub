"""Server TCP di ingestione: handshake IMEI, frame AVL e comandi in discesa.

Il device Teltonika apre una connessione TCP, invia il proprio IMEI e attende
un byte di risposta (0x01 accettato, 0x00 rifiutato). Poi invia i pacchetti
AVL e attende il conteggio dei record accettati (4 byte big-endian). Sulla
stessa connessione il server puo' inviare comandi Codec 12 e attendere la
risposta del device.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import struct
from dataclasses import dataclass, field

from .codec12 import (
    CODEC_12,
    encode_command,
    parse_frame as parse_codec12_frame,
)
from .config import Settings
from .driving import BRAKE, detect
from .notifications import dispatch_email, dispatch_sms, dispatch_voice
from .webhooks import enqueue_webhook
from .store import TelemetryStore
from .teltonika import (
    IMEI_ACCEPT,
    IMEI_REJECT,
    PREAMBLE,
    ProtocolError,
    parse_avl_packet,
)

log = logging.getLogger("devicehub.ingest")


class DeviceOffline(RuntimeError):
    """Il device non ha una connessione aperta: comando non recapitabile."""

    def __init__(self, imei: str) -> None:
        super().__init__(f"device {imei} non connesso")
        self.imei = imei


@dataclass
class DeviceLink:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    pending: asyncio.Future | None = None


class IngestServer:
    def __init__(self, settings: Settings, store: TelemetryStore) -> None:
        self.settings = settings
        self.store = store
        self._server: asyncio.AbstractServer | None = None
        self._last_speed: dict[str, tuple[float, int]] = {}
        self._links: dict[str, DeviceLink] = {}

    @property
    def port(self) -> int:
        if not self._server:
            raise RuntimeError("server non avviato")
        return self._server.sockets[0].getsockname()[1]

    def is_connected(self, imei: str) -> bool:
        return imei in self._links

    async def start(self) -> "IngestServer":
        self._server = await asyncio.start_server(
            self._handle_client, self.settings.tcp_host, self.settings.tcp_port
        )
        log.info(
            "ingestione TCP in ascolto su %s:%s",
            self.settings.tcp_host,
            self.port,
        )
        return self

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def send_command(self, imei: str, text: str, timeout: float = 10.0) -> str:
        """Invia un comando Codec 12 e attende la risposta del device."""
        link = self._links.get(imei)
        if link is None:
            raise DeviceOffline(imei)

        async with link.lock:
            loop = asyncio.get_running_loop()
            future: asyncio.Future = loop.create_future()
            link.pending = future
            try:
                link.writer.write(encode_command(text))
                await link.writer.drain()
                log.info("IMEI %s <- %s", imei, text)
                return await asyncio.wait_for(future, timeout)
            finally:
                link.pending = None

    # --- gestione connessione ---------------------------------------------

    async def _read_exactly(self, reader: asyncio.StreamReader, size: int) -> bytes:
        return await asyncio.wait_for(
            reader.readexactly(size), timeout=self.settings.idle_timeout
        )

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        ip = peer[0] if peer else None
        imei = "?"
        link: DeviceLink | None = None
        try:
            imei = await self._handshake(reader, writer, ip)
            if not imei:
                return
            link = DeviceLink(reader, writer)
            self._links[imei] = link
            await self._read_loop(link, imei)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError):
            log.debug("connessione chiusa da %s (imei %s)", ip, imei)
        except ConnectionResetError:
            log.debug("reset da %s (imei %s)", ip, imei)
        except ProtocolError as exc:
            log.warning("frame non valido da %s (imei %s): %s", ip, imei, exc)
        except Exception:  # pragma: no cover - difesa: nessun crash del server
            log.exception("errore non gestito con %s (imei %s)", ip, imei)
        finally:
            if link is not None and self._links.get(imei) is link:
                self._links.pop(imei, None)
                # Chi attende la risposta di un comando deve sapere subito che
                # il device e' caduto, non attendere il timeout.
                if link.pending and not link.pending.done():
                    link.pending.set_exception(DeviceOffline(imei))
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()

    async def _handshake(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, ip: str | None
    ) -> str | None:
        length = struct.unpack(">H", await self._read_exactly(reader, 2))[0]
        if not 1 <= length <= 32:
            raise ProtocolError(f"lunghezza IMEI non valida: {length}")
        raw = await self._read_exactly(reader, length)
        imei = raw.decode("ascii", errors="replace")

        if await asyncio.to_thread(self.store.register_device, imei, ip):
            log.info("nuovo dispositivo IMEI %s da %s", imei, ip)

        allowed = self.settings.allow_unknown_devices or await asyncio.to_thread(
            self.store.is_active, imei
        )
        if not allowed:
            log.warning(
                "IMEI %s non abilitato: connessione rifiutata."
                " Abilitarlo con POST /devices/%s/activate",
                imei,
                imei,
            )
            writer.write(IMEI_REJECT)
            await writer.drain()
            return None

        writer.write(IMEI_ACCEPT)
        await writer.drain()
        return imei

    async def _evaluate_alerts(
        self, imei: str, record, privacy: bool = False
    ) -> None:
        """Apre gli allarmi che dipendono dagli IO del device.

        AVL 249 = jamming: 1 allarme, 0 rientro. Il Teltonika non puo'
        avvisare mentre e' disturbato, quindi l'evento arriva al primo
        contatto utile: conta comunque, perche' indica un occultamento.

        Con la modalita' privacy attiva le valutazioni che richiedono le
        coordinate (geofence, velocita', furto, carburante) restano spente:
        non devono descrivere dove si trova il mezzo. L'allarme SOS resta
        attivo e conserva la posizione nel proprio record.
        """
        kinds: list[str] = []
        previous = self._last_speed.get(imei)
        self._last_speed[imei] = (
            float(record.speed or 0),
            int(record.timestamp_ms),
        )
        if previous is not None:
            harsh = detect(
                previous[0],
                previous[1],
                float(record.speed or 0),
                int(record.timestamp_ms),
                self.settings.harsh_accel_kmh_s,
                self.settings.harsh_brake_kmh_s,
            )
            if harsh:
                label = "Frenata" if harsh == BRAKE else "Accelerazione"
                created = await asyncio.to_thread(
                    self.store.raise_alert,
                    imei,
                    harsh,
                    "HIGH",
                    f"{label} brusca: {previous[0]:.0f} -> "
                    f"{float(record.speed or 0):.0f} km/h",
                    record.timestamp_ms,
                )
                if created:
                    kinds.append(harsh)
                    log.warning("IMEI %s: allarme %s aperto", imei, harsh)

        jamming = record.io.get(249)
        if jamming == 1:
            created = await asyncio.to_thread(
                self.store.raise_alert,
                imei,
                "JAMMING",
                "CRITICAL",
                "Interferenza su GPS/GSM rilevata dal dispositivo",
                record.timestamp_ms,
            )
            if created:
                kinds.append("JAMMING")
                log.warning("IMEI %s: allarme JAMMING aperto", imei)

        if int(record.io.get(self.settings.sos_io_id, 0) or 0) == 1:
            detail = (
                "Pulsante SOS premuto a "
                f"{record.latitude:.5f}, {record.longitude:.5f}"
            )
            created = await asyncio.to_thread(
                self.store.raise_alert,
                imei,
                "SOS",
                "CRITICAL",
                detail,
                record.timestamp_ms,
                True,
                record.latitude,
                record.longitude,
            )
            if created:
                kinds.append("SOS")
                log.warning("IMEI %s: allarme SOS aperto", imei)

        if self.settings.unplug_enabled:
            unplug = await asyncio.to_thread(
                self.store.detect_power_cut,
                imei,
                record.io,
                record.timestamp_ms,
                self.settings.unplug_min_voltage,
                self.settings.unplug_drop_voltage,
            )
            if unplug:
                kinds.append("UNPLUG")
                log.warning("IMEI %s: allarme UNPLUG aperto", imei)

        if not privacy:
            ignition = int(record.io.get(239, 0) or 0)
            triggered = await asyncio.to_thread(
                self.store.evaluate_notifications,
                imei,
                record.latitude,
                record.longitude,
                record.speed,
                ignition,
                record.timestamp_ms,
                self.settings.fuel_theft_liters,
            )
            for kind in triggered:
                log.warning("IMEI %s: allarme %s aperto", imei, kind)
            kinds.extend(triggered)

        if kinds:
            details = await asyncio.to_thread(
                self.store.alert_details, imei, kinds, record.timestamp_ms
            )
            # Fuori dall'eccezione SOS la privacy vieta di mandare coordinate
            # fuori dal sistema, nemmeno in un'email o in un webhook.
            notify_lat = record.latitude if not privacy or "SOS" in kinds else None
            notify_lon = record.longitude if not privacy or "SOS" in kinds else None
            deliveries = [
                await asyncio.to_thread(
                    dispatch_email,
                    self.store,
                    self.settings,
                    imei,
                    kinds,
                    details,
                    notify_lat,
                    notify_lon,
                    record.timestamp_ms,
                ),
                await asyncio.to_thread(
                    dispatch_sms,
                    self.store,
                    self.settings,
                    imei,
                    kinds,
                    notify_lat,
                    notify_lon,
                    record.timestamp_ms,
                ),
                await asyncio.to_thread(
                    dispatch_voice,
                    self.store,
                    self.settings,
                    imei,
                    kinds,
                    notify_lat,
                    notify_lon,
                    record.timestamp_ms,
                ),
            ]
            for delivery in deliveries:
                if not delivery:
                    continue
                if delivery["status"] == "failed":
                    log.warning(
                        "notifica %s non inviata per IMEI %s: %s",
                        delivery["channel"],
                        imei,
                        delivery.get("detail") or "errore del canale",
                    )
                else:
                    log.info(
                        "notifica %s %s per IMEI %s (%s)",
                        delivery["channel"],
                        delivery["status"],
                        imei,
                        ", ".join(delivery["kinds"]),
                    )

            await asyncio.to_thread(
                enqueue_webhook,
                self.store,
                "alert",
                {
                    "imei": imei,
                    "kinds": kinds,
                    "latitude": notify_lat,
                    "longitude": notify_lon,
                    "speed": record.speed,
                    "timestamp_ms": record.timestamp_ms,
                    "details": details,
                },
                self.settings.webhook_max_pending,
            )

    async def _read_loop(self, link: DeviceLink, imei: str) -> None:
        while True:
            prefix = await self._read_exactly(link.reader, 4)
            if prefix != PREAMBLE:
                raise ProtocolError(f"preambolo inatteso: {prefix.hex()}")
            field_length = struct.unpack(">I", await self._read_exactly(link.reader, 4))[0]
            if field_length < 5 or field_length > 4096:
                raise ProtocolError(f"data field length non valido: {field_length}")
            body = await self._read_exactly(link.reader, field_length + 4)
            raw = prefix + struct.pack(">I", field_length) + body

            if body[0] == CODEC_12:
                message, _ = parse_codec12_frame(raw)
                log.info("IMEI %s -> risposta comando: %s", imei, message.text)
                if link.pending and not link.pending.done():
                    link.pending.set_result(message.text)
                continue

            packet, _ = parse_avl_packet(raw)
            if not packet.crc_ok:
                log.warning(
                    "CRC errato da IMEI %s (atteso %04X, calcolato %04X): scarto il pacchetto",
                    imei,
                    packet.crc_received,
                    packet.crc_computed,
                )
                link.writer.write(struct.pack(">I", 0))
                await link.writer.drain()
                continue

            latest = max(packet.records, key=lambda item: item.timestamp_ms)
            # Il flag privacy puo' arrivare dal portale o dall'ingresso DIN:
            # va deciso prima del salvataggio, altrimenti il pacchetto che
            # porta il cambio verrebbe registrato con le coordinate.
            privacy = await asyncio.to_thread(self.store.privacy_enabled, imei)
            io_id = self.settings.privacy_io_id
            if io_id and io_id in latest.io:
                desired = int(latest.io.get(io_id) or 0) == 1
                if desired != privacy:
                    changed = await asyncio.to_thread(
                        self.store.set_privacy_mode, imei, desired, "device"
                    )
                    if changed:
                        privacy = desired
                        log.info(
                            "IMEI %s: modalita' privacy %s da ingresso DIN %d",
                            imei,
                            "attiva" if desired else "disattivata",
                            io_id,
                        )
            inserted = await asyncio.to_thread(
                self.store.save_records, imei, packet.records, packet.codec_id
            )
            log.info(
                "IMEI %s: %d record (nuovi %d), ultimo %.5f/%.5f %.0f km/h",
                imei,
                len(packet.records),
                inserted,
                latest.latitude,
                latest.longitude,
                latest.speed,
            )
            if self.settings.log_io:
                log.info("IMEI %s IO grezzi: %s", imei, latest.io)

            # ACK subito dopo il salvataggio: il device non deve aspettare le
            # notifiche (email/SMS, geofence) per ricevere la conferma.
            link.writer.write(struct.pack(">I", len(packet.records)))
            await link.writer.drain()

            await self._evaluate_alerts(imei, latest, privacy)
