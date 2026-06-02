"""PyWebView desktop entrypoint.

Creates a native window hosting the HTML/CSS/JS dashboard and wires up the
Python :class:`~desktop.api.Api` bridge.
"""
import logging
import sys
from pathlib import Path

from src import config
from desktop.api import Api


def _web_root() -> Path:
    # PyInstaller frozen: web assets are in _MEIPASS/desktop/web
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "desktop" / "web"  # type: ignore[attr-defined]
    return Path(__file__).parent / "web"


def _setup_logging() -> None:
    Path(config.LOG_DIR).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(Path(config.LOG_DIR) / "desktop.log"),
        ],
    )


def main() -> None:
    _setup_logging()
    try:
        import webview
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            "pywebview is not installed. Run: pip install -r requirements.txt\n"
            "On Linux you also need a GUI backend, e.g.: pip install pywebview[qt]"
        ) from e

    api = Api()
    index = _web_root() / "index.html"
    window = webview.create_window(
        "Kalshi Supervised Trading Assistant",
        str(index),
        js_api=api,
        width=1240,
        height=860,
        min_size=(980, 640),
        background_color="#0f172a",
    )
    api.set_window(window)
    webview.start()


if __name__ == "__main__":
    main()
