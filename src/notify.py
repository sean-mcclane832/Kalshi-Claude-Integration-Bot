"""Phone notifications via ntfy.sh."""
import logging
from typing import Optional

import requests

from src import config

logger = logging.getLogger(__name__)
_NTFY_BASE = "https://ntfy.sh"


def send_trade_alert(
    ticker: str,
    question: str,
    side: str,
    claude_prob: float,
    kalshi_implied: float,
    edge: float,
    confidence: str,
    reasoning: str,
    underlying_label: str,
    underlying_value: float,
    days_to_resolution: float,
    kalshi_price: float,
) -> int:
    action = "BUY YES" if side == "yes" else "BUY NO"
    edge_pct = edge * 100
    side_prob = claude_prob if side == "yes" else 1.0 - claude_prob

    body = f"""**{ticker}** — {action} signal

**Question:** {question}

| Field | Value |
|---|---|
| Claude P({side.upper()}) | {side_prob:.1%} ({confidence} confidence) |
| Kalshi implied | {kalshi_implied:.1%} |
| Edge | **+{edge_pct:.1f} pp** |
| {underlying_label} | ${underlying_value:.3f} |
| Days to resolve | {days_to_resolution:.1f} |
| Suggested entry | ≤ ${kalshi_price:.2f} |

**Reasoning:** {reasoning}

⚠️ MAX POSITION: $500 | MANUAL APPROVAL REQUIRED"""

    return _post(
        title=f"Kalshi Edge: {action} {ticker} (+{edge_pct:.0f}pp)",
        body=body,
        priority="high",
        tags="money,chart_increasing",
        click=f"https://kalshi.com/markets/{ticker.lower().split('-')[0]}",
    )


def send_health_alert(message: str, priority: str = "low") -> None:
    _post(
        title="Kalshi Assistant — System Alert",
        body=message,
        priority=priority,
        tags="warning",
    )


def _post(title: str, body: str, priority: str = "default", tags: str = "", click: Optional[str] = None) -> int:
    headers = {
        "Title": title,
        "Priority": priority,
        "Markdown": "yes",
    }
    if tags:
        headers["Tags"] = tags
    if click:
        headers["Click"] = click
    topic = config.NTFY_TOPIC
    if not topic:
        logger.warning("ntfy topic not configured; skipping notification '%s'", title)
        return 0
    try:
        resp = requests.post(
            f"{_NTFY_BASE}/{topic}",
            data=body.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        logger.info("ntfy response: %d for '%s'", resp.status_code, title)
        return resp.status_code
    except Exception as e:
        logger.error("ntfy send error: %s", e)
        return 0
