"""Public (unauthenticated) Kalshi REST client for market data."""
import logging
from datetime import datetime, timezone
from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import KALSHI_BASE_URL

logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"Accept": "application/json"})


def _retry_on_transient(exc: BaseException) -> bool:
    if isinstance(exc, requests.HTTPError):
        return exc.response is not None and exc.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(exc, requests.ConnectionError)


@retry(
    retry=retry_if_exception_type((requests.ConnectionError, requests.HTTPError)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _get(path: str, params: dict | None = None) -> Any:
    url = f"{KALSHI_BASE_URL}{path}"
    resp = _SESSION.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_markets_by_series(series_ticker: str, status: str = "open") -> list[dict]:
    """List open markets for a series."""
    markets = []
    cursor = None
    while True:
        params: dict = {"series_ticker": series_ticker, "status": status, "limit": 100}
        if cursor:
            params["cursor"] = cursor
        data = _get("/markets", params)
        batch = data.get("markets", [])
        markets.extend(batch)
        cursor = data.get("cursor")
        if not cursor or len(batch) < 100:
            break
    return markets


def get_market(ticker: str) -> dict:
    """Single market details including prices and rules."""
    return _get(f"/markets/{ticker}")["market"]


def get_orderbook(ticker: str) -> dict:
    """Current orderbook for a market (no auth needed)."""
    return _get(f"/markets/{ticker}/orderbook")


def get_series(series_ticker: str) -> dict:
    return _get(f"/series/{series_ticker}")


def get_events(series_ticker: str) -> list[dict]:
    data = _get("/events", {"series_ticker": series_ticker, "status": "open"})
    return data.get("events", [])


def compute_implied_prob(market: dict) -> tuple[float | None, float | None]:
    """Return (yes_implied, no_implied) from market ask prices."""
    yes_ask = market.get("yes_ask")
    yes_bid = market.get("yes_bid")
    if yes_ask is not None and yes_bid is not None:
        yes_implied = yes_ask / 100.0   # Kalshi returns cents
        no_implied = 1.0 - (yes_bid / 100.0)
        return yes_implied, no_implied
    return None, None
