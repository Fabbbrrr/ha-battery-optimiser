"""Solar forecast parsers for Forecast.Solar, Solcast, and generic total-kWh sources."""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    FORECAST_FORMAT_AUTO,
    FORECAST_FORMAT_FORECAST_SOLAR,
    FORECAST_FORMAT_SOLCAST,
    FORECAST_FORMAT_GENERIC_KWH,
)

_LOGGER = logging.getLogger(__name__)

# Slot = (slot_start_datetime, wh_expected)
ForecastSlot = tuple[datetime, float]


def parse_forecast(
    hass: HomeAssistant,
    entity_id: str,
    fmt: str,
    slot_minutes: int,
    n_slots: int,
    start_dt: datetime,
) -> list[float]:
    """Parse solar forecast into a list of kWh values, one per slot.

    Returns a list of length n_slots with expected solar generation (kWh) per slot.
    start_dt is the start of the first slot (timezone-aware).
    """
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unavailable", "unknown"):
        _LOGGER.warning("Forecast entity %s unavailable, returning zeros", entity_id)
        return [0.0] * n_slots

    if fmt == FORECAST_FORMAT_AUTO:
        fmt = _detect_format(state)

    try:
        if fmt == FORECAST_FORMAT_FORECAST_SOLAR:
            raw_slots = _parse_forecast_solar(state)
        elif fmt == FORECAST_FORMAT_SOLCAST:
            raw_slots = _parse_solcast(state)
        else:
            raw_slots = _parse_generic_kwh(hass, state, start_dt, n_slots, slot_minutes)
            # Generic already returns per-slot values
            return raw_slots
    except Exception as err:
        _LOGGER.error("Failed to parse %s forecast from %s: %s", fmt, entity_id, err)
        return [0.0] * n_slots

    return _resample_to_slots(raw_slots, start_dt, slot_minutes, n_slots)


def _detect_format(state) -> str:
    """Auto-detect forecast format from entity state attributes."""
    attrs = state.attributes
    if "detailedForecast" in attrs or "forecasts" in attrs:
        return FORECAST_FORMAT_SOLCAST
    if "watts" in attrs or "wh_period" in attrs or "energy_production_today" in attrs:
        return FORECAST_FORMAT_FORECAST_SOLAR
    return FORECAST_FORMAT_GENERIC_KWH


def _parse_forecast_solar(state) -> list[ForecastSlot]:
    """Parse Forecast.Solar integration format.

    Forecast.Solar exposes:
    - 'watts': dict of ISO timestamp -> watts (instantaneous)
    - OR 'wh_period': dict of ISO timestamp -> Wh for that period
    - OR hourly data in state attributes
    """
    attrs = state.attributes
    slots: list[ForecastSlot] = []

    # Try wh_period first (Wh per period — most direct)
    if "wh_period" in attrs:
        for ts_str, wh in attrs["wh_period"].items():
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                slots.append((dt, float(wh)))
            except (ValueError, TypeError):
                continue
        return slots

    # Try watts (instantaneous W — assume 1-hour periods)
    if "watts" in attrs:
        for ts_str, w in attrs["watts"].items():
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                wh = float(w) * 1.0  # 1 hour period assumed
                slots.append((dt, wh))
            except (ValueError, TypeError):
                continue
        return slots

    # Try detailedForecast list (some versions use this key)
    if "detailedForecast" in attrs:
        return _parse_solcast(state)

    _LOGGER.warning("Forecast.Solar: no recognizable forecast attribute found")
    return []


def _parse_solcast(state) -> list[ForecastSlot]:
    """Parse Solcast integration format.

    Solcast typically exposes:
    - 'detailedForecast': list of dicts with 'period_start' and 'pv_estimate' (kW)
    - OR 'forecasts': list with similar structure
    Each entry covers a 30-minute period.
    """
    attrs = state.attributes
    slots: list[ForecastSlot] = []

    raw_list = attrs.get("detailedForecast") or attrs.get("forecasts") or []

    for entry in raw_list:
        try:
            # Solcast uses 'period_start' and 'pv_estimate' (kW average over 30 min)
            period_start = entry.get("period_start") or entry.get("periodStart") or entry.get("PeriodStart")
            pv_kw = float(entry.get("pv_estimate") or entry.get("pv_estimate50") or entry.get("PvEstimate") or 0)

            if isinstance(period_start, str):
                dt = datetime.fromisoformat(period_start.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            elif isinstance(period_start, datetime):
                dt = period_start
            else:
                continue

            # Solcast periods are 30 min by default → Wh = kW * 0.5h * 1000
            wh = pv_kw * 0.5 * 1000
            slots.append((dt, wh))
        except (TypeError, ValueError, KeyError):
            continue

    return slots


def _parse_generic_kwh(
    hass: HomeAssistant,
    state,
    start_dt: datetime,
    n_slots: int,
    slot_minutes: int,
) -> list[float]:
    """Parse a generic total-kWh sensor and distribute over daylight hours.

    Reads the sensor's state as total expected kWh for today (and tomorrow if available).
    Distributes using a bell curve over the daylight window.
    """
    slot_hours = slot_minutes / 60.0
    result = [0.0] * n_slots

    # Try to get daily kWh value
    try:
        total_kwh_today = float(state.state)
    except (ValueError, TypeError):
        _LOGGER.warning("Generic forecast sensor %s has non-numeric state, returning zeros", state.entity_id)
        return result

    # Determine daylight window from HA sun entity or fallback
    sunrise, sunset = _get_daylight_window(hass, start_dt.date())

    # Distribute today's kWh across slots using bell curve
    _distribute_kwh_to_slots(result, total_kwh_today, sunrise, sunset, start_dt, slot_minutes, 0)

    # If we have tomorrow's kWh in attributes, distribute that too
    tomorrow_kwh = None
    for key in ("energy_production_tomorrow", "kwh_tomorrow", "tomorrow_kwh", "forecast_tomorrow"):
        val = state.attributes.get(key)
        if val is not None:
            try:
                tomorrow_kwh = float(val)
                break
            except (TypeError, ValueError):
                pass

    if tomorrow_kwh is not None:
        tomorrow = start_dt.date() + timedelta(days=1)
        sunrise_t, sunset_t = _get_daylight_window(hass, tomorrow)
        _distribute_kwh_to_slots(result, tomorrow_kwh, sunrise_t, sunset_t, start_dt, slot_minutes, 0)

    return result


def _get_daylight_window(hass: HomeAssistant, day: date) -> tuple[datetime, datetime]:
    """Get sunrise and sunset for a given day using HA sun entity or fallback."""
    sun_state = hass.states.get("sun.sun")
    tz = dt_util.get_time_zone(hass.config.time_zone)

    if sun_state:
        try:
            next_rising = sun_state.attributes.get("next_rising")
            next_setting = sun_state.attributes.get("next_setting")
            if next_rising and next_setting:
                sunrise = datetime.fromisoformat(next_rising.replace("Z", "+00:00")).astimezone(tz)
                sunset = datetime.fromisoformat(next_setting.replace("Z", "+00:00")).astimezone(tz)
                # Use hours only, apply to requested day
                sunrise = datetime(day.year, day.month, day.day, sunrise.hour, sunrise.minute, tzinfo=tz)
                sunset = datetime(day.year, day.month, day.day, sunset.hour, sunset.minute, tzinfo=tz)
                return sunrise, sunset
        except (AttributeError, ValueError):
            pass

    # Fallback: assume 6:00 AM - 6:00 PM
    tz = tz or ZoneInfo("UTC")
    sunrise = datetime(day.year, day.month, day.day, 6, 0, tzinfo=tz)
    sunset = datetime(day.year, day.month, day.day, 18, 0, tzinfo=tz)
    return sunrise, sunset


def _distribute_kwh_to_slots(
    result: list[float],
    total_kwh: float,
    sunrise: datetime,
    sunset: datetime,
    schedule_start: datetime,
    slot_minutes: int,
    day_offset_slots: int,
) -> None:
    """Distribute total_kwh across slots using a bell curve centered at solar noon."""
    if total_kwh <= 0:
        return

    n_slots = len(result)
    slot_delta = timedelta(minutes=slot_minutes)

    # Solar noon = midpoint of daylight window
    solar_noon = sunrise + (sunset - sunrise) / 2
    daylight_hours = (sunset - sunrise).total_seconds() / 3600

    if daylight_hours <= 0:
        return

    # Gaussian sigma = 1/4 of daylight window (bell curve fits within daylight)
    sigma_hours = daylight_hours / 4.0

    # Compute weights for each slot
    weights = []
    slot_times = []
    for i in range(n_slots):
        slot_start = schedule_start + slot_delta * i
        slot_mid = slot_start + slot_delta / 2
        if slot_mid < sunrise or slot_mid > sunset:
            weights.append(0.0)
        else:
            hours_from_noon = (slot_mid - solar_noon).total_seconds() / 3600
            w = math.exp(-0.5 * (hours_from_noon / sigma_hours) ** 2)
            weights.append(w)
        slot_times.append(slot_start)

    total_weight = sum(weights)
    if total_weight == 0:
        return

    slot_hours = slot_minutes / 60.0
    for i, w in enumerate(weights):
        result[i] += total_kwh * (w / total_weight)


def _resample_to_slots(
    raw_slots: list[ForecastSlot],
    start_dt: datetime,
    slot_minutes: int,
    n_slots: int,
) -> list[float]:
    """Resample raw (timestamp, Wh) forecast data into uniform time slots."""
    result = [0.0] * n_slots
    slot_delta = timedelta(minutes=slot_minutes)

    # Sort raw slots by time
    raw_slots = sorted(raw_slots, key=lambda s: s[0])
    if not raw_slots:
        return result

    for i in range(n_slots):
        slot_start = start_dt + slot_delta * i
        slot_end = slot_start + slot_delta

        # Sum Wh from raw slots that overlap this schedule slot
        slot_wh = 0.0
        for raw_start, raw_wh in raw_slots:
            # Assume each raw forecast entry is 30 minutes (Solcast) or 60 minutes (Forecast.Solar)
            # We approximate raw period duration from gaps between entries
            raw_end = raw_start + timedelta(minutes=30)  # default assumption

            # Compute overlap fraction
            overlap_start = max(slot_start, raw_start)
            overlap_end = min(slot_end, raw_end)
            if overlap_end <= overlap_start:
                continue

            raw_duration = (raw_end - raw_start).total_seconds()
            overlap_duration = (overlap_end - overlap_start).total_seconds()
            fraction = overlap_duration / raw_duration if raw_duration > 0 else 0
            slot_wh += raw_wh * fraction

        # Convert Wh to kWh
        result[i] = slot_wh / 1000.0

    return result
