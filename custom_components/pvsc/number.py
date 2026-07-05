"""Zahlen-Entities (entsprechen den vormaligen input_number Helpern)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PVSCCoordinator
from .entity import PVSCEntity


@dataclass(frozen=True, kw_only=True)
class PVSCNumberDescription:
    key: str
    name: str
    min_value: float
    max_value: float
    step: float
    unit: str | None = None
    icon: str | None = None
    mode: NumberMode = NumberMode.SLIDER
    entity_category: str | None = None
    getter: Callable[[PVSCCoordinator], float]
    setter: Callable[[PVSCCoordinator, float], None]


def _set_setting(key: str):
    def _setter(c: PVSCCoordinator, value: float) -> None:
        c.settings[key] = value
    return _setter


NUMBERS: tuple[PVSCNumberDescription, ...] = (
    PVSCNumberDescription(
        key="min_soc", name="Min. SOC", min_value=0, max_value=98, step=1, unit="%",
        icon="mdi:battery-low",
        getter=lambda c: c.settings["min_soc"], setter=_set_setting("min_soc"),
    ),
    PVSCNumberDescription(
        key="optimal_soc", name="Optimaler SOC", min_value=1, max_value=99, step=1, unit="%",
        icon="mdi:battery-70",
        getter=lambda c: c.settings["optimal_soc"], setter=_set_setting("optimal_soc"),
    ),
    PVSCNumberDescription(
        key="high_soc", name="Hoher SOC", min_value=2, max_value=100, step=1, unit="%",
        icon="mdi:battery-high",
        getter=lambda c: c.settings["high_soc"], setter=_set_setting("high_soc"),
    ),
    PVSCNumberDescription(
        key="correction_factor", name="Korrekturfaktor (manuell)", min_value=0, max_value=125,
        step=5, unit="%", icon="mdi:tune-variant",
        getter=lambda c: c.settings["correction_factor"],
        setter=_set_setting("correction_factor"),
    ),
    # Ampere-Totband und die Hysterese-Delays liegen seit 0.5.0b10 im
    # Options-Flow ("Konfigurieren") - das sind Parameter, die nicht täglich
    # geändert werden. Die frühere "Test: erzwungene Ampere"-Entity wurde
    # in 0.5.0b10 ersatzlos entfernt.
    PVSCNumberDescription(
        key="override_ampere", name="Override: Ampere", min_value=6, max_value=16, step=1,
        unit="A", icon="mdi:current-ac",
        getter=lambda c: c.override["ampere"],
        setter=lambda c, v: c.override.__setitem__("ampere", int(v)),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PVSCCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PVSCNumber(coordinator, entry.entry_id, description) for description in NUMBERS
    )


class PVSCNumber(PVSCEntity, NumberEntity):
    def __init__(
        self, coordinator: PVSCCoordinator, entry_id: str, description: PVSCNumberDescription
    ) -> None:
        super().__init__(coordinator, entry_id)
        self._description = description
        self._attr_unique_id = f"pvsc_{entry_id}_{description.key}"
        self._attr_suggested_object_id = f"{coordinator.id_prefix}_{description.key}"
        self.entity_id = f"number.{coordinator.id_prefix}_{description.key}"
        self._attr_translation_key = description.key
        self._attr_native_min_value = description.min_value
        self._attr_native_max_value = description.max_value
        self._attr_native_step = description.step
        self._attr_native_unit_of_measurement = description.unit
        self._attr_icon = description.icon
        self._attr_mode = description.mode
        if description.entity_category:
            self._attr_entity_category = description.entity_category

    @property
    def native_value(self) -> float:
        return self._description.getter(self.coordinator)

    async def async_set_native_value(self, value: float) -> None:
        self._description.setter(self.coordinator, value)
        self.async_write_ha_state()
        await self.coordinator.async_persist_state()
