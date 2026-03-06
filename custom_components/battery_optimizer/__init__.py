"""Battery Optimizer — LP-optimized battery scheduling for Home Assistant."""
from __future__ import annotations

import logging
import pathlib

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import BatteryOptimizerCoordinator
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)

_CARD_PATH = pathlib.Path(__file__).parent / "www"
_CARD_URL = f"/battery_optimizer_static"
_CARD_FILE = "battery-optimizer-card.js"
_CARD_VERSION = "0.1.0"

_frontend_registered = False


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the Lovelace card as a static resource (runs once at HA startup)."""
    global _frontend_registered
    if not _frontend_registered:
        # HA 2024.7+ renamed register_static_path to async_register_static_paths
        if hasattr(hass.http, "async_register_static_paths"):
            from homeassistant.components.http import StaticPathConfig
            await hass.http.async_register_static_paths(
                [StaticPathConfig(_CARD_URL, str(_CARD_PATH), cache_headers=False)]
            )
        else:
            hass.http.register_static_path(
                _CARD_URL,
                str(_CARD_PATH),
                cache_headers=False,
            )
        _frontend_registered = True
        _LOGGER.debug("Battery Optimiser card registered at %s/%s", _CARD_URL, _CARD_FILE)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Battery Optimizer from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = BatteryOptimizerCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: BatteryOptimizerCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

        if not hass.data[DOMAIN]:
            await async_unregister_services(hass)
            hass.data.pop(DOMAIN)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)
