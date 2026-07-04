"""Gemeinsame Basisklasse für alle PVSC-Entities."""
from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN
from .coordinator import PVSCCoordinator


class PVSCEntity(Entity):
    """Registriert sich beim Coordinator, damit sie bei jedem Tick aktualisiert wird."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: PVSCCoordinator, entry_id: str) -> None:
        self.coordinator = coordinator
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="EM2GO Home Wallbox",
            manufacturer="EM2GO",
            model="PV-Überschussladen (pvsc)",
        )

    async def async_added_to_hass(self) -> None:
        self.coordinator.register_entity(self)
