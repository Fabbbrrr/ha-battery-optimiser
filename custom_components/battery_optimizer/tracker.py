"""Planned-vs-actual slot tracking for Battery Optimizer.

At each slot boundary, polls actual SOC, solar generation, and home consumption
from the configured HA sensor entities and stores the values alongside the
original predictions. Data persists in .storage/ with configurable retention.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class PlannedVsActualTracker:
    """Schedules SOC/solar/consumption polls at slot boundaries and records actuals."""

    def __init__(
        self,
        hass: HomeAssistant,
        soc_entity: str,
        solar_entity: str | None,
        consumption_entity: str | None,
        capacity_kwh: float,
        retention_days: int = 90,
    ) -> None:
        self._hass = hass
        self._soc_entity = soc_entity
        self._solar_entity = solar_entity
        self._consumption_entity = consumption_entity
        self._capacity_kwh = capacity_kwh
        self._retention_days = retention_days

        # Records: list of dicts with predicted + actual values per slot boundary
        self._records: list[dict[str, Any]] = []
        self._scheduled_unsubs: list = []

    def load_from_storage(self, records: list[dict[str, Any]]) -> None:
        self._records = records or []

    def to_storage(self) -> list[dict[str, Any]]:
        """Return records pruned to retention window."""
        cutoff = (dt_util.now() - timedelta(days=self._retention_days)).isoformat()
        self._records = [r for r in self._records if r.get("slot_start", "") >= cutoff]
        return self._records

    def schedule_slot_polls(self, slots: list[dict[str, Any]]) -> None:
        """Cancel previous polls and schedule polls at each future slot boundary."""
        # Cancel any previously scheduled polls
        for unsub in self._scheduled_unsubs:
            try:
                unsub()
            except Exception:
                pass
        self._scheduled_unsubs = []

        now = dt_util.now()
        for slot in slots:
            if slot.get("is_historical"):
                continue
            try:
                slot_end_str = slot.get("end", "")
                slot_end = datetime.fromisoformat(slot_end_str)
                if slot_end.tzinfo is None:
                    slot_end = slot_end.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            if slot_end <= now:
                continue

            delay_seconds = (slot_end - now).total_seconds()
            if delay_seconds > 86400 * 7:
                continue  # Don't schedule more than 7 days ahead

            # Capture slot data in closure
            slot_copy = dict(slot)

            def make_callback(s):
                async def _poll(_dt):
                    await self._record_actual(s)
                return _poll

            unsub = async_call_later(self._hass, delay_seconds, make_callback(slot_copy))
            self._scheduled_unsubs.append(unsub)

    async def _record_actual(self, planned_slot: dict[str, Any]) -> None:
        """Poll actual values and append a planned-vs-actual record."""
        actual_soc = self._read_float(self._soc_entity)
        actual_solar = self._read_float(self._solar_entity)
        actual_consumption = self._read_float(self._consumption_entity)

        record = {
            "slot_start": planned_slot.get("start"),
            "slot_end": planned_slot.get("end"),
            "recorded_at": dt_util.now().isoformat(),
            # Planned values
            "planned_action": planned_slot.get("action"),
            "planned_power_kw": planned_slot.get("power_kw"),
            "planned_soc": planned_slot.get("projected_soc"),
            "planned_solar_kwh": planned_slot.get("expected_solar_kwh"),
            "planned_consumption_kwh": planned_slot.get("expected_consumption_kwh"),
            # Actual values
            "actual_soc": actual_soc,
            "actual_solar_kwh": actual_solar,
            "actual_consumption_kwh": actual_consumption,
        }

        self._records.append(record)

        _LOGGER.debug(
            "Recorded actuals for slot %s: SOC planned=%.1f%% actual=%.1f%%",
            planned_slot.get("start"),
            planned_slot.get("projected_soc", 0),
            actual_soc or 0,
        )

    def _read_float(self, entity_id: str | None) -> float | None:
        """Read the current numeric state of a HA entity."""
        if not entity_id:
            return None
        state = self._hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown", "none"):
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    def enrich_historical_slots(self, slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Annotate past slots in the schedule with actual values from records.

        Modifies a copy of each slot dict in-place and marks it is_historical=True.
        """
        record_by_start = {r.get("slot_start"): r for r in self._records}
        now = dt_util.now()
        enriched = []

        for slot in slots:
            slot_copy = dict(slot)
            try:
                slot_end = datetime.fromisoformat(slot.get("end", ""))
                if slot_end.tzinfo is None:
                    slot_end = slot_end.replace(tzinfo=timezone.utc)
                if slot_end <= now:
                    slot_copy["is_historical"] = True
                    rec = record_by_start.get(slot.get("start"))
                    if rec:
                        slot_copy["actual_soc"] = rec.get("actual_soc")
                        slot_copy["actual_solar_kwh"] = rec.get("actual_solar_kwh")
                        slot_copy["actual_consumption_kwh"] = rec.get("actual_consumption_kwh")
            except (ValueError, TypeError):
                pass
            enriched.append(slot_copy)

        return enriched

    def cancel_all(self) -> None:
        """Cancel all scheduled polls (called on integration unload)."""
        for unsub in self._scheduled_unsubs:
            try:
                unsub()
            except Exception:
                pass
        self._scheduled_unsubs = []
