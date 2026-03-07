"""Weather-based forecast confidence modifier and temperature-driven load adjustment.

Two responsibilities:
1. Solar confidence modifier -- scales solar forecast down based on weather conditions
   (cloud cover, precipitation, condition string) so the optimizer is appropriately
   conservative when the weather is bad.

2. Temperature-driven consumption adjustment -- adds/removes load kWh per slot based
   on how far the forecast temperature deviates from the learned comfortable range.
   The temperature->consumption relationship is calibrated via ConsumptionLearner;
   this module just reads it and applies it per slot.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Condition -> base solar confidence multiplier (0.0 = no sun, 1.0 = full sun)
_CONDITION_CONFIDENCE: dict[str, float] = {
    "sunny": 1.0,
    "clear-night": 1.0,
    "partlycloudy": 0.75,
    "cloudy": 0.45,
    "fog": 0.25,
    "hail": 0.15,
    "lightning": 0.10,
    "lightning-rainy": 0.10,
    "pouring": 0.10,
    "rainy": 0.20,
    "snowy": 0.15,
    "snowy-rainy": 0.10,
    "windy": 0.85,
    "windy-variant": 0.75,
    "exceptional": 0.50,
}


@dataclass
class WeatherSnapshot:
    """Point-in-time weather data extracted from a HA weather entity."""
    condition: str
    cloud_coverage: float        # 0-100 %
    precipitation_probability: float  # 0-100 %
    temperature: float           # C
    confidence_multiplier: float # 0.0-1.0 solar yield modifier


@dataclass
class WeatherForecastPoint:
    """A single entry from the weather entity's forecast."""
    dt: datetime
    condition: str
    cloud_coverage: float
    precipitation_probability: float
    temperature: float
    confidence_multiplier: float


def get_weather_snapshot(hass: HomeAssistant, weather_entity: str | None) -> WeatherSnapshot | None:
    """Read current weather entity state and return a WeatherSnapshot."""
    if not weather_entity:
        return None

    state = hass.states.get(weather_entity)
    if state is None or state.state in ("unavailable", "unknown"):
        _LOGGER.debug("Weather entity %s unavailable", weather_entity)
        return None

    attrs = state.attributes
    condition = state.state.lower()
    cloud_coverage = float(attrs.get("cloud_coverage", _condition_to_cloud(condition)))
    precip_prob = float(attrs.get("precipitation_probability", 0.0))
    temperature = float(attrs.get("temperature", 20.0))

    multiplier = _compute_confidence(condition, cloud_coverage, precip_prob)

    return WeatherSnapshot(
        condition=condition,
        cloud_coverage=cloud_coverage,
        precipitation_probability=precip_prob,
        temperature=temperature,
        confidence_multiplier=multiplier,
    )


async def async_get_weather_forecast_points(
    hass: HomeAssistant,
    weather_entity: str | None,
    start_dt: datetime,
    n_slots: int,
    slot_minutes: int,
) -> list[WeatherForecastPoint]:
    """Fetch weather forecast via the HA service call and return per-slot points.

    HA 2024.3+ removed the ``forecast`` attribute from weather entities.
    Forecasts are now retrieved via the ``weather.get_forecasts`` service.
    Falls back to the legacy attribute for older HA versions.

    Returns a list of length n_slots. Slots without forecast data inherit the
    current conditions.
    """
    snapshot = get_weather_snapshot(hass, weather_entity)
    if snapshot is None:
        return []

    raw_forecast: list[dict[str, Any]] = []

    # Try the modern service call first (HA 2024.3+)
    try:
        response = await hass.services.async_call(
            "weather",
            "get_forecasts",
            {"entity_id": weather_entity, "type": "hourly"},
            blocking=True,
            return_response=True,
        )
        if response and weather_entity in response:
            raw_forecast = response[weather_entity].get("forecast", [])
    except Exception:
        _LOGGER.debug("weather.get_forecasts service not available, trying daily")

    # If hourly failed, try daily
    if not raw_forecast:
        try:
            response = await hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": weather_entity, "type": "daily"},
                blocking=True,
                return_response=True,
            )
            if response and weather_entity in response:
                raw_forecast = response[weather_entity].get("forecast", [])
        except Exception:
            _LOGGER.debug("weather.get_forecasts daily also failed")

    # Last resort: legacy attribute (HA < 2024.3)
    if not raw_forecast:
        state = hass.states.get(weather_entity)
        if state:
            raw_forecast = state.attributes.get("forecast", [])

    # Parse forecast entries
    parsed: list[WeatherForecastPoint] = []
    for entry in raw_forecast:
        try:
            dt_str = entry.get("datetime")
            if not dt_str:
                continue
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            cond = str(entry.get("condition", snapshot.condition)).lower()
            cloud = float(entry.get("cloud_coverage", _condition_to_cloud(cond)))
            precip = float(entry.get("precipitation_probability", 0.0))
            temp = float(entry.get("temperature", snapshot.temperature))
            mult = _compute_confidence(cond, cloud, precip)
            parsed.append(WeatherForecastPoint(
                dt=dt, condition=cond, cloud_coverage=cloud,
                precipitation_probability=precip, temperature=temp,
                confidence_multiplier=mult,
            ))
        except (ValueError, TypeError, KeyError):
            continue

    parsed.sort(key=lambda p: p.dt)

    # Map to slots
    slot_delta = timedelta(minutes=slot_minutes)
    result: list[WeatherForecastPoint] = []
    for i in range(n_slots):
        slot_dt = start_dt + slot_delta * i
        # Find the closest forecast point (within 6 hours)
        best = None
        best_diff = timedelta(hours=6)
        for pt in parsed:
            diff = abs(pt.dt - slot_dt)
            if diff < best_diff:
                best_diff = diff
                best = pt
        if best is None:
            # Use current snapshot as fallback
            best = WeatherForecastPoint(
                dt=slot_dt,
                condition=snapshot.condition,
                cloud_coverage=snapshot.cloud_coverage,
                precipitation_probability=snapshot.precipitation_probability,
                temperature=snapshot.temperature,
                confidence_multiplier=snapshot.confidence_multiplier,
            )
        result.append(best)

    return result


def apply_weather_to_forecast(
    solar_kwh: list[float],
    weather_points: list[WeatherForecastPoint],
) -> tuple[list[float], float]:
    """Multiply solar forecast by per-slot weather confidence multipliers.

    Returns (adjusted_solar_kwh, mean_confidence).
    """
    if not weather_points or len(weather_points) != len(solar_kwh):
        return solar_kwh, 1.0

    adjusted = []
    total_confidence = 0.0
    for kwh, pt in zip(solar_kwh, weather_points):
        adjusted.append(kwh * pt.confidence_multiplier)
        total_confidence += pt.confidence_multiplier

    mean_confidence = total_confidence / len(weather_points) if weather_points else 1.0
    return adjusted, round(mean_confidence, 3)


def apply_temperature_load_adjustment(
    load_kwh: list[float],
    weather_points: list[WeatherForecastPoint],
    temp_coefficients: dict,  # From ConsumptionLearner: {"slope_heat": kW/C, "slope_cool": kW/C, "comfort_band": [low, high]}
    slot_hours: float,
) -> list[float]:
    """Adjust load per slot based on temperature deviation from comfort band.

    temp_coefficients keys:
      "comfort_low": lower comfort band temp (C)
      "comfort_high": upper comfort band temp (C)
      "slope_heat": additional kW per degree below comfort_low
      "slope_cool": additional kW per degree above comfort_high
    """
    if not temp_coefficients or not weather_points:
        return load_kwh

    comfort_low = float(temp_coefficients.get("comfort_low", 18.0))
    comfort_high = float(temp_coefficients.get("comfort_high", 24.0))
    slope_heat = float(temp_coefficients.get("slope_heat", 0.05))  # kW per C below comfort
    slope_cool = float(temp_coefficients.get("slope_cool", 0.08))  # kW per C above comfort

    adjusted = []
    n = min(len(load_kwh), len(weather_points))
    for i in range(n):
        temp = weather_points[i].temperature
        extra_kw = 0.0
        if temp < comfort_low:
            extra_kw = slope_heat * (comfort_low - temp)
        elif temp > comfort_high:
            extra_kw = slope_cool * (temp - comfort_high)
        adjusted.append(load_kwh[i] + extra_kw * slot_hours)

    # Pad remainder if lists differ in length
    adjusted.extend(load_kwh[n:])
    return adjusted


def _compute_confidence(condition: str, cloud_coverage: float, precip_probability: float) -> float:
    """Compute a solar confidence multiplier from weather parameters."""
    # Base from condition string
    base = _CONDITION_CONFIDENCE.get(condition, 0.6)

    # Cloud coverage further reduces confidence
    # 0% cloud = no reduction, 100% cloud = extra 40% reduction on top of base
    cloud_factor = 1.0 - (cloud_coverage / 100.0) * 0.4

    # Precipitation probability further reduces confidence
    precip_factor = 1.0 - (precip_probability / 100.0) * 0.3

    multiplier = base * cloud_factor * precip_factor
    return round(max(0.05, min(1.0, multiplier)), 3)


def _condition_to_cloud(condition: str) -> float:
    """Estimate cloud coverage % from condition string (fallback when attribute missing)."""
    mapping = {
        "sunny": 0.0,
        "clear-night": 0.0,
        "partlycloudy": 40.0,
        "windy": 20.0,
        "windy-variant": 40.0,
        "cloudy": 80.0,
        "fog": 90.0,
        "hail": 100.0,
        "lightning": 100.0,
        "lightning-rainy": 100.0,
        "pouring": 100.0,
        "rainy": 85.0,
        "snowy": 90.0,
        "snowy-rainy": 95.0,
        "exceptional": 60.0,
    }
    return mapping.get(condition, 50.0)
