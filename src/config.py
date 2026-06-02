import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_ROOT = Path(__file__).parent.parent
_cfg_path = _ROOT / "config.yaml"

with open(_cfg_path) as f:
    _yaml = yaml.safe_load(f)


def _env(key: str, required: bool = True) -> str | None:
    val = os.environ.get(key)
    if required and not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val


ANTHROPIC_API_KEY: str = _env("ANTHROPIC_API_KEY")
EIA_API_KEY: str = _env("EIA_API_KEY")
NTFY_TOPIC: str = _env("NTFY_TOPIC")
ALPHAVANTAGE_KEY: str | None = _env("ALPHAVANTAGE_KEY", required=False)
KALSHI_API_KEY_ID: str | None = _env("KALSHI_API_KEY_ID", required=False)
KALSHI_PRIVATE_KEY_PATH: str | None = _env("KALSHI_PRIVATE_KEY_PATH", required=False)

POLL_INTERVAL_MINUTES: int = _yaml.get("poll_interval_minutes", 15)
CLAUDE_MODEL: str = _yaml.get("claude_model", "claude-haiku-4-5")
MIN_EDGE: float = _yaml.get("min_edge", 0.08)
MIN_PROBABILITY: float = _yaml.get("min_probability", 0.80)
MIN_CONFIDENCE: str = _yaml.get("min_confidence", "medium")
MAX_SPREAD: float = _yaml.get("max_spread", 0.03)
POSITION_SIZE_CAP: float = _yaml.get("position_size_cap", 500)
COOLDOWN_HOURS: int = _yaml.get("cooldown_hours", 4)
COOLDOWN_EDGE_GROWTH: float = _yaml.get("cooldown_edge_growth", 0.03)
MIN_DAYS_TO_RESOLUTION: int = _yaml.get("min_days_to_resolution", 1)
MAX_DAYS_TO_RESOLUTION: int = _yaml.get("max_days_to_resolution", 60)
MONITORED_SERIES: list[str] = _yaml.get("monitored_series", [])
EIA_CHECK_EVERY_N_CYCLES: int = _yaml.get("eia_check_every_n_cycles", 6)
ENABLE_ORDER_PLACEMENT: bool = _yaml.get("enable_order_placement", False)

KALSHI_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
DB_PATH = _ROOT / "data" / "kalshi_assistant.db"
LOG_DIR = _ROOT / "logs"
