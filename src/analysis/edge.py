"""Edge computation and gate logic."""
import math
import logging
from datetime import datetime, timezone
from typing import Optional

from src.config import (
    MIN_EDGE, MIN_PROBABILITY, MIN_CONFIDENCE, MAX_SPREAD,
    POSITION_SIZE_CAP, COOLDOWN_HOURS, COOLDOWN_EDGE_GROWTH,
    MIN_DAYS_TO_RESOLUTION, MAX_DAYS_TO_RESOLUTION,
)
from src.storage import get_last_notification

logger = logging.getLogger(__name__)

_CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def kalshi_taker_fee(price: float, contracts: int = 1) -> float:
    """Fee per contract: round_up(0.07 * C * P * (1-P))."""
    return math.ceil(0.07 * contracts * price * (1 - price) * 100) / 100


def compute_edge(claude_prob: float, kalshi_implied: float) -> float:
    return claude_prob - kalshi_implied


def should_notify(
    ticker: str,
    claude_prob: float,
    confidence: str,
    kalshi_yes_ask: float,
    kalshi_yes_bid: float,
    days_to_resolution: float,
    orderbook_depth_yes: int,
    orderbook_depth_no: int,
) -> tuple[bool, str, float, str]:
    """
    Returns (should_notify, side, edge, reason_if_rejected).
    side is 'yes' or 'no'.
    """
    # Determine side and implied prob
    spread = kalshi_yes_ask - kalshi_yes_bid
    if spread > MAX_SPREAD:
        return False, "", 0.0, f"Spread ${spread:.3f} > max ${MAX_SPREAD}"

    yes_edge = compute_edge(claude_prob, kalshi_yes_ask / 100.0)
    no_edge = compute_edge(1.0 - claude_prob, 1.0 - kalshi_yes_bid / 100.0)

    if abs(yes_edge) >= abs(no_edge):
        side = "yes"
        edge = yes_edge
        kalshi_implied = kalshi_yes_ask / 100.0
        side_prob = claude_prob
    else:
        side = "no"
        edge = no_edge
        kalshi_implied = 1.0 - kalshi_yes_bid / 100.0
        side_prob = 1.0 - claude_prob

    # Gate 1: confidence and probability
    if side_prob < MIN_PROBABILITY:
        return False, side, edge, f"Prob {side_prob:.2f} < min {MIN_PROBABILITY}"
    if _CONFIDENCE_ORDER.get(confidence, 0) < _CONFIDENCE_ORDER.get(MIN_CONFIDENCE, 1):
        return False, side, edge, f"Confidence '{confidence}' below min '{MIN_CONFIDENCE}'"

    # Gate 2: minimum edge
    if abs(edge) < MIN_EDGE:
        return False, side, edge, f"Edge {edge:.3f} < min {MIN_EDGE}"

    # Gate 3: time filter
    if days_to_resolution < MIN_DAYS_TO_RESOLUTION:
        return False, side, edge, f"Only {days_to_resolution:.1f} days left (min {MIN_DAYS_TO_RESOLUTION})"
    if days_to_resolution > MAX_DAYS_TO_RESOLUTION:
        return False, side, edge, f"{days_to_resolution:.1f} days out (max {MAX_DAYS_TO_RESOLUTION})"

    # Gate 4: cost/EV sanity
    price_dollars = kalshi_implied
    max_contracts = int(POSITION_SIZE_CAP / (price_dollars * 100)) if price_dollars > 0 else 0
    if max_contracts == 0:
        return False, side, edge, "Cannot size position within cap"
    fee_per_contract = kalshi_taker_fee(price_dollars)
    ev = edge - fee_per_contract
    if ev <= 0:
        return False, side, edge, f"EV after fee {ev:.4f} <= 0"

    # Gate 5: cooldown
    last = get_last_notification(ticker)
    if last:
        last_ts = datetime.fromisoformat(last["ts"])
        hours_since = (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
        if hours_since < COOLDOWN_HOURS:
            prior_edge = abs(last["edge"] or 0)
            if abs(edge) < prior_edge + COOLDOWN_EDGE_GROWTH:
                return False, side, edge, f"In cooldown ({hours_since:.1f}h < {COOLDOWN_HOURS}h)"

    return True, side, edge, "passed"
