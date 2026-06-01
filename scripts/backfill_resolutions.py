#!/usr/bin/env python3
"""
Manually record market resolutions for calibration tracking.
Usage: python scripts/backfill_resolutions.py TICKER YES|NO [price]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage import upsert_resolution, init_db

def main():
    if len(sys.argv) < 3:
        print("Usage: backfill_resolutions.py TICKER YES|NO [settlement_price]")
        sys.exit(1)

    ticker = sys.argv[1].upper()
    result_str = sys.argv[2].upper()
    price = float(sys.argv[3]) if len(sys.argv) > 3 else None

    if result_str not in ("YES", "NO"):
        print("Result must be YES or NO")
        sys.exit(1)

    resolved_yes = 1 if result_str == "YES" else 0
    init_db()
    upsert_resolution(ticker, resolved_yes, price, notes="manual backfill")
    print(f"Recorded: {ticker} resolved {result_str}" + (f" @ ${price}" if price else ""))

if __name__ == "__main__":
    main()
