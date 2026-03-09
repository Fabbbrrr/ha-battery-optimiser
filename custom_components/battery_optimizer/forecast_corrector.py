"""Forecast bias correction using exponential-weighted learning from planned vs actual data.

At each slot boundary the tracker records (planned_solar_kwh, actual_solar_kwh,
planned_consumption_kwh, actual_consumption_kwh, planned_soc, actual_soc).
This module ingests those records and maintains per-hour EWM ratios so that
future forecasts are automatically scaled toward the historical truth.

Design goals:
- O(1) storage — a fixed-size set of arrays, independent of history length.
- No hard window — the EWM α parameter controls how fast old observations fade.
  With α=0.1 the effective half-life is ~7 observations per bucket, giving
  ~3-4 days of strong memory for solar (2 obs/day) and ~3-4 days for load.
  Seasonal patterns emerge naturally without needing explicit seasonal buckets.
- Cold-start safety — corrections are not applied until a bucket has at least
  `min_obs` observations to avoid over-fitting to a handful of data points.
- Clamped output — ratios are bounded to [0.3, 2.5] for solar and [0.5, 2.0]
  for load so that bad data cannot produce extreme adjustments.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

_LOGGER = logging.getLogger(__name__)

_WEEKDAY = "weekday"
_WEEKEND = "weekend"
_DAY_TYPES = [_WEEKDAY, _WEEKEND]

# Correction clamp limits
_SOLAR_CLAMP = (0.3, 2.5)
_LOAD_CLAMP  = (0.5, 2.0)

# Ignore planned values smaller than these to avoid noisy ratios
_MIN_SOLAR_PLANNED_KWH = 0.02
_MIN_LOAD_PLANNED_KWH  = 0.02


class ForecastCorrector:
    """Learns and applies multiplicative bias corrections for solar and load forecasts.

    Usage in coordinator:
        corrector.apply_corrections(solar_kwh, load_kwh, slot_start_times)
        → returns (corrected_solar, corrected_load)

        corrector.ingest_record(tracker_record)
        → updates EWM factors; returns True if any bucket was updated

        corrector.get_stats()
        → dict of human-readable state for UI / sensor attributes

        corrector.reset()
        → clears all learned factors back to 1.0
    """

    def __init__(self, alpha: float = 0.1, min_obs: int = 5) -> None:
        self._alpha   = alpha
        self._min_obs = min_obs

        # Solar: one EWM ratio per hour of day (0-23)
        self._solar_ratios: list[float] = [1.0] * 24
        self._solar_counts: list[int]   = [0]   * 24

        # Load: EWM ratio per hour per day-type
        self._load_ratios: dict[str, list[float]] = {dt: [1.0] * 24 for dt in _DAY_TYPES}
        self._load_counts: dict[str, list[int]]   = {dt: [0]   * 24 for dt in _DAY_TYPES}

        # SOC drift: rolling EWM mean of (actual_soc - planned_soc) in pp
        self._soc_drift:       float = 0.0
        self._soc_drift_count: int   = 0

        # ISO timestamp of the last ingested tracker record
        self._last_ingested_at: str = ""

    # ── Public properties ─────────────────────────────────────────────────

    @property
    def last_ingested_at(self) -> str:
        return self._last_ingested_at

    @last_ingested_at.setter
    def last_ingested_at(self, value: str) -> None:
        self._last_ingested_at = value

    # ── Reset ─────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear all learned factors back to 1.0 and reset observation counts."""
        self._solar_ratios = [1.0] * 24
        self._solar_counts = [0]   * 24
        self._load_ratios  = {dt: [1.0] * 24 for dt in _DAY_TYPES}
        self._load_counts  = {dt: [0]   * 24 for dt in _DAY_TYPES}
        self._soc_drift        = 0.0
        self._soc_drift_count  = 0
        self._last_ingested_at = ""
        _LOGGER.info("ForecastCorrector: all factors reset to 1.0")

    # ── Applying corrections ──────────────────────────────────────────────

    def apply_corrections(
        self,
        solar_kwh: list[float],
        load_kwh: list[float],
        slot_start_times: list[datetime],
    ) -> tuple[list[float], list[float]]:
        """Return bias-corrected (solar_kwh, load_kwh) arrays.

        Buckets below min_obs are returned unchanged (factor = 1.0).
        Factors are clamped to prevent runaway adjustments.
        """
        corrected_solar: list[float] = []
        corrected_load:  list[float] = []

        for i, t in enumerate(slot_start_times):
            hour     = t.hour
            day_type = _WEEKEND if t.weekday() >= 5 else _WEEKDAY

            solar_in = solar_kwh[i] if i < len(solar_kwh) else 0.0
            load_in  = load_kwh[i]  if i < len(load_kwh)  else 0.0

            # Solar factor (only applied if bucket has enough observations)
            solar_factor = 1.0
            if self._solar_counts[hour] >= self._min_obs:
                solar_factor = max(_SOLAR_CLAMP[0], min(_SOLAR_CLAMP[1], self._solar_ratios[hour]))

            # Load factor
            load_factor = 1.0
            if self._load_counts[day_type][hour] >= self._min_obs:
                load_factor = max(_LOAD_CLAMP[0], min(_LOAD_CLAMP[1], self._load_ratios[day_type][hour]))

            corrected_solar.append(solar_in * solar_factor)
            corrected_load.append(load_in   * load_factor)

        return corrected_solar, corrected_load

    # ── Ingesting tracker records ─────────────────────────────────────────

    def ingest_record(self, record: dict[str, Any]) -> bool:
        """Update EWM factors from one tracker record.

        Uses actual_generation_kwh if present (real inverter output), falling
        back to actual_solar_kwh (the forecast entity reading at slot end, which
        may not reflect true generation for cloud-based forecasts).

        Returns True if at least one bucket was updated.
        """
        slot_start = record.get("slot_start")
        if not slot_start:
            return False

        try:
            t = datetime.fromisoformat(slot_start)
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return False

        hour     = t.hour
        day_type = _WEEKEND if t.weekday() >= 5 else _WEEKDAY
        α        = self._alpha
        updated  = False

        # Solar ratio ─────────────────────────────────────────────────────
        planned_solar = record.get("planned_solar_kwh")
        # Prefer dedicated generation meter reading over forecast entity snapshot
        actual_solar  = record.get("actual_generation_kwh") or record.get("actual_solar_kwh")

        if (
            planned_solar is not None
            and planned_solar >= _MIN_SOLAR_PLANNED_KWH
            and actual_solar is not None
        ):
            ratio = actual_solar / planned_solar
            self._solar_ratios[hour] = (1 - α) * self._solar_ratios[hour] + α * ratio
            self._solar_counts[hour] = min(self._solar_counts[hour] + 1, 9999)
            updated = True

        # Load ratio ──────────────────────────────────────────────────────
        planned_load = record.get("planned_consumption_kwh")
        actual_load  = record.get("actual_consumption_kwh")

        if (
            planned_load is not None
            and planned_load >= _MIN_LOAD_PLANNED_KWH
            and actual_load is not None
        ):
            ratio = actual_load / planned_load
            self._load_ratios[day_type][hour] = (
                (1 - α) * self._load_ratios[day_type][hour] + α * ratio
            )
            self._load_counts[day_type][hour] = min(
                self._load_counts[day_type][hour] + 1, 9999
            )
            updated = True

        # SOC drift ───────────────────────────────────────────────────────
        planned_soc = record.get("planned_soc")
        actual_soc  = record.get("actual_soc")

        if planned_soc is not None and actual_soc is not None:
            drift  = actual_soc - planned_soc
            α_soc  = min(α, 0.05)  # slower adaptation for SOC — more stable
            self._soc_drift = (1 - α_soc) * self._soc_drift + α_soc * drift
            self._soc_drift_count += 1
            updated = True

        return updated

    # ── Stats for UI / diagnostics ────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return correction state dict suitable for sensor attributes and the panel UI."""
        solar_active = sum(1 for c in self._solar_counts if c >= self._min_obs)
        wd_active    = sum(1 for c in self._load_counts[_WEEKDAY] if c >= self._min_obs)
        we_active    = sum(1 for c in self._load_counts[_WEEKEND] if c >= self._min_obs)

        def _mean(values: list[float], counts: list[int]) -> float | None:
            active = [v for v, c in zip(values, counts) if c >= self._min_obs]
            return round(sum(active) / len(active), 3) if active else None

        return {
            "active":                  solar_active > 0 or wd_active > 0,
            "solar_active_hours":      solar_active,
            "solar_obs_total":         sum(self._solar_counts),
            "solar_mean_ratio":        _mean(self._solar_ratios, self._solar_counts),
            "solar_ratios":            [round(r, 3) for r in self._solar_ratios],
            "solar_counts":            list(self._solar_counts),
            "load_obs_total":          (
                sum(self._load_counts[_WEEKDAY]) + sum(self._load_counts[_WEEKEND])
            ),
            "load_mean_ratio_weekday": _mean(
                self._load_ratios[_WEEKDAY], self._load_counts[_WEEKDAY]
            ),
            "load_mean_ratio_weekend": _mean(
                self._load_ratios[_WEEKEND], self._load_counts[_WEEKEND]
            ),
            "load_ratios_weekday":     [round(r, 3) for r in self._load_ratios[_WEEKDAY]],
            "load_ratios_weekend":     [round(r, 3) for r in self._load_ratios[_WEEKEND]],
            "load_counts_weekday":     list(self._load_counts[_WEEKDAY]),
            "load_counts_weekend":     list(self._load_counts[_WEEKEND]),
            "soc_drift_pp":            (
                round(self._soc_drift, 2) if self._soc_drift_count > 0 else None
            ),
            "soc_drift_obs":           self._soc_drift_count,
            "min_obs_threshold":       self._min_obs,
            "alpha":                   self._alpha,
        }

    # ── Storage ───────────────────────────────────────────────────────────

    def to_storage(self) -> dict[str, Any]:
        """Serialise state for HA storage (~700 bytes, constant size)."""
        return {
            "solar_ratios":          self._solar_ratios,
            "solar_counts":          self._solar_counts,
            "load_ratios_weekday":   self._load_ratios[_WEEKDAY],
            "load_counts_weekday":   self._load_counts[_WEEKDAY],
            "load_ratios_weekend":   self._load_ratios[_WEEKEND],
            "load_counts_weekend":   self._load_counts[_WEEKEND],
            "soc_drift":             self._soc_drift,
            "soc_drift_count":       self._soc_drift_count,
            "last_ingested_at":      self._last_ingested_at,
        }

    def load_from_storage(self, data: dict[str, Any]) -> None:
        """Restore state from HA storage."""
        if not data:
            return
        self._solar_ratios          = data.get("solar_ratios",          [1.0] * 24)
        self._solar_counts          = data.get("solar_counts",          [0]   * 24)
        self._load_ratios[_WEEKDAY] = data.get("load_ratios_weekday",   [1.0] * 24)
        self._load_counts[_WEEKDAY] = data.get("load_counts_weekday",   [0]   * 24)
        self._load_ratios[_WEEKEND] = data.get("load_ratios_weekend",   [1.0] * 24)
        self._load_counts[_WEEKEND] = data.get("load_counts_weekend",   [0]   * 24)
        self._soc_drift             = data.get("soc_drift",             0.0)
        self._soc_drift_count       = data.get("soc_drift_count",       0)
        self._last_ingested_at      = data.get("last_ingested_at",      "")
