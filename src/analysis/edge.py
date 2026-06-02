"""Edge computation and gate logic.

Thresholds are read from :mod:`src.config` at call time so that edits made in
the desktop Settings screen take effect on the next cycle without a restart.
"""
import logging
import math
from datetime import datetime, timezone

from src import config
from src.storage import get_last_notification

logger = logging.getLogger(__name__)

_CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def kalshi_taker_fee(price: float, contracts: int = 1) -> float:
    """Marginal Kalshi taker fee in dollars: ``0.07 * C * P * (1-P)``.

    Kalshi charges ``round_up`` of this to the next cent on the *order total*;
    for per-contract EV math we use the unrounded marginal fee, which matches
    Kalshi's published peak of $0.0175 (1.75c) on a 50c contract and ~$0.0112
    on an 80c contract.
    """
    return 0.07 * contracts * price * (1.0 - price)


def kalshi_taker_fee_charged(price: float, contracts: int = 1) -> float:
    """Actual fee charged: the marginal fee rounded up to the next cent."""
    return math.ceil(kalshi_taker_fee(price, contracts) * 100) / 100


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
    """Decide whether an edge warrants a notification.

    ``kalshi_yes_ask`` / ``kalshi_yes_bid`` are in **cents** (Kalshi's native
    units, 1-99). Returns ``(should_notify, side, edge, reason)`` where ``side``
    is ``"yes"`` or ``"no"`` and ``edge`` is the (positive) edge for the chosen
    side, expressed as a fraction (0-1).
    """
    # Spread gate (convert cents -> dollars to compare with MAX_SPREAD).
    spread = (kalshi_yes_ask - kalshi_yes_bid) / 100.0
    if spread > config.MAX_SPREAD:
        return False, "", 0.0, f"Spread ${spread:.3f} > max ${config.MAX_SPREAD}"

    # Edge of buying each side, as a positive-is-good opportunity.
    #   buy YES: pay the ask, win if YES  -> claude_prob - ask
    #   buy NO : pay (1 - bid), win if NO -> (1 - claude_prob) - (1 - bid)
    yes_ask = kalshi_yes_ask / 100.0
    no_ask = 1.0 - kalshi_yes_bid / 100.0
    edge_yes = claude_prob - yes_ask
    edge_no = (1.0 - claude_prob) - no_ask

    if edge_yes >= edge_no:
        side, edge, kalshi_implied, side_prob = "yes", edge_yes, yes_ask, claude_prob
    else:
        side, edge, kalshi_implied, side_prob = "no", edge_no, no_ask, 1.0 - claude_prob

    # Gate 1: high-confidence discipline rule.
    if side_prob < config.MIN_PROBABILITY:
        return False, side, edge, f"Prob {side_prob:.2f} < min {config.MIN_PROBABILITY}"
    if _CONFIDENCE_ORDER.get(confidence, 0) < _CONFIDENCE_ORDER.get(config.MIN_CONFIDENCE, 1):
        return False, side, edge, f"Confidence '{confidence}' below min '{config.MIN_CONFIDENCE}'"

    # Gate 2: minimum (positive) edge.
    if edge < config.MIN_EDGE:
        return False, side, edge, f"Edge {edge:.3f} < min {config.MIN_EDGE}"

    # Gate 3: time-to-resolution band.
    if days_to_resolution < config.MIN_DAYS_TO_RESOLUTION:
        return False, side, edge, f"Only {days_to_resolution:.1f}d left (min {config.MIN_DAYS_TO_RESOLUTION})"
    if days_to_resolution > config.MAX_DAYS_TO_RESOLUTION:
        return False, side, edge, f"{days_to_resolution:.1f}d out (max {config.MAX_DAYS_TO_RESOLUTION})"

    # Gate 4: cost / EV sanity (after Kalshi taker fee).
    price_dollars = kalshi_implied
    max_contracts = int(config.POSITION_SIZE_CAP / (price_dollars * 100)) if price_dollars > 0 else 0
    if max_contracts == 0:
        return False, side, edge, "Cannot size position within cap"
    fee_per_contract = kalshi_taker_fee(price_dollars)
    ev = edge - fee_per_contract
    if ev <= 0:
        return False, side, edge, f"EV after fee {ev:.4f} <= 0"

    # Gate 5: per-market cooldown (unless edge grew materially).
    last = get_last_notification(ticker)
    if last:
        last_ts = datetime.fromisoformat(last["ts"])
        hours_since = (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
        if hours_since < config.COOLDOWN_HOURS:
            prior_edge = abs(last["edge"] or 0)
            if edge < prior_edge + config.COOLDOWN_EDGE_GROWTH:
                return False, side, edge, f"In cooldown ({hours_since:.1f}h < {config.COOLDOWN_HOURS}h)"

    return True, side, edge, "passed"
