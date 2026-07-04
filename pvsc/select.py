"""Auswahl-Entities: Override-Modus, Override-Phasen, Überschussberechnung."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PVSCCoordinator
from .entity import PVSCEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PVSCCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PVSCOverrideModeSelect(coordinator, entry.entry_id),
            PVSCOverridePhasesSelect(coordinator, entry.entry_id),
            PVSCSurplusModeSelect(coordinator, entry.entry_id),
        ]
    )


class PVSCOverrideModeSelect(PVSCEntity, SelectEntity):
    _attr_icon = "mdi:tune"
    _attr_options = ["pv", "manual", "stop"]

    def __init__(self, coordinator: PVSCCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"pvsc_{entry_id}_override_mode"
        self._attr_suggested_object_id = "pvsc_override_mode"
        self.entity_id = "select.pvsc_override_mode"
        self._attr_translation_key = "override_mode"

    @property
    def current_option(self) -> str:
        return self.coordinator.override.get("mode", "pv")

    async def async_select_option(self, option: str) -> None:
        self.coordinator.override["mode"] = option
        self.async_write_ha_state()


class PVSCOverridePhasesSelect(PVSCEntity, SelectEntity):
    _attr_icon = "mdi:sine-wave"
    _attr_options = ["1", "3"]

    def __init__(self, coordinator: PVSCCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"pvsc_{entry_id}_override_phases"
        self._attr_suggested_object_id = "pvsc_override_phases"
        self.entity_id = "select.pvsc_override_phases"
        self._attr_translation_key = "override_phases"

    @property
    def current_option(self) -> str:
        return str(self.coordinator.override.get("phases", 1))

    async def async_select_option(self, option: str) -> None:
        self.coordinator.override["phases"] = int(option)
        self.async_write_ha_state()


class PVSCSurplusModeSelect(PVSCEntity, SelectEntity):
    _attr_icon = "mdi:scale-balance"
    _attr_options = ["load", "saldo"]
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PVSCCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"pvsc_{entry_id}_surplus_mode"
        self._attr_suggested_object_id = "pvsc_surplus_mode"
        self.entity_id = "select.pvsc_surplus_mode"
        self._attr_translation_key = "surplus_mode"

    @property
    def current_option(self) -> str:
        return self.coordinator.settings.get("surplus_mode", "load")

    async def async_select_option(self, option: str) -> None:
        self.coordinator.settings["surplus_mode"] = option
        self.async_write_ha_state()
