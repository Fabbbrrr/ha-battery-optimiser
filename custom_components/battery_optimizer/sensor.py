"""Sensor entities for Battery Optimizer."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
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
    CONF_FREE_IMPORT_START,
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
        # Individual scalar sensors for dashboards, automations, and history graphs
        CurrentPowerSensor(coordinator, entry),
        ProjectedSOCSensor(coordinator, entry),
        ForecastConfidenceSensor(coordinator, entry),
        EnergySecurityScoreSensor(coordinator, entry),
        EstimatedExportRevenueSensor(coordinator, entry),
        NextActionSensor(coordinator, entry),
        SOCAtFreeChargeStartSensor(coordinator, entry),
        LearningStatusSensor(coordinator, entry),
    ])


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Battery Optimiser",
        manufacturer="Battery Optimiser",
        model="LP Schedule Optimiser",
        sw_version="0.0.10",
    )


def _current_slot(data: dict | None) -> dict | None:
    """Return the first non-historical slot from coordinator data, or None."""
    if not data:
        return None
    slots = data.get(ATTR_SLOTS, [])
    for slot in slots:
        if not slot.get("is_historical"):
            return slot
    return slots[0] if slots else None


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
            "diagnostics": health.get("diagnostics", {}),
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


class CurrentPowerSensor(CoordinatorEntity[BatteryOptimizerCoordinator], SensorEntity):
    """Power command for the current schedule slot (positive = charge, negative = discharge)."""

    _attr_has_entity_name = True
    _attr_name = "Current Power"
    _attr_icon = "mdi:lightning-bolt"
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: BatteryOptimizerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_current_power_kw"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        slot = _current_slot(self.coordinator.data)
        return slot.get("power_kw") if slot else None


class ProjectedSOCSensor(CoordinatorEntity[BatteryOptimizerCoordinator], SensorEntity):
    """Projected battery SOC at the end of the current schedule slot."""

    _attr_has_entity_name = True
    _attr_name = "Projected SOC"
    _attr_icon = "mdi:battery-charging"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: BatteryOptimizerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_projected_soc"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        slot = _current_slot(self.coordinator.data)
        return slot.get("projected_soc") if slot else None


class ForecastConfidenceSensor(CoordinatorEntity[BatteryOptimizerCoordinator], SensorEntity):
    """Optimizer's confidence in the solar forecast (weather-adjusted, 0–100%)."""

    _attr_has_entity_name = True
    _attr_name = "Forecast Confidence"
    _attr_icon = "mdi:cloud-percent"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: BatteryOptimizerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_forecast_confidence"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if not data:
            return None
        val = data.get("health", {}).get(ATTR_FORECAST_CONFIDENCE)
        return round(val * 100, 1) if val is not None else None


class EnergySecurityScoreSensor(CoordinatorEntity[BatteryOptimizerCoordinator], SensorEntity):
    """Energy security score — how well the plan covers the bridge-to point (0–100%)."""

    _attr_has_entity_name = True
    _attr_name = "Energy Security Score"
    _attr_icon = "mdi:shield-check"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: BatteryOptimizerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_energy_security_score"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if not data:
            return None
        val = data.get("health", {}).get(ATTR_ENERGY_SECURITY_SCORE)
        return round(val * 100, 1) if val is not None else None


class EstimatedExportRevenueSensor(CoordinatorEntity[BatteryOptimizerCoordinator], SensorEntity):
    """Estimated export revenue for the current optimization cycle."""

    _attr_has_entity_name = True
    _attr_name = "Estimated Export Revenue"
    _attr_icon = "mdi:cash-plus"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: BatteryOptimizerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_estimated_export_revenue"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if not data:
            return None
        return data.get("health", {}).get(ATTR_ESTIMATED_EXPORT_REVENUE)


class NextActionSensor(CoordinatorEntity[BatteryOptimizerCoordinator], SensorEntity):
    """Action planned for the next schedule slot."""

    _attr_has_entity_name = True
    _attr_name = "Next Action"
    _attr_icon = "mdi:battery-arrow-up"

    def __init__(self, coordinator: BatteryOptimizerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_next_action"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        if not data:
            return None
        slots = data.get(ATTR_SLOTS, [])
        future = [s for s in slots if not s.get("is_historical")]
        # Second future slot is the "next" one (first is current)
        if len(future) >= 2:
            return future[1].get("action")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if not data:
            return {}
        slots = data.get(ATTR_SLOTS, [])
        future = [s for s in slots if not s.get("is_historical")]
        if len(future) >= 2:
            next_slot = future[1]
            return {
                "start": next_slot.get("start"),
                "end": next_slot.get("end"),
                "power_kw": next_slot.get("power_kw"),
                "projected_soc": next_slot.get("projected_soc"),
            }
        return {}


class SOCAtFreeChargeStartSensor(CoordinatorEntity[BatteryOptimizerCoordinator], SensorEntity):
    """Projected battery SOC at the start of the configured free/cheap import window.

    Useful for understanding how full the battery will be when cheap charging starts —
    helps decide whether to pre-charge or let solar fill it during the day.
    """

    _attr_has_entity_name = True
    _attr_name = "SOC at Charge Window Start"
    _attr_icon = "mdi:battery-charging-50"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: BatteryOptimizerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_soc_at_free_charge_start"
        self._attr_device_info = _device_info(entry)
        self._entry = entry

    def _free_import_start(self) -> str | None:
        """Return HH:MM of configured free import window, or None if not set."""
        cfg = {**self._entry.data, **self._entry.options}
        val = cfg.get(CONF_FREE_IMPORT_START)
        return val[:5] if val else None  # normalise to HH:MM

    def _find_slot(self, target_hhmm: str) -> dict | None:
        data = self.coordinator.data
        if not data:
            return None
        for slot in data.get(ATTR_SLOTS, []):
            if slot.get("is_historical"):
                continue
            start_str = slot.get("start", "")
            if len(start_str) >= 16 and start_str[11:16] == target_hhmm:
                return slot
        return None

    @property
    def native_value(self) -> float | None:
        target = self._free_import_start()
        if not target:
            return None
        slot = self._find_slot(target)
        return slot.get("projected_soc") if slot else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        target = self._free_import_start()
        if not target:
            return {"configured": False, "note": "Set free_import_start in integration options"}
        slot = self._find_slot(target)
        if not slot:
            return {"configured": True, "free_import_start": target, "slot_found": False}
        return {
            "configured": True,
            "free_import_start": target,
            "slot_found": True,
            "slot_start": slot.get("start"),
            "slot_end": slot.get("end"),
            "planned_action": slot.get("action"),
            "expected_solar_kwh": slot.get("expected_solar_kwh"),
            "expected_consumption_kwh": slot.get("expected_consumption_kwh"),
        }


class LearningStatusSensor(CoordinatorEntity[BatteryOptimizerCoordinator], SensorEntity):
    """Consumption learner status — trained / learning / not_started.

    Exposes how many days of data have been learned, profile types,
    whether temperature modelling is active, and when the last training run was.
    """

    _attr_has_entity_name = True
    _attr_name = "Learning Status"
    _attr_icon = "mdi:brain"

    def __init__(self, coordinator: BatteryOptimizerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_learning_status"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str:
        data = self.coordinator.data
        if not data:
            return "unavailable"
        learning = data.get("learning", {})
        if not learning:
            return "not_started"
        if learning.get("is_trained"):
            return "trained"
        if learning.get("observation_count", 0) > 0:
            return "learning"
        return "not_started"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if not data:
            return {}
        return data.get("learning", {})
