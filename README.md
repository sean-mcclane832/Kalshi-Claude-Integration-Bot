# Kalshi Supervised Trading Assistant

A Python application that monitors Kalshi gas-price and crude-oil event-contract markets, fetches free market data, asks Claude for a calibrated probability estimate, and sends a push notification when a meaningful edge is detected.

**The system never places trades automatically.** It is a notification/alert system with a human approval gate.

---

## Realistic Expectations

- **The edge is process, not prophecy.** The genuine advantage is monitoring frequency, consistency, and discipline — catching Kalshi quotes that drift from fundamentals, and sticking to the 80%+ confidence + minimum-edge rules. It is **not** an expectation that the LLM will out-predict a liquid, CFTC-regulated market.
- **Latency limits speed edges.** WTI markets are priced off ICE/NYMEX feeds that market makers watch in real time. This system uses ~15-min-delayed free data. Do not expect to win races on speed.
- **Calibration tracking is non-negotiable.** Log every estimate. Check realized outcomes after resolution. If Claude's 80% calls don't resolve ~80% of the time over a multi-month sample, the system is not adding value.
- **Free-data caveats:** AAA has no official API (scraped, once-daily); `yfinance` is unofficial/delayed; EIA is lagged. The system degrades gracefully and never sends a signal computed from stale/missing data.

---

## Two ways to run

- **Desktop app (recommended):** a native window with a dashboard, settings screen,
  alert history, and calibration view. Start/stop monitoring, run a cycle on demand,
  and edit all keys/thresholds in the UI — no file editing required.
- **Headless CLI:** the same engine as a background loop that only sends phone alerts.

## Architecture

```
            ┌──────────────────────────────────────────┐
            │  Desktop UI (PyWebView: HTML/CSS/JS)       │
            │  dashboard · settings · alerts · calib.    │
            └───────────────┬────────────────────────────┘
                            │  JS ↔ Python bridge (desktop/api.py)
                            ▼
   MonitorController (src/monitor.py) ── BackgroundScheduler (every N min)
     │
     ├─ Kalshi REST API → open markets for KXWTI/KXWTIW/KXAAAGASM/KXAAAGASW
     ├─ yfinance CL=F → WTI front-month futures price
     ├─ AAA scraper → national avg regular gas price
     ├─ EIA API (sub-schedule) → cross-check
     │
     ├─ Claude Haiku → P(YES), confidence, reasoning (structured JSON)
     ├─ Edge gate (src/analysis/edge.py) → all 5 conditions must pass
     │
     ├─ ntfy.sh → phone push notification (if edge detected)
     └─ SQLite → log everything (estimates, notifications, resolutions)

Weekly: calibration report (Brier score, reliability curve) → ntfy
```

## Prerequisites

1. **Kalshi account** — no API key needed for market data (public endpoints only)
2. **EIA API key** — free at https://www.eia.gov/opendata/register.php
3. **Anthropic API key** — at https://console.anthropic.com (billed separately from Claude Pro)
4. **ntfy app** — install on iOS/Android, subscribe to your topic
5. Python 3.11+

## Setup

```bash
git clone <repo>
cd kalshi-assistant
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

```

You do **not** need to create `.env` by hand — the desktop app's **Settings**
screen writes it for you. (CLI users can still `cp .env.example .env` and fill in
`ANTHROPIC_API_KEY`, `EIA_API_KEY`, `NTFY_TOPIC`.) The ntfy topic is public by
name, so pick something unguessable.

## Running the desktop app

```bash
python run_desktop.py
```

On first launch, open **Settings**, paste your Anthropic + EIA keys and an ntfy
topic, and click **Save**. Then press **Start monitoring** (or **Run cycle now**).

- **Dashboard** — live WTI/gas fundamentals, every monitored market with Claude's
  probability vs. Kalshi's implied price, the edge, and a 🔔 when all gates pass.
  Click any row for Claude's full reasoning, key risks, and the suggested action.
- **Alerts** — history of notifications that fired.
- **Calibration** — Brier score and reliability-by-bin table.
- **Settings** — API keys and every strategy threshold; changes apply next cycle.

**Platform note (PyWebView backends):** Windows uses the built-in EdgeChromium
(no extra setup). macOS uses the built-in Cocoa/WebKit. On Linux, install a
backend: `pip install "pywebview[qt]"` (or `pywebview[gtk]` with system GTK libs).

## Running headless (CLI)

```bash
python -m src.main          # loop forever, phone alerts only
python -m src.main --once   # run a single cycle and exit
```

Runs the poll cycle immediately, then every `poll_interval_minutes` (default: 15).

## Notification Format

Each alert includes:
- Market ticker and question
- Claude's P(YES/NO) + confidence
- Kalshi implied probability
- Edge in percentage points
- Underlying value (WTI price or AAA gas avg)
- Days to resolution
- Suggested entry price
- One-line reasoning

## Calibration Tracking

Every estimate is logged to SQLite. When a market resolves, record the outcome:

```bash
python scripts/backfill_resolutions.py KXWTIW-25MAY26-B65 YES 66.42
```

A weekly calibration report fires automatically (Sundays 09:00 UTC) showing:
- Brier score vs. naive baseline
- Hit rate per probability bin (does 80% → ~80%?)

**Do not scale capital until calibration is validated over a multi-month sample (≥30 high-confidence resolved calls).**

## Risk Controls (Guardrails)

- **No auto-execution.** `ENABLE_ORDER_PLACEMENT = false` in config.yaml. Order endpoints are stubbed.
- **$500 position cap** surfaced in every notification.
- **Multi-month supervised evaluation** before any consideration of automation.

## Project structure

```
run_desktop.py            # launch the desktop app
config.yaml               # tunable thresholds (UI-managed)
desktop/
├── app.py                # PyWebView window
├── api.py                # JS ↔ Python bridge
└── web/                  # index.html · styles.css · app.js
src/
├── monitor.py            # MonitorController (start/stop/run-once engine)
├── main.py               # headless CLI
├── config.py             # env + yaml loader (live reload, never crashes)
├── kalshi_client.py      # public Kalshi REST calls
├── storage.py            # SQLite logging + queries
├── notify.py             # ntfy push
├── calibration.py        # Brier score / reliability curve
├── data_sources/         # crude (yfinance) · aaa (scrape) · eia
└── analysis/             # claude (LLM) · edge (gate logic)
tests/                    # pytest unit tests for the edge gates
scripts/backfill_resolutions.py
```

## Roadmap

- Stage 0 (now): data pull + logging
- Stage 1: Claude analysis + storage
- Stage 2: edge logic + notifications
- Stage 3: calibration evaluation (months 1-3+)
- Future (behind feature flag): portfolio endpoints + manual approval gate UI

## Disclaimer

This is an information/monitoring tool. Prediction-market trading carries real risk of total loss of capital staked. The $500 cap, manual approval gate, and multi-month evaluation are deliberate risk controls, not guarantees of profit.
