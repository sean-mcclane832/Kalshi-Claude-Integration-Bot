"""AAA national average gas price scraper (primary gas signal)."""
import logging
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_cache: dict = {}
_CACHE_TTL = 3600  # 1 hour — AAA updates once daily


def get_national_average() -> Optional[float]:
    """Scrape AAA's national average regular gas price. Cached 1 hour."""
    now = time.time()
    if "national" in _cache and now - _cache["national"]["ts"] < _CACHE_TTL:
        return _cache["national"]["price"]

    price = _scrape_aaa_national()
    if price is not None:
        _cache["national"] = {"price": price, "ts": now}
        logger.info("AAA national avg gas = $%.3f", price)
    else:
        logger.warning("Failed to fetch AAA national avg; returning cached value if available")
        if "national" in _cache:
            return _cache["national"]["price"]
    return price


@retry(wait=wait_exponential(multiplier=1, min=2, max=20), stop=stop_after_attempt(3), reraise=False)
def _scrape_aaa_national() -> Optional[float]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; KalshiAssistant/1.0; personal research tool)",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        resp = requests.get("https://gasprices.aaa.com/", headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Primary: look for the national average price display element
        # AAA typically shows it in a span/div with class containing "price" near "National Average"
        # Try several selectors in order of specificity
        text = soup.get_text(" ", strip=True)

        # Pattern: dollar amount near "National Average" or "Today's" text
        # Look for patterns like "$3.456" or "3.456"
        patterns = [
            r"National\s+Average[^$]*\$\s*(\d+\.\d{3})",
            r"Today['']s[^$]*\$\s*(\d+\.\d{3})",
            r"\$\s*(\d\.\d{3})",  # fallback: first 4-char dollar amount
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price = float(match.group(1))
                if 1.50 <= price <= 8.00:  # sanity range for US gas prices
                    return price

        logger.warning("Could not parse AAA price from page text. Snippet: %s", text[:500])
        return None
    except Exception as e:
        logger.warning("AAA scrape error: %s", e)
        return None
