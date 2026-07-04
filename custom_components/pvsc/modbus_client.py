"""Minimalistischer asyncio Modbus-Client für die EM2GO Wallbox.

VERLAUF DER FEHLERSUCHE (Framing): Anfangs echtes Modbus-TCP/MBAP
implementiert -> schlug fehl -> Vermutung "RTU-über-TCP-Bridge" (wegen
seriellen Feldern im Node-RED Export) -> ebenfalls fehlgeschlagen ->
per Screenshot der Node-RED UI bestätigt: "TCP Type: DEFAULT" am
modbus-client Node bedeutet echtes Standard-Modbus-TCP (MBAP-Framing).
Die seriellen Felder im JSON-Export waren nur ungenutzte Reste des
Config-Schemas. Standard-Framing ist daher `mbap` (siehe
DEFAULT_MODBUS_FRAMING in const.py). `rtu` bleibt als Fallback über
die Option `modbus_framing` erhalten, falls sich doch noch etwas
anderes zeigen sollte - Umschalten braucht dank Options-Flow keinen
HA-Neustart, nur ein Reload der Integration.

Beide Framing-Modi implementiert:
- `mbap`: MBAP-Header (Transaction-ID, Protocol-ID, Length, Unit-ID) +
  PDU, keine CRC (TCP garantiert Integrität bereits) - Standard.
- `rtu`: [Unit-ID][Function][Data...][CRC16 low][CRC16 high], keine
  MBAP-Hülle, keine Transaction-ID - Fallback/Vergleichsmodus.

Weiterhin bewusst nachgebildete Schutzmechanismen aus der
node-red-contrib-modbus Konfiguration:
- `command_delay`: Mindestpause zwischen zwei Transaktionen (Äquivalent
  zu "commandDelay").
- `reconnect_backoff`: Cool-down nach Fehlern statt sofortigem Retry
  (Äquivalent zu "reconnectTimeout"), verdoppelt sich bei Folgefehlern.
- `timeout`: pro Request konfigurierbar (Äquivalent zu "clientTimeout").
- `connect_settle_delay`: kurze Pause nach frischem Verbindungsaufbau.

Alle Werte sind über den Options-Flow der Integration einstellbar.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import struct
import time

_LOGGER = logging.getLogger(__name__)

MAX_RECONNECT_BACKOFF = 120.0  # Sekunden, Obergrenze für exponentiellen Backoff

FUNC_READ_HOLDING_REGISTERS = 0x03
FUNC_WRITE_SINGLE_REGISTER = 0x06
FUNC_WRITE_MULTIPLE_REGISTERS = 0x10


class ModbusError(Exception):
    """Fehler bei einer Modbus-Transaktion."""


class ModbusCooldownError(ModbusError):
    """Verbindung wird gerade bewusst NICHT versucht (Cool-down nach Fehler)."""


def _crc16(data: bytes) -> int:
    """Modbus-CRC16 (Polynom 0xA001, wie in jeder Modbus-RTU-Implementierung)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


class ModbusTcpClient:
    """Serialisierter RTU-über-TCP Client mit Fehler-Backoff."""

    def __init__(
        self,
        host: str,
        port: int,
        unit_id: int,
        timeout: float = 1.5,
        command_delay: float = 0.1,
        reconnect_backoff: float = 10.0,
        connect_settle_delay: float = 0.25,
        framing: str = "rtu",
    ) -> None:
        self._host = host
        self._port = port
        self._unit_id = unit_id
        self._timeout = timeout
        self._command_delay = command_delay
        self._base_backoff = max(reconnect_backoff, 0.5)
        self._connect_settle_delay = max(connect_settle_delay, 0.0)
        # "rtu": rohe RTU-Rahmen (Unit+Func+Daten+CRC16), kein MBAP-Header -
        # vermuteter Modus für diese Wallbox (Serial-zu-TCP-Bridge).
        # "mbap": echtes Modbus-TCP mit MBAP-Header + Transaction-ID -
        # Fallback, falls sich die RTU-Vermutung nicht bestätigt.
        # Per Option umschaltbar, damit ein Vergleich ohne HA-Neustart
        # möglich ist (nur Config-Entry-Reload nötig).
        self._framing = framing if framing in ("rtu", "mbap") else "rtu"
        self._transaction_id = 0
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

        self._consecutive_failures = 0
        self._last_failure_ts = 0.0

    # ------------------------------------------------------------------
    # Diagnose (für sensor.pvsc_modbus_*)
    # ------------------------------------------------------------------
    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def seconds_until_retry(self) -> float:
        if self._consecutive_failures == 0:
            return 0.0
        backoff = self._current_backoff()
        remaining = backoff - (time.monotonic() - self._last_failure_ts)
        return max(0.0, remaining)

    def _current_backoff(self) -> float:
        backoff = self._base_backoff * (2 ** max(0, self._consecutive_failures - 1))
        return min(backoff, MAX_RECONNECT_BACKOFF)

    # ------------------------------------------------------------------
    # Verbindungsverwaltung
    # ------------------------------------------------------------------
    async def _ensure_connected(self) -> None:
        if self._writer is not None and not self._writer.is_closing():
            return

        if self._consecutive_failures > 0:
            remaining = self.seconds_until_retry
            if remaining > 0:
                raise ModbusCooldownError(
                    f"Cool-down nach {self._consecutive_failures} Fehler(n) in Folge - "
                    f"nächster Verbindungsversuch in {remaining:.0f}s"
                )

        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port), timeout=self._timeout
        )

        sock = self._writer.get_extra_info("socket")
        if sock is not None:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass

        if self._connect_settle_delay > 0:
            await asyncio.sleep(self._connect_settle_delay)

    async def close(self) -> None:
        async with self._lock:
            await self._force_close()

    async def _force_close(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception:  # noqa: BLE001
                pass
        self._writer = None
        self._reader = None

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        self._last_failure_ts = time.monotonic()

    def _record_success(self) -> None:
        if self._consecutive_failures:
            _LOGGER.info(
                "PVSC Modbus: Verbindung nach %d Fehler(n) wiederhergestellt",
                self._consecutive_failures,
            )
        self._consecutive_failures = 0

    # ------------------------------------------------------------------
    # Transaktion - dispatcht auf RTU- oder MBAP-Framing
    # ------------------------------------------------------------------
    async def _transact(self, function_code: int, data: bytes) -> bytes:
        async with self._lock:
            phase = "Verbindungsaufbau"
            try:
                was_fresh = self._writer is None or self._writer.is_closing()
                await self._ensure_connected()
                if was_fresh:
                    _LOGGER.debug(
                        "PVSC Modbus: neue Verbindung zu %s:%s aufgebaut (Framing=%s)",
                        self._host, self._port, self._framing,
                    )

                if self._framing == "mbap":
                    payload, phase = await self._transact_mbap(function_code, data, phase)
                else:
                    payload, phase = await self._transact_rtu(function_code, data, phase)

            except ModbusCooldownError:
                raise
            except (
                asyncio.TimeoutError,
                asyncio.IncompleteReadError,
                ConnectionError,
                OSError,
            ) as err:
                await self._force_close()
                self._record_failure()
                detail = str(err) or type(err).__name__
                raise ModbusError(
                    f"Modbus I/O Fehler bei '{phase}' [{self._framing}] "
                    f"({self._host}:{self._port}), "
                    f"Fehler Nr. {self._consecutive_failures} in Folge, "
                    f"nächster Versuch in {self._current_backoff():.0f}s: {detail}"
                ) from err
            except ModbusError:
                raise
            except Exception as err:  # noqa: BLE001 - CRC-/Parsing-Fehler o.ä.
                await self._force_close()
                self._record_failure()
                raise ModbusError(
                    f"Modbus Protokollfehler bei '{phase}' [{self._framing}] "
                    f"({self._host}:{self._port}): {err}"
                ) from err

            self._record_success()
            if self._command_delay > 0:
                await asyncio.sleep(self._command_delay)
            return payload

    async def _transact_rtu(
        self, function_code: int, data: bytes, phase: str
    ) -> tuple[bytes, str]:
        """RTU-Framing direkt über TCP: [Unit][Func][Daten][CRC16], keine
        MBAP-Hülle, keine Transaction-ID."""
        request = struct.pack(">BB", self._unit_id, function_code) + data
        request += struct.pack("<H", _crc16(request))

        phase = "Senden der Anfrage"
        self._writer.write(request)
        await self._writer.drain()

        # RTU-Rahmen haben keinen expliziten Längen-Header wie MBAP - zuerst
        # Unit-ID + Function-Code lesen, daraus ergibt sich, wie viele Bytes
        # noch folgen.
        phase = "Lesen der Antwort (Unit/Function)"
        head = await asyncio.wait_for(self._reader.readexactly(2), timeout=self._timeout)
        resp_unit, resp_func = struct.unpack(">BB", head)

        if resp_func & 0x80:
            phase = "Lesen der Antwort (Exception)"
            rest = await asyncio.wait_for(
                self._reader.readexactly(3), timeout=self._timeout
            )  # exception_code(1) + CRC(2)
            self._verify_crc(head + rest)
            self._record_success()
            raise ModbusError(f"Modbus Exception, function=0x{resp_func:02x} code={rest[0]}")

        if function_code == FUNC_READ_HOLDING_REGISTERS:
            phase = "Lesen der Antwort (Byte-Count)"
            bc_raw = await asyncio.wait_for(self._reader.readexactly(1), timeout=self._timeout)
            byte_count = bc_raw[0]
            phase = "Lesen der Antwort (Daten+CRC)"
            rest = await asyncio.wait_for(
                self._reader.readexactly(byte_count + 2), timeout=self._timeout
            )
            self._verify_crc(head + bc_raw + rest)
            return rest[:byte_count], phase

        # FC6 (write single register): Echo aus Adresse(2)+Wert(2)+CRC(2)
        phase = "Lesen der Antwort (Echo+CRC)"
        rest = await asyncio.wait_for(self._reader.readexactly(6), timeout=self._timeout)
        self._verify_crc(head + rest)
        return rest[:4], phase

    async def _transact_mbap(
        self, function_code: int, data: bytes, phase: str
    ) -> tuple[bytes, str]:
        """Echtes Modbus-TCP: MBAP-Header (Transaction-ID, Protocol-ID,
        Length, Unit-ID) gefolgt vom PDU, keine CRC (TCP garantiert
        Integrität bereits)."""
        pdu = struct.pack(">B", function_code) + data
        self._transaction_id = (self._transaction_id + 1) % 0xFFFF
        tid = self._transaction_id
        header = struct.pack(">HHHB", tid, 0, len(pdu) + 1, self._unit_id)

        phase = "Senden der Anfrage"
        self._writer.write(header + pdu)
        await self._writer.drain()

        # Antwort lesen - inkl. Resynchronisation: Wenn ein früherer Request
        # in einen Timeout lief, dessen Antwort aber später doch noch ankam,
        # liegt diese veraltete Antwort noch im TCP-Buffer. Ohne Resync wäre
        # ab dann JEDE Antwort um eins versetzt (Dauerfehler "Transaction-ID
        # stimmt nicht überein"). Deshalb: veraltete Antworten verwerfen,
        # bis die zur aktuellen Transaction-ID passende kommt.
        body = b""
        for _ in range(6):  # aktuelle Antwort + max. 5 veraltete
            phase = "Lesen der Antwort (Header)"
            resp_header = await asyncio.wait_for(
                self._reader.readexactly(7), timeout=self._timeout
            )
            r_tid, _r_proto, r_len, _r_unit = struct.unpack(">HHHB", resp_header)

            phase = "Lesen der Antwort (Body)"
            body = await asyncio.wait_for(
                self._reader.readexactly(r_len - 1), timeout=self._timeout
            )
            if r_tid == tid:
                break
            _LOGGER.debug(
                "PVSC Modbus: veraltete Antwort (TID %s, erwartet %s) verworfen",
                r_tid, tid,
            )
        else:
            # ValueError (statt ModbusError) landet im generischen
            # except-Zweig von _transact -> Verbindung wird geschlossen und
            # sauber neu aufgebaut, statt desynchronisiert weiterzulaufen.
            raise ValueError(
                "Transaction-ID stimmt nach mehreren Versuchen nicht überein "
                "(Stream desynchronisiert) - Verbindung wird neu aufgebaut"
            )

        resp_func = body[0]
        if resp_func & 0x80:
            exc_code = body[1] if len(body) > 1 else -1
            self._record_success()
            raise ModbusError(f"Modbus Exception, function=0x{resp_func:02x} code={exc_code}")

        if function_code == FUNC_READ_HOLDING_REGISTERS:
            byte_count = body[1]
            return body[2 : 2 + byte_count], phase
        return body[1:5], phase

    @staticmethod
    def _verify_crc(frame: bytes) -> None:
        received = struct.unpack("<H", frame[-2:])[0]
        computed = _crc16(frame[:-2])
        if received != computed:
            raise ValueError(
                f"CRC ungültig (empfangen 0x{received:04x}, erwartet 0x{computed:04x})"
            )

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------
    async def read_holding_registers(self, address: int, quantity: int) -> list[int]:
        data = struct.pack(">HH", address, quantity)
        payload = await self._transact(FUNC_READ_HOLDING_REGISTERS, data)
        count = len(payload) // 2
        return list(struct.unpack(f">{count}H", payload[: count * 2]))

    async def write_single_register(self, address: int, value: int) -> None:
        """Schreibt EIN Register - aber per FC16 (Write Multiple Registers).

        WICHTIG: Der Node-RED Flow benutzte den modbus-write Node mit
        dataType "MHoldingRegisters" = FC16, nicht FC6. Die EM2GO Wallbox
        hat auf FC6-Writes nicht reagiert (Werte blieben unverändert),
        daher hier exakt wie Node-RED: FC16 mit quantity=1.
        """
        # PDU-Daten: Adresse(2) + Anzahl=1(2) + Byte-Count=2(1) + Wert(2)
        data = struct.pack(">HHBH", address, 1, 2, value & 0xFFFF)
        await self._transact(FUNC_WRITE_MULTIPLE_REGISTERS, data)
