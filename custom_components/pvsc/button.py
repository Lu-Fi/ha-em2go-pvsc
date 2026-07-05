"""Buttons der PV Überschussladen (Test) Integration."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, STOP_CAUSE_NONE
from .coordinator import PVSCCoordinator
from .entity import PVSCEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PVSCCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PVSCResetStopCauseButton(coordinator, entry.entry_id),
            PVSCResetDefaultsButton(coordinator, entry.entry_id),
        ]
    )


class PVSCResetStopCauseButton(PVSCEntity, ButtonEntity):
    _attr_icon = "mdi:refresh-circle"

    def __init__(self, coordinator: PVSCCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"pvsc_{entry_id}_reset_stop_cause"
        self._attr_suggested_object_id = "pvsc_reset_stop_cause"
        self.entity_id = "button.pvsc_reset_stop_cause"
        self._attr_translation_key = "reset_stop_cause"

    async def async_press(self) -> None:
        self.coordinator.stop_cause = STOP_CAUSE_NONE


class PVSCResetDefaultsButton(PVSCEntity, ButtonEntity):
    """Setzt die live einstellbaren Werte (SOC-Stufen, Korrekturfaktor,
    Ampere-Totband, Forced-Ampere, Phasen-Automatik, Überschussmodus,
    Überschuss-Automatik, Override) auf die Werkseinstellungen aus const.py
    zurück. Der Sicherheits-Schalter "Steuerung aktiv" (control_enabled)
    bleibt davon bewusst unberührt - siehe Coordinator.async_reset_to_defaults().
    """

    _attr_icon = "mdi:restore"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PVSCCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"pvsc_{entry_id}_reset_defaults"
        self._attr_suggested_object_id = "pvsc_reset_defaults"
        self.entity_id = "button.pvsc_reset_defaults"
        self._attr_translation_key = "reset_defaults"

    async def async_press(self) -> None:
        await self.coordinator.async_reset_to_defaults()
