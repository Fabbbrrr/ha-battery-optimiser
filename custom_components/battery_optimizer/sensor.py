"""Sensor entities for Battery Optimizer."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SENSOR_SCHEDULE,
    SENSOR_HEALTH,
    SENSOR_STATE,
    ATTR_SLOTS,
    ATTR_SOLVER_STATUS,
    ATTR_FORECAST_STALENESS_SECONDS,
    ATTR_SOC_SENSOR_AVAILABLE,
    ATTR_LAST_RECALCULATION,
    ATTR_SOLVER_DURATION_MS,
    ATTR_PROBLEM_SIZE,
    ATTR_FALLBACK_MODE_ACTIVE,
    ATTR_ESTIMATED_EXPORT_REVENUE,
    ATTR_ENERGY_SECURITY_SCORE,
    ATTR_FORECAST_CONFIDENCE,
    ATTR_BRIDGE_TO_TIME,
    ATTR_BRIDGE_TO_SOURCE,
)
from .coordinator import BatteryOptimizerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Battery Optimizer sensor entities."""
    coordinator: BatteryOptimizerCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        BatteryScheduleSensor(coordinator, entry),
        BatteryHealthSensor(coordinator, entry),
        BatteryOptimizerStateSensor(coordinator, entry),
    ])


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Battery Optimizer",
        manufacturer="Battery Optimizer",
        model="LP Schedule Optimizer",
        sw_version="0.1.0",
    )


class BatteryScheduleSensor(CoordinatorEntity[BatteryOptimizerCoordinator], SensorEntity):
    """Main schedule sensor exposing full slot details as template-friendly attributes."""

    _attr_has_entity_name = True
    _attr_name = "Schedule"
    _attr_icon = "mdi:battery-clock"

    def __init__(self, coordinator: BatteryOptimizerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_SCHEDULE}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str | None:
        """State is the recommended action for the current slot."""
        data = self.coordinator.data
        if not data:
            return None
        slots = data.get(ATTR_SLOTS, [])
        if slots:
            return slots[0].get("action", "hold")
        return "hold"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Full schedule as structured attributes for template automations."""
        data = self.coordinator.data
        if not data:
            return {}
        return {
            ATTR_SLOTS: data.get(ATTR_SLOTS, []),
            "aggressiveness": data.get("aggressiveness", 0.7),
            "state": data.get("state"),
        }


class BatteryHealthSensor(CoordinatorEntity[BatteryOptimizerCoordinator], SensorEntity):
    """Health and data-quality sensor exposing optimizer internals."""

    _attr_has_entity_name = True
    _attr_name = "Health"
    _attr_icon = "mdi:heart-pulse"

    def __init__(self, coordinator: BatteryOptimizerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_HEALTH}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str | None:
        """Overall health status string."""
        data = self.coordinator.data
        if not data:
            return "unavailable"
        health = data.get("health", {})
        if health.get("fallback_mode_active"):
            return "degraded"
        solver_status = health.get(ATTR_SOLVER_STATUS, "unknown")
        if solver_status and solver_status.startswith("error"):
            return "error"
        return "ok"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Full health metrics for automations and dashboards."""
        data = self.coordinator.data
        if not data:
            return {}
        health = data.get("health", {})
        return {
            ATTR_SOLVER_STATUS: health.get(ATTR_SOLVER_STATUS),
            ATTR_FORECAST_STALENESS_SECONDS: health.get(ATTR_FORECAST_STALENESS_SECONDS),
            ATTR_SOC_SENSOR_AVAILABLE: health.get(ATTR_SOC_SENSOR_AVAILABLE),
            ATTR_LAST_RECALCULATION: health.get(ATTR_LAST_RECALCULATION),
            ATTR_SOLVER_DURATION_MS: health.get(ATTR_SOLVER_DURATION_MS),
            ATTR_PROBLEM_SIZE: health.get(ATTR_PROBLEM_SIZE),
            ATTR_FALLBACK_MODE_ACTIVE: health.get(ATTR_FALLBACK_MODE_ACTIVE),
            ATTR_ESTIMATED_EXPORT_REVENUE: health.get(ATTR_ESTIMATED_EXPORT_REVENUE),
            ATTR_ENERGY_SECURITY_SCORE: health.get(ATTR_ENERGY_SECURITY_SCORE),
            ATTR_FORECAST_CONFIDENCE: health.get(ATTR_FORECAST_CONFIDENCE),
            ATTR_BRIDGE_TO_TIME: health.get(ATTR_BRIDGE_TO_TIME),
            ATTR_BRIDGE_TO_SOURCE: health.get(ATTR_BRIDGE_TO_SOURCE),
        }


class BatteryOptimizerStateSensor(CoordinatorEntity[BatteryOptimizerCoordinator], SensorEntity):
    """Optimizer state sensor (running / paused / error / fallback)."""

    _attr_has_entity_name = True
    _attr_name = "Optimizer State"
    _attr_icon = "mdi:state-machine"

    def __init__(self, coordinator: BatteryOptimizerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_STATE}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        if not data:
            return None
        return data.get("state")
