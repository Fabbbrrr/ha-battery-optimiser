"""Constants for the Battery Optimizer integration."""

DOMAIN = "battery_optimizer"
PLATFORMS = ["sensor"]

# Config entry keys
CONF_BATTERY_SOC_ENTITY = "battery_soc_entity"
CONF_BATTERY_CAPACITY_KWH = "battery_capacity_kwh"
CONF_MIN_SOC_FLOOR_PERCENT = "min_soc_floor_percent"
CONF_MAX_CHARGE_RATE_KW = "max_charge_rate_kw"
CONF_MAX_DISCHARGE_RATE_KW = "max_discharge_rate_kw"
CONF_MAX_EXPORT_LIMIT_KW = "max_export_limit_kw"
CONF_MAX_EXPORT_LIMIT_ENTITY = "max_export_limit_entity"

# Solar forecast
CONF_SOLAR_FORECAST_ENTITY = "solar_forecast_entity"
CONF_SOLAR_FORECAST_FORMAT = "solar_forecast_format"
CONF_SOLAR_TOTAL_KWH_ENTITY = "solar_total_kwh_entity"  # generic fallback

# Forecast formats
FORECAST_FORMAT_AUTO = "auto"
FORECAST_FORMAT_FORECAST_SOLAR = "forecast_solar"
FORECAST_FORMAT_SOLCAST = "solcast"
FORECAST_FORMAT_GENERIC_KWH = "generic_kwh"

# Weather
CONF_WEATHER_ENTITY = "weather_entity"

# Consumption
CONF_CONSUMPTION_ENTITY = "consumption_entity"
CONF_CONSUMPTION_BASELINE_KW = "consumption_baseline_kw"
CONF_CONSUMPTION_PROFILE_GRANULARITY = "consumption_profile_granularity"
CONF_CONSUMPTION_LOOKBACK_DAYS = "consumption_lookback_days"

GRANULARITY_SINGLE = "single"
GRANULARITY_WEEKDAY_WEEKEND = "weekday_weekend"
GRANULARITY_FULL_WEEK = "full_week"

# Tariff periods
CONF_TARIFF_PERIODS = "tariff_periods"
CONF_EXPORT_BONUS_START = "export_bonus_start"
CONF_EXPORT_BONUS_END = "export_bonus_end"
CONF_EXPORT_BONUS_RATE = "export_bonus_rate"
CONF_STANDARD_EXPORT_RATE = "standard_export_rate"
CONF_STANDARD_IMPORT_RATE = "standard_import_rate"
CONF_FREE_IMPORT_START = "free_import_start"
CONF_FREE_IMPORT_END = "free_import_end"
CONF_PEAK_IMPORT_START = "peak_import_start"
CONF_PEAK_IMPORT_END = "peak_import_end"
CONF_PEAK_IMPORT_RATE = "peak_import_rate"

# Grid charging
CONF_GRID_CHARGING_ENABLED = "grid_charging_enabled"
CONF_GRID_CHARGE_WINDOWS = "grid_charge_windows"

# Optimizer settings
CONF_SLOT_GRANULARITY_MINUTES = "slot_granularity_minutes"
CONF_LOOKAHEAD_HOURS = "lookahead_hours"
CONF_AGGRESSIVENESS = "aggressiveness"
CONF_RECALCULATION_INTERVAL_MINUTES = "recalculation_interval_minutes"
CONF_SOLVER_TIMEOUT_SECONDS = "solver_timeout_seconds"
CONF_FALLBACK_MODE = "fallback_mode"
CONF_DATA_RETENTION_DAYS = "data_retention_days"
CONF_BRIDGE_TO_FALLBACK_TIME = "bridge_to_fallback_time"

# Fallback modes
FALLBACK_CONSERVATIVE_HOLD = "conservative_hold"
FALLBACK_LAST_KNOWN_GOOD = "last_known_good"
FALLBACK_ERROR_STATE = "error_state"

# Slot actions
ACTION_CHARGE = "charge"
ACTION_DISCHARGE = "discharge"
ACTION_HOLD = "hold"
ACTION_EXPORT = "export"

# Optimizer states
STATE_RUNNING = "running"
STATE_PAUSED = "paused"
STATE_ERROR = "error"
STATE_FALLBACK = "fallback"

# Defaults
DEFAULT_MIN_SOC_FLOOR_PERCENT = 20
DEFAULT_MAX_CHARGE_RATE_KW = 5.0
DEFAULT_MAX_DISCHARGE_RATE_KW = 5.0
DEFAULT_MAX_EXPORT_LIMIT_KW = 5.0
DEFAULT_SLOT_GRANULARITY_MINUTES = 30
DEFAULT_LOOKAHEAD_HOURS = 48
DEFAULT_AGGRESSIVENESS = 0.7
DEFAULT_RECALCULATION_INTERVAL_MINUTES = 30
DEFAULT_SOLVER_TIMEOUT_SECONDS = 30
DEFAULT_FALLBACK_MODE = FALLBACK_CONSERVATIVE_HOLD
DEFAULT_DATA_RETENTION_DAYS = 90
DEFAULT_CONSUMPTION_BASELINE_KW = 0.5
DEFAULT_CONSUMPTION_LOOKBACK_DAYS = 30
DEFAULT_CONSUMPTION_PROFILE_GRANULARITY = GRANULARITY_WEEKDAY_WEEKEND
DEFAULT_BRIDGE_TO_FALLBACK_TIME = "11:00"
DEFAULT_STANDARD_EXPORT_RATE = 0.0
DEFAULT_STANDARD_IMPORT_RATE = 0.30

# Sensor entity IDs
SENSOR_SCHEDULE = "schedule"
SENSOR_HEALTH = "health"
SENSOR_STATE = "state"

# Storage keys
STORAGE_KEY_LEARNED_PROFILES = f"{DOMAIN}.learned_profiles"
STORAGE_KEY_PLANNED_VS_ACTUAL = f"{DOMAIN}.planned_vs_actual"
STORAGE_KEY_OPTIMIZER_STATE = f"{DOMAIN}.optimizer_state"
STORAGE_VERSION = 1

# Events
EVENT_SCHEDULE_CHANGED = f"{DOMAIN}_schedule_changed"

# Services
SERVICE_RECALCULATE_NOW = "recalculate_now"
SERVICE_SET_AGGRESSIVENESS = "set_aggressiveness"
SERVICE_OVERRIDE_SLOT = "override_slot"
SERVICE_PAUSE = "pause"
SERVICE_RESUME = "resume"

# Slot attribute keys
ATTR_SLOTS = "slots"
ATTR_SLOT_START = "start"
ATTR_SLOT_END = "end"
ATTR_ACTION = "action"
ATTR_POWER_KW = "power_kw"
ATTR_PROJECTED_SOC = "projected_soc"
ATTR_EXPECTED_SOLAR_KWH = "expected_solar_kwh"
ATTR_EXPECTED_CONSUMPTION_KWH = "expected_consumption_kwh"
ATTR_NET_ENERGY_KWH = "net_energy_kwh"
ATTR_IS_OVERRIDE = "is_override"
ATTR_IS_HISTORICAL = "is_historical"
ATTR_ACTUAL_SOC = "actual_soc"
ATTR_ACTUAL_SOLAR_KWH = "actual_solar_kwh"
ATTR_ACTUAL_CONSUMPTION_KWH = "actual_consumption_kwh"

# Health attribute keys
ATTR_SOLVER_STATUS = "solver_status"
ATTR_FORECAST_STALENESS_SECONDS = "forecast_staleness_seconds"
ATTR_SOC_SENSOR_AVAILABLE = "soc_sensor_available"
ATTR_LAST_RECALCULATION = "last_recalculation"
ATTR_SOLVER_DURATION_MS = "solver_duration_ms"
ATTR_PROBLEM_SIZE = "problem_size"
ATTR_FALLBACK_MODE_ACTIVE = "fallback_mode_active"
ATTR_ESTIMATED_EXPORT_REVENUE = "estimated_export_revenue"
ATTR_ENERGY_SECURITY_SCORE = "energy_security_score"
ATTR_FORECAST_CONFIDENCE = "forecast_confidence"
ATTR_BRIDGE_TO_TIME = "bridge_to_time"
ATTR_BRIDGE_TO_SOURCE = "bridge_to_source"
