"""Herzstück der Integration: Port des Node-RED "PvSurplusCalculation" Flows.

Die Berechnung in `_calculate()` ist bewusst 1:1 an die Struktur der
originalen JavaScript-Function angelehnt (gleiche Variablennamen wo
sinnvoll, gleiche Reihenfolge, gleiche Kommentare), damit sich Verhalten
gegen den Node-RED Flow abgleichen lässt.

Schreibzugriffe auf die Wallbox (Start/Stopp/Ampere/Phasen) erfolgen NUR,
wenn `self.control_enabled` True ist. Solange das aus ist, wird per Modbus
nur GELESEN und der Regel-Vorschlag berechnet und angezeigt - die Hardware
bleibt unangetastet.
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant, callback, Event, EventStateChangedData
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    AMPERE_CHANGE_INTERVAL,
    DEFAULT_AMPERE_CHANGE_DELAY,
    DEFAULT_ENABLED,
    DEFAULT_MODBUS_FRAMING,
    DEFAULT_NOTIFY_ENTITY,
    DEFAULT_OVERRIDE,
    DEFAULT_SETTINGS,
    DEFAULT_STATE_CHANGE_OFF_DELAY,
    DEFAULT_STATE_CHANGE_ON_DELAY,
    DOMAIN,
    EM2GO_STATE_TEXT_DE,
    EM2GO_STATE_TEXT_EN,
    FIXED_ERR_LIMIT,
    MAX_A,
    MIN_A,
    MODBUS_READS,
    REG_ACTION,
    REG_AMPERE,
    REG_ERR_LIMIT,
    REG_PHASES,
    ACTION_START,
    ACTION_STOP,
    PHASE_CHANGE_DELAY,
    PHASE_DOWN_WATTS,
    PHASE_UP_WATTS,
    STATE_CHANGE_INTERVAL,
    STOP_CAUSE_HIGH_BATTERY_USAGE,
    STOP_CAUSE_LOW_SOC,
    STOP_CAUSE_LOW_SURPLUS,
    STOP_CAUSE_NONE,
    STOP_CAUSE_TEXT_DE,
    STOP_CAUSE_TEXT_EN,
    STORAGE_VERSION,
    SWITCH_RATE_LIMIT_MAX,
    SWITCH_RATE_LIMIT_WINDOW,
    VOLT,
)
from .modbus_client import ModbusCooldownError, ModbusError, ModbusTcpClient

_LOGGER = logging.getLogger(__name__)


def _to_float(state, default: float = -1.0) -> float:
    if state is None or state.state in (None, "unknown", "unavailable", ""):
        return default
    try:
        return float(state.state)
    except (ValueError, TypeError):
        return default


@dataclass
class BatteryState:
    support_watts: float = 0.0
    usage_per_min: float = 0.0
    usage_per_min_count: int = 0
    usage_cache: list[float] = field(default_factory=lambda: [-1.0] * 15)
    usage_cache_ts: float = 0.0
    usage_cache_offset: int = 0

    def cache_avg(self) -> float:
        vals = [v for v in self.usage_cache if v >= 0]
        return round(sum(vals) / len(vals)) if vals else 0

    def add_minute_sample(self, now: float) -> None:
        self.usage_cache_ts = now
        if self.usage_per_min_count == 0:
            return
        self.usage_cache[self.usage_cache_offset] = round(
            self.usage_per_min / self.usage_per_min_count
        )
        self.usage_cache_offset = (self.usage_cache_offset + 1) % len(self.usage_cache)
        self.usage_per_min = 0
        self.usage_per_min_count = 0

    def add_tick_sample(self) -> None:
        self.usage_per_min += self.support_watts
        self.usage_per_min_count += 1


class PVSCCoordinator:
    """Zustand + periodische Regel-Logik, unabhängig von Node-RED."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self.listeners: list[callable] = []

        # --- externe Messwerte (per state-change Listener aktuell gehalten) ---
        self.home = {
            "pv": -1.0, "pv1": -1.0, "charge": -1.0, "discharge": -1.0,
            "import": -1.0, "export": -1.0, "load": -1.0, "soc": -1.0,
        }
        self.car = {"soc": -1.0, "end": None, "power": -1.0, "location": None}
        self.pv_forecast = 0.0

        # --- Wallbox (Quelle: direkter Modbus-Poll, unabhängig davon, ob
        # die Steuerung schreiben darf) ---
        # Einheiten sind überall bereits normalisiert (z.B. ampere = echte
        # Ampere, nicht Rohregister*10; loaded_kwh = kWh, nicht Rohregister).
        self.em2go = {
            "state": -1, "plug": -1, "plug_changed": False, "error": -1,
            "power": -1.0, "l1": -1.0, "l2": -1.0, "l3": -1.0, "energy": -1.0,
            "ampere": -1.0, "phases": -1, "err_limit": -1, "mode": -1,
            "action": -1, "loaded_kwh": -1.0, "time": -1,
        }
        self.modbus_ok = False
        self.modbus_last_error: str | None = None

        # --- eigener Regel-Zustand (Äquivalent zu psc.* im Flow) ---
        self.state = False
        self.target_state = False
        self.ampere = MIN_A
        self.target_ampere: float = -1
        self.ampere_change_ts = 0.0
        self.state_change_ts = 0.0
        self.last_ampere_change_ts = 0.0
        self.last_state_change_ts = 0.0
        self.last_update = 0.0
        self.pv = 0.0
        self.load = 0.0
        self.surplus = 0.0
        self.car_surplus = 0.0
        self.correction_faktor = 0.75
        self.stop_cause = STOP_CAUSE_NONE
        self.battery = BatteryState()
        self.status_text = ""
        self.status_color = "grey"
        self.switch_history: list[float] = []

        # --- live einstellbare Werte, gesetzt durch number/select/switch Entities ---
        # Werkseinstellungen aus const.py (siehe DEFAULT_SETTINGS/DEFAULT_OVERRIDE
        # dort für die Herkunft der einzelnen Werte). Diese Defaults werden nur
        # verwendet, solange in _async_load_persisted_state() noch nichts aus dem
        # Store geladen werden konnte (erster Start bzw. noch nie geändert).
        self.settings = dict(DEFAULT_SETTINGS)
        # Zeitstempel für die automatische Phasenumschaltung (Beginn der
        # stabilen Über-/Unterschreitung der Schwellwerte)
        self.phase_change_ts = 0.0
        self.enabled = DEFAULT_ENABLED
        # Startzustand der Steuerung: wird gleich in _async_load_persisted_state()
        # ggf. aus dem Store überschrieben; ist dort noch nichts gespeichert,
        # verwendet async_setup() weiterhin das Setup-Feld "control_on_start"
        # (True bedeutet: nach jedem (Neu-)Start schreibt die Integration sofort
        # wieder auf die Wallbox, ohne dass der Schalter manuell gesetzt werden
        # muss). Siehe self._control_enabled_restored weiter unten.
        self.control_enabled = False
        self._control_enabled_restored = False
        self.override = dict(DEFAULT_OVERRIDE)

        # Persistiert die oben genannten "live" Werte (settings/override/enabled/
        # control_enabled) dauerhaft in .storage/, damit sie einen HA-Neustart
        # oder ein Update der Integration überstehen (siehe async_persist_state(),
        # _async_load_persisted_state() und async_reset_to_defaults() unten).
        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_live_state"
        )

        # Werden in async_setup() anhand der tatsächlichen Konfiguration
        # gesetzt; Defaults hier nur zur Sicherheit vor dem ersten Setup.
        self.has_car_location = False
        self.has_car_soc = False
        self.has_pv1 = False
        self.has_battery = True
        self.core_ready = True
        self.core_ready_fields = ["pv", "load", "import", "export"]

        self._modbus: ModbusTcpClient | None = None
        self._entities_to_update: list = []
        # Für Ladestart/-stopp-Benachrichtigungen: letzter bekannter
        # Ladezustand (None = noch nie ermittelt, z.B. direkt nach Start -
        # dann keine Meldung, um Neustart-Spam zu vermeiden).
        self._last_charging: bool | None = None
        self._unsub_interval = None
        # Schutz gegen überlappende Ticks: async_track_time_interval wartet
        # NICHT darauf, dass ein vorheriger Tick fertig ist, bevor der
        # nächste startet. Ohne diese Sperre könnten bei einem langsamen/
        # hängenden Modbus-Vorgang zwei _async_tick-Läufe gleichzeitig aktiv
        # werden. Der Lock im Modbus-Client verhindert zwar überlappende
        # Bytes auf der Leitung, aber nicht überlappende _calculate()/
        # _apply_changes()-Aufrufe - deshalb zusätzlich hier abgesichert.
        self._tick_running = False

    # ------------------------------------------------------------------
    # Setup / Teardown
    # ------------------------------------------------------------------
    async def async_setup(self) -> None:
        # Zuvor gespeicherte "live" Werte (number/switch/select) laden, falls
        # vorhanden - siehe _async_load_persisted_state().
        await self._async_load_persisted_state()

        data = self.entry.data
        opts = self.entry.options
        self._modbus = ModbusTcpClient(
            data["modbus_host"],
            data["modbus_port"],
            data["modbus_unit"],
            timeout=opts.get("modbus_timeout", 1.5),
            command_delay=opts.get("modbus_command_delay", 0.15),
            reconnect_backoff=opts.get("modbus_reconnect_backoff", 10.0),
            connect_settle_delay=opts.get("modbus_connect_settle_delay", 0.25),
            framing=opts.get("modbus_framing", DEFAULT_MODBUS_FRAMING),
        )

        mapping = {
            "pv_entity": ("home", "pv"),
            "pv1_entity": ("home", "pv1"),
            "load_entity": ("home", "load"),
            "import_entity": ("home", "import"),
            "export_entity": ("home", "export"),
            "battery_charge_entity": ("home", "charge"),
            "battery_discharge_entity": ("home", "discharge"),
            "home_soc_entity": ("home", "soc"),
        }
        self._entity_map = {}
        for conf_key, (bucket, field_name) in mapping.items():
            entity_id = data.get(conf_key)
            if entity_id:
                self._entity_map[entity_id] = (bucket, field_name)

        # Welche optionalen Quellen sind tatsächlich konfiguriert? Wird
        # benutzt, um Logik, die von "nicht vorhandenen" Daten abhängt,
        # sauber zu deaktivieren statt mit Sentinel-Werten (-1) falsch zu
        # rechnen (siehe _calculate()).
        self.has_car_location = bool(data.get("car_location_entity"))
        self.has_car_soc = bool(data.get("car_soc_entity"))
        self.has_pv1 = bool(data.get("pv1_entity"))
        # Heimspeicher optional: ohne home_soc_entity entfallen SOC-Stufen,
        # SOC-Gate und Batterie-Unterstützung (Korrekturfaktor fix 1.0
        # bzw. manueller Wert).
        self.has_battery = bool(data.get("home_soc_entity"))
        # Nur wenn im Store noch KEIN control_enabled hinterlegt ist (ganz
        # neuer Eintrag, oder Store leer/gelöscht) zählt weiterhin das
        # Setup-Feld "control_on_start" als Startzustand - das erhält das
        # bisherige Sicherheitsverhalten für neue Installationen unverändert
        # (Default: Steuerung startet inaktiv). Sobald der Schalter einmal
        # live betätigt wurde, ist der gespeicherte Zustand maßgeblich und
        # übersteht künftige Neustarts/Updates (siehe _async_load_persisted_state).
        if not self._control_enabled_restored:
            self.control_enabled = bool(data.get("control_on_start", True))
        # Sicherheits-Gate: nur die tatsächlich konfigurierten Kern-Sensoren
        # müssen nach dem Start Werte geliefert haben.
        self.core_ready_fields = [
            field
            for key, field in (
                ("pv_entity", "pv"), ("load_entity", "load"),
                ("import_entity", "import"), ("export_entity", "export"),
                ("battery_charge_entity", "charge"),
                ("battery_discharge_entity", "discharge"),
                ("home_soc_entity", "soc"),
            )
            if data.get(key)
        ]
        self.required_core_entities = [
            k for k in (
                "pv_entity", "load_entity", "import_entity", "export_entity",
                "battery_charge_entity", "battery_discharge_entity", "home_soc_entity",
            ) if data.get(k)
        ]

        watch_entities = list(self._entity_map.keys())

        if data.get("pv_forecast_entity"):
            watch_entities.append(data["pv_forecast_entity"])
        if data.get("car_soc_entity"):
            watch_entities.append(data["car_soc_entity"])
        if data.get("car_end_entity"):
            watch_entities.append(data["car_end_entity"])
        if data.get("car_location_entity"):
            watch_entities.append(data["car_location_entity"])
        if data.get("car_power_entity"):
            watch_entities.append(data["car_power_entity"])

        # initiale Werte einlesen
        for entity_id in watch_entities:
            self._apply_entity_state(entity_id, self.hass.states.get(entity_id))

        self.listeners.append(
            async_track_state_change_event(
                self.hass, watch_entities, self._handle_state_change
            )
        )

        interval = self.entry.options.get("poll_interval", 7)
        self._unsub_interval = async_track_time_interval(
            self.hass, self._async_tick, dt.timedelta(seconds=interval)
        )

    async def async_unload(self) -> None:
        for unsub in self.listeners:
            unsub()
        if self._unsub_interval:
            self._unsub_interval()
        if self._modbus:
            await self._modbus.close()

    def register_entity(self, entity) -> None:
        """Entities registrieren sich hier, um bei jedem Tick aktualisiert zu werden."""
        self._entities_to_update.append(entity)

    def _push_updates(self) -> None:
        for entity in self._entities_to_update:
            entity.async_write_ha_state()

    # ------------------------------------------------------------------
    # Sprache für dynamische Texte (status_text, Abbruchgrund, Wallbox-
    # Status, Ladestart/-stopp-Benachrichtigungen). Diese Werte laufen NICHT
    # über strings.json/translations (das übersetzt nur Entity-Namen),
    # sondern werden hier direkt anhand der aktuellen HA-Systemsprache
    # gewählt - bei jedem Aufruf neu, damit ein Sprachwechsel ohne Neustart
    # der Integration wirkt.
    # ------------------------------------------------------------------
    def _lang(self) -> str:
        """'en' bei englischer HA-Systemsprache (Einstellungen -> System ->
        Allgemein -> Sprache), sonst 'de' (Fallback für alle anderen
        Sprachen, da nur Deutsch/Englisch gepflegt werden)."""
        lang = (self.hass.config.language or "de").lower()
        return "en" if lang.startswith("en") else "de"

    @property
    def stop_cause_text(self) -> str:
        table = STOP_CAUSE_TEXT_EN if self._lang() == "en" else STOP_CAUSE_TEXT_DE
        return table.get(self.stop_cause, str(self.stop_cause))

    @property
    def em2go_state_text(self) -> str:
        table = EM2GO_STATE_TEXT_EN if self._lang() == "en" else EM2GO_STATE_TEXT_DE
        fallback = table.get(0, "?")
        return table.get(self.em2go["state"], fallback)

    # ------------------------------------------------------------------
    # Persistenz der "live" Werte (number/switch/select Entities)
    # ------------------------------------------------------------------
    # Ohne dies leben self.settings/self.override/self.enabled/
    # self.control_enabled nur im Arbeitsspeicher des Coordinator-Objekts und
    # werden bei jedem HA-Neustart bzw. jedem Update der Integration (der
    # Coordinator wird dabei neu instanziiert) wieder auf die Hardcoded-
    # Defaults aus const.py zurückgesetzt. Der Store schreibt eine kleine
    # JSON-Datei nach .storage/pvsc_<entry_id>_live_state, die unabhängig
    # vom Config-Entry (entry.data/entry.options) ist.
    async def _async_load_persisted_state(self) -> None:
        """Lädt zuvor gespeicherte Werte aus dem Store, falls vorhanden, und
        überschreibt damit die in __init__() gesetzten Defaults. Muss vor dem
        Rest von async_setup() laufen, insbesondere vor der control_on_start-
        Auswertung dort."""
        stored = await self._store.async_load()
        if not stored:
            return
        self.settings.update(stored.get("settings", {}))
        self.override.update(stored.get("override", {}))
        if "enabled" in stored:
            self.enabled = stored["enabled"]
        if "control_enabled" in stored:
            self.control_enabled = stored["control_enabled"]
            self._control_enabled_restored = True

    async def async_persist_state(self) -> None:
        """Speichert die aktuellen 'live' Werte dauerhaft. Wird von den
        number/switch/select Entities nach jeder Änderung aufgerufen, damit
        der neue Wert einen HA-Neustart oder ein Integrations-Update übersteht."""
        await self._store.async_save(
            {
                "settings": dict(self.settings),
                "override": dict(self.override),
                "enabled": self.enabled,
                "control_enabled": self.control_enabled,
            }
        )

    async def async_reset_to_defaults(self) -> None:
        """Für button.pvsc_reset_defaults: setzt die live einstellbaren Werte
        (SOC-Stufen, Korrekturfaktor, Ampere-Totband, Forced-Ampere,
        Phasen-Automatik, Überschussmodus, Überschuss-Automatik an/aus sowie
        den PV/Manuell/Stop-Override) auf die Werkseinstellungen aus
        const.py zurück und schreibt sie sofort sichtbar in alle betroffenen
        Entities.

        Bewusst AUSGENOMMEN: control_enabled (Schalter "Steuerung aktiv").
        Das ist der Sicherheits-Schalter, der echtes Schreiben auf die
        Wallbox erlaubt - ein Klick auf "Reset to Default" soll nicht
        nebenbei eine laufende Ladesteuerung abschalten oder umgekehrt eine
        bislang inaktive Steuerung scharfschalten.
        """
        self.settings = dict(DEFAULT_SETTINGS)
        self.override = dict(DEFAULT_OVERRIDE)
        self.enabled = DEFAULT_ENABLED
        self.phase_change_ts = 0.0
        await self.async_persist_state()
        self._push_updates()

    # ------------------------------------------------------------------
    # Eingehende HA-Zustände
    # ------------------------------------------------------------------
    @callback
    def _handle_state_change(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        self._apply_entity_state(entity_id, event.data["new_state"])

    def _apply_entity_state(self, entity_id: str, state) -> None:
        data = self.entry.data
        if entity_id in self._entity_map:
            bucket, field_name = self._entity_map[entity_id]
            getattr(self, bucket)[field_name] = _to_float(state)
            return
        if entity_id == data.get("pv_forecast_entity"):
            self.pv_forecast = _to_float(state, 0.0)
        elif entity_id == data.get("car_soc_entity"):
            self.car["soc"] = _to_float(state)
        elif entity_id == data.get("car_end_entity"):
            self.car["end"] = state.state if state and state.state not in (
                "unknown", "unavailable", None
            ) else None
        elif entity_id == data.get("car_location_entity"):
            self.car["location"] = state.state if state else None
        elif entity_id == data.get("car_power_entity"):
            self.car["power"] = _to_float(state)

    # ------------------------------------------------------------------
    # Modbus-Diagnose (für sensor.pvsc_modbus_*)
    # ------------------------------------------------------------------
    @property
    def modbus_consecutive_failures(self) -> int:
        return self._modbus.consecutive_failures if self._modbus else 0

    @property
    def modbus_seconds_until_retry(self) -> float:
        return round(self._modbus.seconds_until_retry, 1) if self._modbus else 0.0

    # ------------------------------------------------------------------
    # Periodischer Tick: Wallbox-Zustand aktualisieren -> Regel-Logik ->
    # ggf. schreiben (nur wenn control_enabled)
    # ------------------------------------------------------------------
    async def _async_tick(self, _now=None) -> None:
        if self._tick_running:
            # async_track_time_interval wartet nicht auf den vorherigen
            # Aufruf - falls ein Modbus-Vorgang (z.B. durch Timeout) mal
            # länger braucht als das Poll-Intervall, würde sonst ein
            # zweiter Tick parallel starten. Lieber diesen Durchlauf
            # überspringen, als zwei _calculate()/_apply_changes()-Läufe
            # gleichzeitig laufen zu lassen.
            _LOGGER.warning(
                "PVSC: vorheriger Tick läuft noch (Modbus-Vorgang langsam?) - "
                "dieser Tick wird übersprungen, um Überlappung zu vermeiden"
            )
            return
        self._tick_running = True
        try:
            # Wallbox-Zustand wird IMMER direkt per Modbus gelesen -
            # control_enabled steuert ausschließlich, ob auch geschrieben
            # wird (Start/Stopp/Ampere/Phasen).
            await self._poll_modbus_direct()

            self._sync_state_from_em2go()
            await self._maybe_notify_charging_change()

            changes = self._calculate()
            if changes.get("made"):
                await self._apply_changes(changes)

            # plug_changed ist ein "einmaliges" Ereignis-Flag - nach
            # Verbrauch durch _calculate() (und ggf. _apply_changes())
            # zurücksetzen, damit es nicht dauerhaft hängen bleibt (analog
            # zum Reset in der Original-Flow-Function nach erfolgreicher
            # Übermittlung).
            self.em2go["plug_changed"] = False

            self._push_updates()
        finally:
            self._tick_running = False

    async def _maybe_notify_charging_change(self) -> None:
        """Meldung bei Ladestart/-stopp (Ersatz für die Node-RED
        Telegram-Nachrichten). Die Ziel-Entity ist per Options-Flow
        konfigurierbar (notify_entity); notify_enabled=False schaltet
        die Meldungen ab. Kein Versand beim allerersten Tick nach dem
        Start und - beim Stopp - wenn kein Stecker steckt (z.B.
        Wallbox-Neustart ohne Auto)."""
        charging = self.em2go["state"] in (3, 4)
        prev = self._last_charging
        self._last_charging = charging
        if prev is None or charging == prev:
            return
        if not self.entry.options.get("notify_enabled", True):
            return
        notify_entity = self.entry.options.get("notify_entity", DEFAULT_NOTIFY_ENTITY)
        if not notify_entity:
            return

        en = self._lang() == "en"

        if charging:
            if en:
                message = (
                    "Wallbox: charging started\n"
                    f"Meter: {self.em2go['energy']:g} kWh\n"
                    f"Current: {self.em2go['ampere']:g} A"
                )
            else:
                message = (
                    "Wallbox: Ladung gestartet\n"
                    f"Zähler: {self.em2go['energy']:g} kWh\n"
                    f"Strom: {self.em2go['ampere']:g} A"
                )
        else:
            unplugged = self.em2go["plug"] != 1
            if unplugged and not self.em2go.get("plug_changed"):
                # Kein Stecker und auch kein frischer Stecker-Wechsel in
                # diesem Tick -> vermutlich Wallbox-Neustart ohne Auto,
                # keine Meldung (wie im Node-RED-Flow). Ein ECHTES
                # Abstecken (plug_changed=True) meldet dagegen sehr wohl.
                return
            if en:
                grund = "Unplugged" if unplugged else self.stop_cause_text
                message = (
                    "Wallbox: charging finished\n"
                    f"Charged: {self.em2go['loaded_kwh']:g} kWh\n"
                    f"Meter: {self.em2go['energy']:g} kWh\n"
                    f"Reason: {grund}"
                )
            else:
                grund = "Stecker gezogen" if unplugged else self.stop_cause_text
                message = (
                    "Wallbox: Ladung beendet\n"
                    f"Geladen: {self.em2go['loaded_kwh']:g} kWh\n"
                    f"Zähler: {self.em2go['energy']:g} kWh\n"
                    f"Grund: {grund}"
                )
        if self.has_car_soc and self.car["soc"] >= 0:
            message += (
                f"\nCar: {round(self.car['soc'])} %"
                if en
                else f"\nAuto: {round(self.car['soc'])} %"
            )

        try:
            await self.hass.services.async_call(
                "notify",
                "send_message",
                {"entity_id": notify_entity, "message": message},
                blocking=False,
            )
        except Exception as err:  # noqa: BLE001 - Meldung darf Regelung nie stören
            _LOGGER.warning(
                "PVSC: Benachrichtigung über %s fehlgeschlagen: %s", notify_entity, err
            )

    def _sync_state_from_em2go(self) -> None:
        """Gleicht self.state IMMER an den tatsächlichen (gelesenen oder
        gespiegelten) Wallbox-Zustand an - unabhängig davon, wer gerade
        steuert. State 3=Starting, 4=Charging gelten als "lädt"."""
        actually_charging = self.em2go["state"] in (3, 4)
        if actually_charging != self.state:
            self.state = actually_charging

    async def _poll_modbus_direct(self) -> None:
        assert self._modbus is not None
        try:
            values: dict[str, list[int]] = {}
            for name, address, quantity in MODBUS_READS:
                values[name] = await self._modbus.read_holding_registers(address, quantity)

            prev_plug = self.em2go["plug"]
            state_plug_error = values["state_plug_error"]
            new_state = state_plug_error[0]
            new_plug = state_plug_error[1] if len(state_plug_error) > 1 else -1
            new_error = state_plug_error[2] if len(state_plug_error) > 2 else -1

            self.em2go["plug_changed"] = prev_plug not in (-1, new_plug) and prev_plug != new_plug
            self.em2go["state"] = new_state
            self.em2go["plug"] = new_plug
            self.em2go["error"] = new_error
            self.em2go["power"] = _u32(values["power"])
            self.em2go["l1"] = _u32(values["l1"])
            self.em2go["l2"] = _u32(values["l2"])
            self.em2go["l3"] = _u32(values["l3"])
            # Register 28 liefert kWh*10 (per Vergleich mit dem historischen
            # Zählerstand verifiziert), NICHT Wh -> auf echte kWh normieren.
            self.em2go["energy"] = _u32(values["energy"]) / 10
            # Register liefert Ampere*10 bzw. kWh*10 - hier auf die
            # einheitliche interne Darstellung (echte Ampere/kWh) umrechnen.
            self.em2go["loaded_kwh"] = values["loaded"][0] / 10
            self.em2go["time"] = _u32(values["time"])
            self.em2go["err_limit"] = values["err_limit"][0]
            self.em2go["ampere"] = values["ampere"][0] / 10
            self.em2go["mode"] = values["mode"][0]
            self.em2go["phases"] = values["phases"][0]

            self.modbus_ok = True
            self.modbus_last_error = None
        except ModbusCooldownError as err:
            # Erwartetes Verhalten während des Cool-downs - kein neuer Fehler,
            # daher nur Debug-Log statt Warnung bei jedem Tick.
            self.modbus_ok = False
            self.modbus_last_error = str(err)
            _LOGGER.debug("PVSC Modbus Cool-down: %s", err)
        except ModbusError as err:
            self.modbus_ok = False
            self.modbus_last_error = str(err)
            _LOGGER.warning("PVSC Modbus-Fehler: %s", err)

    async def _apply_changes(self, changes: dict) -> None:
        if not self.control_enabled:
            _LOGGER.debug(
                "PVSC Steuerung aus: würde jetzt %s ausführen, control_enabled ist aus",
                changes,
            )
            return
        assert self._modbus is not None

        if "state" in changes:
            now_ts = time.time()
            recent = [t for t in self.switch_history if now_ts - t < SWITCH_RATE_LIMIT_WINDOW]
            if len(recent) >= SWITCH_RATE_LIMIT_MAX:
                _LOGGER.warning(
                    "PVSC Rate-Limit: %d Schaltvorgänge in 15 Min - Schaltung blockiert",
                    len(recent),
                )
                self.state = changes["state"]["old"]
                self.state_change_ts = 0
            else:
                recent.append(now_ts)
                self.switch_history = recent
                try:
                    await self._modbus.write_single_register(
                        REG_ACTION, ACTION_START if changes["state"]["new"] else ACTION_STOP
                    )
                except ModbusError as err:
                    _LOGGER.error("PVSC: Fehler beim Schreiben von state: %s", err)

        if "ampere" in changes:
            try:
                await self._modbus.write_single_register(
                    REG_AMPERE, int(round(changes["ampere"]["new"] * 10))
                )
            except ModbusError as err:
                _LOGGER.error("PVSC: Fehler beim Schreiben von ampere: %s", err)

        if "phases" in changes:
            try:
                await self._modbus.write_single_register(REG_PHASES, changes["phases"]["new"])
            except ModbusError as err:
                _LOGGER.error("PVSC: Fehler beim Schreiben von phases: %s", err)

        if "err_limit" in changes:
            try:
                await self._modbus.write_single_register(REG_ERR_LIMIT, changes["err_limit"]["new"])
            except ModbusError as err:
                _LOGGER.error("PVSC: Fehler beim Schreiben von err_limit: %s", err)

    # ------------------------------------------------------------------
    # Die eigentliche Regel-Logik - 1:1 Port von pvFlow.js PvSurplusCalculation
    # ------------------------------------------------------------------
    def _calculate(self) -> dict:  # noqa: C901 - bewusst 1:1 zur Vorlage
        now = time.time()
        home = self.home
        car = self.car
        em2go = self.em2go
        s = self.settings

        override_mode = self.override.get("mode", "pv")
        changes: dict = {}

        # Sicherheits-Gate: alle konfigurierten Kern-Sensoren (PV, Last,
        # Netzbezug/-einspeisung, Batterie, Heimspeicher-SOC) müssen
        # mindestens einmal einen echten Wert geliefert haben (nicht mehr
        # beim Start-Sentinel -1 stehen), bevor überhaupt geladen wird.
        # Verhindert Fehlentscheidungen durch fehlende/kaputte Sensoren
        # oder direkt nach einem HA-Neustart, bevor Zustände nachgeladen sind.
        core_ready = all(home[field] != -1 for field in self.core_ready_fields)
        self.core_ready = core_ready

        # Ohne Heimspeicher: SOC-Logik neutralisieren (wie "Speicher voll") -
        # SOC-Gate immer offen, Korrekturfaktor wird weiter unten fixiert.
        soc = home["soc"] if self.has_battery else 100.0

        max_load = self.entry.options.get("max_load", 4200)
        battery_kwh = self.entry.options.get("battery_kwh", 6.9)
        max_battery_discharge = self.entry.options.get("max_battery_discharge", 3000)
        inverter_max_output = self.entry.options.get("inverter_max_output", 4800)

        min_soc = s["min_soc"]
        optimal_soc = s["optimal_soc"]
        high_soc = s["high_soc"]

        # Bei schlechter PV-Prognose (< 2x Restkapazität Batterie) strengere SOC-Grenzen
        if self.has_battery and self.pv_forecast < (battery_kwh * ((100 - soc) / 100) * 2):
            min_soc, optimal_soc, high_soc = 80, 90, 95

        local_now = dt_util.now()

        # ── Override: stop ──────────────────────────────────────────
        if override_mode == "stop":
            if self.state is True or em2go["plug_changed"]:
                changes["made"] = True
                changes["state"] = {"old": self.state, "new": False}
                self.state = False
            self.status_text = "🚫 Override: STOP"
            self.status_color = "grey"
            return changes

        # Nächtliches Zurücksetzen des Abbruchgrundes (0-5 Uhr)
        if self.stop_cause and 0 <= local_now.hour <= 5:
            self.stop_cause = STOP_CAUSE_NONE

        self.pv = home["pv"]

        min_a = 6 + (0 if self.state else 1)
        # Maximaler Ladestrom per Option (16 A = 11-kW-, 32 A = 22-kW-Version)
        max_a = self.entry.options.get("max_ampere", MAX_A)
        # Mindestleistung für die Start/Stopp-Entscheidung: Bei aktiver
        # Phasenautomatik zählt das 1-PHASIGE Minimum - fällt der Überschuss
        # unter das 3-phasige Minimum, wird runtergeschaltet statt gestoppt.
        min_phases = em2go["phases"] if em2go["phases"] in (1, 3) else 1
        if s.get("phase_auto"):
            min_phases = 1
        min_watts = min_a * min_phases * VOLT

        # ── Überschussberechnung ────────────────────────────────────
        surplus_mode = s["surplus_mode"]
        if surplus_mode == "saldo" and (
            home["import"] < 0 or home["export"] < 0 or home["charge"] < 0 or home["discharge"] < 0
        ):
            surplus_mode = "load (saldo-fallback)"

        if surplus_mode == "saldo":
            surplus = round(
                em2go["power"] + home["export"] - home["import"] + home["charge"] - home["discharge"]
            )
            self.load = round(self.pv - surplus)
            surplus = max(surplus, 0)
        else:
            self.load = home["load"] - em2go["power"]
            surplus = round(max(self.pv - self.load, 0))

        self.surplus = surplus
        car_surplus = surplus

        # ── SOC-abhängige Batterienutzung als Puffer ────────────────
        self.battery.support_watts = 0
        if car_surplus < min_watts:
            self.battery.support_watts = max(min_watts - car_surplus, 0)
            # Wechselrichter-Ausgangslimit nur anwenden, wenn eine PV1-Quelle
            # konfiguriert ist - ohne sie gäbe es nur den Sentinel-Wert -1,
            # was die Klammer sinnlos verfälschen würde.
            if self.has_pv1 and (home["pv1"] + self.battery.support_watts) > inverter_max_output:
                self.battery.support_watts = max(0, inverter_max_output - home["pv1"])
            if home["discharge"] > max_battery_discharge or (
                home["discharge"] + self.battery.support_watts > max_battery_discharge
            ):
                self.battery.support_watts = 0

        if now > (self.battery.usage_cache_ts + 60):
            self.battery.add_minute_sample(now)
        else:
            self.battery.add_tick_sample()

        if not self.has_battery:
            # Ohne Heimspeicher: keine SOC-Stufen, keine Batterie-Unterstützung.
            # Faktor 1.0 = Überschuss wird 1:1 genutzt (manueller Faktor über
            # correction_auto=aus weiterhin möglich).
            self.correction_faktor = 1.0
            self.battery.support_watts = 0
        elif soc >= high_soc:
            self.correction_faktor = 1.05 if self.battery.support_watts < 50 else 1.0
            if local_now.hour >= 15 and self.pv_forecast < 5:
                self.correction_faktor = 0.9
                self.battery.support_watts = 0
        elif soc >= optimal_soc:
            self.correction_faktor = 0.9
        elif soc >= min_soc:
            self.correction_faktor = 0.75
            self.battery.support_watts = 0
        else:
            self.correction_faktor = 0
            self.battery.support_watts = 0

        battery_avg = self.battery.cache_avg()
        if self.battery.support_watts > 50 and (
            self.stop_cause > 0
            or (self.load + self.battery.support_watts) > max_load
            or battery_avg > min_watts
            or soc <= high_soc
        ):
            self.battery.support_watts = 0

        if self.stop_cause > 0 and car_surplus > min_watts and self.battery.support_watts < 50:
            self.stop_cause = STOP_CAUSE_NONE

        corr_auto = s["correction_auto"]
        if not corr_auto:
            self.correction_faktor = s["correction_factor"] / 100

        car_surplus = round(surplus * self.correction_faktor + self.battery.support_watts)
        car_surplus = max(0, car_surplus)
        if em2go["power"] > 0:
            self.surplus = surplus - car_surplus
        self.car_surplus = car_surplus

        target_ampere = round(car_surplus / (VOLT * max(em2go["phases"], 1)) * 10) / 10
        target_ampere = min(max_a, max(min_a, target_ampere))

        forced_ampere = s.get("forced_ampere", 0)
        if forced_ampere > 0:
            target_ampere = max_a
        elif override_mode == "manual":
            target_ampere = min(max_a, max(6, self.override.get("ampere", 6)))
            target_phases = self.override.get("phases", 1)
            if em2go["phases"] != target_phases:
                changes["made"] = True
                changes["phases"] = {"old": em2go["phases"], "new": target_phases}
        else:
            # PV-Modus: Standard ist 1-phasig. Mit aktivierter Phasen-
            # automatik wird während des Ladens auf 3 Phasen hochgeschaltet,
            # wenn der Auto-Überschuss PHASE_CHANGE_DELAY lang über
            # PHASE_UP_WATTS liegt - und zurück auf 1 Phase, wenn er so
            # lange unter PHASE_DOWN_WATTS fällt (Hysterese gegen Flattern).
            desired_phases = 1
            if s.get("phase_auto") and self.state and em2go["plug"] == 1:
                if em2go["phases"] == 3:
                    desired_phases = 3
                    if car_surplus < PHASE_DOWN_WATTS:
                        if not self.phase_change_ts:
                            self.phase_change_ts = now
                        elif (now - self.phase_change_ts) > PHASE_CHANGE_DELAY:
                            desired_phases = 1
                            self.phase_change_ts = 0
                    else:
                        self.phase_change_ts = 0
                else:
                    if car_surplus > PHASE_UP_WATTS:
                        if not self.phase_change_ts:
                            self.phase_change_ts = now
                        elif (now - self.phase_change_ts) > PHASE_CHANGE_DELAY:
                            desired_phases = 3
                            self.phase_change_ts = 0
                    else:
                        self.phase_change_ts = 0
            else:
                self.phase_change_ts = 0

            if em2go["phases"] not in (-1, desired_phases):
                changes["made"] = True
                changes["phases"] = {"old": em2go["phases"], "new": desired_phases}

        if em2go["err_limit"] != FIXED_ERR_LIMIT:
            changes["made"] = True
            changes["err_limit"] = {"old": em2go["err_limit"], "new": FIXED_ERR_LIMIT}

        self.target_ampere = target_ampere

        target_state = (
            (forced_ampere > 0 or override_mode == "manual" or car_surplus >= min_watts)
            and soc >= min_soc
            and em2go["plug"] == 1
            and (not self.has_car_location or car["location"] == "home")
            and self.enabled
            and em2go["state"] != 6
            and core_ready
        )
        self.target_state = target_state

        # state_change_on_delay/off_delay und ampere_change_delay sind seit
        # 0.5.0b5 per Options-Flow konfigurierbar (siehe config_flow.py). Die
        # DEFAULT_*-Konstanten greifen nur, solange noch keine eigene
        # Einstellung gespeichert wurde. STATE_CHANGE_INTERVAL/
        # AMPERE_CHANGE_INTERVAL bleiben bewusst fest (siehe const.py).
        opts = self.entry.options
        state_change_on_delay = opts.get("state_change_on_delay", DEFAULT_STATE_CHANGE_ON_DELAY)
        state_change_off_delay = opts.get("state_change_off_delay", DEFAULT_STATE_CHANGE_OFF_DELAY)
        ampere_change_delay = opts.get("ampere_change_delay", DEFAULT_AMPERE_CHANGE_DELAY)

        state_change_delay = state_change_on_delay if target_state else state_change_off_delay
        state_change_needed = self.state != target_state or em2go["plug_changed"]
        deadband = s["ampere_deadband"]
        ampere_change_needed = abs(self.ampere - target_ampere) >= deadband or em2go["plug_changed"]
        state_change_allowed = (
            not self.state_change_ts
            or em2go["plug_changed"]
            or (
                (now - self.state_change_ts) > state_change_delay
                and (now - self.last_state_change_ts) > STATE_CHANGE_INTERVAL
            )
        )
        ampere_change_allowed = (
            not self.ampere_change_ts
            or em2go["plug_changed"]
            or (
                (now - self.ampere_change_ts) > ampere_change_delay
                and (now - self.last_ampere_change_ts) > AMPERE_CHANGE_INTERVAL
            )
        )

        if em2go["plug"] == 1:
            if state_change_needed:
                if not self.state_change_ts and not em2go["plug_changed"]:
                    self.state_change_ts = now
                elif state_change_allowed:
                    if target_state is False:
                        # Abbruchgrund bestimmen. Reihenfolge/Schwellen:
                        # 1) Hohe Batterienutzung (battery_avg > 500 W) - unabhängig
                        #    vom SOC-Band, weil das auf eine kritisch hohe
                        #    Entladeleistung hindeutet, die man so oder so
                        #    sehen will.
                        # 2) Heimspeicher-SOC unter der ECHTEN Untergrenze
                        #    min_soc (nicht optimal_soc!) - das ist die Stufe,
                        #    unter der laut Konfiguration gar nicht mehr
                        #    geladen werden soll (target_state oben enthält
                        #    dafür bereits "soc >= min_soc").
                        # 3) Andere Gründe, warum target_state False wurde und
                        #    die schon einen eigenen, aussagekräftigeren
                        #    Status-Text haben (_build_status_text) - hier
                        #    bewusst KEINEN "zu wenig PV"-Grund setzen, sonst
                        #    wäre z.B. "Automatik deaktiviert" oder "Auto
                        #    nicht zuhause" fälschlich als PV-Mangel gemeldet.
                        # 4) Alles andere: schlicht zu wenig PV-Überschuss
                        #    (inkl. Fälle, in denen soc zwischen min_soc und
                        #    optimal_soc liegt und die Batterie deshalb nicht
                        #    mehr aushelfen darf - siehe Antwort im Chat: das
                        #    ist keine "SOC zu niedrig"-Situation im Sinne der
                        #    echten Untergrenze, sondern schlicht ein PV-
                        #    Engpass, den die Batterie-Politik nicht mehr
                        #    ausgleicht).
                        if battery_avg > 500:
                            self.stop_cause = STOP_CAUSE_HIGH_BATTERY_USAGE
                        elif soc < min_soc:
                            self.stop_cause = STOP_CAUSE_LOW_SOC
                        elif (
                            not self.enabled
                            or em2go["state"] == 6
                            or (self.has_car_location and car["location"] != "home")
                            or not core_ready
                        ):
                            self.stop_cause = STOP_CAUSE_NONE
                        else:
                            self.stop_cause = STOP_CAUSE_LOW_SURPLUS
                        self.last_ampere_change_ts = now
                        self.ampere_change_ts = 0
                        target_ampere = min_a
                        self.target_ampere = min_a
                        self.ampere = min_a
                    else:
                        self.stop_cause = STOP_CAUSE_NONE

                    changes["made"] = True
                    changes["state"] = {"old": self.state, "new": target_state}
                    self.state = target_state
                    self.last_state_change_ts = self.state_change_ts
                    self.state_change_ts = 0
                    self.last_update = now
            else:
                self.state_change_ts = 0
        else:
            if em2go["plug_changed"]:
                self.state = False
                self.target_state = False
                target_ampere = min_a
                self.target_ampere = min_a
                self.ampere = min_a
                changes["made"] = True
                changes["state"] = {"old": self.state, "new": False}
                self.state_change_ts = 0
                self.ampere_change_ts = 0
                self.last_update = 0

        if self.state is True:
            if ampere_change_needed:
                if not self.ampere_change_ts and not em2go["plug_changed"]:
                    self.ampere_change_ts = now
                elif ampere_change_allowed:
                    changes["made"] = True
                    changes["ampere"] = {"old": self.ampere, "new": target_ampere}
                    self.ampere = target_ampere
                    self.last_ampere_change_ts = self.ampere_change_ts
                    self.ampere_change_ts = 0
                    self.last_update = now
            else:
                self.ampere_change_ts = 0

        self._build_status_text(
            override_mode, corr_auto, battery_avg, surplus_mode, state_change_needed,
            ampere_change_needed,
        )
        return changes

    def _build_status_text(
        self, override_mode, corr_auto, battery_avg, surplus_mode,
        state_change_needed, ampere_change_needed,
    ) -> None:
        """Kurzer Klartext-Status ohne Icons und ohne redundante Messwerte -
        PV, Hauslast, SOC, Überschuss usw. haben ihre eigenen Sensoren.
        Sprache folgt der HA-Systemsprache (siehe _lang())."""
        home = self.home
        em2go = self.em2go
        en = self._lang() == "en"

        if not getattr(self, "core_ready", True):
            text = "Waiting for sensor data" if en else "Warte auf Sensordaten"
        elif override_mode == "stop":
            text = "Stopped (override)" if en else "Gestoppt (Override)"
        elif em2go["plug"] != 1:
            text = "No vehicle connected" if en else "Kein Fahrzeug angeschlossen"
        elif self.state:
            if en:
                text = "Charging manually" if override_mode == "manual" else "Charging"
                text += f" at {self.ampere:g} A"
                if override_mode != "manual" and abs(self.target_ampere - self.ampere) >= 0.05:
                    text += f", target {self.target_ampere:g} A"
            else:
                text = "Lädt manuell" if override_mode == "manual" else "Lädt"
                text += f" mit {self.ampere:g} A"
                if override_mode != "manual" and abs(self.target_ampere - self.ampere) >= 0.05:
                    text += f", Ziel {self.target_ampere:g} A"
        elif self.target_state:
            text = "Start scheduled" if en else "Start geplant"
        elif not self.enabled:
            text = "Automation disabled" if en else "Automatik deaktiviert"
        elif self.stop_cause:
            text = (
                f"Stopped: {self.stop_cause_text}" if en else f"Gestoppt: {self.stop_cause_text}"
            )
        elif em2go["state"] == 6:
            text = "Charging finished" if en else "Laden beendet"
        elif self.has_battery and home["soc"] < self.settings["min_soc"]:
            text = (
                "Waiting: home battery SOC too low"
                if en
                else "Wartet: Heimspeicher-SOC zu niedrig"
            )
        else:
            text = "Waiting for PV surplus" if en else "Wartet auf PV-Überschuss"

        color = "yellow"
        if self.state:
            color = "green"
        if state_change_needed or ampere_change_needed:
            color = "blue"
        if home["import"] > 100:
            color = "red"
        if self.has_battery and home["soc"] < min(self.settings["min_soc"], 100):
            color = "grey"

        if not getattr(self, "core_ready", True):
            color = "grey"

        if not self.control_enabled:
            text = ("Control off: " + text) if en else ("Steuerung aus: " + text)

        self.status_text = text
        self.status_color = color


def _u32(regs: list[int]) -> float:
    """Kombiniert zwei 16-Bit Register zu einem vorzeichenlosen 32-Bit Wert (High-Word zuerst)."""
    if len(regs) < 2:
        return float(regs[0]) if regs else -1.0
    return float((regs[0] << 16) | regs[1])
