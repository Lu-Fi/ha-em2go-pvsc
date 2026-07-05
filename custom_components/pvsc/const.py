"""Constants for the EM2GO Home PV-Überschussladen (pvsc) integration.

PV-Überschussladen für die EM2GO Home Wallbox per Modbus TCP. Der
Wallbox-Zustand wird immer direkt per Modbus gelesen; GESCHRIEBEN
(Start/Stopp/Ampere/Phasen) wird nur, solange der Schalter
`switch.pvsc_control_enabled` an ist.

WICHTIG: Die EM2GO-Wallbox akzeptiert nur EINE gleichzeitige
Modbus-TCP-Verbindung - es darf also kein zweites System (z.B. Node-RED)
parallel mit der Box sprechen.
"""
from __future__ import annotations

DOMAIN = "pvsc"
PLATFORMS = ["sensor", "binary_sensor", "switch", "number", "select", "button"]

# Version des persistierten "live" Zustands (Store-Helper). Bei inkompatiblen
# Änderungen am gespeicherten Schema hochzählen und ggf. async_migrate_func
# im Store ergänzen.
STORAGE_VERSION = 1

# ---------------------------------------------------------------------------
# Config-Entry Keys (beim Einrichten festgelegt, änderbar über "Konfigurieren")
# ---------------------------------------------------------------------------
CONF_MODBUS_HOST = "modbus_host"
CONF_MODBUS_PORT = "modbus_port"
CONF_MODBUS_UNIT = "modbus_unit"

CONF_PV_ENTITY = "pv_entity"                      # aktuelle PV-Gesamtleistung (W)
CONF_PV1_ENTITY = "pv1_entity"                    # Wechselrichter PV-Leistung (für 4800W-Limit)
CONF_LOAD_ENTITY = "load_entity"                  # Hauslast (W)
CONF_IMPORT_ENTITY = "import_entity"              # Netzbezug (W)
CONF_EXPORT_ENTITY = "export_entity"               # Netzeinspeisung (W)
CONF_BATTERY_CHARGE_ENTITY = "battery_charge_entity"
CONF_BATTERY_DISCHARGE_ENTITY = "battery_discharge_entity"
CONF_HOME_SOC_ENTITY = "home_soc_entity"          # Heimspeicher SOC (%)
CONF_PV_FORECAST_ENTITY = "pv_forecast_entity"    # PV-Prognose Rest-Tag (kWh), optional
CONF_CAR_SOC_ENTITY = "car_soc_entity"
CONF_CAR_END_ENTITY = "car_end_entity"
CONF_CAR_LOCATION_ENTITY = "car_location_entity"
CONF_CAR_POWER_ENTITY = "car_power_entity"        # optional, nur Anzeige

# ---------------------------------------------------------------------------
# Optionen (technische Parameter, per Options-Flow änderbar)
# ---------------------------------------------------------------------------
OPT_MAX_LOAD = "max_load"
OPT_BATTERY_KWH = "battery_kwh"
OPT_MAX_BATTERY_DISCHARGE = "max_battery_discharge"
OPT_INVERTER_MAX_OUTPUT = "inverter_max_output"
OPT_POLL_INTERVAL = "poll_interval"
OPT_MODBUS_TIMEOUT = "modbus_timeout"
OPT_MODBUS_COMMAND_DELAY = "modbus_command_delay"
OPT_MODBUS_RECONNECT_BACKOFF = "modbus_reconnect_backoff"
OPT_MODBUS_CONNECT_SETTLE_DELAY = "modbus_connect_settle_delay"
OPT_MODBUS_FRAMING = "modbus_framing"
OPT_NOTIFY_ENABLED = "notify_enabled"
OPT_NOTIFY_ENTITY = "notify_entity"

OPT_MAX_AMPERE = "max_ampere"
CONF_CONTROL_ON_START = "control_on_start"

# Start-/Stopp- und Ampere-Anpassungs-Hysterese (Sekunden) - von 0.5.0b5 bis
# 0.5.0b5 im Options-Flow, seit 0.5.0b6 als number-Entities PRO WALLBOX
# (settings-Keys "state_change_on_delay" / "state_change_off_delay" /
# "ampere_change_delay", siehe DEFAULT_SETTINGS unten). Die alten
# Options-Schlüssel bleiben hier nur für die einmalige Migration bestehender
# Einträge definiert (coordinator._async_load_persisted_state()).
OPT_STATE_CHANGE_ON_DELAY = "state_change_on_delay"
OPT_STATE_CHANGE_OFF_DELAY = "state_change_off_delay"
OPT_AMPERE_CHANGE_DELAY = "ampere_change_delay"

# Notify-Ziel für Ladestart/-stopp-Meldungen. Per Options-Flow wählbar
# (beliebige notify-Entity, z.B. Telegram oder App-Push). Leer = keine
# Meldungen. Bewusst KEIN vorbelegtes Ziel, damit die Integration ohne
# Anpassung in fremden Installationen nutzbar ist.
DEFAULT_NOTIFY_ENTITY = ""

DEFAULT_MODBUS_FRAMING = "mbap"  # "rtu" oder "mbap" - per Options-Flow umschaltbar.
# Bestätigt via Node-RED modbus-client Node-Konfiguration: "TCP Type: DEFAULT"
# bedeutet echtes Modbus-TCP/MBAP-Framing (node-red-contrib-modbus reserviert
# eigene TCP-Type-Werte für Gateway-Spezialfälle wie RTU-über-TCP-Bridges -
# "DEFAULT" ist explizit das Standardprotokoll, keine Bridge-Sonderbehandlung).
DEFAULT_MODBUS_PORT = 502
# Unit-ID 255 ist zwingend: Direkttest (2026-07-04) gegen die Wallbox ergab,
# dass sie NUR auf Unit-ID 255 antwortet (Unit 0 -> keine Antwort/Timeout,
# Unit 1 -> Verbindungsabbruch). Entspricht der unit_id=255 des Node-RED
# modbus-client Nodes. In __init__.py werden Alt-Einträge mit Unit 0
# automatisch auf 255 migriert.
DEFAULT_MODBUS_UNIT = 255
DEFAULT_MAX_LOAD = 4200
DEFAULT_BATTERY_KWH = 6.9
DEFAULT_MAX_BATTERY_DISCHARGE = 3000
DEFAULT_INVERTER_MAX_OUTPUT = 4800
DEFAULT_POLL_INTERVAL = 7  # Sekunden, Kompromiss aus Reaktionszeit und Last

# Modbus-Robustheit - Defaults orientiert an der bewährten Node-RED
# modbus-client Konfiguration (clientTimeout=1000ms, commandDelay=100ms,
# reconnectTimeout=10000ms), leicht defensiver für parallelen Zugriff.
DEFAULT_MODBUS_TIMEOUT = 1.5          # Sekunden pro Request
DEFAULT_MODBUS_COMMAND_DELAY = 0.15   # Sekunden Pause zwischen Transaktionen
DEFAULT_MODBUS_RECONNECT_BACKOFF = 10.0  # Sekunden Cool-down nach Fehler (verdoppelt sich pro Folgefehler, Deckel 120s)
DEFAULT_MODBUS_CONNECT_SETTLE_DELAY = 0.25  # Sekunden Pause nach frischem Connect vor erster Anfrage

# ---------------------------------------------------------------------------
# Live einstellbare Werte (als number/switch/select Entities, wie zuvor die
# input_number/input_boolean Helper von Node-RED)
# ---------------------------------------------------------------------------
DEFAULT_MIN_SOC = 40
DEFAULT_OPTIMAL_SOC = 80
DEFAULT_HIGH_SOC = 90
DEFAULT_CORRECTION_FACTOR = 75  # %
DEFAULT_CORRECTION_AUTO = True
DEFAULT_AMPERE_DEADBAND = 0.1
DEFAULT_SURPLUS_MODE = "load"
DEFAULT_FORCED_AMPERE = 0
DEFAULT_ENABLED = True  # switch.pvsc_enabled (Überschuss-Automatik an/aus)

DEFAULT_OVERRIDE_MODE = "pv"
DEFAULT_OVERRIDE_AMPERE = 6
DEFAULT_OVERRIDE_PHASES = 1

# Automatische 1<->3-Phasenumschaltung (optional, switch.pvsc_phase_auto):
# Hochschalten, wenn der Auto-Überschuss PHASE_CHANGE_DELAY lang über
# PHASE_UP_WATTS liegt; runterschalten, wenn er so lange unter
# PHASE_DOWN_WATTS fällt. PHASE_UP_WATTS liegt bewusst über dem
# 3-phasigen Minimum (6 A x 3 x 230 V = 4140 W), damit nach dem
# Hochschalten nicht sofort wieder runtergeschaltet werden muss.
DEFAULT_PHASE_AUTO = False
PHASE_CHANGE_DELAY = 5 * 60  # Sekunden stabile Über-/Unterschreitung
PHASE_UP_WATTS = 7 * 3 * 230    # 4830 W
PHASE_DOWN_WATTS = 6 * 3 * 230  # 4140 W

# Werkseinstellungen für die "live" number/switch/select Werte. Werden beim
# ersten Start eines Config-Entries verwendet, beim "Reset to Default"-Button
# (button.pvsc_reset_defaults) sowie als Fallback, falls im Store (siehe
# coordinator.PVSCCoordinator._store) noch kein Wert für einen Schlüssel
# hinterlegt ist. Einzeln als DEFAULT_*-Konstanten oben gehalten, hier nur
# zu den Dicts zusammengefasst, die den Laufzeit-Strukturen in
# PVSCCoordinator.__init__ (self.settings / self.override) entsprechen.
# Hysterese-Delays (Sekunden) - seit 0.5.0b6 live einstellbar PRO WALLBOX
# über number-Entities (Teil von settings, persistiert im Store). Werte
# vorher im Options-Flow (0.5.0b5) bzw. fest kodiert (davor).
DEFAULT_STATE_CHANGE_ON_DELAY = 3 * 60
# Ursprünglich 3 Minuten wie beim Start (1:1 zum Node-RED Flow). Per
# Nutzerwunsch auf 1 Minute reduziert: bei einem Lastspitzen-bedingten
# Einbruch des PV-Überschusses (Überschuss, nicht zwingend PV-Produktion!)
# reagiert die Ladung so deutlich schneller mit einem echten Stopp, statt
# 3 Minuten lang mit Mindeststrom weiterzuladen.
DEFAULT_STATE_CHANGE_OFF_DELAY = 60
DEFAULT_AMPERE_CHANGE_DELAY = 30

DEFAULT_SETTINGS = {
    "min_soc": DEFAULT_MIN_SOC,
    "optimal_soc": DEFAULT_OPTIMAL_SOC,
    "high_soc": DEFAULT_HIGH_SOC,
    "correction_factor": DEFAULT_CORRECTION_FACTOR,
    "correction_auto": DEFAULT_CORRECTION_AUTO,
    "ampere_deadband": DEFAULT_AMPERE_DEADBAND,
    "surplus_mode": DEFAULT_SURPLUS_MODE,
    "forced_ampere": DEFAULT_FORCED_AMPERE,
    "phase_auto": DEFAULT_PHASE_AUTO,
    "state_change_on_delay": DEFAULT_STATE_CHANGE_ON_DELAY,
    "state_change_off_delay": DEFAULT_STATE_CHANGE_OFF_DELAY,
    "ampere_change_delay": DEFAULT_AMPERE_CHANGE_DELAY,
}
DEFAULT_OVERRIDE = {
    "mode": DEFAULT_OVERRIDE_MODE,
    "ampere": DEFAULT_OVERRIDE_AMPERE,
    "phases": DEFAULT_OVERRIDE_PHASES,
}

# Zeitkonstanten (Sekunden). Die einstellbaren Delays sind oben bei
# DEFAULT_STATE_CHANGE_ON_DELAY/OFF_DELAY/AMPERE_CHANGE_DELAY definiert
# (pro Wallbox über number-Entities, Teil von DEFAULT_SETTINGS).
#
# STATE_CHANGE_INTERVAL und AMPERE_CHANGE_INTERVAL bleiben bewusst fest
# (nicht konfigurierbar): das ist ein zusätzliches Rate-Limit, das verhindert,
# dass kurz nacheinander zwei Zustands-/Ampere-Änderungen passieren, selbst
# wenn die jeweilige *_DELAY schon abgelaufen ist - z.B. blockiert es einen
# Stopp weiterhin bis mindestens STATE_CHANGE_INTERVAL Sekunden seit der
# letzten Zustandsänderung vergangen sind, auch wenn state_change_off_delay
# kürzer eingestellt wurde.
STATE_CHANGE_INTERVAL = 3 * 60
AMPERE_CHANGE_INTERVAL = 30

MIN_A = 6
MAX_A = 16
VOLT = 230

SWITCH_RATE_LIMIT_MAX = 3
SWITCH_RATE_LIMIT_WINDOW = 15 * 60  # Sekunden

STOP_CAUSE_NONE = 0
STOP_CAUSE_HIGH_BATTERY_USAGE = 1
# STOP_CAUSE_LOW_SOC: Heimspeicher-SOC ist unter die ECHTE Untergrenze
# min_soc gefallen (nicht nur unter optimal_soc) - target_state ist in
# diesem Fall bereits über "soc >= min_soc" in _calculate() blockiert.
STOP_CAUSE_LOW_SOC = 2
# STOP_CAUSE_LOW_SURPLUS: schlichter PV-Engpass - inkl. der Fälle, in denen
# der SOC zwar zwischen min_soc und optimal_soc liegt (Batterie darf dort
# per Policy nicht mehr aushelfen) und der PV-Überschuss allein nicht
# reicht. Vor Version 0.5.1 wurde das fälschlich als "SOC zu niedrig"
# gemeldet, obwohl min_soc gar nicht unterschritten war.
STOP_CAUSE_LOW_SURPLUS = 3

# ---------------------------------------------------------------------------
# Zweisprachige Texte (DE/EN) für dynamische Sensor-Werte und Benachrichtigungen.
# Diese Texte werden NICHT über strings.json/translations übersetzt (das
# funktioniert nur für Entity-Namen), sondern folgen zur Laufzeit der
# HA-Systemsprache (Einstellungen -> System -> Allgemein -> Sprache) - siehe
# PVSCCoordinator._lang() in coordinator.py. Jede andere Systemsprache als
# Englisch fällt auf Deutsch zurück.
# ---------------------------------------------------------------------------
STOP_CAUSE_TEXT_DE = {
    0: "Kein Abbruch",
    1: "Hohe Batterienutzung",
    2: "SOC zu niedrig",
    3: "Zu wenig PV-Überschuss",
}
STOP_CAUSE_TEXT_EN = {
    0: "No stop",
    1: "High battery usage",
    2: "SOC too low",
    3: "Insufficient PV surplus",
}

EM2GO_STATE_TEXT_DE = {
    0: "Unbekannt",
    1: "Bereit",
    2: "Verbunden",
    3: "Starte…",
    4: "Lädt",
    5: "Fehler",
    6: "Laden beendet",
}
EM2GO_STATE_TEXT_EN = {
    0: "Unknown",
    1: "Ready",
    2: "Connected",
    3: "Starting…",
    4: "Charging",
    5: "Error",
    6: "Charging finished",
}

# Modbus-Register der EM2GO Wallbox (identisch zum bestehenden Node-RED Flow)
# (name, address, quantity)
MODBUS_READS = [
    ("state_plug_error", 0, 3),
    ("power", 12, 2),
    ("l1", 16, 2),
    ("l2", 20, 2),
    ("l3", 24, 2),
    ("energy", 28, 2),
    ("loaded", 72, 1),
    ("time", 78, 2),
    ("err_limit", 87, 1),
    ("ampere", 91, 1),
    ("mode", 93, 1),
    ("phases", 200, 1),
]

REG_ERR_LIMIT = 87
REG_AMPERE = 91
REG_ACTION = 95
REG_PHASES = 200
FIXED_ERR_LIMIT = 60

ACTION_START = 1
ACTION_STOP = 2

ATTR_OVERRIDE_MODE = "override_mode"
