"""EM2GO Home PV-Überschussladen (pvsc).

PV-Überschussladen für die EM2GO Home Wallbox per Modbus TCP. Solange
switch.pvsc_control_enabled aus ist, liest die Integration nur und greift
nicht in die Wallbox-Steuerung ein.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import persistent_notification
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS
from .coordinator import PVSCCoordinator

_LOGGER = logging.getLogger(__name__)

CARD_URL = "/pvsc/pvsc-card.js"


async def _async_register_card(hass: HomeAssistant) -> None:
    """Liefert die mitgelieferte Lovelace-Card (www/pvsc-card.js) selbst aus
    und lädt sie automatisch auf allen Dashboards - kein manuelles Kopieren
    nach config/www und keine Dashboard-Resource nötig."""
    if hass.data.get(f"{DOMAIN}_card_registered"):
        return
    hass.data[f"{DOMAIN}_card_registered"] = True

    card_path = Path(__file__).parent / "www" / "pvsc-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(card_path), cache_headers=False)]
    )
    # Versions-Anhang als Cache-Buster, damit Browser nach Updates die
    # neue Card laden.
    from homeassistant.loader import async_get_integration

    integration = await async_get_integration(hass, DOMAIN)
    add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")

    # add_extra_js_url wirkt nur in-memory und wird bei jedem HA-Neustart
    # neu aufgebaut. Bereits offene Browser-Tabs/Apps kennen die (neu)
    # registrierte Card erst nach einem harten Neuladen - bis dahin zeigt
    # jede "custom:pvsc-card" fälschlich "Konfigurationsfehler: Custom
    # element doesn't exist". Aktive Erinnerung statt stillem Fehlerbild.
    persistent_notification.async_create(
        hass,
        (
            f"Die pvsc-card (Version {integration.version}) wurde beim "
            "Start neu registriert. Bereits offene Dashboards/Apps zeigen "
            "bei 'custom:pvsc-card' bis zu einem harten Neuladen "
            "fälschlich 'Konfigurationsfehler: Custom element doesn't "
            "exist: pvsc-card'. Browser: Strg+Shift+R (bzw. Cmd+Shift+R) - "
            "Companion-App: App beenden und neu öffnen."
        ),
        title="PVSC: Karte neu geladen - Browser/App neu laden",
        notification_id="pvsc_card_reload",
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    await _async_register_card(hass)

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

    _async_apply_id_prefix(hass, entry)
    _async_remove_stale_entities(hass, entry)

    coordinator = PVSCCoordinator(hass, entry)
    await coordinator.async_setup()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _async_apply_id_prefix(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Wendet ein per Reconfigure geändertes Objekt-ID-Präfix (entry.data
    ["id_prefix"], Standard "pvsc") auf die BESTEHENDEN Entities dieses
    Eintrags an. Nötig, weil die Entity-Registry die entity_id anhand der
    unique_id festhält - eine Änderung des Präfixes im Code allein würde
    bereits registrierte Entities nie umbenennen.

    Bewusst vorsichtig: umbenannt wird nur, wenn die aktuelle Objekt-ID noch
    dem Schema "<irgendein_prefix>_<key>" folgt (also auf "_<key>" endet).
    Eine von Hand frei umbenannte Entity (z.B. sensor.meine_wallbox) wird
    nicht angefasst. Kollisionen mit bereits vergebenen IDs werden
    übersprungen und geloggt."""
    prefix = entry.data.get("id_prefix", "pvsc")
    registry = er.async_get(hass)
    uid_prefix = f"pvsc_{entry.entry_id}_"
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if not reg_entry.unique_id.startswith(uid_prefix):
            continue
        key = reg_entry.unique_id[len(uid_prefix):]
        desired = f"{reg_entry.domain}.{prefix}_{key}"
        if reg_entry.entity_id == desired:
            continue
        current_object_id = reg_entry.entity_id.split(".", 1)[1]
        if not current_object_id.endswith(f"_{key}"):
            # Von Hand umbenannt -> respektieren.
            continue
        if registry.async_get(desired):
            _LOGGER.warning(
                "PVSC: Kann %s nicht in %s umbenennen - ID bereits vergeben",
                reg_entry.entity_id, desired,
            )
            continue
        _LOGGER.info("PVSC: Benenne %s in %s um (id_prefix=%s)",
                     reg_entry.entity_id, desired, prefix)
        registry.async_update_entity(reg_entry.entity_id, new_entity_id=desired)


# Entity-Keys, die in früheren Versionen als Entities existierten und
# inzwischen entfernt wurden (0.5.0b10: Delays + Totband in den Options-Flow
# verschoben, "Test: erzwungene Ampere" ersatzlos gestrichen). Ohne aktives
# Aufräumen blieben sie als dauerhaft "nicht verfügbare" Registry-Leichen
# sichtbar.
_REMOVED_ENTITY_KEYS = {
    "state_change_on_delay",
    "state_change_off_delay",
    "ampere_change_delay",
    "ampere_deadband",
    "forced_ampere",
}


def _async_remove_stale_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    registry = er.async_get(hass)
    uid_prefix = f"pvsc_{entry.entry_id}_"
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if not reg_entry.unique_id.startswith(uid_prefix):
            continue
        if reg_entry.unique_id[len(uid_prefix):] in _REMOVED_ENTITY_KEYS:
            _LOGGER.info("PVSC: Entferne veraltete Entity %s", reg_entry.entity_id)
            registry.async_remove(reg_entry.entity_id)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: PVSCCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_unload()
    return unload_ok
