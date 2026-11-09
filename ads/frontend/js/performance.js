import { api } from "./api.js";
import { boot, esc, onRefresh, toast, when } from "./ui.js";
import { barList, columnChart } from "./charts.js";
import { count, dayLabel, money, pct, per } from "./format.js";

const $ = (id) => document.getElementById(id);
let me;
let range = "7";
try { range = localStorage.getItem("ebads-range") || "7"; } catch (e) {}

const STATUS = {
  ACTIVE: ["ok", "Running"], PAUSED: ["", "Paused"], CAMPAIGN_PAUSED: ["", "Campaign paused"],
  ADSET_PAUSED: ["", "Ad set paused"], IN_PROCESS: ["warn", "In review"], PENDING_REVIEW: ["warn", "In review"],
  DISAPPROVED: ["bad", "Rejected"], WITH_ISSUES: ["bad", "Has issues"], ARCHIVED: ["", "Archived"],
  PENDING_BILLING_INFO: ["bad", "Needs billing"],
};
const statusPill = (s) => { const [k, l] = STATUS[s] || ["", (s || "Unknown").toLowerCase()]; return `<span class="pill ${k}">${esc(l)}</span>`; };

function yesterdayLine(y) {
  if (!y) return "";
  const m = (v) => money(v, { exact: true });
  const vs = (now, before, fmt) => (now === before ? "same as the day before" : `${now > before ? "up" : "down"} from ${fmt(before)}`);
  return `<span class="sub">Yesterday: ${m(y.spend_cents)} spent (${vs(y.spend_cents, y.prev_spend_cents, m)}), ${count(y.leads)} lead${y.leads === 1 ? "" : "s"} (${vs(y.leads, y.prev_leads, count)})</span>`;
}

function render(data) {
  const t = data.totals;
  const cpl = t.leads ? t.spend_cents / t.leads : null;
  const noData = !data.ads.length && !t.spend_cents;
  const alerts = data.alerts.map((a) => `<p class="note ${a.level}" role="status">${esc(a.text)}</p>`).join("");

  const cap = pacingPanel(data);

  if (noData) {
    $("perf").innerHTML = alerts + cap + `<section class="panel empty"><h3>No results yet</h3><p>Once the ads have run for a full day, spend, leads and cost per lead show up here.${me.role === "admin" ? " Connect Meta in Settings, then use Refresh from Meta." : ""}</p>${me.role === "admin" ? '<a class="btn" href="/settings.html">Open Settings</a>' : ""}</section>`;
    fixInlineWidths();
    wirePacing();
    return;
  }

  const figures = `<section class="panel figures" aria-label="Totals for the period">
    <div class="figure hero"><span class="label">Cost per lead</span><span class="value">${cpl ? money(cpl, { exact: true }) : "—"}</span><span class="sub">${count(t.leads)} lead${t.leads === 1 ? "" : "s"} from ${money(t.spend_cents)}</span>${yesterdayLine(data.yesterday)}</div>
    <div class="figure"><span class="label">Spent</span><span class="value">${money(t.spend_cents)}</span></div>
    <div class="figure"><span class="label">Leads</span><span class="value">${count(t.leads)}</span></div>
    <div class="figure"><span class="label">Qualified or won</span><span class="value">${count(t.qualified)}</span><span class="sub">from the leads inbox</span></div>
    <div class="figure"><span class="label">Cost per qualified lead</span><span class="value">${per(t.spend_cents, t.qualified)}</span><span class="sub">the number that matters most</span></div>
  </section>`;

  const charts = `<div class="charts">
    <section class="panel"><div class="panel-head"><h2>Spend per day</h2></div><div class="chart" id="c-spend"></div></section>
    <section class="panel"><div class="panel-head"><h2>Leads per day</h2></div><div class="chart" id="c-leads"></div></section>
  </div>
  <details class="table-view panel"><summary class="panel-body">Show the days as a table</summary><div class="panel-body scroll-x"><table class="table">
    <thead><tr><th>Day</th><th class="num">Spent</th><th class="num">Leads</th></tr></thead>
    <tbody>${data.series.map((d) => `<tr><td>${dayLabel(d.day)}</td><td class="num">${money(d.spend_cents, { exact: true })}</td><td class="num">${d.leads}</td></tr>`).join("")}</tbody></table></div></details>`;

  const rows = data.ads.map((a) => `<tr>
    <td><span class="ad-cell">${a.thumbnail_url ? `<img src="${esc(a.thumbnail_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '<span class="ph"></span>'}<b>${esc(a.name)}</b></span></td>
    <td>${statusPill(a.effective_status)}</td>
    <td class="num">${money(a.spend_cents, { exact: true })}</td>
    <td class="num">${count(a.impressions)}</td>
    <td class="num">${pct(a.link_clicks, a.impressions)}</td>
    <td class="num">${count(a.leads)}</td>
    <td class="num">${per(a.spend_cents, a.leads)}</td>
    <td class="num">${count(a.qualified)}</td>
  </tr>`).join("");
  const ads = `<section class="panel"><div class="panel-head"><h2>Ads</h2><p>Click rate = link clicks ÷ impressions.</p></div><div class="panel-body scroll-x"><table class="table middle">
    <thead><tr><th>Ad</th><th>Status</th><th class="num">Spent</th><th class="num">Impressions</th><th class="num">Click rate</th><th class="num">Leads</th><th class="num">Cost per lead</th><th class="num">Qualified</th></tr></thead>
    <tbody>${rows}</tbody></table></div></section>
    <p class="muted small flush">Complete days only (${dayLabel(data.range.start)} to ${dayLabel(data.range.end)}): today is left out because Meta reports late. Judge an ad only after it has spent at least twice your target cost per lead.</p>`;

  const extra = `<section class="panel"><div class="panel-head wrap"><h2>Who and where</h2><p>All ads, same period</p><span class="spacer"></span>
      <div class="format-scroll"><div class="segmented" id="acc-by">${[["placement", "Placement"], ["age", "Age"], ["gender", "Gender"], ["device", "Device"], ["region", "Region"], ["hour", "Hour"]].map(([k, l]) => `<button type="button" data-by="${k}" aria-pressed="${k === accBy}">${l}</button>`).join("")}</div></div></div>
      <div class="panel-body aud-grid"><div><h3 class="chart-title">Share of spend</h3><div id="acc-spend"><p class="muted">Loading from Meta…</p></div></div>
      <div><h3 class="chart-title">Leads and cost per lead</h3><div id="acc-leads"></div></div></div></section>
    ${me.role === "admin" ? `<section class="panel"><div class="panel-head"><h2>What changed on Meta</h2><p>Last 14 days, from Meta's own history: Ads Manager, this dashboard and Meta's automatic changes</p></div><div class="panel-body" id="activity"><p class="muted">Loading…</p></div></section>` : ""}`;
  $("perf").innerHTML = alerts + cap + figures + charts + ads + extra;
  wirePacing();
  loadAccountBreakdown();
  if (me.role === "admin") loadActivity();
  fixInlineWidths();
  columnChart({ el: $("c-spend"), series: data.series, key: "spend_cents", color: "var(--chart-spend)", title: "Spend per day",
    format: (v) => money(v, { exact: true }), axisFormat: (v) => `$${Math.round(v / 100)}` });
  columnChart({ el: $("c-leads"), series: data.series, key: "leads", color: "var(--chart-leads)", title: "Leads per day", integer: true,
    format: (v) => `${v} lead${v === 1 ? "" : "s"}`, axisFormat: (v) => String(Math.round(v)) });
}

// This month: spend so far, where it lands at this pace, the spending limit and the target.
const shortDay = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });

function pacingPanel(data) {
  const p = data.pacing;
  if (!p) return "";
  const capFig = data.cap && data.cap.limit_cents ? (() => {
    const used = data.cap.spent_cents / data.cap.limit_cents;
    const sub = data.cap.remaining_cents <= 0 ? "Reached: every ad is paused until it's raised"
      : p.cap_days !== null ? `Runs out around ${shortDay(p.cap_date)} at this pace` : `${money(data.cap.remaining_cents)} left`;
    return `<div class="figure"><span class="label">Account spending limit</span><span class="value">${money(data.cap.spent_cents)} <small>of ${money(data.cap.limit_cents)}</small></span>
      <div class="meter ${used >= 1 ? "bad" : used >= 0.8 ? "warn" : ""}" role="meter" aria-valuemin="0" aria-valuemax="${data.cap.limit_cents}" aria-valuenow="${data.cap.spent_cents}" aria-label="Spending limit used"><i data-w="${Math.min(used, 1) * 100}"></i></div>
      <span class="sub">${sub}</span></div>`;
  })() : "";
  const target = p.target_cents
    ? `<span class="value">${money(p.target_cents)}</span><span class="sub">${p.needed_daily_cents === 0 ? "Already spent" : `Land on it with ${money(p.needed_daily_cents, { exact: true })} a day from today`}${p.vs_target_pct ? `; this pace is ${Math.abs(p.vs_target_pct)}% ${p.vs_target_pct > 0 ? "over" : "under"}` : ""}</span>`
    : `<span class="value muted">—</span><span class="sub">Not set${data.can_set_target ? "" : " (an admin sets it)"}</span>`;
  const edit = data.can_set_target ? `<button type="button" class="btn btn-quiet small" id="target-edit">${p.target_cents ? "Change" : "Set a target"}</button>
      <form class="target-form" id="target-form" hidden novalidate><label class="sr-only" for="target-dollars">Monthly target in dollars</label>
        <span class="money-input">$<input class="input" id="target-dollars" name="dollars" inputmode="decimal" value="${p.target_cents ? p.target_cents / 100 : ""}" placeholder="600"></span>
        <button class="btn btn-primary" type="submit">Save</button></form>` : "";
  return `<h2 class="section-title pace-title">${esc(p.month)} so far</h2>
    <section class="panel figures pace" aria-label="This month's pace">
      <div class="figure"><span class="label">Spent this month</span><span class="value">${money(p.mtd_cents)}</span><span class="sub">including today so far</span></div>
      <div class="figure"><span class="label">Month at this pace</span><span class="value">${money(p.projected_cents)}</span><span class="sub">${money(p.rate_cents, { exact: true })} a day (last 7 days), ${p.days_left} day${p.days_left === 1 ? "" : "s"} to go</span></div>
      ${capFig}
      <div class="figure"><span class="label">Monthly target</span>${target}${edit}</div>
    </section>`;
}

function wirePacing() {
  const btn = document.getElementById("target-edit");
  if (!btn) return;
  btn.addEventListener("click", () => { $("target-form").hidden = false; btn.hidden = true; $("target-dollars").focus(); });
  $("target-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/api/performance/target", { method: "PUT", body: { dollars: $("target-dollars").value.trim() } });
      toast($("target-dollars").value.trim() ? "Monthly target saved" : "Monthly target cleared");
      load();
    } catch (err) { toast(err.message, "bad"); }
  });
}

// The CSP forbids inline style attributes, so meter widths are applied from JS.
function fixInlineWidths() {
  document.querySelectorAll(".meter i[data-w]").forEach((i) => { i.style.width = `${i.dataset.w}%`; });
}

let accBy = "placement";

async function loadAccountBreakdown() {
  if (me.role !== "admin") { const el = document.getElementById("acc-spend"); if (el) el.closest(".panel").remove(); return; }
  try {
    const d = await api(`/api/insights/breakdown?level=account&by=${accBy}&range=${range}`);
    const total = d.items.reduce((s, i) => s + i.spend_cents, 0);
    barList($("acc-spend"), d.items, { key: "spend_cents", format: (v) => (total ? `${Math.round((v / total) * 100)}%` : "—"), extra: (i) => money(i.spend_cents) });
    barList($("acc-leads"), d.items, { key: "leads", format: (v) => count(v), extra: (i) => (i.leads ? `${per(i.spend_cents, i.leads)} per lead` : "no leads") });
  } catch (err) { $("acc-spend").innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

const fmtVal = (v) => (v == null ? "" : typeof v === "object" ? (v.new_value ?? v.value ?? JSON.stringify(v)) : v);

async function loadActivity() {
  try {
    const d = await api("/api/insights/activity?days=14");
    $("activity").innerHTML = d.items.length ? `<ul class="changes">${d.items.map((a) => {
      const change = a.old != null || a.new != null ? `: ${esc(String(fmtVal(a.old)))} → ${esc(String(fmtVal(a.new)))}` : "";
      return `<li><span><b>${esc(a.what || "")}</b>${a.object ? ` · ${esc(a.object)}` : ""}${change}</span><small>${esc(when(a.time))}${a.who ? ` · ${esc(a.who)}` : ""}</small></li>`;
    }).join("")}</ul>` : '<p class="muted flush">No changes in the last 14 days.</p>';
  } catch (err) { $("activity").innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

async function load() {
  document.querySelectorAll("#range button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.range === range)));
  try { render(await api(`/api/performance?range=${range}`)); } catch (err) { toast(err.message, "bad"); }
}

me = await boot({ page: "performance" });
if (me) {
  document.addEventListener("click", (e) => {
    const b = e.target.closest("#acc-by [data-by]");
    if (!b) return;
    accBy = b.dataset.by;
    document.querySelectorAll("#acc-by button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    loadAccountBreakdown();
  });
  $("range").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-range]");
    if (!b) return;
    range = b.dataset.range;
    try { localStorage.setItem("ebads-range", range); } catch (err) {}
    load();
  });
  onRefresh(load);
  load();
}
