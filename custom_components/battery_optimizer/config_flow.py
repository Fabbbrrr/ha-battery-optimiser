"""Config flow for Battery Optimizer."""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
try:
    from homeassistant.config_entries import ConfigFlowResult as FlowResult
except ImportError:
    from homeassistant.data_entry_flow import FlowResult  # type: ignore[assignment]
from homeassistant.helpers import entity_registry as er, selector

from .const import (
    DOMAIN,
    # Battery
    CONF_BATTERY_SOC_ENTITY,
    CONF_BATTERY_CAPACITY_KWH,
    CONF_MIN_SOC_FLOOR_PERCENT,
    CONF_MAX_CHARGE_RATE_KW,
    CONF_MAX_DISCHARGE_RATE_KW,
    CONF_MAX_EXPORT_LIMIT_KW,
    CONF_MAX_EXPORT_LIMIT_ENTITY,
    # Solar
    CONF_SOLAR_FORECAST_ENTITY,
    CONF_SOLAR_FORECAST_FORMAT,
    CONF_SOLAR_TOTAL_KWH_ENTITY,
    CONF_SOLAR_FORECAST_TOMORROW_ENTITY,
    FORECAST_FORMAT_AUTO,
    FORECAST_FORMAT_FORECAST_SOLAR,
    FORECAST_FORMAT_SOLCAST,
    FORECAST_FORMAT_GENERIC_KWH,
    # Tariff
    CONF_EXPORT_BONUS_START,
    CONF_EXPORT_BONUS_END,
    CONF_EXPORT_BONUS_RATE,
    CONF_STANDARD_EXPORT_RATE,
    CONF_STANDARD_IMPORT_RATE,
    CONF_FREE_IMPORT_START,
    CONF_FREE_IMPORT_END,
    CONF_PEAK_IMPORT_START,
    CONF_PEAK_IMPORT_END,
    CONF_PEAK_IMPORT_RATE,
    # Grid charging
    CONF_GRID_CHARGING_ENABLED,
    # Weather / consumption
    CONF_WEATHER_ENTITY,
    CONF_CONSUMPTION_ENTITY,
    CONF_CONSUMPTION_BASELINE_KW,
    CONF_CONSUMPTION_PROFILE_GRANULARITY,
    CONF_CONSUMPTION_LOOKBACK_DAYS,
    GRANULARITY_SINGLE,
    GRANULARITY_WEEKDAY_WEEKEND,
    GRANULARITY_FULL_WEEK,
    # Optimizer
    CONF_SLOT_GRANULARITY_MINUTES,
    CONF_LOOKAHEAD_HOURS,
    CONF_AGGRESSIVENESS,
    CONF_RECALCULATION_INTERVAL_MINUTES,
    CONF_SOLVER_TIMEOUT_SECONDS,
    CONF_FALLBACK_MODE,
    CONF_DATA_RETENTION_DAYS,
    CONF_BRIDGE_TO_FALLBACK_TIME,
    FALLBACK_CONSERVATIVE_HOLD,
    FALLBACK_LAST_KNOWN_GOOD,
    FALLBACK_ERROR_STATE,
    # Defaults
    DEFAULT_MIN_SOC_FLOOR_PERCENT,
    DEFAULT_MAX_CHARGE_RATE_KW,
    DEFAULT_MAX_DISCHARGE_RATE_KW,
    DEFAULT_MAX_EXPORT_LIMIT_KW,
    DEFAULT_SLOT_GRANULARITY_MINUTES,
    DEFAULT_LOOKAHEAD_HOURS,
    DEFAULT_AGGRESSIVENESS,
    DEFAULT_RECALCULATION_INTERVAL_MINUTES,
    DEFAULT_SOLVER_TIMEOUT_SECONDS,
    DEFAULT_FALLBACK_MODE,
    DEFAULT_DATA_RETENTION_DAYS,
    DEFAULT_CONSUMPTION_BASELINE_KW,
    DEFAULT_CONSUMPTION_LOOKBACK_DAYS,
    DEFAULT_CONSUMPTION_PROFILE_GRANULARITY,
    DEFAULT_BRIDGE_TO_FALLBACK_TIME,
    DEFAULT_STANDARD_EXPORT_RATE,
    DEFAULT_STANDARD_IMPORT_RATE,
)

_LOGGER = logging.getLogger(__name__)

TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


def _validate_time(value: str) -> str:
    if not TIME_PATTERN.match(value):
        raise vol.Invalid("Time must be in HH:MM format")
    return value


def _suggest_battery_entities(hass: HomeAssistant) -> list[str]:
    """Return entity IDs likely to be battery SOC sensors."""
    registry = er.async_get(hass)
    suggestions = []
    for entity in registry.entities.values():
        if entity.domain == "sensor" and entity.device_class in ("battery", None):
            state = hass.states.get(entity.entity_id)
            if state and "soc" in entity.entity_id.lower():
                suggestions.append(entity.entity_id)
    return suggestions


def _suggest_forecast_entities(hass: HomeAssistant) -> list[str]:
    """Return entity IDs that look like solar forecast sensors."""
    registry = er.async_get(hass)
    keywords = ("forecast", "solar", "pv", "solcast")
    suggestions = []
    for entity in registry.entities.values():
        if entity.domain == "sensor":
            eid = entity.entity_id.lower()
            if any(k in eid for k in keywords):
                suggestions.append(entity.entity_id)
    return suggestions


def _detect_forecast_format(hass: HomeAssistant, entity_id: str) -> str:
    """Attempt to auto-detect the forecast format from entity attributes."""
    state = hass.states.get(entity_id)
    if not state:
        return FORECAST_FORMAT_GENERIC_KWH

    attrs = state.attributes
    # Solcast: typically has 'detailedForecast' or 'forecasts' list attribute
    if "detailedForecast" in attrs or "forecasts" in attrs:
        return FORECAST_FORMAT_SOLCAST

    # Forecast.Solar: typically has 'watts' dict or 'wh_period' dict
    if "watts" in attrs or "wh_period" in attrs:
        return FORECAST_FORMAT_FORECAST_SOLAR

    return FORECAST_FORMAT_GENERIC_KWH


class BatteryOptimizerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Multi-step guided setup wizard for Battery Optimizer."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 1 (required): Battery basics — SOC entity, capacity, SOC floor."""
        errors: dict[str, str] = {}

        if user_input is not None:
            soc_entity = user_input[CONF_BATTERY_SOC_ENTITY]
            state = self.hass.states.get(soc_entity)
            if state is None:
                errors[CONF_BATTERY_SOC_ENTITY] = "entity_not_found"
            else:
                self._data.update(user_input)
                return await self.async_step_export_window()

        suggestions = _suggest_battery_entities(self.hass)

        schema = vol.Schema({
            vol.Required(CONF_BATTERY_SOC_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_BATTERY_CAPACITY_KWH): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.5, max=500, step=0.1, unit_of_measurement="kWh", mode="box")
            ),
            vol.Required(CONF_MIN_SOC_FLOOR_PERCENT, default=DEFAULT_MIN_SOC_FLOOR_PERCENT): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=50, step=1, unit_of_measurement="%", mode="slider")
            ),
        })

        suggested_text = (
            "Detected SOC sensors: " + ", ".join(suggestions[:3])
            if suggestions else
            "No SOC sensors auto-detected — search for a sensor whose name contains 'soc' or 'charge'."
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"suggested": suggested_text},
        )

    async def async_step_export_window(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 2 (required): Export bonus window and rates."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                _validate_time(user_input[CONF_EXPORT_BONUS_START])
                _validate_time(user_input[CONF_EXPORT_BONUS_END])
                self._data.update(user_input)
                return await self.async_step_solar_forecast()
            except vol.Invalid as e:
                errors["base"] = str(e)

        schema = vol.Schema({
            vol.Required(CONF_EXPORT_BONUS_START, default="18:00"): selector.TextSelector(
                selector.TextSelectorConfig(type="time")
            ),
            vol.Required(CONF_EXPORT_BONUS_END, default="20:00"): selector.TextSelector(
                selector.TextSelectorConfig(type="time")
            ),
            vol.Required(CONF_EXPORT_BONUS_RATE): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=10, step=0.01, unit_of_measurement="$/kWh", mode="box")
            ),
            vol.Optional(CONF_STANDARD_EXPORT_RATE, default=DEFAULT_STANDARD_EXPORT_RATE): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=5, step=0.01, unit_of_measurement="$/kWh", mode="box")
            ),
            vol.Optional(CONF_STANDARD_IMPORT_RATE, default=DEFAULT_STANDARD_IMPORT_RATE): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=5, step=0.01, unit_of_measurement="$/kWh", mode="box")
            ),
        })

        return self.async_show_form(
            step_id="export_window",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_solar_forecast(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 3 (required): Solar forecast entity selection with format auto-detection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            entity_id = user_input[CONF_SOLAR_FORECAST_ENTITY]
            state = self.hass.states.get(entity_id)
            if state is None:
                errors[CONF_SOLAR_FORECAST_ENTITY] = "entity_not_found"
            else:
                detected_format = _detect_forecast_format(self.hass, entity_id)
                self._data[CONF_SOLAR_FORECAST_ENTITY] = entity_id
                self._data[CONF_SOLAR_FORECAST_FORMAT] = detected_format
                _LOGGER.info("Detected solar forecast format: %s for %s", detected_format, entity_id)
                return await self.async_step_optional_tariffs()

        suggestions = _suggest_forecast_entities(self.hass)

        schema = vol.Schema({
            vol.Required(CONF_SOLAR_FORECAST_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
        })

        suggested_text = (
            "Detected forecast sensors: " + ", ".join(suggestions[:3])
            if suggestions else
            "No forecast sensors auto-detected — search for a sensor whose name contains 'solcast', 'forecast', or 'solar'."
        )
        return self.async_show_form(
            step_id="solar_forecast",
            data_schema=schema,
            errors=errors,
            description_placeholders={"suggested": suggested_text},
        )

    async def async_step_optional_tariffs(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 4 (optional): Additional tariff periods — free import, peak, grid charging."""
        if user_input is not None:
            if user_input.get("skip"):
                return await self.async_step_optional_consumption()

            self._data.update({k: v for k, v in user_input.items() if k != "skip" and v is not None and v != ""})
            return await self.async_step_optional_consumption()

        schema = vol.Schema({
            vol.Optional(CONF_FREE_IMPORT_START): selector.TextSelector(
                selector.TextSelectorConfig(type="time")
            ),
            vol.Optional(CONF_FREE_IMPORT_END): selector.TextSelector(
                selector.TextSelectorConfig(type="time")
            ),
            vol.Optional(CONF_PEAK_IMPORT_START): selector.TextSelector(
                selector.TextSelectorConfig(type="time")
            ),
            vol.Optional(CONF_PEAK_IMPORT_END): selector.TextSelector(
                selector.TextSelectorConfig(type="time")
            ),
            vol.Optional(CONF_PEAK_IMPORT_RATE): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=5, step=0.01, unit_of_measurement="$/kWh", mode="box")
            ),
            vol.Optional(CONF_GRID_CHARGING_ENABLED, default=False): selector.BooleanSelector(),
        })

        return self.async_show_form(
            step_id="optional_tariffs",
            data_schema=schema,
            description_placeholders={"note": "All fields optional — leave blank to skip"},
        )

    async def async_step_optional_consumption(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 5 (optional): Home consumption entity and baseline."""
        if user_input is not None:
            if user_input.get("skip"):
                return await self.async_step_optional_weather()
            self._data.update({k: v for k, v in user_input.items() if k != "skip"})
            return await self.async_step_optional_weather()

        schema = vol.Schema({
            vol.Optional(CONF_CONSUMPTION_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(CONF_CONSUMPTION_BASELINE_KW, default=DEFAULT_CONSUMPTION_BASELINE_KW): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.1, max=20, step=0.1, unit_of_measurement="kW", mode="box")
            ),
            vol.Optional(CONF_CONSUMPTION_PROFILE_GRANULARITY, default=DEFAULT_CONSUMPTION_PROFILE_GRANULARITY): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    {"value": GRANULARITY_SINGLE, "label": "Single average profile"},
                    {"value": GRANULARITY_WEEKDAY_WEEKEND, "label": "Weekday / Weekend (recommended)"},
                    {"value": GRANULARITY_FULL_WEEK, "label": "Full 7-day profiles"},
                ])
            ),
            vol.Optional(CONF_CONSUMPTION_LOOKBACK_DAYS, default=DEFAULT_CONSUMPTION_LOOKBACK_DAYS): selector.NumberSelector(
                selector.NumberSelectorConfig(min=7, max=365, step=1, unit_of_measurement="days", mode="box")
            ),
        })

        return self.async_show_form(
            step_id="optional_consumption",
            data_schema=schema,
            description_placeholders={"note": "Optional — skip to use static baseline only"},
        )

    async def async_step_optional_weather(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 6 (optional): Weather entity for forecast confidence and temperature load."""
        if user_input is not None:
            if user_input.get("skip"):
                return await self.async_step_optional_battery_rates()
            self._data.update({k: v for k, v in user_input.items() if k != "skip"})
            return await self.async_step_optional_battery_rates()

        schema = vol.Schema({
            vol.Optional(CONF_WEATHER_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="weather")
            ),
        })

        return self.async_show_form(
            step_id="optional_weather",
            data_schema=schema,
            description_placeholders={"note": "Optional — improves forecast accuracy via weather-based confidence modifier"},
        )

    async def async_step_optional_battery_rates(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 7 (optional): Battery charge/discharge/export rate limits."""
        if user_input is not None:
            if user_input.get("skip"):
                return self._create_entry()
            self._data.update({k: v for k, v in user_input.items() if k != "skip"})
            return self._create_entry()

        schema = vol.Schema({
            vol.Optional(CONF_MAX_CHARGE_RATE_KW, default=DEFAULT_MAX_CHARGE_RATE_KW): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.1, max=50, step=0.1, unit_of_measurement="kW", mode="box")
            ),
            vol.Optional(CONF_MAX_DISCHARGE_RATE_KW, default=DEFAULT_MAX_DISCHARGE_RATE_KW): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.1, max=50, step=0.1, unit_of_measurement="kW", mode="box")
            ),
            vol.Optional(CONF_MAX_EXPORT_LIMIT_KW, default=DEFAULT_MAX_EXPORT_LIMIT_KW): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.1, max=50, step=0.1, unit_of_measurement="kW", mode="box")
            ),
            vol.Optional(CONF_MAX_EXPORT_LIMIT_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
        })

        return self.async_show_form(
            step_id="optional_battery_rates",
            data_schema=schema,
            description_placeholders={"note": "Optional — defaults work for most 5kW inverter systems"},
        )

    def _create_entry(self) -> FlowResult:
        """Create the config entry with all collected data."""
        title = f"Battery Optimiser ({self._data.get(CONF_BATTERY_CAPACITY_KWH, '?')}kWh)"
        return self.async_create_entry(title=title, data=self._data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> BatteryOptimizerOptionsFlow:
        return BatteryOptimizerOptionsFlow(config_entry)


class BatteryOptimizerOptionsFlow(config_entries.OptionsFlow):
    """Options flow — revisit all config after initial setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._options: dict[str, Any] = dict(config_entry.options)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Show the main options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options={
                "optimizer_settings": "Optimizer Settings",
                "tariff_settings": "Tariff & Rates",
                "entity_settings": "Entity Mappings",
                "advanced_settings": "Advanced Settings",
            },
        )

    async def async_step_optimizer_settings(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Options: optimizer tuning parameters."""
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)

        current = self._config_entry.data

        schema = vol.Schema({
            vol.Optional(CONF_AGGRESSIVENESS, default=current.get(CONF_AGGRESSIVENESS, DEFAULT_AGGRESSIVENESS)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.0, max=1.0, step=0.05, mode="slider")
            ),
            vol.Optional(CONF_SLOT_GRANULARITY_MINUTES, default=current.get(CONF_SLOT_GRANULARITY_MINUTES, DEFAULT_SLOT_GRANULARITY_MINUTES)): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    {"value": "15", "label": "15 minutes"},
                    {"value": "30", "label": "30 minutes (recommended)"},
                    {"value": "60", "label": "60 minutes"},
                ])
            ),
            vol.Optional(CONF_LOOKAHEAD_HOURS, default=current.get(CONF_LOOKAHEAD_HOURS, DEFAULT_LOOKAHEAD_HOURS)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=12, max=168, step=12, unit_of_measurement="hours", mode="box")
            ),
            vol.Optional(CONF_RECALCULATION_INTERVAL_MINUTES, default=current.get(CONF_RECALCULATION_INTERVAL_MINUTES, DEFAULT_RECALCULATION_INTERVAL_MINUTES)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=5, max=120, step=5, unit_of_measurement="minutes", mode="box")
            ),
            vol.Optional(CONF_BRIDGE_TO_FALLBACK_TIME, default=current.get(CONF_BRIDGE_TO_FALLBACK_TIME, DEFAULT_BRIDGE_TO_FALLBACK_TIME)): selector.TextSelector(
                selector.TextSelectorConfig(type="time")
            ),
        })

        return self.async_show_form(step_id="optimizer_settings", data_schema=schema)

    async def async_step_tariff_settings(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Options: tariff and rate configuration."""
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)

        current = self._config_entry.data
        schema = vol.Schema({
            vol.Optional(CONF_EXPORT_BONUS_START, default=current.get(CONF_EXPORT_BONUS_START, "18:00")): selector.TextSelector(selector.TextSelectorConfig(type="time")),
            vol.Optional(CONF_EXPORT_BONUS_END, default=current.get(CONF_EXPORT_BONUS_END, "20:00")): selector.TextSelector(selector.TextSelectorConfig(type="time")),
            vol.Optional(CONF_EXPORT_BONUS_RATE, default=current.get(CONF_EXPORT_BONUS_RATE, 0.0)): selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=10, step=0.01, unit_of_measurement="$/kWh", mode="box")),
            vol.Optional(CONF_STANDARD_EXPORT_RATE, default=current.get(CONF_STANDARD_EXPORT_RATE, DEFAULT_STANDARD_EXPORT_RATE)): selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=5, step=0.01, unit_of_measurement="$/kWh", mode="box")),
            vol.Optional(CONF_STANDARD_IMPORT_RATE, default=current.get(CONF_STANDARD_IMPORT_RATE, DEFAULT_STANDARD_IMPORT_RATE)): selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=5, step=0.01, unit_of_measurement="$/kWh", mode="box")),
            vol.Optional(CONF_FREE_IMPORT_START, default=current.get(CONF_FREE_IMPORT_START, "")): selector.TextSelector(selector.TextSelectorConfig(type="time")),
            vol.Optional(CONF_FREE_IMPORT_END, default=current.get(CONF_FREE_IMPORT_END, "")): selector.TextSelector(selector.TextSelectorConfig(type="time")),
            vol.Optional(CONF_GRID_CHARGING_ENABLED, default=current.get(CONF_GRID_CHARGING_ENABLED, False)): selector.BooleanSelector(),
        })

        return self.async_show_form(step_id="tariff_settings", data_schema=schema)

    async def async_step_entity_settings(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Options: re-map all entity selections."""
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)

        current = self._config_entry.data
        schema = vol.Schema({
            vol.Optional(CONF_BATTERY_SOC_ENTITY, default=current.get(CONF_BATTERY_SOC_ENTITY, "")): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_SOLAR_FORECAST_ENTITY, default=current.get(CONF_SOLAR_FORECAST_ENTITY, "")): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_SOLAR_FORECAST_TOMORROW_ENTITY, default=current.get(CONF_SOLAR_FORECAST_TOMORROW_ENTITY, "")): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_CONSUMPTION_ENTITY, default=current.get(CONF_CONSUMPTION_ENTITY, "")): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_WEATHER_ENTITY, default=current.get(CONF_WEATHER_ENTITY, "")): selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
            vol.Optional(CONF_MAX_EXPORT_LIMIT_ENTITY, default=current.get(CONF_MAX_EXPORT_LIMIT_ENTITY, "")): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        })

        return self.async_show_form(step_id="entity_settings", data_schema=schema)

    async def async_step_advanced_settings(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Options: advanced/performance settings."""
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)

        current = self._config_entry.data
        schema = vol.Schema({
            vol.Optional(CONF_FALLBACK_MODE, default=current.get(CONF_FALLBACK_MODE, DEFAULT_FALLBACK_MODE)): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    {"value": FALLBACK_CONSERVATIVE_HOLD, "label": "Conservative hold (recommended)"},
                    {"value": FALLBACK_LAST_KNOWN_GOOD, "label": "Last known good schedule"},
                    {"value": FALLBACK_ERROR_STATE, "label": "Error state"},
                ])
            ),
            vol.Optional(CONF_SOLVER_TIMEOUT_SECONDS, default=current.get(CONF_SOLVER_TIMEOUT_SECONDS, DEFAULT_SOLVER_TIMEOUT_SECONDS)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=5, max=120, step=5, unit_of_measurement="seconds", mode="box")
            ),
            vol.Optional(CONF_DATA_RETENTION_DAYS, default=current.get(CONF_DATA_RETENTION_DAYS, DEFAULT_DATA_RETENTION_DAYS)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=7, max=365, step=1, unit_of_measurement="days", mode="box")
            ),
            vol.Optional(CONF_MIN_SOC_FLOOR_PERCENT, default=current.get(CONF_MIN_SOC_FLOOR_PERCENT, DEFAULT_MIN_SOC_FLOOR_PERCENT)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=50, step=1, unit_of_measurement="%", mode="slider")
            ),
        })

        return self.async_show_form(step_id="advanced_settings", data_schema=schema)
