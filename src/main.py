"""Headless CLI entrypoint (no GUI).

Runs the monitoring loop in the foreground. For the desktop app, run
``python run_desktop.py`` instead.
"""
import argparse
import logging
import time
from pathlib import Path

from src import config
from src.monitor import MonitorController


def _setup_logging() -> None:
    Path(config.LOG_DIR).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(Path(config.LOG_DIR) / "assistant.log"),
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Kalshi Supervised Trading Assistant (CLI)")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    args = parser.parse_args()

    _setup_logging()
    logger = logging.getLogger(__name__)

    missing = config.get_missing_keys()
    if missing:
        logger.error("Missing required keys: %s. Set them in .env (see .env.example).", ", ".join(missing))
        raise SystemExit(1)

    controller = MonitorController()
    logger.info("Kalshi Supervised Trading Assistant starting (NO AUTO-TRADING).")

    if args.once:
        controller.run_one_cycle()
        return

    result = controller.start()
    if not result.get("ok"):
        logger.error("Could not start: %s", result.get("error"))
        raise SystemExit(1)

    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down.")
        controller.stop()


if __name__ == "__main__":
    main()
