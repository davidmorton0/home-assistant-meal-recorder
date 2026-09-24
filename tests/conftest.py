"""Test setup.

The pure modules (items, storage, aggregate, auth) hold no Home Assistant
imports, so they can be tested without it installed. The package __init__ does
import Home Assistant, so when it is missing we stand in a namespace package
pointing at the same directory; with Home Assistant installed the real package
is imported as usual.
"""

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:  # The DNS resolver starts a thread the test plugin would report as leaked.
    import pycares

    pycares.Channel()
except Exception:  # noqa: BLE001 - only a warm-up
    pass

if importlib.util.find_spec("homeassistant") is None:
    for name, path in (
        ("custom_components", ROOT / "custom_components"),
        ("custom_components.meal_recorder", ROOT / "custom_components" / "meal_recorder"),
    ):
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules.setdefault(name, module)
