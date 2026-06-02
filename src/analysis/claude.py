"""Claude API integration for probability estimation."""
import json
import logging
from typing import Optional

from anthropic import Anthropic
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)
_client = Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """You are a calibrated prediction market analyst specializing in energy commodities.
Your task is to estimate the probability that a specific Kalshi binary contract resolves YES.

Rules for your analysis:
1. Reason from fundamentals to probability — don't just echo the market price.
2. Explicitly account for: time remaining to resolution, current underlying value vs threshold/range, historical volatility, and directional trend.
3. Provide a well-calibrated probability. If you say 80%, you should be right about 80% of the time.
4. Be independent — form your estimate before considering the Kalshi price, then note any discrepancy.
5. Assign confidence: "high" only if you have strong conviction; "medium" for reasonable evidence; "low" if highly uncertain.

Respond ONLY with valid JSON matching the schema provided. No other text."""


class ProbabilityEstimate(BaseModel):
    probability: float = Field(ge=0.0, le=1.0, description="P(YES), 0.0-1.0")
    confidence: str = Field(description="'low', 'medium', or 'high'")
    reasoning: str = Field(description="One-paragraph reasoning")
    key_risks: list[str] = Field(description="2-4 key risks or uncertainties")


def estimate_probability(
    market_ticker: str,
    market_question: str,
    rules_primary: str,
    close_time: str,
    days_to_resolution: float,
    kalshi_yes_ask: Optional[float],
    kalshi_yes_bid: Optional[float],
    underlying_value: float,
    underlying_label: str,
    underlying_history: list[dict],
    market_type: str,  # "gas" or "crude"
) -> Optional[ProbabilityEstimate]:
    prompt = _build_prompt(
        market_ticker, market_question, rules_primary, close_time,
        days_to_resolution, kalshi_yes_ask, kalshi_yes_bid,
        underlying_value, underlying_label, underlying_history, market_type
    )
    return _call_claude(prompt)


def _build_prompt(
    ticker: str,
    question: str,
    rules: str,
    close_time: str,
    days: float,
    yes_ask: Optional[float],
    yes_bid: Optional[float],
    underlying: float,
    underlying_label: str,
    history: list[dict],
    market_type: str,
) -> str:
    history_str = json.dumps(history[-10:], indent=2) if history else "[]"
    kalshi_price_str = f"YES ask: ${yes_ask:.2f}, YES bid: ${yes_bid:.2f}" if yes_ask else "N/A"

    return f"""MARKET ANALYSIS REQUEST

Ticker: {ticker}
Question: {question}
Resolution rule: {rules}
Closes: {close_time} ({days:.1f} days from now)

CURRENT FUNDAMENTAL DATA
{underlying_label}: ${underlying:.3f}

KALSHI MARKET PRICE (for reference — form your estimate independently first)
{kalshi_price_str}

RECENT HISTORY (last 10 data points)
{history_str}

Estimate the probability this market resolves YES. Respond with JSON only:
{{
  "probability": <float 0-1>,
  "confidence": "<low|medium|high>",
  "reasoning": "<one paragraph>",
  "key_risks": ["<risk 1>", "<risk 2>", ...]
}}"""


@retry(wait=wait_exponential(multiplier=1, min=2, max=20), stop=stop_after_attempt(2), reraise=False)
def _call_claude(prompt: str) -> Optional[ProbabilityEstimate]:
    try:
        resp = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            temperature=0.1,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        return ProbabilityEstimate(**data)
    except Exception as e:
        logger.error("Claude API error: %s", e)
        return None
