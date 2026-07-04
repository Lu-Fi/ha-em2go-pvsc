"""Binäre Sensoren der PV Überschussladen (Test) Integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PVSCCoordinator
from .entity import PVSCEntity


@dataclass(frozen=True, kw_only=True)
class PVSCBinarySensorDescription:
    key: str
    name: str
    icon: str | None = None
    device_class: BinarySensorDeviceClass | None = None
    value_fn: Callable[[PVSCCoordinator], bool]


BINARY_SENSORS: tuple[PVSCBinarySensorDescription, ...] = (
    PVSCBinarySensorDescription(
        key="plug_connected", name="Stecker verbunden",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda c: c.em2go["plug"] == 1,
    ),
    PVSCBinarySensorDescription(
        key="charging", name="Lädt (Ist-Zustand)",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda c: bool(c.state),
    ),
    PVSCBinarySensorDescription(
        key="target_charging", name="Soll laden (eigene Logik)",
        icon="mdi:target",
        value_fn=lambda c: bool(c.target_state),
    ),
    PVSCBinarySensorDescription(
        key="car_home", name="Auto zuhause",
        device_class=BinarySensorDeviceClass.PRESENCE,
        value_fn=lambda c: c.car.get("location") == "home",
    ),
    PVSCBinarySensorDescription(
        key="modbus_connected", name="Modbus verbunden",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda c: c.modbus_ok,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PVSCCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PVSCBinarySensor(coordinator, entry.entry_id, description)
        for description in BINARY_SENSORS
    )


class PVSCBinarySensor(PVSCEntity, BinarySensorEntity):
    def __init__(
        self,
        coordinator: PVSCCoordinator,
        entry_id: str,
        description: PVSCBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, entry_id)
        self._description = description
        self._attr_unique_id = f"pvsc_{entry_id}_{description.key}"
        self._attr_suggested_object_id = f"pvsc_{description.key}"
        self.entity_id = f"binary_sensor.pvsc_{description.key}"
        self._attr_translation_key = description.key
        self._attr_icon = description.icon
        self._attr_device_class = description.device_class

    @property
    def is_on(self) -> bool:
        try:
            return self._description.value_fn(self.coordinator)
        except Exception:  # noqa: BLE001
            return False
