"""Calibration analysis: reliability curve and Brier score."""
import json
import logging
import sqlite3
from collections import defaultdict
from typing import Optional

from src.config import DB_PATH
from src.notify import send_health_alert

logger = logging.getLogger(__name__)


def run_calibration_report(send_notification: bool = True) -> dict:
    """
    Join estimates to resolutions, bin by predicted probability,
    compute hit rate per bin and Brier score.
    """
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT e.claude_prob, e.confidence, r.resolved_yes
            FROM estimates e
            JOIN resolutions r ON e.market_ticker = r.market_ticker
            WHERE r.resolved_yes IS NOT NULL
        """).fetchall()

    if not rows:
        logger.info("No resolved estimates yet for calibration.")
        return {}

    bins = defaultdict(list)
    brier_sum = 0.0

    for row in rows:
        p = row["claude_prob"]
        y = row["resolved_yes"]
        brier_sum += (p - y) ** 2
        bin_key = round(p * 10) / 10  # nearest 0.1
        bins[bin_key].append(y)

    brier_score = brier_sum / len(rows)
    # Naive baseline: always predict market implied (approximate with 0.5)
    naive_brier = sum((0.5 - r["resolved_yes"]) ** 2 for r in rows) / len(rows)

    report_lines = [
        f"**Calibration Report** ({len(rows)} resolved estimates)",
        f"Brier Score: {brier_score:.4f} (naive baseline: {naive_brier:.4f})",
        "",
        "| Predicted bin | N | Hit rate |",
        "|---|---|---|",
    ]
    calibration = {}
    for bin_key in sorted(bins.keys()):
        outcomes = bins[bin_key]
        hit_rate = sum(outcomes) / len(outcomes)
        calibration[bin_key] = {"n": len(outcomes), "hit_rate": hit_rate}
        report_lines.append(f"| {bin_key:.0%} | {len(outcomes)} | {hit_rate:.1%} |")

    report = "\n".join(report_lines)
    logger.info(report)

    if send_notification:
        send_health_alert(report, priority="default")

    return {
        "brier_score": brier_score,
        "naive_brier": naive_brier,
        "n_resolved": len(rows),
        "calibration": calibration,
    }
