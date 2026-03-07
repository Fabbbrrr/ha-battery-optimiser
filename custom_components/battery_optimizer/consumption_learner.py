"""Consumption profile learner.

Pulls historical home consumption from HA's recorder (long-term statistics),
builds time-of-day load profiles with configurable granularity (single / weekday-weekend / 7-day),
and learns the temperature→consumption relationship via linear regression.

Exponential decay weighting ensures recent data shapes the model more than old data.
All learned state persists in HA's .storage/ via StorageManager (handled by coordinator).
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    GRANULARITY_FULL_WEEK,
    GRANULARITY_SINGLE,
    GRANULARITY_WEEKDAY_WEEKEND,
    DEFAULT_CONSUMPTION_BASELINE_KW,
    DEFAULT_CONSUMPTION_LOOKBACK_DAYS,
    DEFAULT_DATA_RETENTION_DAYS,
)

_LOGGER = logging.getLogger(__name__)

# Day-type keys used in profile dicts
DAY_TYPE_SINGLE = "all"
DAY_TYPE_WEEKDAY = "weekday"
DAY_TYPE_WEEKEND = "weekend"
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Decay factor per day: weight = decay_factor^(days_ago)
# 0.95 = yesterday is 95% as important as today, 30 days ago ≈ 21%
DEFAULT_DECAY_FACTOR = 0.95


class ConsumptionLearner:
    """Manages learned consumption profiles and temperature correlations."""

    def __init__(
        self,
        baseline_kw: float = DEFAULT_CONSUMPTION_BASELINE_KW,
        granularity: str = GRANULARITY_WEEKDAY_WEEKEND,
        lookback_days: int = DEFAULT_CONSUMPTION_LOOKBACK_DAYS,
        retention_days: int = DEFAULT_DATA_RETENTION_DAYS,
        decay_factor: float = DEFAULT_DECAY_FACTOR,
    ) -> None:
        self.baseline_kw = baseline_kw
        self.granularity = granularity
        self.lookback_days = lookback_days
        self.retention_days = retention_days
        self.decay_factor = decay_factor

        # Learned profiles: day_type → hour (0-23) → avg kW
        # Keyed by granularity type
        self._profiles: dict[str, dict[int, float]] = {}

        # Temperature correlation coefficients
        self._temp_coefficients: dict[str, float] = {}

        # Raw hourly observations for incremental learning
        # Format: list of {"ts": ISO, "hour": int, "day_type": str, "kwh": float, "temp": float|None}
        self._observations: list[dict[str, Any]] = []

        self._is_trained = False

    def get_load_profile(
        self,
        start_dt: datetime,
        n_slots: int,
        slot_minutes: int,
    ) -> list[float]:
        """Return expected load (kWh) for each slot starting at start_dt.

        Falls back to static baseline_kw if no learned profile is available.
        """
        slot_hours = slot_minutes / 60.0
        slot_delta = timedelta(minutes=slot_minutes)
        result = []

        for i in range(n_slots):
            slot_dt = start_dt + slot_delta * i
            kw = self._lookup_kw(slot_dt)
            result.append(kw * slot_hours)

        return result

    def get_learning_status(self) -> dict[str, Any]:
        """Return a summary of current learning state for sensors and the UI card."""
        obs = self._observations
        count = len(obs)

        days_covered = 0
        last_trained: str | None = None
        oldest: str | None = None
        if obs:
            timestamps = [o.get("ts", "") for o in obs if o.get("ts")]
            if timestamps:
                timestamps.sort()
                oldest = timestamps[0]
                last_trained = timestamps[-1]
                try:
                    t0 = datetime.fromisoformat(oldest)
                    if t0.tzinfo is None:
                        t0 = t0.replace(tzinfo=timezone.utc)
                    t1 = datetime.fromisoformat(last_trained)
                    if t1.tzinfo is None:
                        t1 = t1.replace(tzinfo=timezone.utc)
                    days_covered = round((t1 - t0).total_seconds() / 86400, 1)
                except (ValueError, TypeError):
                    pass

        return {
            "is_trained": self._is_trained,
            "observation_count": count,
            "profile_types": sorted(self._profiles.keys()),
            "days_covered": days_covered,
            "has_temperature_model": bool(self._temp_coefficients),
            "last_trained": last_trained,
            "oldest_data": oldest,
            "granularity": self.granularity,
            "baseline_kw": self.baseline_kw,
            "lookback_days": self.lookback_days,
        }

    def get_temperature_coefficients(self) -> dict[str, float]:
        """Return learned temperature→consumption coefficients.

        Keys: comfort_low, comfort_high, slope_heat, slope_cool
        Returns empty dict if not yet calibrated.
        """
        return dict(self._temp_coefficients)

    def load_from_storage(self, stored: dict[str, Any]) -> None:
        """Restore learned state from .storage/ JSON."""
        if not stored:
            return
        self._profiles = stored.get("profiles", {})
        self._temp_coefficients = stored.get("temp_coefficients", {})
        self._observations = stored.get("observations", [])
        self._is_trained = bool(self._profiles)
        _LOGGER.debug(
            "ConsumptionLearner restored: %d profiles, %d observations",
            len(self._profiles),
            len(self._observations),
        )

    def to_storage(self) -> dict[str, Any]:
        """Serialize current state for .storage/ persistence."""
        # Prune old observations before saving
        cutoff = (dt_util.now() - timedelta(days=self.retention_days)).isoformat()
        self._observations = [o for o in self._observations if o.get("ts", "") >= cutoff]

        return {
            "profiles": self._profiles,
            "temp_coefficients": self._temp_coefficients,
            "observations": self._observations,
        }

    async def async_train_from_recorder(self, hass: HomeAssistant, consumption_entity: str) -> None:
        """Pull historical consumption from HA recorder and rebuild learned profile."""
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.statistics import (
                statistics_during_period,
            )
        except ImportError:
            _LOGGER.warning("Recorder integration not available — using baseline only")
            return

        end_dt = dt_util.now()
        start_dt = end_dt - timedelta(days=self.lookback_days)

        try:
            recorder = get_instance(hass)
            stats = await recorder.async_add_executor_job(
                statistics_during_period,
                hass,
                start_dt,
                end_dt,
                {consumption_entity},
                "hour",
                None,
                {"mean", "sum"},
            )
        except Exception as err:
            _LOGGER.error("Failed to read recorder statistics for %s: %s", consumption_entity, err)
            return

        _LOGGER.info(
            "Recorder returned stats for %d statistic IDs (looking for '%s')",
            len(stats),
            consumption_entity,
        )
        entity_stats = stats.get(consumption_entity, [])
        if not entity_stats:
            _LOGGER.warning(
                "No recorder statistics found for consumption entity '%s'. "
                "This entity must have state_class: total or total_increasing so that "
                "HA recorder tracks long-term statistics for it. "
                "Daily-resetting 'today total' sensors (like household_load_today_energy) work fine "
                "because HA compensates for resets in the statistics sum. "
                "Check: Developer Tools → Statistics and search for '%s'.",
                consumption_entity,
                consumption_entity,
            )
            return

        # Sort stats by timestamp so we can compute per-hour deltas from consecutive sum values.
        # HA recorder returns the running cumulative sum in stat["sum"] for energy sensors
        # (state_class: total_increasing). We must compute sum[t] - sum[t-1] to get per-hour kWh.
        def _stat_ts(s: dict) -> datetime:
            ts = s.get("start") or s.get("datetime")
            if isinstance(ts, (int, float)):
                # Unix timestamp (returned by some HA recorder versions)
                return datetime.fromtimestamp(float(ts), tz=timezone.utc)
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    return ts.replace(tzinfo=timezone.utc)
                return ts
            # Fallback: return epoch so it sorts first and gets skipped
            return datetime(1970, 1, 1, tzinfo=timezone.utc)

        try:
            entity_stats_sorted = sorted(entity_stats, key=_stat_ts)
        except Exception:
            entity_stats_sorted = list(entity_stats)

        # Convert stats to observations
        new_observations = []
        now = dt_util.now()
        prev_sum: float | None = None

        for stat in entity_stats_sorted:
            try:
                obs_dt = _stat_ts(stat)

                current_sum = stat.get("sum")
                mean_val = stat.get("mean")

                if current_sum is not None:
                    # Compute per-hour delta from consecutive cumulative sum values.
                    # Skip the first record (no previous to diff against).
                    if prev_sum is None:
                        prev_sum = current_sum
                        continue
                    kwh = current_sum - prev_sum
                    prev_sum = current_sum
                    # Guard against resets or negative deltas (e.g. sensor replaced)
                    if kwh < 0:
                        kwh = 0.0
                    # Guard against implausibly large spikes (>50 kWh/h) — treat as reset
                    if kwh > 50.0:
                        kwh = mean_val if mean_val is not None else self.baseline_kw
                elif mean_val is not None:
                    kwh = float(mean_val)
                else:
                    kwh = self.baseline_kw

                days_ago = (now - obs_dt).days
                if days_ago > self.retention_days:
                    continue

                new_observations.append({
                    "ts": obs_dt.isoformat(),
                    "hour": obs_dt.hour,
                    "day_type": _get_day_type(obs_dt, self.granularity),
                    "kwh": float(kwh),
                    "temp": None,  # Temperature linked separately
                    "weight": self.decay_factor ** days_ago,
                })
            except (KeyError, ValueError, TypeError):
                continue

        _LOGGER.info(
            "Recorder: %d raw stat records → %d usable observations after delta computation",
            len(entity_stats_sorted),
            len(new_observations),
        )
        if new_observations:
            self._observations = new_observations
            self._rebuild_profiles()
            _LOGGER.info(
                "ConsumptionLearner trained on %d hourly observations",
                len(new_observations),
            )
        else:
            _LOGGER.warning(
                "ConsumptionLearner: 0 observations after processing %d stat records for '%s'. "
                "Check that the entity has at least 2 hourly stat records in "
                "Developer Tools → Statistics.",
                len(entity_stats_sorted),
                consumption_entity,
            )

    def record_observation(
        self,
        obs_dt: datetime,
        kwh: float,
        temperature: float | None = None,
    ) -> None:
        """Record a single slot observation for incremental learning."""
        now = dt_util.now()
        days_ago = max(0, (now - obs_dt).days)

        self._observations.append({
            "ts": obs_dt.isoformat(),
            "hour": obs_dt.hour,
            "day_type": _get_day_type(obs_dt, self.granularity),
            "kwh": float(kwh),
            "temp": float(temperature) if temperature is not None else None,
            "weight": self.decay_factor ** days_ago,
        })

        # Rebuild incrementally after enough new data
        if len(self._observations) % 24 == 0:
            self._rebuild_profiles()

    def train_temperature_correlation(
        self,
        observations_with_temp: list[dict[str, Any]],
    ) -> None:
        """Fit temperature→consumption linear model from paired observations.

        Uses simple linear regression separately for heating (temp < comfort_low)
        and cooling (temp > comfort_high) ranges.
        """
        # Separate into heating/cooling regime observations
        # First pass: estimate comfort band as 25th-75th percentile of observed temps
        temps = [o["temp"] for o in observations_with_temp if o.get("temp") is not None]
        if len(temps) < 10:
            return

        temps_sorted = sorted(temps)
        p25 = temps_sorted[len(temps_sorted) // 4]
        p75 = temps_sorted[3 * len(temps_sorted) // 4]

        # Midrange consumption (in comfort zone) as baseline for regression
        comfort_obs = [
            o for o in observations_with_temp
            if o.get("temp") is not None and p25 <= o["temp"] <= p75
        ]
        if not comfort_obs:
            return

        weighted_sum = sum(o["kwh"] * o.get("weight", 1.0) for o in comfort_obs)
        weight_total = sum(o.get("weight", 1.0) for o in comfort_obs)
        comfort_baseline_kwh = weighted_sum / weight_total if weight_total > 0 else self.baseline_kw

        # Heating regime: obs below p25
        heat_obs = [o for o in observations_with_temp if o.get("temp") is not None and o["temp"] < p25]
        slope_heat = _fit_slope(heat_obs, p25, comfort_baseline_kwh)

        # Cooling regime: obs above p75
        cool_obs = [o for o in observations_with_temp if o.get("temp") is not None and o["temp"] > p75]
        slope_cool = _fit_slope(cool_obs, p75, comfort_baseline_kwh, invert=True)

        self._temp_coefficients = {
            "comfort_low": round(p25, 1),
            "comfort_high": round(p75, 1),
            "slope_heat": round(max(0.0, slope_heat), 4),
            "slope_cool": round(max(0.0, slope_cool), 4),
        }

        _LOGGER.debug("Temperature coefficients calibrated: %s", self._temp_coefficients)

    def _rebuild_profiles(self) -> None:
        """Rebuild time-of-day profiles from observations using weighted averaging."""
        if not self._observations:
            return

        # Group by day_type and hour
        buckets: dict[str, dict[int, list[tuple[float, float]]]] = {}
        # day_type → hour → [(kwh, weight), ...]

        for obs in self._observations:
            day_type = obs.get("day_type", DAY_TYPE_SINGLE)
            hour = obs.get("hour", 0)
            kwh = obs.get("kwh", self.baseline_kw)
            weight = obs.get("weight", 1.0)

            if day_type not in buckets:
                buckets[day_type] = {}
            if hour not in buckets[day_type]:
                buckets[day_type][hour] = []
            buckets[day_type][hour].append((kwh, weight))

        # Compute weighted average per bucket
        new_profiles: dict[str, dict[int, float]] = {}
        for day_type, hours in buckets.items():
            new_profiles[day_type] = {}
            for hour, samples in hours.items():
                w_sum = sum(w for _, w in samples)
                if w_sum > 0:
                    new_profiles[day_type][hour] = sum(v * w for v, w in samples) / w_sum
                else:
                    new_profiles[day_type][hour] = self.baseline_kw

        self._profiles = new_profiles
        self._is_trained = True

        # Also attempt temperature correlation
        obs_with_temp = [o for o in self._observations if o.get("temp") is not None]
        if len(obs_with_temp) >= 20:
            self.train_temperature_correlation(obs_with_temp)

    def _lookup_kw(self, slot_dt: datetime) -> float:
        """Look up the learned average kW for a given datetime slot."""
        if not self._is_trained or not self._profiles:
            return self.baseline_kw

        day_type = _get_day_type(slot_dt, self.granularity)
        hour = slot_dt.hour

        profile = self._profiles.get(day_type)
        if not profile:
            # Fall back to single profile if specific day_type not available
            profile = self._profiles.get(DAY_TYPE_SINGLE, {})

        if hour in profile:
            return profile[hour]

        # Interpolate from neighbouring hours
        if profile:
            prev_hour = max((h for h in profile if h <= hour), default=None)
            next_hour = min((h for h in profile if h >= hour), default=None)
            if prev_hour is not None and next_hour is not None and prev_hour != next_hour:
                frac = (hour - prev_hour) / (next_hour - prev_hour)
                return profile[prev_hour] + frac * (profile[next_hour] - profile[prev_hour])
            if prev_hour is not None:
                return profile[prev_hour]
            if next_hour is not None:
                return profile[next_hour]

        return self.baseline_kw


def _get_day_type(dt: datetime, granularity: str) -> str:
    """Return the day-type key for a datetime given the configured granularity."""
    if granularity == GRANULARITY_SINGLE:
        return DAY_TYPE_SINGLE
    if granularity == GRANULARITY_WEEKDAY_WEEKEND:
        return DAY_TYPE_WEEKDAY if dt.weekday() < 5 else DAY_TYPE_WEEKEND
    if granularity == GRANULARITY_FULL_WEEK:
        return DAY_NAMES[dt.weekday()]
    return DAY_TYPE_SINGLE


def _fit_slope(
    observations: list[dict[str, Any]],
    reference_temp: float,
    baseline_kwh: float,
    invert: bool = False,
) -> float:
    """Fit a weighted linear slope: extra_kwh per degree of temperature deviation.

    For heating: slope = Δkwh / Δtemp (below reference)
    For cooling: slope = Δkwh / Δtemp (above reference), invert=True flips the sign
    """
    if len(observations) < 3:
        return 0.0

    # Weighted least squares: slope = Σ(w * x * y) / Σ(w * x²)
    # where x = |temp - reference_temp|, y = kwh - baseline_kwh
    sx2 = 0.0
    sxy = 0.0

    for obs in observations:
        temp = obs.get("temp")
        kwh = obs.get("kwh", baseline_kwh)
        w = obs.get("weight", 1.0)
        if temp is None:
            continue

        x = abs(temp - reference_temp)
        y = kwh - baseline_kwh
        if invert:
            x = abs(temp - reference_temp)  # same direction

        sx2 += w * x * x
        sxy += w * x * y

    if sx2 < 1e-9:
        return 0.0

    slope = sxy / sx2
    return max(0.0, slope)  # Clamp negative slopes (more load from temp deviation)
