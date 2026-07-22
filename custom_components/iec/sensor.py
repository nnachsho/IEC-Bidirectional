"""Sensor platform for IEC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IECCoordinator, IECMeterData


@dataclass(frozen=True, kw_only=True)
class IECSensorDescription(SensorEntityDescription):
    value_fn: Callable[[IECMeterData], float | None]


SENSORS: tuple[IECSensorDescription, ...] = (
    IECSensorDescription(key="total_import", translation_key="total_import", device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING, native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, value_fn=lambda data: data.total_import),
    IECSensorDescription(key="total_export", translation_key="total_export", device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING, native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, value_fn=lambda data: data.total_export),
    IECSensorDescription(key="period_import", translation_key="period_import", device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL, native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, value_fn=lambda data: data.period_import),
    IECSensorDescription(key="period_export", translation_key="period_export", device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL, native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, value_fn=lambda data: data.period_export),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry[IECCoordinator], async_add_entities: AddEntitiesCallback) -> None:
    """Set up IEC sensors."""
    async_add_entities(IECSensor(entry.runtime_data, description) for description in SENSORS)


class IECSensor(CoordinatorEntity[IECCoordinator], SensorEntity):
    """An IEC meter sensor."""

    entity_description: IECSensorDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator: IECCoordinator, description: IECSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry.entry_id)},
            manufacturer="Israel Electric Company",
            name="IEC electricity meter",
            model="Smart meter",
            serial_number=data.meter_serial,
        )

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return {
            "meter_serial": data.meter_serial,
            "meter_code": data.meter_code,
            "period_start": data.period_start,
            "period_end": data.period_end,
            "last_register_readings": data.last_readings,
            **data.attributes,
        }
