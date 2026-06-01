"""WTI crude oil price from yfinance (primary) with Alpha Vantage fallback."""
import logging
import time
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import ALPHAVANTAGE_KEY

logger = logging.getLogger(__name__)

_cache: dict = {}
_CACHE_TTL = 600  # 10 minutes


def get_wti_price() -> Optional[float]:
    """Return front-month WTI futures price (CL=F). Cached 10 min."""
    now = time.time()
    if "wti" in _cache and now - _cache["wti"]["ts"] < _CACHE_TTL:
        return _cache["wti"]["price"]

    price = _fetch_yfinance("CL=F")
    if price is None:
        logger.warning("yfinance failed for CL=F, trying Alpha Vantage")
        price = _fetch_alpha_vantage_wti()

    if price is not None:
        _cache["wti"] = {"price": price, "ts": now}
    return price


def get_brent_price() -> Optional[float]:
    """Return front-month Brent futures price (BZ=F). Cached 10 min."""
    now = time.time()
    if "brent" in _cache and now - _cache["brent"]["ts"] < _CACHE_TTL:
        return _cache["brent"]["price"]

    price = _fetch_yfinance("BZ=F")
    if price is not None:
        _cache["brent"] = {"price": price, "ts": now}
    return price


def _fetch_yfinance(ticker: str) -> Optional[float]:
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).fast_info
        price = float(info["last_price"])
        logger.debug("yfinance %s = %.2f", ticker, price)
        return price
    except Exception as e:
        logger.warning("yfinance error for %s: %s", ticker, e)
        return None


@retry(wait=wait_exponential(multiplier=1, min=2, max=16), stop=stop_after_attempt(2), reraise=False)
def _fetch_alpha_vantage_wti() -> Optional[float]:
    if not ALPHAVANTAGE_KEY:
        return None
    try:
        url = "https://www.alphavantage.co/query"
        params = {"function": "WTI", "interval": "daily", "apikey": ALPHAVANTAGE_KEY}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        latest = data.get("data", [{}])[0]
        price = float(latest.get("value", "nan"))
        logger.debug("Alpha Vantage WTI = %.2f", price)
        return price
    except Exception as e:
        logger.warning("Alpha Vantage WTI error: %s", e)
        return None
