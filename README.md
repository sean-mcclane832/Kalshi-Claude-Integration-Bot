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

## Three ways to run

- **Standalone executable (easiest):** double-click `KalshiAssistant` — no Python
  required. Build once with `python build.py`, then distribute `dist/KalshiAssistant/`.
- **Desktop app (Python source):** `python run_desktop.py` — native window with
  dashboard, settings, alert history, and calibration. No file editing required.
- **Headless CLI:** the same engine as a background loop that only sends phone alerts.

---

## Quick Start (install in 5 minutes)

This is the full path from a fresh machine to a running app. If you just want the
shortest route, follow **Step 1 → 2 → 3A**.

### Step 1 — Get your free credentials

You need three things before the app can do anything (all free except Anthropic usage):

| Credential | Where to get it | Notes |
|------------|-----------------|-------|
| **Anthropic API key** | https://console.anthropic.com → *API Keys* | Pay-as-you-go; this is the only one that costs money (a few cents per cycle). Keep it secret. |
| **EIA API key** | https://www.eia.gov/opendata/register.php | Free, instant, emailed to you. |
| **ntfy topic** | Just invent a name, e.g. `kalshi-7f3a9-alerts` | Install the **ntfy** app (iOS/Android), then *Subscribe* to that exact name. Pick something unguessable — anyone who knows it can read your alerts. |

> You do **not** need a Kalshi API key — market data comes from public endpoints.

### Step 2 — Install

```bash
# 1. Get the code
git clone <repo-url>
cd Kalshi-Claude-Integration-Bot

# 2. Create an isolated Python environment (Python 3.11+)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

**Linux only:** the desktop window needs a WebView backend. Install one:
```bash
pip install "pywebview[qt]"      # Qt backend (simplest)
# — or — system GTK: sudo apt install gir1.2-webkit2-4.0
```
(Windows and macOS need nothing extra — they use the built-in browser engine.)

### Step 3A — Run the desktop app

```bash
python run_desktop.py
```

A window opens. **On first launch it will show a "Setup required" banner** because
no keys are saved yet:

1. Click **Open Settings** (or the **Settings** tab).
2. Paste your **Anthropic key**, **EIA key**, and your **ntfy topic** name.
3. *(Optional)* tweak strategy thresholds and pick which markets to monitor.
4. Click **Save settings**. The banner disappears.
5. *(Optional)* click **Send test notification** — your phone should buzz.
6. Click **Start monitoring** (runs every N minutes) or **Run cycle now** (one pass).

That's it. Your keys are saved to a local `.env` file (gitignored, never uploaded).

### Step 3B — Build a double-click app (no terminal needed afterwards)

If you'd rather not use the terminal each time, build a standalone executable once:

```bash
python build.py                  # creates dist/KalshiAssistant/
```

Then launch `dist/KalshiAssistant/KalshiAssistant` (`.exe` on Windows, or the
`KalshiAssistant.app` bundle on macOS) by double-clicking. Enter your keys in
**Settings** exactly as in Step 3A. See
[Building a standalone executable](#building-a-standalone-executable) for platform notes.

### Step 3C — Run headless (phone alerts only, no window)

```bash
python -m src.main               # loop forever
python -m src.main --once        # one cycle, then exit
```

CLI mode reads keys from `.env`. Create it once: `cp .env.example .env` and fill in
`ANTHROPIC_API_KEY`, `EIA_API_KEY`, and `NTFY_TOPIC`.

---

## Using the app day-to-day

Once monitoring is running, here's what each tab does:

- **Dashboard** — the main view. Top cards show live WTI and gas prices, cycles run,
  and how many markets currently have a signal. The table lists every monitored
  market with Claude's probability, its confidence, Kalshi's implied price, and the
  **edge**. A 🔔 appears when *all* gates pass. **Click any row** to open a drawer with
  Claude's full reasoning, the key risks it flagged, and a suggested entry price.
- **Alerts** — a history of every notification that fired, so you can review past calls.
- **Calibration** — once markets resolve and you've recorded outcomes (see
  [Calibration Tracking](#calibration-tracking)), this shows the Brier score and a
  reliability table answering the key question: *do Claude's 80% calls actually win ~80%
  of the time?*
- **Settings** — change keys or any strategy threshold at any time. Edits apply on the
  **next cycle** — no restart needed.

**What to do when an alert fires:** the app never trades for you. A notification is a
prompt to *go look*. Open the drawer, read the reasoning and risks, and if you agree,
place the trade yourself on Kalshi — respecting the **$500 position cap**. This human
approval gate is intentional.

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

> Installation and first-run steps are covered in **[Quick Start](#quick-start-install-in-5-minutes)** above.
> The sections below are reference detail for building and running.

## Building a standalone executable

```bash
pip install pyinstaller>=6.0      # one-time
python build.py                   # creates dist/KalshiAssistant/
```

Then distribute the entire `dist/KalshiAssistant/` folder. The executable is
`dist/KalshiAssistant/KalshiAssistant` (or `.exe` on Windows, `.app` on macOS via
the generated `KalshiAssistant.app` bundle).

**Platform notes:**
- **Windows** — requires no extra setup; EdgeChromium is built-in.
- **macOS** — use `KalshiAssistant.app`. Gatekeeper may block unsigned apps; right-click → Open.
- **Linux** — install a WebView backend before building:
  `sudo apt install gir1.2-webkit2-4.0`  (GTK) or `pip install PyQtWebEngine` (Qt).

**Security note:** `.env` (your API keys) is **never** bundled. On first launch the
app writes it next to the executable when you save keys in Settings.

## Running headless (CLI)

```bash
python -m src.main          # loop forever, phone alerts only
python -m src.main --once   # run a single cycle and exit
```

Runs the poll cycle immediately, then every `poll_interval_minutes` (default: 15).
CLI mode reads keys from `.env` (see [Quick Start → Step 3C](#step-3c--run-headless-phone-alerts-only-no-window)).

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
run_desktop.py            # launch the desktop app (Python source)
build.py                  # build standalone executable via PyInstaller
app.spec                  # PyInstaller spec (bundling rules)
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
