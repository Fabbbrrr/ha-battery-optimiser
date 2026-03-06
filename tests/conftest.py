"""Test configuration - mocks homeassistant for unit testing."""
import sys
from unittest.mock import MagicMock

# Mock all homeassistant modules before any test imports
for mod_name in [
    "homeassistant",
    "homeassistant.core",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.helpers",
    "homeassistant.helpers.event",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.helpers.storage",
    "homeassistant.helpers.entity_registry",
    "homeassistant.helpers.selector",
    "homeassistant.util",
    "homeassistant.util.dt",
    "homeassistant.data_entry_flow",
    "homeassistant.components",
    "homeassistant.components.recorder",
    "homeassistant.components.recorder.statistics",
    "homeassistant.http",
    "voluptuous",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

# Add custom_components to path for imports
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components"))
