"""Button entities for Battery Optimizer."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import BatteryOptimizerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Battery Optimizer button entities."""
    coordinator: BatteryOptimizerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RetrainLearnerButton(coordinator, entry)])


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Battery Optimiser",
        manufacturer="Battery Optimiser",
        model="LP Schedule Optimiser",
        sw_version="0.0.7",
    )


class RetrainLearnerButton(ButtonEntity):
    """Button that triggers a full re-train of the consumption learner from recorder history."""

    _attr_has_entity_name = True
    _attr_name = "Retrain Learning Data"
    _attr_icon = "mdi:brain"

    def __init__(self, coordinator: BatteryOptimizerCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_retrain_learner"
        self._attr_device_info = _device_info(entry)

    async def async_press(self) -> None:
        """Re-train from recorder history and refresh the schedule."""
        _LOGGER.info("Retrain Learning Data button pressed")
        await self._coordinator.async_retrain_learner()
        if self._coordinator.optimizer_state == "running":
            await self._coordinator.async_refresh()
