"""Service handlers for Battery Optimizer."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_RECALCULATE_NOW,
    SERVICE_SET_AGGRESSIVENESS,
    SERVICE_OVERRIDE_SLOT,
    SERVICE_PAUSE,
    SERVICE_RESUME,
    SERVICE_RETRAIN_LEARNER,
    ACTION_CHARGE,
    ACTION_DISCHARGE,
    ACTION_HOLD,
    ACTION_EXPORT,
)

_LOGGER = logging.getLogger(__name__)

_services_registered = False

VALID_ACTIONS = [ACTION_CHARGE, ACTION_DISCHARGE, ACTION_HOLD, ACTION_EXPORT]

SET_AGGRESSIVENESS_SCHEMA = vol.Schema({
    vol.Required("aggressiveness"): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1.0)),
})

OVERRIDE_SLOT_SCHEMA = vol.Schema({
    vol.Optional("start"): cv.string,          # ISO datetime or HH:MM; if omitted = current slot
    vol.Required("action"): vol.In(VALID_ACTIONS),
    vol.Optional("power_kw"): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=100.0)),
    vol.Required("duration_minutes"): vol.All(vol.Coerce(int), vol.Range(min=5, max=480)),
})


async def async_register_services(hass: HomeAssistant) -> None:
    """Register Battery Optimizer HA services."""
    global _services_registered
    if _services_registered:
        return

    def _get_coordinators(hass: HomeAssistant):
        return list(hass.data.get(DOMAIN, {}).values())

    async def handle_recalculate_now(call: ServiceCall) -> None:
        """Force an immediate schedule recalculation."""
        for coordinator in _get_coordinators(hass):
            _LOGGER.info("recalculate_now called via service")
            await coordinator.async_refresh()

    async def handle_set_aggressiveness(call: ServiceCall) -> None:
        """Set the optimizer aggressiveness level at runtime."""
        value = float(call.data["aggressiveness"])
        for coordinator in _get_coordinators(hass):
            _LOGGER.info("set_aggressiveness: %.2f", value)
            await coordinator.async_set_aggressiveness(value)

    async def handle_override_slot(call: ServiceCall) -> None:
        """Override one or more slots with a specific action and optional power."""
        action = call.data["action"]
        power_kw = call.data.get("power_kw")
        duration_minutes = int(call.data["duration_minutes"])
        start = call.data.get("start")

        for coordinator in _get_coordinators(hass):
            _LOGGER.info(
                "override_slot: action=%s power_kw=%s duration=%dmin start=%s",
                action, power_kw, duration_minutes, start,
            )
            await coordinator.async_override_slot(
                start=start,
                action=action,
                power_kw=power_kw,
                duration_minutes=duration_minutes,
            )

    async def handle_pause(call: ServiceCall) -> None:
        """Pause the optimizer — stops recalculations, sets all slots to hold."""
        for coordinator in _get_coordinators(hass):
            _LOGGER.info("Optimizer paused via service")
            await coordinator.async_pause()

    async def handle_resume(call: ServiceCall) -> None:
        """Resume the optimizer from paused state."""
        for coordinator in _get_coordinators(hass):
            _LOGGER.info("Optimizer resumed via service")
            await coordinator.async_resume()

    async def handle_retrain_learner(call: ServiceCall) -> None:
        """Re-train the consumption learner from recorder history and trigger recalculation."""
        for coordinator in _get_coordinators(hass):
            _LOGGER.info("retrain_learner called via service")
            await coordinator.async_retrain_learner()
            if coordinator.optimizer_state == "running":
                await coordinator.async_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_RECALCULATE_NOW, handle_recalculate_now
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_AGGRESSIVENESS, handle_set_aggressiveness,
        schema=SET_AGGRESSIVENESS_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_OVERRIDE_SLOT, handle_override_slot,
        schema=OVERRIDE_SLOT_SCHEMA,
    )
    hass.services.async_register(DOMAIN, SERVICE_PAUSE, handle_pause)
    hass.services.async_register(DOMAIN, SERVICE_RESUME, handle_resume)
    hass.services.async_register(DOMAIN, SERVICE_RETRAIN_LEARNER, handle_retrain_learner)

    _services_registered = True
    _LOGGER.debug("Battery Optimizer services registered")


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister all services when the last config entry is removed."""
    global _services_registered
    for service in (
        SERVICE_RECALCULATE_NOW,
        SERVICE_SET_AGGRESSIVENESS,
        SERVICE_OVERRIDE_SLOT,
        SERVICE_PAUSE,
        SERVICE_RESUME,
        SERVICE_RETRAIN_LEARNER,
    ):
        hass.services.async_remove(DOMAIN, service)
    _services_registered = False
