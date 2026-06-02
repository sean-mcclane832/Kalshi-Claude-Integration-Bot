"""Central configuration.

Loads secrets from ``.env`` and tunables from ``config.yaml``.

This module never raises at import time so that the desktop app can launch on a
fresh machine (with no keys yet) and let the user enter credentials in the
Settings screen. Call :func:`get_missing_keys` to check whether the app is
ready to run, and :func:`reload` after the user edits settings so new values
take effect without restarting.
"""
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv


def _find_root() -> Path:
    # When running as a PyInstaller frozen bundle, sys._MEIPASS is the temp
    # directory where the bundle is extracted.  The .env and config.yaml must
    # live next to the executable (sys.executable) so the user can edit them.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


_ROOT = _find_root()
CONFIG_PATH = _ROOT / "config.yaml"
ENV_PATH = _ROOT / ".env"

# --- Secrets (from .env) ---
ANTHROPIC_API_KEY: str | None = None
EIA_API_KEY: str | None = None
NTFY_TOPIC: str | None = None
ALPHAVANTAGE_KEY: str | None = None
KALSHI_API_KEY_ID: str | None = None
KALSHI_PRIVATE_KEY_PATH: str | None = None

# --- Tunables (from config.yaml; defaults below) ---
POLL_INTERVAL_MINUTES: int = 15
CLAUDE_MODEL: str = "claude-haiku-4-5"
MIN_EDGE: float = 0.08
MIN_PROBABILITY: float = 0.80
MIN_CONFIDENCE: str = "medium"
MAX_SPREAD: float = 0.03
POSITION_SIZE_CAP: float = 500
COOLDOWN_HOURS: int = 4
COOLDOWN_EDGE_GROWTH: float = 0.03
MIN_DAYS_TO_RESOLUTION: int = 1
MAX_DAYS_TO_RESOLUTION: int = 60
MONITORED_SERIES: list[str] = []
EIA_CHECK_EVERY_N_CYCLES: int = 6
ENABLE_ORDER_PLACEMENT: bool = False

# --- Constants ---
KALSHI_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
DB_PATH = _ROOT / "data" / "kalshi_assistant.db"
LOG_DIR = _ROOT / "logs"

# Secret keys required before monitoring can start.
REQUIRED_FOR_RUN = ("ANTHROPIC_API_KEY", "EIA_API_KEY", "NTFY_TOPIC")
# All secret keys the Settings screen manages.
SECRET_KEYS = (
    "ANTHROPIC_API_KEY",
    "EIA_API_KEY",
    "NTFY_TOPIC",
    "ALPHAVANTAGE_KEY",
    "KALSHI_API_KEY_ID",
    "KALSHI_PRIVATE_KEY_PATH",
)

# Tunable keys exposed to the Settings screen (yaml name -> module attribute).
TUNABLE_KEYS = (
    "poll_interval_minutes",
    "claude_model",
    "min_edge",
    "min_probability",
    "min_confidence",
    "max_spread",
    "position_size_cap",
    "cooldown_hours",
    "cooldown_edge_growth",
    "min_days_to_resolution",
    "max_days_to_resolution",
    "monitored_series",
    "eia_check_every_n_cycles",
    "enable_order_placement",
)


def reload() -> None:
    """Re-read ``.env`` and ``config.yaml`` and update module globals."""
    global ANTHROPIC_API_KEY, EIA_API_KEY, NTFY_TOPIC, ALPHAVANTAGE_KEY
    global KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH
    global POLL_INTERVAL_MINUTES, CLAUDE_MODEL, MIN_EDGE, MIN_PROBABILITY
    global MIN_CONFIDENCE, MAX_SPREAD, POSITION_SIZE_CAP, COOLDOWN_HOURS
    global COOLDOWN_EDGE_GROWTH, MIN_DAYS_TO_RESOLUTION, MAX_DAYS_TO_RESOLUTION
    global MONITORED_SERIES, EIA_CHECK_EVERY_N_CYCLES, ENABLE_ORDER_PLACEMENT

    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=True)
    else:
        load_dotenv(override=True)

    def _secret(key: str) -> str | None:
        val = os.environ.get(key)
        return val if val else None

    ANTHROPIC_API_KEY = _secret("ANTHROPIC_API_KEY")
    EIA_API_KEY = _secret("EIA_API_KEY")
    NTFY_TOPIC = _secret("NTFY_TOPIC")
    ALPHAVANTAGE_KEY = _secret("ALPHAVANTAGE_KEY")
    KALSHI_API_KEY_ID = _secret("KALSHI_API_KEY_ID")
    KALSHI_PRIVATE_KEY_PATH = _secret("KALSHI_PRIVATE_KEY_PATH")

    y: dict = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            y = yaml.safe_load(f) or {}

    POLL_INTERVAL_MINUTES = y.get("poll_interval_minutes", 15)
    CLAUDE_MODEL = y.get("claude_model", "claude-haiku-4-5")
    MIN_EDGE = y.get("min_edge", 0.08)
    MIN_PROBABILITY = y.get("min_probability", 0.80)
    MIN_CONFIDENCE = y.get("min_confidence", "medium")
    MAX_SPREAD = y.get("max_spread", 0.03)
    POSITION_SIZE_CAP = y.get("position_size_cap", 500)
    COOLDOWN_HOURS = y.get("cooldown_hours", 4)
    COOLDOWN_EDGE_GROWTH = y.get("cooldown_edge_growth", 0.03)
    MIN_DAYS_TO_RESOLUTION = y.get("min_days_to_resolution", 1)
    MAX_DAYS_TO_RESOLUTION = y.get("max_days_to_resolution", 60)
    MONITORED_SERIES = y.get("monitored_series", [])
    EIA_CHECK_EVERY_N_CYCLES = y.get("eia_check_every_n_cycles", 6)
    ENABLE_ORDER_PLACEMENT = y.get("enable_order_placement", False)


def get_missing_keys() -> list[str]:
    """Return the required secret keys that are not yet set."""
    return [k for k in REQUIRED_FOR_RUN if not os.environ.get(k)]


def is_ready() -> bool:
    return not get_missing_keys()


def as_tunables_dict() -> dict:
    """Current tunable values keyed by their yaml names (for the UI)."""
    return {
        "poll_interval_minutes": POLL_INTERVAL_MINUTES,
        "claude_model": CLAUDE_MODEL,
        "min_edge": MIN_EDGE,
        "min_probability": MIN_PROBABILITY,
        "min_confidence": MIN_CONFIDENCE,
        "max_spread": MAX_SPREAD,
        "position_size_cap": POSITION_SIZE_CAP,
        "cooldown_hours": COOLDOWN_HOURS,
        "cooldown_edge_growth": COOLDOWN_EDGE_GROWTH,
        "min_days_to_resolution": MIN_DAYS_TO_RESOLUTION,
        "max_days_to_resolution": MAX_DAYS_TO_RESOLUTION,
        "monitored_series": list(MONITORED_SERIES),
        "eia_check_every_n_cycles": EIA_CHECK_EVERY_N_CYCLES,
        "enable_order_placement": ENABLE_ORDER_PLACEMENT,
    }


def save_tunables(updates: dict) -> None:
    """Persist tunables to ``config.yaml`` and reload."""
    current = as_tunables_dict()
    for key in TUNABLE_KEYS:
        if key in updates and updates[key] is not None:
            current[key] = updates[key]
    header = (
        "# Kalshi Supervised Trading Assistant configuration.\n"
        "# Managed by the desktop Settings screen; safe to hand-edit too.\n"
    )
    with open(CONFIG_PATH, "w") as f:
        f.write(header)
        yaml.safe_dump(current, f, default_flow_style=False, sort_keys=False)
    reload()


def save_secrets(updates: dict) -> None:
    """Update ``.env`` with the provided secret values (blank = leave as-is)."""
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    out: list[str] = []
    seen: set[str] = set()

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates and str(updates[key]).strip():
                out.append(f"{key}={str(updates[key]).strip()}")
                seen.add(key)
                continue
        out.append(line)

    for key, val in updates.items():
        if key in SECRET_KEYS and key not in seen and str(val).strip():
            out.append(f"{key}={str(val).strip()}")

    ENV_PATH.write_text("\n".join(out).rstrip("\n") + "\n")
    reload()


# Initialize on import (never raises).
reload()
