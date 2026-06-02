"""Main scheduler loop for the Kalshi Supervised Trading Assistant."""
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.blocking import BlockingScheduler

from src.config import (
    POLL_INTERVAL_MINUTES, MONITORED_SERIES, CLAUDE_MODEL,
    EIA_CHECK_EVERY_N_CYCLES, ENABLE_ORDER_PLACEMENT,
)
from src.kalshi_client import get_markets_by_series, get_market, get_orderbook, compute_implied_prob
from src.data_sources.crude import get_wti_price
from src.data_sources.aaa import get_national_average
from src.data_sources.eia import get_wti_spot_latest, get_retail_gas_latest
from src.analysis.claude import estimate_probability
from src.analysis.edge import should_notify
from src.notify import send_trade_alert, send_health_alert
from src.storage import init_db, log_snapshot, log_estimate, log_notification
from src.calibration import run_calibration_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent.parent / "logs" / "assistant.log"),
    ],
)
logger = logging.getLogger(__name__)

_cycle_count = 0


def _market_type(series_ticker: str) -> str:
    return "gas" if "GAS" in series_ticker.upper() or "AAA" in series_ticker.upper() else "crude"


def _days_until(close_time_str: str) -> float:
    try:
        close = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
        delta = (close - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta / 86400.0)
    except Exception:
        return 0.0


def _get_underlying(mtype: str) -> tuple[Optional[float], str, list[dict]]:
    """Returns (price, label, history_placeholder)."""
    if mtype == "gas":
        price = get_national_average()
        return price, "AAA National Avg Gas", []
    else:
        price = get_wti_price()
        return price, "WTI Front-Month Futures (CL=F)", []


def poll_cycle() -> None:
    global _cycle_count
    _cycle_count += 1
    run_id = str(uuid.uuid4())[:8]
    logger.info("=== Cycle %d (run_id=%s) ===", _cycle_count, run_id)

    if ENABLE_ORDER_PLACEMENT:
        logger.critical("ENABLE_ORDER_PLACEMENT is True — this should never happen in supervised phase!")
        raise RuntimeError("Order placement is disabled in supervised phase.")

    # EIA cross-check on slower sub-schedule
    if _cycle_count % EIA_CHECK_EVERY_N_CYCLES == 0:
        eia_wti = get_wti_spot_latest()
        eia_gas = get_retail_gas_latest()
        logger.info("EIA cross-check: WTI spot=$%.2f, retail gas=$%.3f",
                    eia_wti or 0, eia_gas or 0)

    failures: list[str] = []

    for series_ticker in MONITORED_SERIES:
        mtype = _market_type(series_ticker)
        try:
            markets = get_markets_by_series(series_ticker)
        except Exception as e:
            logger.warning("Failed to fetch markets for %s: %s", series_ticker, e)
            failures.append(f"Kalshi/{series_ticker}")
            continue

        underlying, underlying_label, history = _get_underlying(mtype)
        if underlying is None:
            logger.warning("No underlying price for %s — skipping series", series_ticker)
            failures.append(f"underlying/{mtype}")
            continue

        for mkt in markets:
            ticker = mkt.get("ticker", "")
            try:
                _process_market(run_id, ticker, mkt, mtype, underlying, underlying_label, history)
            except Exception as e:
                logger.error("Error processing market %s: %s", ticker, e, exc_info=True)

    if failures:
        send_health_alert(
            f"Cycle {_cycle_count}: data source failures: {', '.join(failures)}",
            priority="low",
        )


def _process_market(
    run_id: str,
    ticker: str,
    mkt: dict,
    mtype: str,
    underlying: float,
    underlying_label: str,
    history: list[dict],
) -> None:
    close_time = mkt.get("close_time", "")
    days = _days_until(close_time)
    question = mkt.get("title", ticker)
    rules = mkt.get("rules_primary", "")

    yes_ask = mkt.get("yes_ask")  # cents
    yes_bid = mkt.get("yes_bid")  # cents

    snapshot = {
        "market": mkt,
        "underlying": underlying,
        "days_to_resolution": days,
    }
    log_snapshot(run_id, ticker, snapshot)

    if yes_ask is None or yes_bid is None:
        logger.debug("Skipping %s — no bid/ask", ticker)
        return

    estimate = estimate_probability(
        market_ticker=ticker,
        market_question=question,
        rules_primary=rules,
        close_time=close_time,
        days_to_resolution=days,
        kalshi_yes_ask=yes_ask / 100.0,
        kalshi_yes_bid=yes_bid / 100.0,
        underlying_value=underlying,
        underlying_label=underlying_label,
        underlying_history=history,
        market_type=mtype,
    )

    if estimate is None:
        log_estimate(
            run_id, ticker, question, 0.0, "low", "Claude failed", [],
            yes_ask / 100.0, 1 - yes_bid / 100.0, None, CLAUDE_MODEL, "",
            data_quality="claude_error",
        )
        return

    yes_implied = yes_ask / 100.0
    no_implied = 1.0 - yes_bid / 100.0
    edge_yes = estimate.probability - yes_implied
    edge = edge_yes

    estimate_id = log_estimate(
        run_id, ticker, question,
        estimate.probability, estimate.confidence, estimate.reasoning,
        estimate.key_risks, yes_implied, no_implied, edge, CLAUDE_MODEL,
        f"{ticker}|{underlying}|{yes_ask}|{yes_bid}",
    )

    try:
        ob = get_orderbook(ticker)
        depth_yes = len(ob.get("orderbook", {}).get("yes", []))
        depth_no = len(ob.get("orderbook", {}).get("no", []))
    except Exception:
        depth_yes = depth_no = 0

    fire, side, final_edge, reason = should_notify(
        ticker=ticker,
        claude_prob=estimate.probability,
        confidence=estimate.confidence,
        kalshi_yes_ask=float(yes_ask),
        kalshi_yes_bid=float(yes_bid),
        days_to_resolution=days,
        orderbook_depth_yes=depth_yes,
        orderbook_depth_no=depth_no,
    )

    logger.info(
        "%s | underlying=%.3f | claude=%.2f %s | edge=%.3f | notify=%s (%s)",
        ticker, underlying, estimate.probability, estimate.confidence,
        final_edge, fire, reason,
    )

    if fire:
        kalshi_implied = yes_implied if side == "yes" else no_implied
        kalshi_price = yes_ask / 100.0 if side == "yes" else (100 - yes_bid) / 100.0
        status = send_trade_alert(
            ticker=ticker,
            question=question,
            side=side,
            claude_prob=estimate.probability,
            kalshi_implied=kalshi_implied,
            edge=final_edge,
            confidence=estimate.confidence,
            reasoning=estimate.reasoning,
            underlying_label=underlying_label,
            underlying_value=underlying,
            days_to_resolution=days,
            kalshi_price=kalshi_price,
        )
        log_notification(run_id, ticker, side, final_edge, estimate.probability, kalshi_implied, status)


def main() -> None:
    Path("logs").mkdir(exist_ok=True)
    init_db()
    logger.info("Kalshi Supervised Trading Assistant starting (NO AUTO-TRADING)")

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(poll_cycle, "interval", minutes=POLL_INTERVAL_MINUTES, id="poll")

    # Weekly calibration report (Sundays at 09:00 UTC)
    scheduler.add_job(run_calibration_report, "cron", day_of_week="sun", hour=9, id="calibration")

    logger.info("Scheduler started. Poll every %d min.", POLL_INTERVAL_MINUTES)

    # Run once immediately on startup
    poll_cycle()
    scheduler.start()


if __name__ == "__main__":
    main()
