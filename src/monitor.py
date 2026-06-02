"""Monitoring engine: a controllable poll loop the desktop UI and CLI share.

The :class:`MonitorController` wraps an APScheduler ``BackgroundScheduler`` so the
loop runs off the main thread (keeping the GUI responsive), tracks live state for
the dashboard, and exposes ``start`` / ``stop`` / ``run_once`` controls.
"""
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler

from src import config
from src.analysis.claude import estimate_probability
from src.analysis.edge import compute_edge, should_notify
from src.calibration import run_calibration_report
from src.data_sources.aaa import get_national_average
from src.data_sources.crude import get_wti_price
from src.data_sources.eia import get_retail_gas_latest, get_wti_spot_latest
from src.kalshi_client import get_markets_by_series, get_orderbook
from src.notify import send_health_alert, send_trade_alert
from src.storage import init_db, log_estimate, log_notification, log_snapshot

logger = logging.getLogger(__name__)


def _market_type(series_ticker: str) -> str:
    s = series_ticker.upper()
    return "gas" if ("GAS" in s or "AAA" in s) else "crude"


def _days_until(close_time_str: str) -> float:
    try:
        close = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
        return max(0.0, (close - datetime.now(timezone.utc)).total_seconds() / 86400.0)
    except Exception:
        return 0.0


class MonitorController:
    """Owns the scheduler, runs poll cycles, and holds live state for the UI."""

    def __init__(
        self,
        on_cycle_complete: Optional[Callable[[dict], None]] = None,
        on_alert: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self.on_cycle_complete = on_cycle_complete
        self.on_alert = on_alert

        self._scheduler: Optional[BackgroundScheduler] = None
        self._running = False
        self._cycle_lock = threading.Lock()

        self.cycle_count = 0
        self.last_cycle_ts: Optional[datetime] = None
        self.next_cycle_ts: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.latest_results: list[dict] = []
        self.fundamentals: dict = {"wti": None, "gas": None, "wti_ts": None, "gas_ts": None}

        init_db()

    # ------------------------------------------------------------------ control
    def start(self) -> dict:
        if self._running:
            return {"ok": True, "already": True}
        missing = config.get_missing_keys()
        if missing:
            return {"ok": False, "error": f"Missing required keys: {', '.join(missing)}"}

        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._scheduler.add_job(
            self._scheduled_cycle,
            "interval",
            minutes=config.POLL_INTERVAL_MINUTES,
            id="poll",
            next_run_time=datetime.now(timezone.utc),
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.add_job(
            lambda: run_calibration_report(send_notification=True),
            "cron",
            day_of_week="sun",
            hour=9,
            id="calibration",
        )
        self._scheduler.start()
        self._running = True
        self._refresh_next_run()
        logger.info("Monitoring started (poll every %d min).", config.POLL_INTERVAL_MINUTES)
        return {"ok": True}

    def stop(self) -> dict:
        if not self._running:
            return {"ok": True, "already": True}
        try:
            if self._scheduler:
                self._scheduler.shutdown(wait=False)
        finally:
            self._scheduler = None
            self._running = False
            self.next_cycle_ts = None
        logger.info("Monitoring stopped.")
        return {"ok": True}

    def run_once_async(self) -> dict:
        """Trigger a single cycle on a worker thread (non-blocking for the UI)."""
        missing = config.get_missing_keys()
        if missing:
            return {"ok": False, "error": f"Missing required keys: {', '.join(missing)}"}
        if self._cycle_lock.locked():
            return {"ok": False, "error": "A cycle is already running"}
        threading.Thread(target=self.run_one_cycle, daemon=True).start()
        return {"ok": True}

    @property
    def running(self) -> bool:
        return self._running

    # --------------------------------------------------------------------- state
    def state(self) -> dict:
        return {
            "running": self._running,
            "cycle_count": self.cycle_count,
            "last_cycle": self.last_cycle_ts.isoformat() if self.last_cycle_ts else None,
            "next_cycle": self.next_cycle_ts.isoformat() if self.next_cycle_ts else None,
            "busy": self._cycle_lock.locked(),
            "last_error": self.last_error,
            "fundamentals": self.fundamentals,
            "markets": self.latest_results,
            "alert_count": sum(1 for r in self.latest_results if r.get("fire")),
            "missing_keys": config.get_missing_keys(),
            "order_placement_enabled": config.ENABLE_ORDER_PLACEMENT,
            "poll_interval_minutes": config.POLL_INTERVAL_MINUTES,
        }

    # --------------------------------------------------------------------- cycles
    def _scheduled_cycle(self) -> None:
        self.run_one_cycle()
        self._refresh_next_run()

    def _refresh_next_run(self) -> None:
        if self._scheduler:
            job = self._scheduler.get_job("poll")
            self.next_cycle_ts = getattr(job, "next_run_time", None) if job else None

    def run_one_cycle(self) -> list[dict]:
        if not self._cycle_lock.acquire(blocking=False):
            logger.info("Cycle already in progress; skipping overlap.")
            return self.latest_results
        try:
            return self._run_one_cycle_locked()
        finally:
            self._cycle_lock.release()

    def _run_one_cycle_locked(self) -> list[dict]:
        self.cycle_count += 1
        run_id = str(uuid.uuid4())[:8]
        self.last_error = None
        logger.info("=== Cycle %d (run_id=%s) ===", self.cycle_count, run_id)

        if config.ENABLE_ORDER_PLACEMENT:
            self.last_error = "ENABLE_ORDER_PLACEMENT is True — refusing to run in supervised phase."
            logger.critical(self.last_error)
            return self.latest_results

        # Slow sub-schedule EIA cross-check.
        if config.EIA_CHECK_EVERY_N_CYCLES and self.cycle_count % config.EIA_CHECK_EVERY_N_CYCLES == 0:
            try:
                eia_wti = get_wti_spot_latest()
                eia_gas = get_retail_gas_latest()
                logger.info("EIA cross-check: WTI=$%s retail gas=$%s", eia_wti, eia_gas)
            except Exception as e:  # noqa: BLE001
                logger.warning("EIA cross-check failed: %s", e)

        results: list[dict] = []
        failures: list[str] = []

        for series_ticker in config.MONITORED_SERIES:
            mtype = _market_type(series_ticker)
            try:
                markets = get_markets_by_series(series_ticker)
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to fetch markets for %s: %s", series_ticker, e)
                failures.append(f"Kalshi/{series_ticker}")
                continue

            underlying, underlying_label = self._underlying(mtype)
            if underlying is None:
                logger.warning("No underlying price for %s — skipping.", series_ticker)
                failures.append(f"underlying/{mtype}")
                continue

            for mkt in markets:
                ticker = mkt.get("ticker", "")
                try:
                    row = self._process_market(run_id, ticker, mkt, mtype, underlying, underlying_label)
                    if row:
                        results.append(row)
                except Exception as e:  # noqa: BLE001
                    logger.error("Error processing %s: %s", ticker, e, exc_info=True)

        self.latest_results = results
        self.last_cycle_ts = datetime.now(timezone.utc)

        if failures:
            self.last_error = "Data source issues: " + ", ".join(failures)
            try:
                send_health_alert(
                    f"Cycle {self.cycle_count}: data source failures: {', '.join(failures)}",
                    priority="low",
                )
            except Exception:  # noqa: BLE001
                pass

        if self.on_cycle_complete:
            try:
                self.on_cycle_complete(self.state())
            except Exception:  # noqa: BLE001
                pass

        return results

    def _underlying(self, mtype: str) -> tuple[Optional[float], str]:
        now = datetime.now(timezone.utc).isoformat()
        if mtype == "gas":
            price = get_national_average()
            if price is not None:
                self.fundamentals["gas"] = price
                self.fundamentals["gas_ts"] = now
            return price, "AAA National Avg Gas"
        price = get_wti_price()
        if price is not None:
            self.fundamentals["wti"] = price
            self.fundamentals["wti_ts"] = now
        return price, "WTI Front-Month Futures (CL=F)"

    def _process_market(
        self,
        run_id: str,
        ticker: str,
        mkt: dict,
        mtype: str,
        underlying: float,
        underlying_label: str,
    ) -> Optional[dict]:
        close_time = mkt.get("close_time", "")
        days = _days_until(close_time)
        question = mkt.get("title", ticker)
        rules = mkt.get("rules_primary", "")
        yes_ask = mkt.get("yes_ask")  # cents
        yes_bid = mkt.get("yes_bid")  # cents

        log_snapshot(run_id, ticker, {"market": mkt, "underlying": underlying, "days_to_resolution": days})

        if yes_ask is None or yes_bid is None:
            return {
                "ticker": ticker, "question": question, "market_type": mtype,
                "underlying": underlying, "underlying_label": underlying_label,
                "days_to_resolution": round(days, 2), "claude_prob": None,
                "confidence": None, "kalshi_yes_ask": None, "kalshi_yes_bid": None,
                "kalshi_implied": None, "edge": None, "side": "", "fire": False,
                "reason": "no bid/ask", "reasoning": "", "key_risks": [],
            }

        estimate = estimate_probability(
            market_ticker=ticker, market_question=question, rules_primary=rules,
            close_time=close_time, days_to_resolution=days,
            kalshi_yes_ask=yes_ask / 100.0, kalshi_yes_bid=yes_bid / 100.0,
            underlying_value=underlying, underlying_label=underlying_label,
            underlying_history=[], market_type=mtype,
        )

        yes_implied = yes_ask / 100.0
        no_implied = 1.0 - yes_bid / 100.0

        if estimate is None:
            log_estimate(
                run_id, ticker, question, 0.0, "low", "Claude failed", [],
                yes_implied, no_implied, None, config.CLAUDE_MODEL, "",
                data_quality="claude_error",
            )
            return {
                "ticker": ticker, "question": question, "market_type": mtype,
                "underlying": underlying, "underlying_label": underlying_label,
                "days_to_resolution": round(days, 2), "claude_prob": None,
                "confidence": "error", "kalshi_yes_ask": yes_implied,
                "kalshi_yes_bid": yes_bid / 100.0, "kalshi_implied": yes_implied,
                "edge": None, "side": "", "fire": False,
                "reason": "Claude error", "reasoning": "", "key_risks": [],
            }

        edge_yes = compute_edge(estimate.probability, yes_implied)
        log_estimate(
            run_id, ticker, question, estimate.probability, estimate.confidence,
            estimate.reasoning, estimate.key_risks, yes_implied, no_implied, edge_yes,
            config.CLAUDE_MODEL, f"{ticker}|{underlying}|{yes_ask}|{yes_bid}",
        )

        try:
            ob = get_orderbook(ticker)
            depth_yes = len(ob.get("orderbook", {}).get("yes", []) or [])
            depth_no = len(ob.get("orderbook", {}).get("no", []) or [])
        except Exception:  # noqa: BLE001
            depth_yes = depth_no = 0

        fire, side, final_edge, reason = should_notify(
            ticker=ticker, claude_prob=estimate.probability, confidence=estimate.confidence,
            kalshi_yes_ask=float(yes_ask), kalshi_yes_bid=float(yes_bid),
            days_to_resolution=days, orderbook_depth_yes=depth_yes, orderbook_depth_no=depth_no,
        )

        kalshi_implied = yes_implied if side == "yes" else no_implied
        kalshi_price = yes_ask / 100.0 if side == "yes" else (100 - yes_bid) / 100.0

        row = {
            "ticker": ticker, "question": question, "market_type": mtype,
            "underlying": round(underlying, 3), "underlying_label": underlying_label,
            "days_to_resolution": round(days, 2),
            "claude_prob": round(estimate.probability, 4),
            "confidence": estimate.confidence,
            "kalshi_yes_ask": yes_implied, "kalshi_yes_bid": yes_bid / 100.0,
            "kalshi_implied": round(kalshi_implied, 4),
            "edge": round(final_edge, 4), "side": side, "fire": bool(fire),
            "reason": reason, "reasoning": estimate.reasoning,
            "key_risks": estimate.key_risks, "suggested_price": round(kalshi_price, 2),
        }

        logger.info(
            "%s | u=%.3f | claude=%.2f %s | edge=%.3f | notify=%s (%s)",
            ticker, underlying, estimate.probability, estimate.confidence,
            final_edge, fire, reason,
        )

        if fire:
            status = send_trade_alert(
                ticker=ticker, question=question, side=side,
                claude_prob=estimate.probability, kalshi_implied=kalshi_implied,
                edge=final_edge, confidence=estimate.confidence, reasoning=estimate.reasoning,
                underlying_label=underlying_label, underlying_value=underlying,
                days_to_resolution=days, kalshi_price=kalshi_price,
            )
            log_notification(run_id, ticker, side, final_edge, estimate.probability, kalshi_implied, status)
            row["ntfy_status"] = status
            if self.on_alert:
                try:
                    self.on_alert(row)
                except Exception:  # noqa: BLE001
                    pass

        return row
