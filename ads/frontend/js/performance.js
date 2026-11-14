import { api, startLoad } from "./api.js";
import { boot, entityLink, esc, icon, linkNote, onRefresh, pairNote, rememberList, skeleton, sourceNote, toast, when, showLoadError } from "./ui.js";
import { compareHtml } from "./mx.js";
import { barList, columnChart, marksPanel } from "./charts.js";
import { EXPLAIN, FOLLOW, LOST_REASONS, RANGES, STATUS as FORMAT_STATUS, WORDS, count, plural, dayLabel, money, pct, per, moneyWhole, currencySymbol, rangeSelect, rememberCampaign, rememberRange, sharedCampaign, sharedRange, statusPill } from "./format.js";

const $ = (id) => document.getElementById(id);
let me;
let data;
// The dates picked last on any page (Ads, Campaign, Ad set, Ad, Compare), unless the link names its own.
let range = sharedRange();
const RANGE_KEYS = RANGES.map(([k]) => k);
const qs = new URLSearchParams(location.search);
// By idea moved to Creative › Ideas: an older link to a tag here (?idea=<dimension>&tag=<value>) opens it there.
if (qs.has("idea")) {
  location.replace(`/ideas.html?${new URLSearchParams({ by: qs.get("idea"), ...(qs.get("tag") ? { tag: qs.get("tag") } : {}) })}`);
  await new Promise(() => {});
}
if (RANGE_KEYS.includes(qs.get("range"))) range = qs.get("range");
// One day or a few, linked from Settings → Numbers vs Ads Manager (D1): ?range=custom&start=&end=, this page only.
const ISO = /^\d{4}-\d{2}-\d{2}$/;
let custom = qs.get("range") === "custom" && ISO.test(qs.get("start") || "")
  ? { start: qs.get("start"), end: ISO.test(qs.get("end") || "") ? qs.get("end") : qs.get("start") } : null;
if (custom) range = "custom";
const rangeQs = () => (custom ? `range=custom&start=${custom.start}&end=${custom.end}` : `range=${encodeURIComponent(range)}`);
const customLabel = () => (custom.start === custom.end ? dayLabel(custom.start) : `${dayLabel(custom.start)} – ${dayLabel(custom.end)}`);
const rangeChoices = () => (custom ? [["custom", customLabel()], ...RANGES] : RANGES);
// The campaign picked last in this tab (Results or Compare), unless the link names its own ("" = all).
let campaign = qs.has("campaign") ? qs.get("campaign") : sharedCampaign();
// Lead quality (L2): by ad, form or answer, and which question, kept in the address (?lq_by=&lq_q=).
const Q_BY = [["ad", "By ad"], ["form", "By form"], ["answer", "By answer"]];
let qBy = Q_BY.some(([k]) => k === qs.get("lq_by")) ? qs.get("lq_by") : "ad";
let qQ = qs.get("lq_q") || "";

// The ads table: which ads, in what order. Kept per browser.
const FILTERS = {
  spent: ["Spent money", (a) => a.spend_cents > 0],
  running: ["Delivering", (a) => a.effective_status === "ACTIVE"],
  all: ["All", () => true],
};
// Deleted ads stay out of the table unless asked for; what they spent still counts in the figures above.
// Only deleted ads that spent in the period come back: the hundreds with nothing spent tell Eugene nothing.
const deleted = (a) => a.effective_status === "DELETED";
let showDeleted = qs.get("deleted") === "1";
const listed = (a) => !deleted(a) || (showDeleted && a.spend_cents > 0);
const COLUMNS = [
  { key: "name", label: "Ad", text: true, value: (a) => (a.name || "").toLowerCase() },
  { key: "status", label: "Status", text: true, value: (a) => (STATUS[a.effective_status] || ["", a.effective_status || ""])[1] },
  { key: "spend", label: WORDS.spend, value: (a) => a.spend_cents },
  { key: "impressions", label: WORDS.impressions, value: (a) => a.impressions, title: EXPLAIN.impressions },
  { key: "ctr", label: WORDS.ctr, value: (a) => (a.impressions ? a.link_clicks / a.impressions : null), title: EXPLAIN.ctr },
  { key: "leads", label: "Leads", value: (a) => a.leads },
  { key: "cpl", label: WORDS.cpl, value: (a) => (a.leads ? a.spend_cents / a.leads : null), low: true },
  { key: "qualified", label: WORDS.qualified, value: (a) => a.qualified, title: "Marked Qualified or Won in your leads list" },
  { key: "cpq", label: WORDS.cpql, value: (a) => (a.qualified ? a.spend_cents / a.qualified : null), low: true },
  // Booked calls (L1): only for an account that has booked one (the server's tracks_bookings).
  { key: "booked", label: FOLLOW.booked_col, value: (a) => a.booked, title: FOLLOW.booked_title, booked: true },
  { key: "cpb", label: FOLLOW.cpb_col, value: (a) => (a.booked ? a.spend_cents / a.booked : null), low: true, title: FOLLOW.booked_title, booked: true },
];
const cols = () => COLUMNS.filter((c) => !c.booked || (data && data.tracks_bookings));
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

// "▲ 18% vs prior 7 days": `better` says which direction is good news (null: neither). FU-C: Today is compared with
// yesterday up to the same hour ("vs yesterday by 3 PM: +$4.10"); a range with today compares its complete days only.
function change(now, before, better, prev, fmt = count) {
  const cmp = data.compare || {};
  if (cmp.mode === "hours") {
    if (!cmp.by) return `<span class="delta" title="Meta's hour-by-hour numbers for yesterday aren't in yet">not compared yet</span>`;
    if (now == null || before == null) return "";
    const diff = now - before;
    const words = Math.abs(diff) < 0.5 ? "same" : `${diff > 0 ? "+" : "−"}${fmt(Math.abs(diff))}`;
    const tone = better === null || Math.abs(diff) < 0.5 ? "" : (diff < 0) === (better === "down") ? "good" : "bad";
    return `<span class="delta ${tone}" title="Today so far against yesterday up to the same hour">vs yesterday by ${esc(cmp.by)}: ${words}</span>`;
  }
  const span = `${dayLabel(prev.start)} – ${dayLabel(prev.end)}${cmp.note ? " · complete days" : ""}`;
  const days = cmp.note ? cmp.before_days : data.range.days;
  const prior = ["mtd", "lastmonth"].includes(range) ? "the month before" : days === 1 ? "the day before" : `prior ${days} days`;
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
  // What "vs before" compares: the complete days when the range has today in it (FU-C), else the figures shown.
  const c = data.compare_now || t;
  const exact = (v) => money(v, { exact: true });
  const cpl = t.leads ? t.spend_cents / t.leads : null;
  const noData = !data.ads.length && !t.spend_cents;
  const alerts = data.alerts.map((a) => `<p class="note ${a.level}" role="status">${esc(a.text)}${a.href ? ` <a href="${esc(a.href)}">${esc(a.link || "Open")}</a>` : ""}</p>`).join("");

  const cap = pacingPanel(data);

  if (noData) {
    $("perf").innerHTML = alerts + cap + `<div class="src-alone" id="fig-src">${sourceNote(data.source)}</div><section class="panel empty"><h3>No results yet</h3><p>Once the ads have run for a full day, spend, leads and cost per lead show up here.${me.role === "admin" ? " Connect Meta in Settings, then use Refresh from Meta." : ""}</p>${me.role === "admin" ? '<a class="btn" href="/settings.html">Open Settings</a>' : ""}</section>`;
    fixInlineWidths();
    wirePacing();
    return;
  }

  const ratio = (c, n) => (n ? c / n : null);
  const figures = `<section class="panel figures${data.tracks_bookings ? " booked" : ""}" aria-label="Totals for the period">
    <div class="figure hero"><span class="label">Cost per lead</span><span class="value">${cpl ? money(cpl, { exact: true }) : "—"}</span>${change(ratio(c.spend_cents, c.leads), ratio(p.spend_cents, p.leads), "down", p, exact)}<span class="sub">${count(t.leads)} lead${t.leads === 1 ? "" : "s"} from ${money(t.spend_cents)}</span>${yesterdayLine(data.yesterday)}</div>
    <div class="figure" id="fig-spent"><span class="label">Spent</span><span class="value">${money(t.spend_cents)}</span>${change(c.spend_cents, p.spend_cents, null, p, exact)}</div>
    <div class="figure" id="fig-leads"><span class="label">Leads</span><span class="value">${count(t.leads)}</span>${change(c.leads, p.leads, "up", p)}${pairNote(data.source && data.source.leads)}</div>
    <div class="figure"><span class="label">Qualified or won</span><span class="value">${count(t.qualified)}</span>${change(c.qualified, p.qualified, "up", p)}<span class="sub">got that far · from your leads</span></div>
    <div class="figure"><span class="label">Cost per qualified lead</span><span class="value">${per(t.spend_cents, t.qualified)}</span>${change(ratio(c.spend_cents, c.qualified), ratio(p.spend_cents, p.qualified), "down", p, exact)}<span class="sub">the number that matters most</span></div>
    ${data.tracks_bookings ? `<div class="figure" id="fig-booked"><span class="label">${FOLLOW.booked}</span><span class="value">${count(t.booked)}</span>${change(c.booked, p.booked, "up", p)}<span class="sub">${count(t.held)} held, ${plural(t.no_show, "no-show")}</span></div>
    <div class="figure" id="fig-cpb"><span class="label">${FOLLOW.cpb}</span><span class="value">${per(t.spend_cents, t.booked)}</span>${change(ratio(c.spend_cents, c.booked), ratio(p.spend_cents, p.booked), "down", p, exact)}<span class="sub">from your leads</span></div>` : ""}
  </section>${data.compare && data.compare.note ? `<p class="td-note-line" id="cmp-note">Compared without today: today isn't over yet. The changes compare ${esc(data.compare.now_label)} with ${esc(data.compare.before_label)}.</p>` : ""}`;

  const charts = `<div class="charts">
    <section class="panel"><div class="panel-head"><h2>Spend per day</h2></div><div class="chart" id="c-spend"></div></section>
    <section class="panel"><div class="panel-head"><h2>Leads per day</h2></div><div class="chart" id="c-leads"></div></section>
  </div>
  <div class="fig-foot"><div class="fig-src" id="fig-src"></div><div class="fig-marks" id="chg-panel"></div></div>
  <details class="table-view panel"><summary class="panel-body">Show the days as a table</summary><div class="panel-body scroll-x"><table class="table">
    <thead><tr><th>Day</th><th class="num">Spent</th><th class="num">Leads</th></tr></thead>
    <tbody>${data.series.map((d) => `<tr><td>${dayLabel(d.day)}</td><td class="num">${money(d.spend_cents, { exact: true })}</td><td class="num">${d.leads}</td></tr>`).join("")}</tbody></table></div></details>`;

  const withToday = data.source && data.source.today && data.source.today.included;
  const ads = `<section class="panel" id="cr-panel" aria-label="Ads"></section>
    <p class="muted small flush">${withToday ? `${data.range.label === "Today" ? "Today so far" : esc(data.range.label)}: Meta is still counting today and reports some leads late.` : `Complete days only (${dayLabel(data.range.start)} to ${dayLabel(data.range.end)}): today is left out because Meta reports late.`} A cost in grey comes from fewer than ${EARLY} leads, too few to judge the ad on.</p>`;
  const quality = `<section class="panel quality-panel" id="quality-panel" aria-labelledby="quality-h">
      <div class="panel-head wrap"><h2 id="quality-h">Lead quality</h2><p>What happened to the leads from each ad, same period</p><span class="spacer"></span>
        <div class="quality-tools"><div class="segmented" id="quality-by" role="group" aria-label="Lead quality by">${Q_BY.map(([k, l]) =>
          `<button type="button" data-qby="${k}" aria-pressed="${k === qBy}">${l}</button>`).join("")}</div>
          <label class="sr-only" for="quality-question">Question</label><select class="input tool" id="quality-question" hidden></select></div></div>
      <div class="panel-body" id="quality-body">${skeleton()}</div></section>`;

  // Who and where is read for whole days only (FU-C): name the days it covers, which stop at yesterday.
  const settledWords = (k) => (["7", "14", "30"].includes(k) ? `the last ${k} complete days, to yesterday` : k === "mtd" ? "this month to yesterday (complete days)" : "complete days only, to yesterday");
  const extra = `<section class="panel"><div class="panel-head wrap"><h2>Who and where</h2><p>${campaign ? "This campaign" : "All ads"}, ${range === "today" ? "yesterday: read for whole days only" : withToday ? settledWords(range) : "same period"}</p><span class="spacer"></span>
      <div class="format-scroll"><div class="segmented" id="acc-by">${[["placement", "Placement"], ["age", "Age"], ["gender", "Gender"], ["device", "Device"], ["region", "Region"], ["hour", "Hour"]].map(([k, l]) => `<button type="button" data-by="${k}" aria-pressed="${k === accBy}">${l}</button>`).join("")}</div></div></div>
      <div class="panel-body aud-grid"><div><h3 class="chart-title">Share of spend</h3><div id="acc-spend">${skeleton("Loading from Meta…")}</div></div>
      <div><h3 class="chart-title">Leads and cost per lead</h3><div id="acc-leads"></div></div></div></section>
    ${me.role === "admin" ? `<section class="panel"><div class="panel-head"><h2>What changed on Meta</h2><p>Last 14 days, from Meta's own history: Ads Manager, this dashboard and Meta's automatic changes</p></div><div class="panel-body" id="activity">${skeleton()}</div></section>` : ""}`;
  // By idea lives in Creative › Ideas; here one line on the hooks for the same dates, and the way there.
  const ideas = `<section class="panel" id="ideas-panel"><div class="panel-head wrap"><h2>By idea</h2><p>Which hooks, angles and offers bring the cheapest leads</p><span class="spacer"></span>
      <a class="btn btn-quiet btn-small" id="ideas-open" href="/ideas.html?range=${encodeURIComponent(custom ? sharedRange() : range)}">Open Ideas</a></div>
      <div class="panel-body" id="ideas-sum">${skeleton()}</div></section>`;
  // AM-E (owner and account admins): how you compare, Meta's trend and the unusual changes it spotted, via the Mac's link.
  const mxd = data.meta_extras;
  const mxCard = mxd && mxd.compare ? `<section class="panel mx-panel" id="mx-results"><div class="panel-body">${compareHtml(mxd.compare, { id: "mx-results-cmp", head: "h2" })}</div></section>` : "";
  const mxLines = mxd ? [
    mxd.trend && mxd.trend.line ? `<div class="mx-line" id="mx-trend"><p class="flush">${icon("chart")}<span>${esc(mxd.trend.line)}</span></p>${linkNote(mxd.trend.source)}</div>` : "",
    mxd.anomalies && mxd.anomalies.count ? `<p class="mx-line flush" id="mx-anom">${icon("alarm")}<a href="${esc(mxd.anomalies.href)}">Meta noticed ${plural(mxd.anomalies.count, "unusual change")}</a></p>` : "",
  ].join("") : "";
  $("perf").innerHTML = alerts + cap + figures + mxCard + charts + mxLines + ads + quality + ideas + extra;
  loadQuality();
  loadIdeas();
  renderAds();
  wirePacing();
  loadAccountBreakdown();
  if (me.role === "admin") loadActivity();
  fixInlineWidths();
  const marks = data.marks || [], marksSummary = data.marks_summary || "";
  columnChart({ el: $("c-spend"), series: data.series, key: "spend_cents", color: "var(--chart-spend)", title: "Spend per day",
    format: (v) => money(v, { exact: true }), axisFormat: (v) => moneyWhole(v), marks, marksSummary });
  columnChart({ el: $("c-leads"), series: data.series, key: "leads", color: "var(--chart-leads)", title: "Leads per day", integer: true,
    format: (v) => `${v} lead${v === 1 ? "" : "s"}`, axisFormat: (v) => String(Math.round(v)), marks, marksSummary });
  marksPanel($("chg-panel"), marks, marksSummary, data.marks_list);
  $("fig-src").innerHTML = sourceNote(data.source);
}

function adsShown() {
  const q = table.q.trim().toLowerCase();
  const col = cols().find((c) => c.key === table.sort) || COLUMNS[2];
  const sign = table.dir === "asc" ? 1 : -1;
  return data.ads.filter(listed).filter(FILTERS[table.filter][1]).filter((a) => !q || (a.name || "").toLowerCase().includes(q)).sort((a, b) => {
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
    ${data.tracks_bookings ? `<td class="num">${count(a.booked)}</td><td class="num">${costCell(a.spend_cents, a.booked)}</td>` : ""}
  </tr>`;
}

function totalRow(list) {
  const sum = (k) => list.reduce((s, a) => s + (a[k] || 0), 0);
  const [spend, imp, clicks, leads, qual, booked] = ["spend_cents", "impressions", "link_clicks", "leads", "qualified", "booked"].map(sum);
  return `<tr><th scope="row" colspan="2">Total · ${list.length} ad${list.length === 1 ? "" : "s"}</th>
    <td class="num">${money(spend, { exact: true })}</td><td class="num">${count(imp)}</td><td class="num">${pct(clicks, imp)}</td>
    <td class="num">${count(leads)}</td><td class="num">${per(spend, leads)}</td><td class="num">${count(qual)}</td><td class="num">${per(spend, qual)}</td>
    ${data.tracks_bookings ? `<td class="num">${count(booked)}</td><td class="num">${per(spend, booked)}</td>` : ""}</tr>`;
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
  const pool = data.ads.filter(listed);
  const counts = Object.fromEntries(Object.entries(FILTERS).map(([k, [, fn]]) => [k, pool.filter(fn).length]));
  const gone = data.ads.filter((a) => deleted(a) && a.spend_cents > 0);
  const goneSpend = gone.reduce((s, a) => s + a.spend_cents, 0);
  const body = list.length
    ? `<div class="scroll-x"><table class="table middle results-table">
        <thead><tr>${cols().map(headCell).join("")}</tr></thead>
        <tbody>${list.map(adRow).join("")}</tbody>
        ${list.length > 1 ? `<tfoot>${totalRow(list)}</tfoot>` : ""}</table></div>`
    : `<div class="empty-inline"><p class="muted">${table.q ? `No ad called “${esc(table.q)}”` : `No ads ${{ spent: "spent money", running: "are running", all: "" }[table.filter]} in this period`.replace("  ", " ")}.</p>
        <button type="button" class="btn btn-quiet btn-small" data-clear>Show all ads</button></div>`;
  const head = box.querySelector(".results-bar");
  const bar = `<div class="panel-head wrap results-bar"><h2>Ads</h2>
      <div class="filters" id="cr-filter" role="group" aria-label="Show ads">${Object.entries(FILTERS).map(([k, [l]]) =>
        `<button type="button" class="view-chip" data-filter="${k}" aria-pressed="${k === table.filter}">${esc(l)} <span class="n">${counts[k]}</span></button>`).join("")}
        <button type="button" class="view-chip" id="cr-deleted" aria-pressed="${showDeleted}" title="Ads deleted on Meta: hidden unless you ask"${gone.length ? "" : " hidden"}>Deleted <span class="n">${gone.length}</span></button></div>
      <div class="search">${icon("search")}<label class="sr-only" for="cr-q">Find an ad</label><input class="input" id="cr-q" type="search" placeholder="Find an ad" autocomplete="off" value="${esc(table.q)}"></div>
      <a class="btn btn-quiet btn-small" id="cr-open" href="#">${icon("ads")}Open in Ads</a>
    </div>
    <p class="muted small flush cr-note" id="cr-note"></p>`;
  if (!head) box.innerHTML = bar + '<div class="panel-body" id="cr-results"></div>';
  else box.querySelectorAll("#cr-filter [data-filter]").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.filter === table.filter));
    b.querySelector(".n").textContent = counts[b.dataset.filter];
  });
  const del = document.getElementById("cr-deleted");
  del.hidden = !gone.length;
  del.setAttribute("aria-pressed", String(showDeleted));
  del.querySelector(".n").textContent = gone.length;
  // The analysis lives here; turning ads on or off, budgets and several at once live in Ads, opened on the same days and campaign.
  document.getElementById("cr-open").href = adsHref();
  // Read-only clients change nothing in Ads, so they get no action wording.
  document.getElementById("cr-note").textContent = [
    me.role === "client" ? "" : "To turn ads on or off or change budgets, open them in Ads.",
    gone.length && !showDeleted ? `${gone.length} deleted ad${gone.length === 1 ? "" : "s"} spent ${money(goneSpend, { exact: true })} in these days: counted in the figures above, left out of this table.` : "",
  ].filter(Boolean).join(" ");
  document.getElementById("cr-note").hidden = !document.getElementById("cr-note").textContent;
  document.getElementById("cr-results").innerHTML = body;
}

function wireAds() {
  document.addEventListener("click", (e) => {
    const f = e.target.closest("#cr-filter [data-filter]");
    if (f) { table.filter = f.dataset.filter; saveTable(); renderAds(); return; }
    const s = e.target.closest(".results-table [data-sort]");
    if (s) {
      const col = cols().find((c) => c.key === s.dataset.sort);
      if (table.sort === col.key) table.dir = table.dir === "asc" ? "desc" : "asc";
      else { table.sort = col.key; table.dir = col.text || col.low ? "asc" : "desc"; }
      saveTable(); renderAds();
      document.querySelector(`.results-table [data-sort="${col.key}"]`)?.focus();
      return;
    }
    if (e.target.closest("#cr-deleted")) { showDeleted = !showDeleted; syncUrl(); renderAds(); return; }
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

// Ads opened from here: the same days and campaign, with "vs before", on the view that matches the filter.
function adsHref() {
  const u = new URLSearchParams({ range: custom ? "custom" : range, vs: "1" });
  if (custom) { u.set("from", custom.start); u.set("to", custom.end); }
  if (campaign) u.set("campaign", campaign);
  if (table.filter === "running") u.set("view", "delivering");
  if (showDeleted) u.set("archived", "1");
  return `/ads.html?${u}`;
}

function syncUrl() {
  const u = new URL(location.href);
  u.searchParams.set("range", range);
  if (custom) { u.searchParams.set("start", custom.start); u.searchParams.set("end", custom.end); }
  else { u.searchParams.delete("start"); u.searchParams.delete("end"); }
  if (campaign) u.searchParams.set("campaign", campaign); else u.searchParams.delete("campaign");
  if (showDeleted) u.searchParams.set("deleted", "1"); else u.searchParams.delete("deleted");
  if (qBy !== "ad") u.searchParams.set("lq_by", qBy); else u.searchParams.delete("lq_by");
  if (qBy === "answer" && qQ) u.searchParams.set("lq_q", qQ); else u.searchParams.delete("lq_q");
  history.replaceState(null, "", u);
  // The tabs and breadcrumbs reopen Results on this campaign; the dates come from the shared range, so a
  // range picked later on another page isn't overruled by an old one kept here.
  const kept = new URL(u);
  kept.searchParams.delete("range");
  kept.searchParams.delete("start");
  kept.searchParams.delete("end");
  rememberList(kept.pathname + kept.search);
  rememberCampaign(campaign);
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
      <span class="sub">${sub}${data.can_set_target ? ' · <a href="/settings.html#spend-limit" id="cap-change">Change the limit</a>' : ""}</span></div>`;
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

// ---------- Lead quality (L2): what happened to the leads from each ad, form or answer

const rate = (r) => (r == null ? "—" : `${Math.round(r * 100)}%`);
const lostText = (lost) => {
  const parts = Object.entries(lost || {}).map(([k, n]) => `${n} ${(k === "none" ? "no reason given" : LOST_REASONS[k] || k).toLowerCase()}`);
  return parts.length ? parts.join(" · ") : "—";
};
const early = (text, enough, why) => (enough ? text : `<span class="early" title="${esc(why)}">${text}</span>`);

function qualityName(d, r) {
  if (r.is_page) return `<span class="quality-name"><b>${esc(r.label)}</b></span>`;
  const best = d.best === r.key ? ' <span class="pill ok">cheapest qualified</span>' : "";
  if (d.by === "ad") {
    return `<span class="quality-name">${entityLink("ad", r.key, r.label)}${best}<small><a href="/leads.html?ad=${encodeURIComponent(r.key)}&status=all">Its leads</a></small></span>`;
  }
  if (d.by === "form") {
    return r.key === "none" ? `<span class="quality-name">${esc(r.label)}</span>`
      : `<span class="quality-name"><a href="/leads.html?form=${encodeURIComponent(r.key)}&status=all">${esc(r.label)}</a>${best}</span>`;
  }
  return `<span class="quality-name">${esc(r.label)}</span>`;
}

function qualityCells(d, r) {
  const few = `Only ${plural(r.leads, "lead")} so far: too early to judge`;
  const judge = `Needs 3 qualified leads${d.target_cents ? ` and twice the ${money(d.target_cents, { exact: true })} target in spend` : ""} before it means much`;
  return {
    qualified: early(`${count(r.qualified)} · ${rate(r.qualified_rate)}`, r.rates_enough, few),
    junk: early(`${count(r.junk)} · ${rate(r.junk_rate)}`, r.rates_enough, few),
    cpq: r.cpq_cents == null ? "—" : early(money(r.cpq_cents, { exact: true }), r.cpq_enough, judge),
  };
}

function qualityHtml(d) {
  const v = d.verdict || {};
  const thru = d.verdict_through ? ` <span class="td-thru">(through yesterday)</span>` : "";
  const verdict = `<p class="quality-verdict" id="quality-verdict">${v.name ? `<b>${esc(v.name)}</b> ` : ""}${esc(v.text || "")}${thru}</p>`;
  if (!d.rows.length) return verdict;
  const head = d.by === "ad" ? "Ad" : d.by === "form" ? "Form" : "Answer";
  const rows = d.rows.map((r) => {
    const c = qualityCells(d, r);
    return `<tr data-key="${esc(r.key)}"><td>${qualityName(d, r)}</td><td class="num">${count(r.leads)}</td><td class="num">${count(r.repeats)}</td>
      <td class="num">${c.qualified}</td><td class="num">${c.junk}</td><td class="num">${c.cpq}</td><td class="why">${esc(lostText(r.lost))}</td></tr>`;
  }).join("");
  const cards = d.rows.map((r) => {
    const c = qualityCells(d, r);
    return `<li class="quality-card" data-key="${esc(r.key)}"><h3>${qualityName(d, r)}</h3>
      <dl><div><dt>Leads</dt><dd>${count(r.leads)}${r.repeats ? ` <small>+${count(r.repeats)} repeat${r.repeats === 1 ? "" : "s"}</small>` : ""}</dd></div>
        <div><dt>Qualified</dt><dd>${c.qualified}</dd></div><div><dt>Looks like junk</dt><dd>${c.junk}</dd></div>
        <div><dt>${WORDS.cpql}</dt><dd>${c.cpq}</dd></div></dl>
      <p class="why">Why lost: ${esc(lostText(r.lost))}</p></li>`;
  }).join("");
  return `${verdict}<div class="quality-wide scroll-x"><table class="table middle quality-table">
      <thead><tr><th>${head}</th><th class="num" title="People who filled in the form; repeats counted once">Leads</th><th class="num">Repeats</th>
        <th class="num" title="Got to Qualified or Won, ÷ leads">Qualified</th><th class="num" title="Marked spam, or looks fake and was never contacted, ÷ leads">Looks like junk</th>
        <th class="num">${WORDS.cpql}</th><th class="why">Why lost</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <ul class="quality-cards" id="quality-cards">${cards}</ul>
    <p class="quality-note" id="quality-junk">${esc(d.junk_note || "")}</p>`;
}

async function loadQuality() {
  const box = $("quality-body");
  if (!box) return;
  const superseded = startLoad("quality");
  const u = new URLSearchParams(rangeQs());
  u.set("by", qBy);
  if (campaign) u.set("campaign", campaign);
  if (qBy === "answer" && qQ) u.set("question", qQ);
  try {
    const d = await api(`/api/performance/quality?${u}`);
    if (superseded() || !$("quality-body")) return;
    const sel = $("quality-question");
    if (qBy === "answer") {
      qQ = d.question || "";
      sel.innerHTML = d.questions.map((q) => `<option value="${esc(q.name)}" ${q.name === qQ ? "selected" : ""}>${esc(q.label)}</option>`).join("");
    }
    sel.hidden = qBy !== "answer" || !d.questions.length;
    $("quality-body").innerHTML = qualityHtml(d);
    // Opened on By idea (below this panel), already scrolled there: the table drawn above it must not push it away.
    if (ideaShown && location.hash === "#ideas-panel" && $("ideas-panel")) $("ideas-panel").scrollIntoView({ block: "start" });
    syncUrl();
  } catch (err) { if (!superseded() && $("quality-body")) $("quality-body").innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

let accBy = "placement";
let ideaShown = false;

// One sentence on the hooks for the dates picked here; the groups, pictures and every dimension are on Ideas.
async function loadIdeas() {
  const box = document.getElementById("ideas-sum");
  if (!box) return;
  const superseded = startLoad("ideas");
  try {
    const d = await api(`/api/concepts?by=hook&${rangeQs()}`);
    if (superseded()) return;
    const tagged = d.groups.filter((g) => g.value !== "Not tagged");
    const best = d.groups.find((g) => g.best);
    const line = !d.groups.length ? "No ad spent money in these dates."
      : !tagged.length ? "No ad that spent in these dates has a hook tagged yet."
        : !best ? `${count(tagged.length)} hook${tagged.length === 1 ? "" : "s"} so far, too early to say which works best: each needs 3 or more leads and twice the target cost in spend.`
          : d.best_is_clear ? `<b>${esc(best.value)}</b> is the hook bringing the cheapest leads, ${d.best_confidence}% sure.`
            : `<b>${esc(best.value)}</b> is the cheapest hook so far, but only ${d.best_confidence}% sure: the difference could be chance.`;
    // Ideas has no campaign filter: with one campaign picked here, say this line still counts all of them.
    box.innerHTML = `<p class="flush">${line}</p>${campaign ? `<p class="muted small flush" id="ideas-all">Counts every campaign, not just the one picked above.</p>` : ""}`;
    // Opened as "Results: By idea" (an older link to #ideas-panel): the panel is drawn after the data, so the browser's own jump missed it.
    if (location.hash === "#ideas-panel" && !ideaShown) {
      ideaShown = true;
      $("ideas-panel").scrollIntoView({ block: "start" });
    }
  } catch (err) { if (!superseded()) box.innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

async function loadAccountBreakdown() {
  if (me.role !== "admin") { const el = document.getElementById("acc-spend"); if (el) el.closest(".panel").remove(); return; }
  const superseded = startLoad("who-where");
  try {
    const scope = campaign ? `level=campaign&id=${encodeURIComponent(campaign)}` : "level=account";
    const d = await api(`/api/insights/breakdown?${scope}&by=${accBy}&${rangeQs()}`);
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
  if ($("range-pick") && $("range-pick").options.length === rangeChoices().length) $("range-pick").value = range;
  else ($("range-pick") || $("range-box")).outerHTML = rangeSelect("range-pick", range, rangeChoices());
  syncUrl();
  const superseded = startLoad("performance");
  let d;
  try {
    d = await api(`/api/performance?${rangeQs()}${campaign ? `&campaign=${encodeURIComponent(campaign)}` : ""}`);
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
    const b = e.target.closest("#acc-by [data-by]");
    if (!b) return;
    accBy = b.dataset.by;
    document.querySelectorAll("#acc-by button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    loadAccountBreakdown();
  });
  wireAds();
  document.addEventListener("click", (e) => {
    const b = e.target.closest("#quality-by [data-qby]");
    if (!b || b.dataset.qby === qBy) return;
    qBy = b.dataset.qby;
    document.querySelectorAll("#quality-by [data-qby]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    loadQuality();
  });
  document.addEventListener("change", (e) => {
    if (e.target.id !== "quality-question") return;
    qQ = e.target.value;
    loadQuality();
  });
  $("campaign").addEventListener("change", () => { campaign = $("campaign").value; load(); });
  document.querySelector(".page-head").addEventListener("change", (e) => {
    if (e.target.id !== "range-pick" || e.target.value === "custom") return;
    range = e.target.value;
    custom = null; // the dates linked from the numbers check give way to the ones picked here
    rememberRange(range);
    load();
  });
  onRefresh(load);
  load();
}
