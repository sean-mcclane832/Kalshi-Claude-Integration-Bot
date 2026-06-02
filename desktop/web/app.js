"use strict";

/* ---------- pywebview bridge ---------- */
let API_READY = false;

function whenReady() {
  return new Promise((resolve) => {
    if (window.pywebview && window.pywebview.api) { API_READY = true; return resolve(); }
    window.addEventListener("pywebviewready", () => { API_READY = true; resolve(); }, { once: true });
    // Fallback poll in case the event already fired.
    const t = setInterval(() => {
      if (window.pywebview && window.pywebview.api) { clearInterval(t); API_READY = true; resolve(); }
    }, 100);
  });
}

async function api(method, ...args) {
  if (!window.pywebview || !window.pywebview.api) throw new Error("Bridge not ready");
  return window.pywebview.api[method](...args);
}

/* ---------- helpers ---------- */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const pct = (x) => (x == null ? "—" : (x * 100).toFixed(0) + "%");
const pct1 = (x) => (x == null ? "—" : (x * 100).toFixed(1) + "%");
const usd = (x, d = 2) => (x == null ? "—" : "$" + Number(x).toFixed(d));
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}
function fmtAgo(iso) {
  if (!iso) return "";
  const secs = (Date.now() - new Date(iso).getTime()) / 1000;
  if (secs < 60) return "just now";
  if (secs < 3600) return Math.floor(secs / 60) + "m ago";
  return Math.floor(secs / 3600) + "h ago";
}

/* ---------- state ---------- */
let rowsByTicker = {};
let currentView = "dashboard";
let settingsCache = null;

/* ---------- navigation ---------- */
function showView(name) {
  currentView = name;
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle("hidden", v.id !== "view-" + name));
  if (name === "alerts") loadAlerts();
  if (name === "calibration") loadCalibration();
  if (name === "settings") loadSettings();
}

/* ---------- dashboard render ---------- */
function renderState(s) {
  // Status pill
  const pill = $("#statusPill"), txt = $("#statusText");
  pill.className = "pill";
  if (s.busy) { pill.classList.add("pill-busy"); txt.textContent = "Running cycle…"; }
  else if (s.running) { pill.classList.add("pill-live"); txt.textContent = "Monitoring"; }
  else { pill.classList.add("pill-idle"); txt.textContent = "Stopped"; }

  // Toggle button
  const tgl = $("#btnToggle");
  if (s.running) { tgl.textContent = "Stop monitoring"; tgl.className = "btn btn-danger"; }
  else { tgl.textContent = "Start monitoring"; tgl.className = "btn btn-primary"; }

  // Setup banner
  const missing = s.missing_keys || [];
  $("#setupBanner").classList.toggle("hidden", missing.length === 0);
  if (missing.length) {
    $("#setupBannerText").textContent =
      "Add your API keys to start monitoring: " + missing.join(", ") + ".";
  }
  $("#btnToggle").disabled = missing.length > 0 && !s.running;
  $("#btnRunNow").disabled = missing.length > 0;

  // Metrics
  const f = s.fundamentals || {};
  $("#mWti").textContent = f.wti != null ? usd(f.wti) : "—";
  $("#mWtiTs").textContent = f.wti_ts ? fmtAgo(f.wti_ts) : "no data yet";
  $("#mGas").textContent = f.gas != null ? usd(f.gas, 3) : "—";
  $("#mGasTs").textContent = f.gas_ts ? fmtAgo(f.gas_ts) : "no data yet";
  $("#mCycles").textContent = s.cycle_count || 0;
  $("#mNext").textContent = s.running && s.next_cycle ? "next " + fmtTime(s.next_cycle) : "idle";
  $("#mSignals").textContent = s.alert_count || 0;

  // Last updated
  $("#lastUpdated").textContent = s.last_cycle ? "Last cycle " + fmtTime(s.last_cycle) : "";

  // Error strip
  const err = $("#errorStrip");
  if (s.last_error) { err.classList.remove("hidden"); err.textContent = "⚠ " + s.last_error; }
  else err.classList.add("hidden");

  renderMarkets(s.markets || []);
}

function confBadge(c) {
  if (!c) return "";
  const cls = { high: "badge-conf-high", medium: "badge-conf-medium", low: "badge-conf-low" }[c] || "badge-conf-low";
  return `<span class="badge ${cls}">${esc(c)}</span>`;
}

function renderMarkets(markets) {
  rowsByTicker = {};
  const body = $("#marketsBody");
  $("#marketsMeta").textContent = markets.length ? `${markets.length} markets` : "";

  if (!markets.length) {
    body.innerHTML = `<tr class="empty-row"><td colspan="9">No data yet. Press <b>Run cycle now</b> or <b>Start monitoring</b>.</td></tr>`;
    return;
  }

  // Sort: firing first, then by edge desc.
  markets.sort((a, b) => (b.fire - a.fire) || ((b.edge || -1) - (a.edge || -1)));

  body.innerHTML = markets.map((m) => {
    rowsByTicker[m.ticker] = m;
    const edgeTxt = m.edge == null ? "—" : (m.edge >= 0 ? "+" : "") + (m.edge * 100).toFixed(1) + "pp";
    const edgeCls = m.edge == null ? "" : (m.edge >= 0 ? "edge-pos" : "edge-neg");
    const sideBadge = m.side === "yes" ? '<span class="badge badge-yes">YES</span>'
      : m.side === "no" ? '<span class="badge badge-no">NO</span>' : "";
    const status = m.fire
      ? `${sideBadge} <span class="bell">🔔</span>`
      : `<span class="muted small">${esc(m.reason || "")}</span>`;
    return `<tr class="${m.fire ? "fire" : ""}" data-ticker="${esc(m.ticker)}">
      <td><span class="signal-dot ${m.fire ? "on" : ""}"></span></td>
      <td><b>${esc(m.ticker)}</b><br><span class="muted small">${esc((m.question || "").slice(0, 46))}</span></td>
      <td><span class="badge badge-type">${esc(m.market_type || "")}</span></td>
      <td class="num">${m.underlying != null ? usd(m.underlying, m.market_type === "gas" ? 3 : 2) : "—"}</td>
      <td class="num">${pct(m.claude_prob)}</td>
      <td>${confBadge(m.confidence)}</td>
      <td class="num">${pct(m.kalshi_implied)}</td>
      <td class="num ${edgeCls}">${edgeTxt}</td>
      <td>${status}</td>
    </tr>`;
  }).join("");

  $$("#marketsBody tr[data-ticker]").forEach((tr) =>
    tr.addEventListener("click", () => openDrawer(tr.dataset.ticker))
  );
}

/* ---------- drawer ---------- */
function openDrawer(ticker) {
  const m = rowsByTicker[ticker];
  if (!m) return;
  $("#dTicker").textContent = m.ticker;
  $("#dQuestion").textContent = m.question || "";

  const sig = $("#dSignal");
  if (m.fire) {
    sig.className = "drawer-signal fire";
    const action = m.side === "yes" ? "BUY YES" : "BUY NO";
    sig.textContent = `🔔 ${action} signal · entry ≤ ${usd(m.suggested_price)} · edge +${((m.edge || 0) * 100).toFixed(1)}pp`;
  } else {
    sig.className = "drawer-signal nofire";
    sig.textContent = "No signal — " + (m.reason || "gates not met");
  }

  const stats = {
    "Claude P(YES)": pct1(m.claude_prob),
    "Confidence": m.confidence || "—",
    "Kalshi implied": pct1(m.kalshi_implied),
    "Edge": m.edge == null ? "—" : ((m.edge >= 0 ? "+" : "") + (m.edge * 100).toFixed(1) + " pp"),
    [m.underlying_label || "Underlying"]: m.underlying != null ? usd(m.underlying, m.market_type === "gas" ? 3 : 2) : "—",
    "Days to resolve": m.days_to_resolution != null ? m.days_to_resolution.toFixed(1) : "—",
  };
  $("#dStats").innerHTML = Object.entries(stats)
    .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");

  $("#dReasoning").textContent = m.reasoning || "—";
  const risks = m.key_risks || [];
  $("#dRisks").innerHTML = risks.length ? risks.map((r) => `<li>${esc(r)}</li>`).join("") : "<li class='muted'>None provided</li>";

  $("#drawer").classList.remove("hidden");
}
function closeDrawer() { $("#drawer").classList.add("hidden"); }

/* ---------- alerts ---------- */
async function loadAlerts() {
  const body = $("#alertsBody");
  try {
    const rows = await api("get_notifications", 100);
    if (!rows.length) { body.innerHTML = `<tr class="empty-row"><td colspan="7">No alerts yet.</td></tr>`; return; }
    body.innerHTML = rows.map((r) => `
      <tr>
        <td>${esc((r.ts || "").replace("T", " ").slice(0, 19))}</td>
        <td><b>${esc(r.market_ticker)}</b></td>
        <td>${r.side === "yes" ? '<span class="badge badge-yes">YES</span>' : '<span class="badge badge-no">NO</span>'}</td>
        <td class="num">${pct(r.claude_prob)}</td>
        <td class="num">${pct(r.kalshi_implied)}</td>
        <td class="num edge-pos">+${((r.edge || 0) * 100).toFixed(1)}pp</td>
        <td>${r.ntfy_status === 200 ? "✓" : esc(r.ntfy_status)}</td>
      </tr>`).join("");
  } catch (e) {
    body.innerHTML = `<tr class="empty-row"><td colspan="7">Could not load alerts.</td></tr>`;
  }
}

/* ---------- calibration ---------- */
async function loadCalibration() {
  try {
    const r = await api("get_calibration");
    const counts = r.counts || {};
    $("#cN").textContent = r.n_resolved || 0;
    $("#cBrier").textContent = r.brier_score != null ? r.brier_score.toFixed(4) : "—";
    $("#cNaive").textContent = r.naive_brier != null ? r.naive_brier.toFixed(4) : "—";
    $("#cEstimates").textContent = counts.estimates || 0;

    const body = $("#calibBody");
    const cal = r.calibration || {};
    const keys = Object.keys(cal).sort((a, b) => parseFloat(a) - parseFloat(b));
    if (!keys.length) {
      body.innerHTML = `<tr class="empty-row"><td colspan="4">No resolved markets yet. Record outcomes with <code>scripts/backfill_resolutions.py</code>.</td></tr>`;
      return;
    }
    body.innerHTML = keys.map((k) => {
      const b = cal[k];
      const hr = b.hit_rate;
      return `<tr>
        <td>${(parseFloat(k) * 100).toFixed(0)}%</td>
        <td class="num">${b.n}</td>
        <td class="num">${(hr * 100).toFixed(1)}%</td>
        <td><div class="relbar"><i style="width:${(hr * 100).toFixed(0)}%"></i></div></td>
      </tr>`;
    }).join("");
  } catch (e) {
    $("#calibBody").innerHTML = `<tr class="empty-row"><td colspan="4">Could not load calibration.</td></tr>`;
  }
}

/* ---------- settings ---------- */
async function loadSettings() {
  try {
    const s = await api("get_settings");
    settingsCache = s;
    const sec = s.secrets || {};
    const stateLabel = (k) => sec[k] && sec[k].set ? "Currently set: " + sec[k].masked : "Not set";
    $("#sAnthropicState").textContent = stateLabel("ANTHROPIC_API_KEY");
    $("#sEiaState").textContent = stateLabel("EIA_API_KEY");
    $("#sNtfyState").textContent = sec.NTFY_TOPIC && sec.NTFY_TOPIC.set ? "Currently set: " + sec.NTFY_TOPIC.masked : "Not set";
    $("#sAlphaState").textContent = stateLabel("ALPHAVANTAGE_KEY");

    const t = s.tunables || {};
    $("#tProb").value = t.min_probability;
    $("#tEdge").value = t.min_edge;
    $("#tSpread").value = t.max_spread;
    $("#tCap").value = t.position_size_cap;
    $("#tPoll").value = t.poll_interval_minutes;
    $("#tCooldown").value = t.cooldown_hours;
    $("#tCooldownGrow").value = t.cooldown_edge_growth;
    $("#tMinDays").value = t.min_days_to_resolution;
    $("#tMaxDays").value = t.max_days_to_resolution;
    $("#tEiaEvery").value = t.eia_check_every_n_cycles;

    // Selects
    $("#tConf").innerHTML = (s.confidence_levels || []).map((c) =>
      `<option value="${c}" ${c === t.min_confidence ? "selected" : ""}>${c}</option>`).join("");
    $("#tModel").innerHTML = (s.claude_models || []).map((m) =>
      `<option value="${m}" ${m === t.claude_model ? "selected" : ""}>${m}</option>`).join("");

    // Series checkboxes
    const chosen = new Set(t.monitored_series || []);
    $("#seriesList").innerHTML = (s.available_series || []).map((srv) => `
      <label class="series-item">
        <input type="checkbox" value="${srv.ticker}" ${chosen.has(srv.ticker) ? "checked" : ""}/>
        <span><span class="s-ticker">${esc(srv.ticker)}</span><br><span class="s-label">${esc(srv.label)}</span></span>
      </label>`).join("");
  } catch (e) {
    console.error(e);
  }
}

async function saveSettings() {
  const msg = $("#saveMsg");
  msg.textContent = "Saving…";
  const secrets = {};
  const map = { ANTHROPIC_API_KEY: "#sAnthropic", EIA_API_KEY: "#sEia", NTFY_TOPIC: "#sNtfy", ALPHAVANTAGE_KEY: "#sAlpha" };
  for (const [k, sel] of Object.entries(map)) {
    const v = $(sel).value.trim();
    if (v) secrets[k] = v;
  }
  const series = $$("#seriesList input:checked").map((i) => i.value);
  const tunables = {
    min_probability: parseFloat($("#tProb").value),
    min_edge: parseFloat($("#tEdge").value),
    min_confidence: $("#tConf").value,
    max_spread: parseFloat($("#tSpread").value),
    position_size_cap: parseFloat($("#tCap").value),
    poll_interval_minutes: parseInt($("#tPoll").value, 10),
    cooldown_hours: parseInt($("#tCooldown").value, 10),
    cooldown_edge_growth: parseFloat($("#tCooldownGrow").value),
    min_days_to_resolution: parseInt($("#tMinDays").value, 10),
    max_days_to_resolution: parseInt($("#tMaxDays").value, 10),
    claude_model: $("#tModel").value,
    eia_check_every_n_cycles: parseInt($("#tEiaEvery").value, 10),
    monitored_series: series,
  };
  try {
    const r = await api("save_settings", { secrets, tunables });
    if (r.ok) {
      msg.textContent = "Saved ✓";
      ["#sAnthropic", "#sEia", "#sNtfy", "#sAlpha"].forEach((s) => ($(s).value = ""));
      await loadSettings();
      await poll();
      setTimeout(() => (msg.textContent = ""), 2500);
    } else {
      msg.textContent = "Error: " + (r.error || "unknown");
    }
  } catch (e) {
    msg.textContent = "Error: " + e.message;
  }
}

/* ---------- controls ---------- */
async function toggleMonitoring() {
  const s = await api("get_state");
  const r = s.running ? await api("stop_monitoring") : await api("start_monitoring");
  if (!r.ok && r.error) alert(r.error);
  await poll();
}
async function runCycleNow() {
  const r = await api("run_cycle_now");
  if (!r.ok && r.error) alert(r.error);
  await poll();
}
async function testNotification() {
  const msg = $("#testNotifyMsg");
  msg.textContent = "Sending…";
  const r = await api("test_notification");
  msg.textContent = r.ok ? "Sent to topic ✓" : "Error: " + (r.error || "unknown");
  setTimeout(() => (msg.textContent = ""), 4000);
}

/* ---------- polling ---------- */
async function poll() {
  if (!API_READY) return;
  try {
    const s = await api("get_state");
    renderState(s);
  } catch (e) { /* bridge momentarily unavailable */ }
}

/* ---------- wire up ---------- */
function wire() {
  $$(".tab").forEach((t) => t.addEventListener("click", () => showView(t.dataset.view)));
  $$("[data-goto]").forEach((b) => b.addEventListener("click", () => showView(b.dataset.goto)));
  $$("[data-close-drawer]").forEach((el) => el.addEventListener("click", closeDrawer));
  $("#btnToggle").addEventListener("click", toggleMonitoring);
  $("#btnRunNow").addEventListener("click", runCycleNow);
  $("#btnRefreshAlerts").addEventListener("click", loadAlerts);
  $("#btnRefreshCalib").addEventListener("click", loadCalibration);
  $("#btnSaveSettings").addEventListener("click", saveSettings);
  $("#btnTestNotify").addEventListener("click", testNotification);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
}

(async function init() {
  wire();
  await whenReady();
  await poll();
  setInterval(poll, 4000);
})();
