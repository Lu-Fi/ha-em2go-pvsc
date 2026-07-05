"""Schalter der PV Überschussladen (Test) Integration."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity, SwitchDeviceClass
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
            PVSCControlEnabledSwitch(coordinator, entry.entry_id),
            PVSCEnabledSwitch(coordinator, entry.entry_id),
            PVSCCorrectionAutoSwitch(coordinator, entry.entry_id),
            PVSCPhaseAutoSwitch(coordinator, entry.entry_id),
        ]
    )


class PVSCControlEnabledSwitch(PVSCEntity, SwitchEntity):
    """Sicherheits-Freigabe: erst wenn AN, schreibt die Integration auf die Wallbox."""

    _attr_icon = "mdi:shield-lock-open-outline"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: PVSCCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"pvsc_{entry_id}_control_enabled"
        self._attr_suggested_object_id = "pvsc_control_enabled"
        self.entity_id = "switch.pvsc_control_enabled"
        self._attr_translation_key = "control_enabled"

    @property
    def is_on(self) -> bool:
        return self.coordinator.control_enabled

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.control_enabled = True
        self.async_write_ha_state()
        await self.coordinator.async_persist_state()

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.control_enabled = False
        self.async_write_ha_state()
        await self.coordinator.async_persist_state()


class PVSCEnabledSwitch(PVSCEntity, SwitchEntity):
    """Entspricht psc.enabled im Node-RED Flow (Automatik grundsätzlich an/aus)."""

    _attr_icon = "mdi:auto-fix"

    def __init__(self, coordinator: PVSCCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"pvsc_{entry_id}_enabled"
        self._attr_suggested_object_id = "pvsc_enabled"
        self.entity_id = "switch.pvsc_enabled"
        self._attr_translation_key = "enabled"

    @property
    def is_on(self) -> bool:
        return self.coordinator.enabled

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.enabled = True
        self.async_write_ha_state()
        await self.coordinator.async_persist_state()

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.enabled = False
        self.async_write_ha_state()
        await self.coordinator.async_persist_state()


class PVSCCorrectionAutoSwitch(PVSCEntity, SwitchEntity):
    _attr_icon = "mdi:auto-fix"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PVSCCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"pvsc_{entry_id}_correction_auto"
        self._attr_suggested_object_id = "pvsc_correction_auto"
        self.entity_id = "switch.pvsc_correction_auto"
        self._attr_translation_key = "correction_auto"

    @property
    def is_on(self) -> bool:
        return self.coordinator.settings["correction_auto"]

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.settings["correction_auto"] = True
        self.async_write_ha_state()
        await self.coordinator.async_persist_state()

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.settings["correction_auto"] = False
        self.async_write_ha_state()
        await self.coordinator.async_persist_state()


class PVSCPhaseAutoSwitch(PVSCEntity, SwitchEntity):
    """Optionale automatische 1<->3-Phasenumschaltung im PV-Modus.

    AN: Bei dauerhaft hohem Überschuss (> PHASE_UP_WATTS für 5 Min) wird
    auf 3 Phasen hochgeschaltet, bei dauerhaft niedrigem (< PHASE_DOWN_WATTS
    für 5 Min) zurück auf 1 Phase. AUS (Standard): im PV-Modus immer 1-phasig.
    """

    _attr_icon = "mdi:sine-wave"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PVSCCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"pvsc_{entry_id}_phase_auto"
        self._attr_suggested_object_id = "pvsc_phase_auto"
        self.entity_id = "switch.pvsc_phase_auto"
        self._attr_translation_key = "phase_auto"

    @property
    def is_on(self) -> bool:
        return self.coordinator.settings["phase_auto"]

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.settings["phase_auto"] = True
        self.async_write_ha_state()
        await self.coordinator.async_persist_state()

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.settings["phase_auto"] = False
        self.coordinator.phase_change_ts = 0
        self.async_write_ha_state()
        await self.coordinator.async_persist_state()
