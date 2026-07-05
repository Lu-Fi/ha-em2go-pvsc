"""Config- und Options-Flow für PV Überschussladen (Test)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DEFAULT_BATTERY_KWH,
    DEFAULT_INVERTER_MAX_OUTPUT,
    DEFAULT_MAX_BATTERY_DISCHARGE,
    DEFAULT_MAX_LOAD,
    DEFAULT_NOTIFY_ENTITY,
    MAX_A,
    DEFAULT_MODBUS_COMMAND_DELAY,
    DEFAULT_MODBUS_CONNECT_SETTLE_DELAY,
    DEFAULT_MODBUS_FRAMING,
    DEFAULT_MODBUS_PORT,
    DEFAULT_MODBUS_RECONNECT_BACKOFF,
    DEFAULT_MODBUS_TIMEOUT,
    DEFAULT_MODBUS_UNIT,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)


def _entity_selector(domain: str | list[str] | None = None):
    return selector.selector({"entity": {"domain": domain}} if domain else {"entity": {}})


def _sensor_selector():
    return _entity_selector("sensor")


DATA_SCHEMA = vol.Schema(
    {
        vol.Required("modbus_host"): str,
        vol.Required("modbus_port", default=DEFAULT_MODBUS_PORT): int,
        vol.Required("modbus_unit", default=DEFAULT_MODBUS_UNIT): int,
        # Sicherheit: Neue Installationen starten mit inaktiver Steuerung
        # (False) - die Integration liest dann nur und schreibt erst auf die
        # Wallbox, wenn der Nutzer das bewusst aktiviert (hier oder später
        # am Schalter "Steuerung aktiv").
        vol.Required("control_on_start", default=False): bool,
        vol.Required("pv_entity"): _sensor_selector(),
        # pv1_entity ist optional: wird nur für eine zusätzliche
        # Wechselrichter-Ausgangslimit-Klammer beim Batterie-Support genutzt.
        # Ohne sie funktioniert die restliche Logik unverändert.
        vol.Optional("pv1_entity"): _sensor_selector(),
        vol.Required("load_entity"): _sensor_selector(),
        vol.Required("import_entity"): _sensor_selector(),
        vol.Required("export_entity"): _sensor_selector(),
        # Heimspeicher ist optional: Ohne home_soc_entity entfallen die
        # SOC-Stufen und die Batterie-Unterstützung komplett (Korrekturfaktor
        # dann fix 1.0 bzw. manueller Wert) - für Haushalte ohne Batterie.
        vol.Optional("battery_charge_entity"): _sensor_selector(),
        vol.Optional("battery_discharge_entity"): _sensor_selector(),
        vol.Optional("home_soc_entity"): _sensor_selector(),
        vol.Optional("pv_forecast_entity"): _sensor_selector(),
        # car_*-Entities sind rein informativ bzw. optional; car_location:
        # WENN gesetzt, muss das Auto "home" sein, damit geladen wird.
        vol.Optional("car_soc_entity"): _sensor_selector(),
        vol.Optional("car_end_entity"): _sensor_selector(),
        vol.Optional("car_location_entity"): _entity_selector("device_tracker"),
        vol.Optional("car_power_entity"): _sensor_selector(),
    }
)


class PVSCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Einrichtungs-Dialog."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input['modbus_host']}:{user_input['modbus_port']}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="EM2GO Home PV-Überschussladen", data=user_input
            )

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Nachträgliches Ändern der Setup-Werte (Modbus-Host/IP, Port,
        Unit-ID, alle Sensor-Entities) über den Menüpunkt "Neu konfigurieren"
        am Config-Eintrag - ohne die Integration löschen und neu anlegen zu
        müssen. Die Live-Einstellungen (SOC-Stufen, Delays, Overrides, ...)
        bleiben dabei erhalten, weil sie im Store pro entry_id liegen und
        die entry_id unverändert bleibt."""
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            new_unique_id = f"{user_input['modbus_host']}:{user_input['modbus_port']}"
            # Duplikat-Schutz von Hand: Die unique_id ist "host:port". Ein
            # Wechsel auf die Adresse einer ANDEREN, bereits eingerichteten
            # Wallbox wird abgelehnt; die unveränderte eigene Adresse (oder
            # eine ganz neue) ist erlaubt.
            for other in self._async_current_entries():
                if other.entry_id != entry.entry_id and other.unique_id == new_unique_id:
                    return self.async_abort(reason="already_configured")
            # data=user_input ersetzt entry.data KOMPLETT (kein Merge):
            # nur so lässt sich eine optionale Entity (z.B. Auto-Sensor)
            # durch Leeren des Feldes auch wieder ENTFERNEN. Alle übrigen
            # Schlüssel (inkl. control_on_start) sind Teil des Formulars.
            return self.async_update_reload_and_abort(
                entry, unique_id=new_unique_id, data=user_input
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(DATA_SCHEMA, entry.data),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PVSCOptionsFlow(config_entry)


class PVSCOptionsFlow(config_entries.OptionsFlow):
    """Technische Feinabstimmung (selten geändert)."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self._config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    "notify_enabled",
                    default=opts.get("notify_enabled", True),
                ): bool,
                vol.Optional(
                    "notify_entity",
                    default=opts.get("notify_entity", DEFAULT_NOTIFY_ENTITY),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="notify")
                ),
                vol.Required(
                    "max_load", default=opts.get("max_load", DEFAULT_MAX_LOAD)
                ): vol.Coerce(int),
                vol.Required(
                    "battery_kwh", default=opts.get("battery_kwh", DEFAULT_BATTERY_KWH)
                ): vol.Coerce(float),
                vol.Required(
                    "max_battery_discharge",
                    default=opts.get("max_battery_discharge", DEFAULT_MAX_BATTERY_DISCHARGE),
                ): vol.Coerce(int),
                vol.Required(
                    "inverter_max_output",
                    default=opts.get("inverter_max_output", DEFAULT_INVERTER_MAX_OUTPUT),
                ): vol.Coerce(int),
                vol.Required(
                    "poll_interval",
                    default=opts.get("poll_interval", DEFAULT_POLL_INTERVAL),
                ): vol.Coerce(int),
                vol.Required(
                    "modbus_timeout",
                    default=opts.get("modbus_timeout", DEFAULT_MODBUS_TIMEOUT),
                ): vol.Coerce(float),
                vol.Required(
                    "modbus_command_delay",
                    default=opts.get("modbus_command_delay", DEFAULT_MODBUS_COMMAND_DELAY),
                ): vol.Coerce(float),
                vol.Required(
                    "modbus_reconnect_backoff",
                    default=opts.get(
                        "modbus_reconnect_backoff", DEFAULT_MODBUS_RECONNECT_BACKOFF
                    ),
                ): vol.Coerce(float),
                vol.Required(
                    "modbus_connect_settle_delay",
                    default=opts.get(
                        "modbus_connect_settle_delay", DEFAULT_MODBUS_CONNECT_SETTLE_DELAY
                    ),
                ): vol.Coerce(float),
                vol.Required(
                    "modbus_framing",
                    default=opts.get("modbus_framing", DEFAULT_MODBUS_FRAMING),
                ): vol.In(["rtu", "mbap"]),
                vol.Required(
                    "max_ampere",
                    default=opts.get("max_ampere", MAX_A),
                ): vol.All(vol.Coerce(int), vol.Range(min=6, max=32)),
                # Die Hysterese-Delays (Start-/Stopp-Verzögerung, Ampere-
                # Anpassungsverzögerung) sind seit 0.5.0b6 KEINE Optionen
                # mehr, sondern number-Entities pro Wallbox (number.pvsc_
                # state_change_on_delay usw.) - bestehende Options-Werte
                # werden beim ersten Start einmalig übernommen (siehe
                # coordinator._async_load_persisted_state()).
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
