"""EIA API cross-checks for WTI spot and retail gasoline."""
import logging
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import EIA_API_KEY

logger = logging.getLogger(__name__)
_BASE = "https://api.eia.gov/v2"


@retry(wait=wait_exponential(multiplier=1, min=2, max=20), stop=stop_after_attempt(3), reraise=False)
def get_wti_spot_latest() -> Optional[float]:
    """Latest EIA WTI Cushing spot price (daily, lagged ~3-4 business days)."""
    try:
        params = {
            "api_key": EIA_API_KEY,
            "data[]": "value",
            "facets[series][]": "RWTC",
            "frequency": "daily",
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": 1,
        }
        resp = requests.get(f"{_BASE}/petroleum/pri/spt/data", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("response", {}).get("data", [])
        if rows:
            price = float(rows[0]["value"])
            logger.debug("EIA WTI spot = %.2f (period: %s)", price, rows[0].get("period"))
            return price
    except Exception as e:
        logger.warning("EIA WTI spot error: %s", e)
    return None


@retry(wait=wait_exponential(multiplier=1, min=2, max=20), stop=stop_after_attempt(3), reraise=False)
def get_retail_gas_latest() -> Optional[float]:
    """Latest EIA US regular retail gasoline price (weekly, ~1-week lag)."""
    try:
        params = {
            "api_key": EIA_API_KEY,
            "data[]": "value",
            "facets[series][]": "EMM_EPMR_PTE_NUS_DPG",
            "frequency": "weekly",
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": 1,
        }
        resp = requests.get(f"{_BASE}/petroleum/pri/gnd/data", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("response", {}).get("data", [])
        if rows:
            price = float(rows[0]["value"]) / 100.0  # EIA returns cents/gallon
            logger.debug("EIA retail gas = $%.3f (period: %s)", price, rows[0].get("period"))
            return price
    except Exception as e:
        logger.warning("EIA retail gas error: %s", e)
    return None
