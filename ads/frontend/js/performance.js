import { api, startLoad } from "./api.js";
import { boot, entityLink, esc, icon, onRefresh, rememberList, skeleton, toast, when, showLoadError } from "./ui.js";
import { barList, columnChart } from "./charts.js";
import { EXPLAIN, RANGES, STATUS as FORMAT_STATUS, WORDS, count, dayLabel, money, pct, per, moneyWhole, currencySymbol, rangeSelect, rememberRange, sharedRange, statusPill } from "./format.js";

const $ = (id) => document.getElementById(id);
let me;
let data;
// The dates picked last on any page (Ads, Campaign, Ad set, Ad, Compare), unless the link names its own.
let range = sharedRange();
const RANGE_KEYS = RANGES.map(([k]) => k);
const qs = new URLSearchParams(location.search);
if (RANGE_KEYS.includes(qs.get("range"))) range = qs.get("range");
let campaign = qs.get("campaign") || "";

// The ads table: which ads, in what order. Kept per browser.
const FILTERS = {
  spent: ["Spent money", (a) => a.spend_cents > 0],
  running: ["Delivering", (a) => a.effective_status === "ACTIVE"],
  all: ["All", (a) => a.effective_status !== "DELETED" || a.spend_cents > 0],
};
const COLUMNS = [
  { key: "name", label: "Ad", text: true, value: (a) => (a.name || "").toLowerCase() },
  { key: "status", label: "Status", text: true, value: (a) => (STATUS[a.effective_status] || ["", a.effective_status || ""])[1] },
  { key: "spend", label: WORDS.spend, value: (a) => a.spend_cents },
  { key: "impressions", label: WORDS.impressions, value: (a) => a.impressions, title: EXPLAIN.impressions },
  { key: "ctr", label: WORDS.ctr, value: (a) => (a.impressions ? a.link_clicks / a.impressions : null), title: EXPLAIN.ctr },
  { key: "leads", label: "Leads", value: (a) => a.leads },
  { key: "cpl", label: WORDS.cpl, value: (a) => (a.leads ? a.spend_cents / a.leads : null), low: true },
  { key: "qualified", label: WORDS.qualified, value: (a) => a.qualified, title: "Marked Qualified or Won in the leads inbox" },
  { key: "cpq", label: WORDS.cpql, value: (a) => (a.qualified ? a.spend_cents / a.qualified : null), low: true },
];
const EARLY = 3; // fewer leads than this: too early to judge an ad's cost per lead
let table = { filter: "spent", sort: "spend", dir: "desc", q: "" };
try { table = { ...table, ...JSON.parse(localStorage.getItem("ebads-results") || "{}"), q: "" }; } catch (e) {}
if (!FILTERS[table.filter]) table.filter = "spent";
if (!COLUMNS.some((c) => c.key === table.sort)) { table.sort = "spend"; table.dir = "desc"; }
const saveTable = () => { try { localStorage.setItem("ebads-results", JSON.stringify({ filter: table.filter, sort: table.sort, dir: table.dir })); } catch (e) {} };

const STATUS = FORMAT_STATUS;

function yesterdayLine(y) {
  if (!y) return "";
  const m = (v) => money(v, { exact: true });
  const vs = (now, before, fmt) => (now === before ? "same as the day before" : `${now > before ? "up" : "down"} from ${fmt(before)}`);
  return `<span class="sub">Yesterday: ${m(y.spend_cents)} spent (${vs(y.spend_cents, y.prev_spend_cents, m)}), ${count(y.leads)} lead${y.leads === 1 ? "" : "s"} (${vs(y.leads, y.prev_leads, count)})</span>`;
}

// "▲ 18% vs prior 7 days": `better` says which direction is good news (null: neither).
function change(now, before, better, prev) {
  const span = `${dayLabel(prev.start)} – ${dayLabel(prev.end)}`;
  const prior = ["mtd", "lastmonth"].includes(range) ? "the month before" : `prior ${data.range.days} days`;
  const vs = `vs ${prior}`;
  if (now == null) return "";
  if (before == null || before === 0) return `<span class="delta" title="${esc(span)}">none in ${prior}</span>`;
  const d = Math.round(((now - before) / before) * 100);
  if (d === 0) return `<span class="delta" title="${esc(span)}">same as ${prior}</span>`;
  const tone = better === null ? "" : (d < 0) === (better === "down") ? "good" : "bad";
  return `<span class="delta ${tone}" title="${esc(span)}">${d > 0 ? "▲" : "▼"} ${Math.abs(d)}% ${vs}</span>`;
}

function render() {
  const t = data.totals;
  const p = data.previous;
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

  const ratio = (c, n) => (n ? c / n : null);
  const figures = `<section class="panel figures" aria-label="Totals for the period">
    <div class="figure hero"><span class="label">Cost per lead</span><span class="value">${cpl ? money(cpl, { exact: true }) : "—"}</span>${change(cpl, ratio(p.spend_cents, p.leads), "down", p)}<span class="sub">${count(t.leads)} lead${t.leads === 1 ? "" : "s"} from ${money(t.spend_cents)}</span>${yesterdayLine(data.yesterday)}</div>
    <div class="figure"><span class="label">Spent</span><span class="value">${money(t.spend_cents)}</span>${change(t.spend_cents, p.spend_cents, null, p)}</div>
    <div class="figure"><span class="label">Leads</span><span class="value">${count(t.leads)}</span>${change(t.leads, p.leads, "up", p)}</div>
    <div class="figure"><span class="label">Qualified or won</span><span class="value">${count(t.qualified)}</span>${change(t.qualified, p.qualified, "up", p)}<span class="sub">from the leads inbox</span></div>
    <div class="figure"><span class="label">Cost per qualified lead</span><span class="value">${per(t.spend_cents, t.qualified)}</span>${change(ratio(t.spend_cents, t.qualified), ratio(p.spend_cents, p.qualified), "down", p)}<span class="sub">the number that matters most</span></div>
  </section>`;

  const charts = `<div class="charts">
    <section class="panel"><div class="panel-head"><h2>Spend per day</h2></div><div class="chart" id="c-spend"></div></section>
    <section class="panel"><div class="panel-head"><h2>Leads per day</h2></div><div class="chart" id="c-leads"></div></section>
  </div>
  <details class="table-view panel"><summary class="panel-body">Show the days as a table</summary><div class="panel-body scroll-x"><table class="table">
    <thead><tr><th>Day</th><th class="num">Spent</th><th class="num">Leads</th></tr></thead>
    <tbody>${data.series.map((d) => `<tr><td>${dayLabel(d.day)}</td><td class="num">${money(d.spend_cents, { exact: true })}</td><td class="num">${d.leads}</td></tr>`).join("")}</tbody></table></div></details>`;

  const ads = `<section class="panel" id="cr-panel" aria-label="Ads"></section>
    <p class="muted small flush">Complete days only (${dayLabel(data.range.start)} to ${dayLabel(data.range.end)}): today is left out because Meta reports late. A cost in grey comes from fewer than ${EARLY} leads, too few to judge the ad on.</p>`;

  const extra = `<section class="panel"><div class="panel-head wrap"><h2>Who and where</h2><p>${campaign ? "This campaign" : "All ads"}, same period</p><span class="spacer"></span>
      <div class="format-scroll"><div class="segmented" id="acc-by">${[["placement", "Placement"], ["age", "Age"], ["gender", "Gender"], ["device", "Device"], ["region", "Region"], ["hour", "Hour"]].map(([k, l]) => `<button type="button" data-by="${k}" aria-pressed="${k === accBy}">${l}</button>`).join("")}</div></div></div>
      <div class="panel-body aud-grid"><div><h3 class="chart-title">Share of spend</h3><div id="acc-spend">${skeleton("Loading from Meta…")}</div></div>
      <div><h3 class="chart-title">Leads and cost per lead</h3><div id="acc-leads"></div></div></div></section>
    ${me.role === "admin" ? `<section class="panel"><div class="panel-head"><h2>What changed on Meta</h2><p>Last 14 days, from Meta's own history: Ads Manager, this dashboard and Meta's automatic changes</p></div><div class="panel-body" id="activity">${skeleton()}</div></section>` : ""}`;
  const ideas = `<section class="panel" id="ideas-panel"><div class="panel-head wrap"><h2>By idea</h2><p>Ads grouped by their tags, last 30 days</p><span class="spacer"></span>
      <div class="format-scroll"><div class="segmented" id="idea-by" role="group" aria-label="Group by">${[["hook", "Hook"], ["angle", "Angle"], ["persona", "Who it's for"], ["format", "Format"], ["offer", "Offer"]].map(([k, l]) => `<button type="button" data-idea="${k}" aria-pressed="${k === ideaBy}">${l}</button>`).join("")}</div></div></div>
      <div class="panel-body" id="ideas">${skeleton()}</div></section>`;
  $("perf").innerHTML = alerts + cap + figures + charts + ads + ideas + extra;
  loadIdeas();
  renderAds();
  wirePacing();
  loadAccountBreakdown();
  if (me.role === "admin") loadActivity();
  fixInlineWidths();
  columnChart({ el: $("c-spend"), series: data.series, key: "spend_cents", color: "var(--chart-spend)", title: "Spend per day",
    format: (v) => money(v, { exact: true }), axisFormat: (v) => moneyWhole(v) });
  columnChart({ el: $("c-leads"), series: data.series, key: "leads", color: "var(--chart-leads)", title: "Leads per day", integer: true,
    format: (v) => `${v} lead${v === 1 ? "" : "s"}`, axisFormat: (v) => String(Math.round(v)) });
}

function adsShown() {
  const q = table.q.trim().toLowerCase();
  const col = COLUMNS.find((c) => c.key === table.sort);
  const sign = table.dir === "asc" ? 1 : -1;
  return data.ads.filter(FILTERS[table.filter][1]).filter((a) => !q || (a.name || "").toLowerCase().includes(q)).sort((a, b) => {
    const x = col.value(a), y = col.value(b);
    if (x == null || y == null) return x == null && y == null ? 0 : x == null ? 1 : -1; // no value: always last
    return (x < y ? -1 : x > y ? 1 : 0) * sign || b.spend_cents - a.spend_cents;
  });
}

function costCell(cents, n) {
  if (!n) return "—";
  const v = money(cents / n, { exact: true });
  return n < EARLY ? `<span class="early" title="Only ${n} so far: too early to judge">${v}</span>` : v;
}

function adRow(a) {
  return `<tr>
    <td><a class="cr-cell" href="/ad.html?id=${encodeURIComponent(a.id)}">${a.thumbnail_url ? `<img src="${esc(a.thumbnail_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '<span class="ph"></span>'}<b>${esc(a.name)}</b></a></td>
    <td>${statusPill(a.effective_status)}</td>
    <td class="num">${money(a.spend_cents, { exact: true })}</td>
    <td class="num">${count(a.impressions)}</td>
    <td class="num">${pct(a.link_clicks, a.impressions)}</td>
    <td class="num">${count(a.leads)}</td>
    <td class="num">${costCell(a.spend_cents, a.leads)}</td>
    <td class="num">${count(a.qualified)}</td>
    <td class="num">${costCell(a.spend_cents, a.qualified)}</td>
  </tr>`;
}

function totalRow(list) {
  const sum = (k) => list.reduce((s, a) => s + (a[k] || 0), 0);
  const [spend, imp, clicks, leads, qual] = ["spend_cents", "impressions", "link_clicks", "leads", "qualified"].map(sum);
  return `<tr><th scope="row" colspan="2">Total · ${list.length} ad${list.length === 1 ? "" : "s"}</th>
    <td class="num">${money(spend, { exact: true })}</td><td class="num">${count(imp)}</td><td class="num">${pct(clicks, imp)}</td>
    <td class="num">${count(leads)}</td><td class="num">${per(spend, leads)}</td><td class="num">${count(qual)}</td><td class="num">${per(spend, qual)}</td></tr>`;
}

function headCell(c) {
  const on = c.key === table.sort;
  const sort = on ? (table.dir === "asc" ? "ascending" : "descending") : "none";
  return `<th class="${c.text ? "" : "num"}" aria-sort="${sort}"${c.title ? ` title="${esc(c.title)}"` : ""}><button type="button" class="th-sort" data-sort="${c.key}">${esc(c.label)}<span class="arrow" aria-hidden="true">${on ? (table.dir === "asc" ? "↑" : "↓") : "↕"}</span></button></th>`;
}

function renderAds() {
  const box = document.getElementById("cr-panel");
  if (!box) return;
  const list = adsShown();
  const counts = Object.fromEntries(Object.entries(FILTERS).map(([k, [, fn]]) => [k, data.ads.filter(fn).length]));
  const body = list.length
    ? `<div class="scroll-x"><table class="table middle results-table">
        <thead><tr>${COLUMNS.map(headCell).join("")}</tr></thead>
        <tbody>${list.map(adRow).join("")}</tbody>
        ${list.length > 1 ? `<tfoot>${totalRow(list)}</tfoot>` : ""}</table></div>`
    : `<div class="empty-inline"><p class="muted">${table.q ? `No ad called “${esc(table.q)}”` : `No ads ${{ spent: "spent money", running: "are running", all: "" }[table.filter]} in this period`.replace("  ", " ")}.</p>
        <button type="button" class="btn btn-quiet btn-small" data-clear>Show all ads</button></div>`;
  const head = box.querySelector(".results-bar");
  const bar = `<div class="panel-head wrap results-bar"><h2>Ads</h2><a class="more" href="/ads.html?range=${encodeURIComponent(range)}&vs=1${campaign ? `&campaign=${encodeURIComponent(campaign)}` : ""}" title="Turn ads on or off, compare or change several at once">Manage in Ads</a>
      <div class="filters" id="cr-filter" role="group" aria-label="Show ads">${Object.entries(FILTERS).map(([k, [l]]) =>
        `<button type="button" class="view-chip" data-filter="${k}" aria-pressed="${k === table.filter}">${esc(l)} <span class="n">${counts[k]}</span></button>`).join("")}</div>
      <div class="search">${icon("search")}<label class="sr-only" for="cr-q">Find an ad</label><input class="input" id="cr-q" type="search" placeholder="Find an ad" autocomplete="off" value="${esc(table.q)}"></div>
    </div>`;
  if (!head) box.innerHTML = bar + '<div class="panel-body" id="cr-results"></div>';
  else box.querySelectorAll("#cr-filter button").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.filter === table.filter));
    b.querySelector(".n").textContent = counts[b.dataset.filter];
  });
  document.getElementById("cr-results").innerHTML = body;
}

function wireAds() {
  document.addEventListener("click", (e) => {
    const f = e.target.closest("#cr-filter [data-filter]");
    if (f) { table.filter = f.dataset.filter; saveTable(); renderAds(); return; }
    const s = e.target.closest(".results-table [data-sort]");
    if (s) {
      const col = COLUMNS.find((c) => c.key === s.dataset.sort);
      if (table.sort === col.key) table.dir = table.dir === "asc" ? "desc" : "asc";
      else { table.sort = col.key; table.dir = col.text || col.low ? "asc" : "desc"; }
      saveTable(); renderAds();
      document.querySelector(`.results-table [data-sort="${col.key}"]`)?.focus();
      return;
    }
    if (e.target.closest("#cr-panel [data-clear]")) {
      table.filter = "all"; table.q = "";
      const q = document.getElementById("cr-q"); if (q) q.value = "";
      saveTable(); renderAds();
    }
  });
  document.addEventListener("input", (e) => {
    if (e.target.id !== "cr-q") return;
    table.q = e.target.value; renderAds();
  });
}

// One campaign or all of them; only offered when there is more than one.
function campaignPicker() {
  const el = $("campaign-pick");
  const list = data.campaigns || [];
  if (list.length < 2 && !campaign) { el.hidden = true; return; }
  el.hidden = false;
  $("campaign").innerHTML = `<option value="">All campaigns</option>` + list.map((c) =>
    `<option value="${esc(c.id)}" ${c.id === campaign ? "selected" : ""}>${esc(c.name)}${c.effective_status === "ACTIVE" ? "" : " (off)"}</option>`).join("");
}

function syncUrl() {
  const u = new URL(location.href);
  u.searchParams.set("range", range);
  if (campaign) u.searchParams.set("campaign", campaign); else u.searchParams.delete("campaign");
  history.replaceState(null, "", u);
  rememberList();
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
        <span class="money-input">${currencySymbol()}<input class="input" id="target-dollars" name="dollars" inputmode="decimal" value="${p.target_cents ? p.target_cents / 100 : ""}" placeholder="600"></span>
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
// ?idea=<dimension>&tag=<value> (a tag named on Compare or a report) opens By idea on that row.
const IDEA_DIMS = ["hook", "angle", "persona", "format", "offer"];
let ideaBy = IDEA_DIMS.includes(qs.get("idea")) ? qs.get("idea") : "hook";
let ideaTag = qs.get("tag") || "";
let ideaShown = false;

const ratePct = (v) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);

async function loadIdeas() {
  const box = document.getElementById("ideas");
  if (!box) return;
  const superseded = startLoad("ideas");
  try {
    const d = await api(`/api/concepts?by=${ideaBy}&range=30`);
    if (superseded()) return;
    if (!d.groups.length) { box.innerHTML = '<p class="muted flush">No ad spent money in the last 30 days.</p>'; return; }
    const best = d.groups.find((g) => g.best);
    const verdict = !best ? '<p class="note">Too early to say which idea works best: each group needs 3 or more leads and twice the target cost in spend.</p>'
      : d.best_is_clear ? `<p class="note ok"><b>${esc(best.value)}</b> brings the cheapest leads, ${d.best_confidence}% sure.</p>`
        : `<p class="note"><b>${esc(best.value)}</b> is cheapest so far, but only ${d.best_confidence}% sure: the difference could be chance. Keep the ideas running side by side.</p>`;
    box.innerHTML = `${verdict}<div class="scroll-x"><table class="table middle ideas-table">
      <thead><tr><th>${esc(d.dimensions[d.by][0])}</th><th class="num">Ads</th><th class="num">Spent</th><th class="num">Leads</th><th class="num">Cost per lead</th>
        <th class="num" title="${esc(EXPLAIN.hook)}">${WORDS.hook}</th><th class="num" title="${esc(EXPLAIN.hold)}">${WORDS.hold}</th><th class="num" title="Qualified or won ÷ leads">Qualified rate</th></tr></thead>
      <tbody>${d.groups.map((g) => `<tr class="${g.best ? "lead" : ""}${g.value === "Not tagged" ? " untagged" : ""}${ideaTag && g.value.toLowerCase() === ideaTag.toLowerCase() ? " flash" : ""}" data-idea-row="${esc(g.value)}">
        <th scope="row"><b>${esc(g.value)}</b>${g.best ? ' <span class="pill ok">cheapest</span>' : ""}${g.enough ? "" : ' <span class="pill" title="Fewer than 3 leads or less than twice the target cost spent">too early</span>'}<span class="idea-ads">${(g.members || g.ad_names.map((name) => ({ name }))).map((m) => entityLink("ad", m.id, m.name)).join(", ")}</span></th>
        <td class="num">${count(g.ads)}</td><td class="num">${money(g.spend_cents)}</td><td class="num">${count(g.leads)}</td>
        <td class="num">${g.cpl_cents != null ? `<span class="${g.enough ? "" : "early"}">${money(g.cpl_cents, { exact: true })}</span>` : "—"}</td>
        <td class="num">${ratePct(g.hook_rate)}</td><td class="num">${ratePct(g.hold_rate)}</td><td class="num">${ratePct(g.qualified_rate)}</td></tr>`).join("")}</tbody></table></div>
      ${ideaTag && !d.groups.some((g) => g.value.toLowerCase() === ideaTag.toLowerCase()) ? `<p class="muted small flush">No ad tagged “${esc(ideaTag)}” spent money in the last 30 days.</p>` : ""}
      ${d.untagged_ads ? `<p class="muted small flush">${d.untagged_ads} ad${d.untagged_ads === 1 ? " has" : "s have"} no ${esc(d.dimensions[d.by][0].toLowerCase())} yet: tag them under "The idea" on each ad's page, or ask Claude to.</p>` : ""}`;
    // Opened for a tag (the row is marked) or as "Results: By idea" (#ideas-panel): the panel is drawn after the data, so the browser's own jump missed it.
    if ((ideaTag || location.hash === "#ideas-panel") && !ideaShown) {
      ideaShown = true;
      (box.querySelector("tr.flash") || $("ideas-panel")).scrollIntoView({ block: ideaTag ? "center" : "start" });
    }
  } catch (err) { if (!superseded()) box.innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

async function loadAccountBreakdown() {
  if (me.role !== "admin") { const el = document.getElementById("acc-spend"); if (el) el.closest(".panel").remove(); return; }
  const superseded = startLoad("who-where");
  try {
    const scope = campaign ? `level=campaign&id=${encodeURIComponent(campaign)}` : "level=account";
    const d = await api(`/api/insights/breakdown?${scope}&by=${accBy}&range=${range}`);
    if (superseded() || !$("acc-spend")) return;
    const total = d.items.reduce((s, i) => s + i.spend_cents, 0);
    barList($("acc-spend"), d.items, { key: "spend_cents", format: (v) => (total ? `${Math.round((v / total) * 100)}%` : "—"), extra: (i) => money(i.spend_cents) });
    barList($("acc-leads"), d.items, { key: "leads", format: (v) => count(v), extra: (i) => (i.leads ? `${per(i.spend_cents, i.leads)} per lead` : "no leads") });
  } catch (err) { if (!superseded() && $("acc-spend")) $("acc-spend").innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

// Budget amounts come in cents marked `money` (never shown as a bare 2000).
const fmtVal = (v, isMoney) => (v == null ? "" : isMoney ? money(v, { exact: true }) : typeof v === "object" ? (v.new_value ?? v.value ?? JSON.stringify(v)) : v);

async function loadActivity() {
  try {
    const d = await api("/api/insights/activity?days=14");
    $("activity").innerHTML = d.items.length ? `<ul class="chg-list">${d.items.map((a) => {
      const change = a.old != null || a.new != null ? `: ${esc(String(fmtVal(a.old, a.money)))} → ${esc(String(fmtVal(a.new, a.money)))}` : "";
      return `<li><span><b>${esc(a.what || "")}</b>${a.object ? ` · ${a.about ? entityLink(a.about.level, a.about.id, a.object) : esc(a.object)}` : ""}${change}</span><small>${esc(when(a.time))}${a.who ? ` · ${esc(a.who)}` : ""}</small></li>`;
    }).join("")}</ul>` : '<p class="muted flush">No changes in the last 14 days.</p>';
  } catch (err) { $("activity").innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

async function load() {
  if ($("range-pick")) $("range-pick").value = range; else $("range-box").outerHTML = rangeSelect("range-pick", range);
  syncUrl();
  const superseded = startLoad("performance");
  let d;
  try {
    d = await api(`/api/performance?range=${range}${campaign ? `&campaign=${encodeURIComponent(campaign)}` : ""}`);
  } catch (err) {
    if (superseded()) return;
    if (campaign) { campaign = ""; return load(); }
    showLoadError($("perf"), err, load); return;
  }
  if (superseded()) return;
  data = d;
  if (campaign && !data.campaigns.some((c) => c.id === campaign)) { campaign = ""; return load(); }
  campaignPicker();
  render();
}

me = await boot({ page: "performance" });
if (me) {
  document.addEventListener("click", (e) => {
    const ib = e.target.closest("#idea-by [data-idea]");
    if (ib) {
      ideaBy = ib.dataset.idea;
      ideaTag = "";
      document.querySelectorAll("#idea-by button").forEach((x) => x.setAttribute("aria-pressed", String(x === ib)));
      loadIdeas();
      return;
    }
    const b = e.target.closest("#acc-by [data-by]");
    if (!b) return;
    accBy = b.dataset.by;
    document.querySelectorAll("#acc-by button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    loadAccountBreakdown();
  });
  wireAds();
  $("campaign").addEventListener("change", () => { campaign = $("campaign").value; load(); });
  document.querySelector(".page-head").addEventListener("change", (e) => {
    if (e.target.id !== "range-pick") return;
    range = e.target.value;
    rememberRange(range);
    load();
  });
  onRefresh(load);
  load();
}
