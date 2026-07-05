"""Sensoren der PV Überschussladen (Test) Integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PVSCCoordinator
from .entity import PVSCEntity


@dataclass(frozen=True, kw_only=True)
class PVSCSensorDescription:
    key: str
    name: str
    unit: str | None = None
    icon: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    value_fn: Callable[[PVSCCoordinator], object] = lambda c: None
    entity_category: str | None = None


SENSORS: tuple[PVSCSensorDescription, ...] = (
    PVSCSensorDescription(
        key="pv", name="PV-Leistung", unit="W", device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:solar-power",
        value_fn=lambda c: round(c.pv),
    ),
    PVSCSensorDescription(
        key="load", name="Hauslast", unit="W", device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT, icon="mdi:home-lightning-bolt",
        value_fn=lambda c: round(c.load),
    ),
    PVSCSensorDescription(
        key="surplus", name="PV-Überschuss (Haus)", unit="W",
        device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power-variant", value_fn=lambda c: round(c.surplus),
    ),
    PVSCSensorDescription(
        key="car_surplus", name="Überschuss für Auto", unit="W",
        device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:car-electric", value_fn=lambda c: round(c.car_surplus),
    ),
    PVSCSensorDescription(
        key="target_ampere", name="Ziel-Ampere", unit="A",
        device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac", value_fn=lambda c: c.target_ampere,
    ),
    PVSCSensorDescription(
        key="ampere", name="Aktuelle Ampere (Vorgabe)", unit="A",
        device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac", value_fn=lambda c: c.ampere,
    ),
    PVSCSensorDescription(
        key="correction_faktor", name="Korrekturfaktor", icon="mdi:tune-variant",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: round(c.correction_faktor, 2),
    ),
    PVSCSensorDescription(
        key="battery_support_watts", name="Batterie-Unterstützung", unit="W",
        device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-arrow-up", value_fn=lambda c: round(c.battery.support_watts),
    ),
    PVSCSensorDescription(
        key="battery_avg", name="Batterienutzung Ø 15min", unit="W",
        device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery-clock", value_fn=lambda c: c.battery.cache_avg(),
    ),
    PVSCSensorDescription(
        key="stop_cause", name="Abbruchgrund", icon="mdi:alert-circle-outline",
        value_fn=lambda c: c.stop_cause_text,
    ),
    PVSCSensorDescription(
        key="status_text", name="Status", icon="mdi:text-box-outline",
        value_fn=lambda c: c.status_text,
    ),
    PVSCSensorDescription(
        key="em2go_state", name="Status-Code", icon="mdi:ev-station",
        value_fn=lambda c: c.em2go["state"],
    ),
    PVSCSensorDescription(
        key="em2go_state_text", name="Status (Wallbox)", icon="mdi:ev-station",
        value_fn=lambda c: c.em2go_state_text,
    ),
    PVSCSensorDescription(
        key="em2go_power", name="Leistung", unit="W",
        device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:ev-plug-type2", value_fn=lambda c: round(c.em2go["power"]),
    ),
    PVSCSensorDescription(
        key="em2go_ampere", name="Strombegrenzung (Ist)", unit="A",
        device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac", value_fn=lambda c: c.em2go["ampere"] if c.em2go["ampere"] >= 0 else None,
    ),
    PVSCSensorDescription(
        key="em2go_phases", name="Phasen", icon="mdi:sine-wave",
        value_fn=lambda c: c.em2go["phases"],
    ),
    PVSCSensorDescription(
        key="em2go_energy", name="Zählerstand", unit="kWh",
        device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter", value_fn=lambda c: c.em2go["energy"] if c.em2go["energy"] >= 0 else None,
    ),
    PVSCSensorDescription(
        key="em2go_session_kwh", name="Geladen (aktuelle Session)", unit="kWh",
        # Kein device_class=ENERGY hier: ENERGY verlangt state_class
        # total/total_increasing, aber dieser Wert ist ein Session-Gauge,
        # der bei jedem neuen Ladevorgang auf 0 zurückspringt (HA würde
        # sonst eine Warnung werfen / falsche Statistiken bilden).
        icon="mdi:counter",
        value_fn=lambda c: round(c.em2go["loaded_kwh"], 2) if c.em2go["loaded_kwh"] >= 0 else None,
    ),
    PVSCSensorDescription(
        key="car_soc", name="Auto Ladezustand", unit="%",
        device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:car-battery", value_fn=lambda c: c.car["soc"] if c.car["soc"] >= 0 else None,
    ),
    PVSCSensorDescription(
        key="car_end", name="Auto Ladeende", icon="mdi:clock-end",
        value_fn=lambda c: c.car["end"],
    ),
    PVSCSensorDescription(
        key="modbus_status", name="Datenquelle Wallbox", icon="mdi:lan-connect",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.modbus_last_error or ("OK" if c.modbus_ok else "Fehler"),
    ),
    PVSCSensorDescription(
        key="modbus_consecutive_failures", name="Modbus Fehler in Folge",
        icon="mdi:counter", entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.modbus_consecutive_failures,
    ),
    PVSCSensorDescription(
        key="modbus_retry_in", name="Modbus nächster Versuch in", unit="s",
        icon="mdi:timer-sand", entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.modbus_seconds_until_retry,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PVSCCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PVSCSensor(coordinator, entry.entry_id, description) for description in SENSORS
    )


class PVSCSensor(PVSCEntity, SensorEntity):
    def __init__(
        self, coordinator: PVSCCoordinator, entry_id: str, description: PVSCSensorDescription
    ) -> None:
        super().__init__(coordinator, entry_id)
        self._description = description
        self._attr_unique_id = f"pvsc_{entry_id}_{description.key}"
        self._attr_suggested_object_id = f"{coordinator.id_prefix}_{description.key}"
        # has_entity_name + Gerätename überstimmt suggested_object_id bei der
        # Entity-ID-Vergabe - deshalb entity_id hier hart erzwingen, damit
        # Karte/Dashboard verlässlich auf sensor.pvsc_<key> zeigen können.
        self.entity_id = f"sensor.{coordinator.id_prefix}_{description.key}"
        self._attr_translation_key = description.key
        self._attr_native_unit_of_measurement = description.unit
        self._attr_icon = description.icon
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        if description.entity_category:
            self._attr_entity_category = description.entity_category

    @property
    def native_value(self):
        try:
            return self._description.value_fn(self.coordinator)
        except Exception:  # noqa: BLE001
            return None
