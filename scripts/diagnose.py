#!/usr/bin/env python3
"""
Diagnostic script — run this to check what's broken.

    python scripts/diagnose.py

Tests in order:
  1. .env loading (are keys actually set?)
  2. ntfy — sends a real test notification to your topic
  3. Claude API — makes a real (cheap) API call
  4. Kalshi API — fetches live market data
  5. yfinance / AAA — fetches WTI price and gas price
"""
import sys
import os

# Make sure src/ is importable when run from project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config  # noqa: E402 — loads .env on import

PASS = "  ✓"
FAIL = "  ✗"
WARN = "  !"


def section(title):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print('='*50)


# ── 1. ENV CHECK ─────────────────────────────────────────────────────────────
section("1. Environment / .env")

env_path = config.ENV_PATH
print(f"  .env path:  {env_path}")
print(f"  .env exists: {env_path.exists()}")
print(f"  config.yaml: {config.CONFIG_PATH.exists()}")

keys = {
    "ANTHROPIC_API_KEY": config.ANTHROPIC_API_KEY,
    "EIA_API_KEY":       config.EIA_API_KEY,
    "NTFY_TOPIC":        config.NTFY_TOPIC,
}
all_set = True
for name, val in keys.items():
    if val:
        masked = ("•" * 6 + val[-4:]) if len(val) > 4 else "•" * len(val)
        print(f"{PASS} {name}: {masked}")
    else:
        print(f"{FAIL} {name}: NOT SET")
        all_set = False

if not all_set:
    print("\n  Some keys are missing. Open Settings in the app and save them,")
    print("  or add them to .env manually, then re-run this script.")
    sys.exit(1)


# ── 2. NTFY ──────────────────────────────────────────────────────────────────
section("2. ntfy notification")
print(f"  Topic: {config.NTFY_TOPIC}")
try:
    import requests
    resp = requests.post(
        f"https://ntfy.sh/{config.NTFY_TOPIC}",
        data=b"Kalshi Assistant diagnostic test — ntfy is working!",
        headers={"Title": "Kalshi Diagnostic", "Priority": "default", "Tags": "white_check_mark"},
        timeout=10,
    )
    if resp.status_code == 200:
        print(f"{PASS} ntfy responded 200 — check your phone for the notification")
    else:
        print(f"{FAIL} ntfy responded {resp.status_code}: {resp.text[:200]}")
except Exception as e:
    print(f"{FAIL} ntfy request failed: {e}")


# ── 3. CLAUDE API ─────────────────────────────────────────────────────────────
section("3. Claude API")
print(f"  Model: {config.CLAUDE_MODEL}")
try:
    from anthropic import Anthropic
    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=32,
        messages=[{"role": "user", "content": "Reply with just the word PONG."}],
    )
    reply = resp.content[0].text.strip()
    print(f"{PASS} Claude replied: {reply!r}")
except Exception as e:
    print(f"{FAIL} Claude API error: {e}")


# ── 4. KALSHI API ─────────────────────────────────────────────────────────────
section("4. Kalshi API")
try:
    from src.kalshi_client import KalshiClient
    client = KalshiClient()
    series = client.get_series("KXWTIW")
    if series:
        print(f"{PASS} Kalshi responded — series KXWTIW found")
    else:
        markets = client.get_markets("KXWTIW")
        if markets is not None:
            print(f"{PASS} Kalshi responded — {len(markets)} KXWTIW markets")
        else:
            print(f"{WARN} Kalshi returned empty response (may be no active markets right now)")
except Exception as e:
    print(f"{FAIL} Kalshi API error: {e}")


# ── 5. MARKET DATA ────────────────────────────────────────────────────────────
section("5. Market data (yfinance WTI + AAA gas)")
try:
    from src.data_sources.crude import get_wti_price
    wti = get_wti_price()
    if wti:
        print(f"{PASS} WTI price: ${wti:.2f}")
    else:
        print(f"{WARN} WTI: returned None (yfinance may be rate-limiting; try again)")
except Exception as e:
    print(f"{FAIL} WTI error: {e}")

try:
    from src.data_sources.aaa import get_gas_price
    gas = get_gas_price()
    if gas:
        print(f"{PASS} AAA gas: ${gas:.3f}")
    else:
        print(f"{WARN} AAA gas: returned None (scrape may have failed)")
except Exception as e:
    print(f"{FAIL} AAA gas error: {e}")


print("\n" + "="*50)
print("  Diagnostic complete.")
print("="*50 + "\n")
