"""EM2GO Home PV-Überschussladen (pvsc).

PV-Überschussladen für die EM2GO Home Wallbox per Modbus TCP. Solange
switch.pvsc_control_enabled aus ist, liest die Integration nur und greift
nicht in die Wallbox-Steuerung ein.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import PVSCCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    # Migration: Die EM2GO Wallbox antwortet nur auf Unit-ID 255 (per
    # Direkttest bestätigt; Unit 0 = Broadcast -> keine Antwort -> Timeout).
    # Alte Einträge, die noch mit dem früheren Default 0 angelegt wurden,
    # werden hier einmalig auf 255 korrigiert.
    if entry.data.get("modbus_unit", 0) == 0:
        _LOGGER.warning(
            "PVSC: Modbus Unit-ID 0 im Config-Eintrag gefunden - wird auf 255 "
            "migriert (Wallbox antwortet nur auf Unit-ID 255)"
        )
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "modbus_unit": 255}
        )

    # Umbenennung: alter Test-Titel -> sprechender Name.
    if entry.title in ("PV Überschussladen (Test)", "PV Überschussladen"):
        hass.config_entries.async_update_entry(
            entry, title="EM2GO Home PV-Überschussladen"
        )

    # Migration: Einträge von vor Einführung des Setup-Felds
    # "control_on_start" verhielten sich wie control_on_start=True
    # (Steuerung nach Start aktiv) - das bleibt für sie erhalten.
    # Neue Installationen wählen das explizit im Setup (Default: aus).
    if "control_on_start" not in entry.data:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "control_on_start": True}
        )

    # Migration: Schatten-Modus wurde entfernt - übrig gebliebene
    # shadow_*-Felder aus alten Einträgen ausräumen.
    if any(k.startswith("shadow_") for k in entry.data):
        hass.config_entries.async_update_entry(
            entry,
            data={k: v for k, v in entry.data.items() if not k.startswith("shadow_")},
        )

    coordinator = PVSCCoordinator(hass, entry)
    await coordinator.async_setup()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: PVSCCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_unload()
    return unload_ok
