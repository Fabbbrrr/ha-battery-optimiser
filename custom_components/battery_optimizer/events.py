"""Schedule-changed event detection and firing for Battery Optimizer."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant

from .const import EVENT_SCHEDULE_CHANGED

_LOGGER = logging.getLogger(__name__)

# Slots within this many minutes from now are considered "imminent"
IMMINENT_WINDOW_MINUTES = 120


def detect_and_fire_schedule_changes(
    hass: HomeAssistant,
    old_slots: list[dict[str, Any]],
    new_slots: list[dict[str, Any]],
    now: datetime,
) -> int:
    """Compare old and new schedules; fire EVENT_SCHEDULE_CHANGED for imminent slot changes.

    Only fires for slots whose start time is within IMMINENT_WINDOW_MINUTES of now,
    since those are actionable by automations right now.

    Returns the number of change events fired.
    """
    if not old_slots or not new_slots:
        return 0

    imminent_cutoff = now + timedelta(minutes=IMMINENT_WINDOW_MINUTES)
    old_by_start = {s.get("start", ""): s for s in old_slots}
    events_fired = 0

    for new_slot in new_slots:
        slot_start_str = new_slot.get("start", "")
        if not slot_start_str:
            continue

        try:
            slot_dt = datetime.fromisoformat(slot_start_str)
            if slot_dt.tzinfo is None:
                slot_dt = slot_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        # Only care about imminent slots
        if slot_dt < now or slot_dt > imminent_cutoff:
            continue

        old_slot = old_by_start.get(slot_start_str)
        if old_slot is None:
            # New slot with no prior — skip (fresh schedule start)
            continue

        old_action = old_slot.get("action")
        new_action = new_slot.get("action")
        old_power = old_slot.get("power_kw", 0.0)
        new_power = new_slot.get("power_kw", 0.0)

        action_changed = old_action != new_action
        # Consider power changed if it differs by more than 0.1 kW
        power_changed = abs((new_power or 0.0) - (old_power or 0.0)) > 0.1

        if action_changed or power_changed:
            event_data = {
                "slot_start": slot_start_str,
                "slot_end": new_slot.get("end", ""),
                "old_action": old_action,
                "new_action": new_action,
                "old_power_kw": old_power,
                "new_power_kw": new_power,
                "projected_soc": new_slot.get("projected_soc"),
                "reason": _determine_reason(old_slot, new_slot),
            }
            hass.bus.async_fire(EVENT_SCHEDULE_CHANGED, event_data)
            _LOGGER.debug(
                "schedule_changed fired: %s → %s at %s (power %.2f→%.2f kW)",
                old_action, new_action, slot_start_str, old_power, new_power,
            )
            events_fired += 1

    return events_fired


def _determine_reason(old_slot: dict[str, Any], new_slot: dict[str, Any]) -> str:
    """Return a human-readable reason string for the schedule change."""
    old_action = old_slot.get("action", "unknown")
    new_action = new_slot.get("action", "unknown")

    if new_slot.get("is_override"):
        return "manual_override"
    if old_action != new_action:
        return f"action_changed_{old_action}_to_{new_action}"
    old_power = old_slot.get("power_kw", 0.0)
    new_power = new_slot.get("power_kw", 0.0)
    if abs((new_power or 0.0) - (old_power or 0.0)) > 0.1:
        direction = "increased" if (new_power or 0.0) > (old_power or 0.0) else "reduced"
        return f"power_{direction}"
    return "schedule_updated"
