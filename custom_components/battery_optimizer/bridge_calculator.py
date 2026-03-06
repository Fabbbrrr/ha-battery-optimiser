"""Bridge-to-point calculator for energy security constraints."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import NamedTuple

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

SOLAR_MEANINGFUL_KWH_THRESHOLD = 0.1  # kWh per slot to consider "meaningful" solar


class BridgePoint(NamedTuple):
    """The earliest time at which energy security is restored."""
    slot_index: int          # Index into the schedule slots array
    dt: datetime             # Datetime of the bridge-to point
    source: str              # "solar_generation" | "free_import_window" | "fallback_fixed"
    energy_needed_kwh: float # Energy required in battery at current time to safely bridge


def compute_bridge_point(
    hass: HomeAssistant,
    start_dt: datetime,
    slot_minutes: int,
    n_slots: int,
    solar_kwh_per_slot: list[float],
    load_kwh_per_slot: list[float],
    min_soc_floor_kwh: float,
    free_import_start: str | None,  # "HH:MM" or None
    free_import_end: str | None,
    bridge_to_fallback_time: str,   # "HH:MM"
) -> BridgePoint:
    """Compute the earliest slot where energy security is restored.

    "Energy security restored" = first slot where either:
    1. Solar generation meaningfully exceeds home load (solar rescue), OR
    2. A free import tariff window starts (grid rescue)

    Returns a BridgePoint with the slot index, datetime, source, and
    the energy (kWh) required in the battery NOW to safely bridge to that point
    while staying above the SOC floor the entire time.
    """
    slot_delta = timedelta(minutes=slot_minutes)

    # Compute candidate bridge points
    solar_bridge = _find_solar_bridge(solar_kwh_per_slot, load_kwh_per_slot, start_dt, slot_delta)
    import_bridge = _find_import_window_bridge(free_import_start, start_dt, slot_delta, n_slots)
    fallback_bridge = _find_fallback_bridge(bridge_to_fallback_time, start_dt, slot_delta, n_slots)

    # Pick the earliest rescue source
    candidates = [c for c in [solar_bridge, import_bridge, fallback_bridge] if c is not None]

    if not candidates:
        # Default to end of lookahead if nothing found
        bridge_slot = n_slots - 1
        bridge_source = "fallback_fixed"
    else:
        best = min(candidates, key=lambda c: c[0])
        bridge_slot, bridge_source = best

    bridge_dt = start_dt + slot_delta * bridge_slot

    # Compute energy needed: sum of net deficits from now to bridge point (capped at 0 per slot)
    # i.e., how much battery energy is needed to cover home load not covered by solar
    energy_needed = min_soc_floor_kwh
    for i in range(bridge_slot):
        net = load_kwh_per_slot[i] - solar_kwh_per_slot[i]
        if net > 0:
            energy_needed += net

    _LOGGER.debug(
        "Bridge point: slot %d at %s via %s, energy needed: %.2f kWh",
        bridge_slot, bridge_dt, bridge_source, energy_needed,
    )

    return BridgePoint(
        slot_index=bridge_slot,
        dt=bridge_dt,
        source=bridge_source,
        energy_needed_kwh=energy_needed,
    )


def _find_solar_bridge(
    solar_kwh: list[float],
    load_kwh: list[float],
    start_dt: datetime,
    slot_delta: timedelta,
) -> tuple[int, str] | None:
    """Find the first slot where solar generation meaningfully exceeds load."""
    # Skip slots in the near future that are clearly nighttime (next 3 hours)
    min_slot = max(0, 3 * 60 // int(slot_delta.total_seconds() / 60))

    for i in range(min_slot, len(solar_kwh)):
        dt = start_dt + slot_delta * i
        # Only consider daytime slots (5 AM to 8 PM)
        if 5 <= dt.hour <= 20:
            surplus = solar_kwh[i] - load_kwh[i]
            if surplus >= SOLAR_MEANINGFUL_KWH_THRESHOLD:
                return (i, "solar_generation")
    return None


def _find_import_window_bridge(
    free_import_start: str | None,
    start_dt: datetime,
    slot_delta: timedelta,
    n_slots: int,
) -> tuple[int, str] | None:
    """Find the first slot that falls within a free import window."""
    if not free_import_start:
        return None

    try:
        import_hour, import_minute = map(int, free_import_start.split(":"))
    except (ValueError, AttributeError):
        return None

    # Look for the free import window across the lookahead
    for day_offset in range(n_slots * int(slot_delta.total_seconds() / 3600) // 24 + 2):
        candidate = start_dt.replace(
            hour=import_hour,
            minute=import_minute,
            second=0,
            microsecond=0,
        ) + timedelta(days=day_offset)

        if candidate <= start_dt:
            continue

        # Find the slot index for this time
        slot_idx = int((candidate - start_dt).total_seconds() / slot_delta.total_seconds())
        if 0 <= slot_idx < n_slots:
            return (slot_idx, "free_import_window")

    return None


def _find_fallback_bridge(
    bridge_to_fallback_time: str,
    start_dt: datetime,
    slot_delta: timedelta,
    n_slots: int,
) -> tuple[int, str] | None:
    """Find the next occurrence of the configured fallback bridge time."""
    try:
        hour, minute = map(int, bridge_to_fallback_time.split(":"))
    except (ValueError, AttributeError):
        hour, minute = 11, 0

    for day_offset in range(3):
        candidate = start_dt.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        ) + timedelta(days=day_offset)

        if candidate <= start_dt:
            continue

        slot_idx = int((candidate - start_dt).total_seconds() / slot_delta.total_seconds())
        if 0 <= slot_idx < n_slots:
            return (slot_idx, "fallback_fixed")

    return None


def compute_energy_security_score(
    schedule_slots: list[dict],
    bridge_point: BridgePoint,
    capacity_kwh: float,
    min_soc_floor_kwh: float,
) -> float:
    """Compute a 0.0-1.0 energy security score.

    1.0 = projected SOC at bridge point is at or above what's needed.
    0.0 = projected SOC at bridge point is at or below the floor.
    """
    if not schedule_slots or bridge_point.slot_index >= len(schedule_slots):
        return 0.5  # Unknown

    bridge_slot = schedule_slots[bridge_point.slot_index]
    projected_soc_pct = bridge_slot.get("projected_soc", 0)
    projected_soc_kwh = (projected_soc_pct / 100.0) * capacity_kwh

    # Score: how much buffer above the floor at the bridge point
    if bridge_point.energy_needed_kwh <= min_soc_floor_kwh:
        return 1.0

    available = projected_soc_kwh - min_soc_floor_kwh
    needed = bridge_point.energy_needed_kwh - min_soc_floor_kwh

    if needed <= 0:
        return 1.0

    score = min(1.0, max(0.0, available / needed))
    return round(score, 3)
