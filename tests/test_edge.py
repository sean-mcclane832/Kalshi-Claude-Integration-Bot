"""Unit tests for edge computation logic."""
import pytest
from unittest.mock import patch
from src.analysis.edge import compute_edge, kalshi_taker_fee, should_notify


def test_compute_edge_positive():
    assert abs(compute_edge(0.85, 0.75) - 0.10) < 1e-9


def test_compute_edge_negative():
    assert abs(compute_edge(0.60, 0.75) - (-0.15)) < 1e-9


def test_taker_fee_peak_at_50():
    fee_50 = kalshi_taker_fee(0.50)
    fee_80 = kalshi_taker_fee(0.80)
    assert fee_50 > fee_80


def test_taker_fee_formula():
    # Marginal fee at 0.50: 0.07 * 1 * 0.5 * 0.5 = 0.0175
    assert kalshi_taker_fee(0.50) == pytest.approx(0.0175)


def test_should_notify_blocked_by_spread():
    with patch("src.analysis.edge.get_last_notification", return_value=None):
        fired, side, edge, reason = should_notify(
            ticker="TEST-1",
            claude_prob=0.90,
            confidence="high",
            kalshi_yes_ask=60.0,
            kalshi_yes_bid=50.0,  # spread = $0.10 > $0.03 max
            days_to_resolution=10.0,
            orderbook_depth_yes=10,
            orderbook_depth_no=10,
        )
    assert not fired
    assert "Spread" in reason


def test_should_notify_blocked_by_prob():
    with patch("src.analysis.edge.get_last_notification", return_value=None):
        fired, side, edge, reason = should_notify(
            ticker="TEST-2",
            claude_prob=0.70,  # below 0.80 min
            confidence="high",
            kalshi_yes_ask=55.0,
            kalshi_yes_bid=53.0,
            days_to_resolution=10.0,
            orderbook_depth_yes=10,
            orderbook_depth_no=10,
        )
    assert not fired


def test_should_notify_passes():
    with patch("src.analysis.edge.get_last_notification", return_value=None):
        fired, side, edge, reason = should_notify(
            ticker="TEST-3",
            claude_prob=0.92,  # high prob
            confidence="high",
            kalshi_yes_ask=80.0,
            kalshi_yes_bid=79.0,  # tight spread
            days_to_resolution=10.0,
            orderbook_depth_yes=50,
            orderbook_depth_no=50,
        )
    assert fired
    assert side == "yes"
