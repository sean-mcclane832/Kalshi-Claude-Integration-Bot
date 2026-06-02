"""JavaScript bridge API exposed to the PyWebView frontend.

Every public method here is callable from the frontend as
``pywebview.api.<method>(...)`` and must return JSON-serializable values.
"""
import logging
import os
from typing import Optional

from src import config
from src.calibration import run_calibration_report
from src.monitor import MonitorController
from src.notify import send_health_alert
from src.storage import count_rows, get_recent_estimates, get_recent_notifications

logger = logging.getLogger(__name__)

# Series the UI offers in Settings (label shown to the user).
AVAILABLE_SERIES = [
    {"ticker": "KXAAAGASM", "label": "US gas prices — monthly (AAA)"},
    {"ticker": "KXAAAGASW", "label": "US gas prices — weekly (AAA)"},
    {"ticker": "KXAAAGASMAX", "label": "US gas yearly high (AAA)"},
    {"ticker": "KXWTI", "label": "WTI oil — daily range (ICE front-month)"},
    {"ticker": "KXWTIW", "label": "WTI oil — weekly range (ICE front-month)"},
    {"ticker": "KXWTIMAX", "label": "WTI oil yearly high (ICE front-month)"},
]

CLAUDE_MODELS = ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"]
CONFIDENCE_LEVELS = ["low", "medium", "high"]


def _mask(value: Optional[str]) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "•" * len(value)
    return "•" * 6 + value[-4:]


class Api:
    def __init__(self) -> None:
        self.controller = MonitorController()
        self._window = None

    def set_window(self, window) -> None:
        self._window = window

    # ----------------------------------------------------------------- monitor
    def get_state(self) -> dict:
        return self.controller.state()

    def start_monitoring(self) -> dict:
        return self.controller.start()

    def stop_monitoring(self) -> dict:
        return self.controller.stop()

    def run_cycle_now(self) -> dict:
        return self.controller.run_once_async()

    # ---------------------------------------------------------------- settings
    def get_settings(self) -> dict:
        secrets = {}
        for key in config.SECRET_KEYS:
            val = os.environ.get(key)
            secrets[key] = {"set": bool(val), "masked": _mask(val)}
        return {
            "secrets": secrets,
            "tunables": config.as_tunables_dict(),
            "available_series": AVAILABLE_SERIES,
            "claude_models": CLAUDE_MODELS,
            "confidence_levels": CONFIDENCE_LEVELS,
            "required_keys": list(config.REQUIRED_FOR_RUN),
            "missing_keys": config.get_missing_keys(),
        }

    def save_settings(self, payload: dict) -> dict:
        """Persist secrets (.env) and tunables (config.yaml). Blank secrets are
        left unchanged. Refuses to enable order placement (supervised guardrail).
        """
        try:
            secrets = (payload or {}).get("secrets", {}) or {}
            tunables = (payload or {}).get("tunables", {}) or {}

            # Guardrail: never allow the UI to enable auto-execution.
            tunables["enable_order_placement"] = False

            clean_secrets = {k: v for k, v in secrets.items() if k in config.SECRET_KEYS and str(v).strip()}
            if clean_secrets:
                config.save_secrets(clean_secrets)
            if tunables:
                config.save_tunables(tunables)

            return {"ok": True, "missing_keys": config.get_missing_keys()}
        except Exception as e:  # noqa: BLE001
            logger.error("save_settings failed: %s", e, exc_info=True)
            return {"ok": False, "error": str(e)}

    def test_notification(self) -> dict:
        if not config.NTFY_TOPIC:
            return {"ok": False, "error": "Set an ntfy topic first."}
        try:
            send_health_alert(
                "✅ Test alert from your Kalshi Assistant. Notifications are working.",
                priority="default",
            )
            return {"ok": True, "topic": config.NTFY_TOPIC}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------- history
    def get_notifications(self, limit: int = 50) -> list:
        try:
            return get_recent_notifications(limit)
        except Exception as e:  # noqa: BLE001
            logger.error("get_notifications failed: %s", e)
            return []

    def get_estimates(self, limit: int = 100) -> list:
        try:
            return get_recent_estimates(limit)
        except Exception as e:  # noqa: BLE001
            return []

    def get_calibration(self) -> dict:
        try:
            report = run_calibration_report(send_notification=False)
            report["counts"] = count_rows()
            return report
        except Exception as e:  # noqa: BLE001
            logger.error("get_calibration failed: %s", e)
            return {"error": str(e)}
