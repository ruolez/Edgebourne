// Campaign and ad set pages: their numbers with "vs before", a daily chart, (ad sets) learning progress
// and who sees it, the ad sets / ads inside in the manager table, and one History timeline.
import { api, startLoad } from "./api.js";
import { boot, emptyState, esc, icon, onRefresh, setCrumbs, switchHtml, timelineHtml, toast, when, errorState, withFrom } from "./ui.js";
import { columnChart, marksPanel } from "./charts.js";
import { count, dayLabel, explain, money, moneyWhole, rangeSelect, rememberRange, sharedRange } from "./format.js";
import * as UrlState from "./urlstate.js";
import { LIVE, bulkBarHtml, closePeek, figuresHtml, flatten, setBooked, listHtml, narrow, peek, statusCell, tableHtml, hasTrack, trackLegend, unlistedNote, wire } from "./manager.js";

const $ = (id) => document.getElementById(id);
const LEVEL = document.body.dataset.level;
const id = new URLSearchParams(location.search).get("id");
// The dates are the ones picked last on any page (Ads, Results, Compare…), unless the link says otherwise.
const DEFAULTS = { id: "", tab: LEVEL === "campaign" ? "adsets" : "ads", range: sharedRange(), vs: true, sort: "spend", dir: "desc", peek: "" };
let state = UrlState.read({ ...DEFAULTS, id });
let data = null, me = null, rows = null;
const selected = new Set();

const childLevel = () => (state.tab === "adsets" ? "adset" : "ad");
const children = () => (rows ? rows[childLevel()] : []);
const picked = () => children().filter((r) => selected.has(r.id));

// Who sees it is always shown; learning progress beside it only when Meta reports a stage.
function audienceCard(s) {
  const l = s.learning || {};
  const stage = l.status || s.learning_stage;
  const got = l.conversions;
  const edited = l.last_sig_edit_ts ? new Date(l.last_sig_edit_ts * 1000) : null;
  const words = stage === "SUCCESS" ? "Finished learning: delivery is stable."
    : stage === "FAIL" ? explain("learning_limited") : explain("learning").replace(/^Learning: /, "");
  const pct = got != null ? Math.min(100, Math.round((got / 50) * 100)) : null;
  const learning = stage ? `<div class="learn"><h3 class="learn-h">Learning</h3><p class="muted small">${esc(words)}</p>
    ${got != null ? `<div class="learn-row"><b class="tnum">${count(got)} of 50</b><span class="muted">results since the last big edit</span></div><span class="bar ${stage === "FAIL" ? "warn" : ""}"><i data-w="${pct}"></i></span>` : ""}
    ${edited ? `<p class="muted small">Last edit that restarted learning: ${esc(when(edited.toISOString()))}.</p>` : ""}</div>` : "";
  return `<section class="panel who-card" id="who-sees"><div class="panel-body${learning ? " who-split" : ""}">
    <div><h3 class="learn-h">Who sees it</h3><p>${s.targeting_summary ? esc(s.targeting_summary) : '<span class="muted">Meta hasn\'t said who this ad set reaches yet. It shows here after the next refresh.</span>'}</p>
      <p class="muted small" id="estimate"></p></div>
    ${learning}</div></section>`;
}

function render() {
  const e = data.entity;
  const canControl = e.can_control ?? data.campaign.can_control;
  $("en-title").textContent = e.name;
  document.title = `${e.name} | Edge Bourne Ads`;
  $("en-sub").innerHTML = `${statusCell({ ...e, level: LEVEL })} <span class="sep-dot">·</span> ${esc(data.range.label)}${state.vs && data.prev_range ? ` vs ${esc(data.prev_range.label)}` : ""}`;
  const live = LIVE.includes(e.status);
  const budget = e.daily_budget_cents ? (canControl && live ? `<button type="button" class="chip" data-budget="${LEVEL}:${e.id}" data-current="${e.daily_budget_cents}" data-name="${esc(e.name)}">${money(e.daily_budget_cents, { exact: true })}/day</button>` : `<span class="chip">${money(e.daily_budget_cents, { exact: true })}/day</span>`) : "";
  $("en-actions").innerHTML = `${budget}
    <a class="btn" href="/leads.html?${LEVEL}=${encodeURIComponent(e.id)}" id="en-leads">${icon("leads")}Its leads</a>
    ${LEVEL === "campaign" ? `<a class="btn" href="/performance.html?campaign=${encodeURIComponent(e.id)}&range=${encodeURIComponent(state.range)}" id="en-results">${icon("chart")}Results</a>` : ""}
    ${me.role === "admin" && live ? (LEVEL === "campaign" ? `<a class="btn" href="${esc(withFrom(`/new-adset.html?campaign=${encodeURIComponent(e.id)}`))}">${icon("plus")}New ad set</a>` : `<a class="btn" href="${esc(withFrom(`/new-ad.html?adset=${encodeURIComponent(e.id)}`))}">${icon("plus")}New ad</a>`) : ""}
    ${me.role === "admin" ? `<a class="btn btn-claude-outline" href="/desk.html?ask=1&campaign=${encodeURIComponent(data.campaign.id)}">${icon("spark")}Ask Claude</a>` : ""}
    ${canControl && live ? `<span class="pk-sw">${switchHtml(e.status === "ACTIVE", `data-toggle="${LEVEL}:${e.id}" data-name="${esc(e.name)}"`, `${e.name} on or off`)} ${e.status === "ACTIVE" ? "On" : "Off"}</span>` : ""}`;
  const tabs = [...(LEVEL === "campaign" ? [["adsets", "Ad sets", rows.adset.length]] : []), ["ads", "Ads", rows.ad.length], ["history", "History", data.timeline.length]];
  const list = children();
  const body = state.tab === "history"
    ? `<section class="panel"><div class="panel-body">${data.timeline.length ? timelineHtml(data.timeline) : '<p class="muted">Nothing recorded yet.</p>'}</div></section>`
    : list.length && narrow() ? listHtml({ rows: list.map((r) => (state.vs ? r : { ...r, prev: null })), selected, sort: state.sort, dir: state.dir })
    : list.length ? tableHtml({ level: childLevel(), rows: list.map((r) => (state.vs ? r : { ...r, prev: null })), cols: "results", sort: state.sort, dir: state.dir, selected, selectable: true, range: state.range })
    : emptyHere(e, live);
  $("cr-all").innerHTML = `${figuresHtml(e.m, state.vs ? e.prev : null, data.target_qualified_cents, { today: e.today, ever: e.ever })}
    <div class="charts"><section class="panel"><div class="panel-head"><h2>Spend per day</h2></div><div class="chart" id="c-spend"></div></section>
      <section class="panel"><div class="panel-head"><h2>Leads per day</h2></div><div class="chart" id="c-leads"></div></section></div>
    <div class="fig-foot"><span class="fig-src"></span><div class="fig-marks" id="chg-panel"></div></div>
    ${LEVEL === "adset" ? audienceCard(e) : ""}
    <div class="cr-toolbar"><div class="tabs" role="tablist" aria-label="Show" data-tabpanel="en-panel">${tabs.map(([k, l, n]) => `<button type="button" role="tab" data-tab="${k}" aria-selected="${state.tab === k}">${l}<span class="n">${n}</span></button>`).join("")}</div>
      <span class="spacer"></span>
      ${rangeSelect("range-pick", state.range)}
      <button type="button" class="view-chip" id="vs" aria-pressed="${state.vs}">vs before</button></div>
    <div id="en-panel">${body}</div>
    ${state.tab !== "history" && !narrow() && hasTrack(list) ? trackLegend() : ""}
    <p class="muted small flush">Complete days only (${esc(dayLabel(data.range.start))} to ${esc(dayLabel(data.range.end))}).${esc(unlistedNote(e.m, rows.ad))}</p>`;
  document.querySelectorAll("#cr-all [data-w]").forEach((i) => { i.style.width = `${i.dataset.w}%`; });
  const marks = data.marks || [], marksSummary = data.marks_summary || "";
  columnChart({ el: $("c-spend"), series: data.series, key: "spend_cents", color: "var(--chart-spend)", title: "Spend per day", height: 170,
    format: (v) => money(v, { exact: true }), axisFormat: (v) => moneyWhole(v), marks, marksSummary });
  columnChart({ el: $("c-leads"), series: data.series, key: "leads", color: "var(--chart-leads)", title: "Leads per day", integer: true, height: 170,
    format: (v) => `${v} lead${v === 1 ? "" : "s"}`, axisFormat: (v) => String(Math.round(v)), marks, marksSummary });
  marksPanel($("chg-panel"), marks, marksSummary, data.marks_list);
  if (LEVEL === "adset" && $("estimate")) api(`/api/insights/adset/${encodeURIComponent(e.id)}/estimate`).then((x) => { if (x.lower && x.upper) $("estimate").textContent = `Meta estimates ${count(x.lower)}–${count(x.upper)} people could see these ads.`; }).catch(() => {});
  $("bulk").innerHTML = bulkBarHtml(childLevel(), picked(), canControl);
  document.body.classList.toggle("has-bulk", selected.size > 0);
}

// An empty campaign or ad set says so and offers to make the first one inside it (admins, while it can run).
function emptyHere(e, live) {
  const inCampaign = state.tab === "adsets";
  const make = me.role === "admin" && live
    ? (inCampaign ? `<a class="btn btn-primary" id="empty-new" href="${esc(withFrom(`/new-adset.html?campaign=${encodeURIComponent(e.id)}`))}">${icon("plus")}New ad set</a>`
      : `<a class="btn btn-primary" id="empty-new" href="${esc(withFrom(LEVEL === "adset" ? `/new-ad.html?adset=${encodeURIComponent(e.id)}` : "/new-ad.html"))}">${icon("plus")}New ad</a>`)
    : "";
  const what = inCampaign ? "This campaign has no ad sets yet." : LEVEL === "campaign" ? "This campaign has no ads yet." : "This ad set has no ads yet.";
  return emptyState({ title: "Nothing here yet", body: `${what}${make ? "" : live ? "" : " It's archived or deleted, so nothing new can go in it."}`, actions: make, tag: "div" });
}

async function load() {
  const superseded = startLoad("entity");
  let d;
  try {
    d = await api(`/api/${LEVEL === "campaign" ? "campaigns" : "adsets"}/${encodeURIComponent(id)}?range=${encodeURIComponent(state.range)}${state.vs ? "&vs=prev" : ""}`);
  } catch (err) {
    if (!superseded()) errorState($("cr-all"), err, load, { href: "/ads.html", label: "Back to Ads" });
    return;
  }
  if (superseded()) return;
  data = d;
  setBooked(d.tracks_bookings);
  rows = flatten({ campaigns: data.campaigns });
  if (LEVEL === "adset") { rows.ad = rows.ad.filter((a) => a.adset.id === id); rows.adset = rows.adset.filter((s) => s.id === id); }
  data.entity = LEVEL === "campaign" ? rows.campaign[0] : rows.adset[0];
  setCrumbs([{ label: "Ads", href: "/ads.html" },
    ...(LEVEL === "adset" ? [{ label: data.campaign.name, href: `/campaign.html?id=${encodeURIComponent(data.campaign.id)}` }] : []),
    { label: data.entity.name, href: location.pathname + location.search }]);
  render();
  if (state.peek) openPeek(state.peek, { quiet: true });
}

// id's default is "", so writing the state always keeps ?id= in the address (it used to drop it on a change of dates).
const KEYS = DEFAULTS;
const set = (patch, reload = false) => {
  if (Object.keys(patch).some((k) => k !== "peek")) UrlState.leaveLayer();
  state = { ...state, ...patch }; UrlState.write(state, KEYS); if (reload) load(); else render();
};

// The quick look is in the URL (?peek=) and Back closes it, like on Ads.
let popping = false;
function openPeek(key, { quiet = false, fromHistory = false } = {}) {
  const [lv, rid] = key.split(":");
  const r = (rows[lv] || []).find((x) => x.id === rid);
  if (!r) return;
  const wasOpen = Boolean(state.peek);
  state.peek = key;
  if (!fromHistory) { if (quiet || wasOpen) UrlState.write(state, KEYS); else UrlState.openLayer(UrlState.url(state, KEYS)); }
  peek(r, { focus: !quiet, onClose: (changed) => {
    const was = state.peek;
    state.peek = "";
    if (was && !popping) UrlState.closeLayer(UrlState.url(state, KEYS));
    if (changed) load();
  } });
}
// Closed by the page itself (another tab): no step back, the entry just stops being the quick look's.
function dropPeek() { popping = true; closePeek(); popping = false; UrlState.leaveLayer(); }

me = await boot({ page: LEVEL });
if (me) {
  const ctx = {
    reload: () => { selected.clear(); load(); }, level: childLevel, range: () => state.range, picked,
    clear: () => { selected.clear(); render(); },
    pick: (rid, on) => { if (on) selected.add(rid); else selected.delete(rid); render(); },
    pickAll: (on) => { children().forEach((r) => (on ? selected.add(r.id) : selected.delete(r.id))); render(); },
    sortBy: (key) => set({ sort: key, dir: state.sort === key && state.dir === "desc" ? "asc" : "desc" }),
    peek: (key) => (state.peek === key ? closePeek() : openPeek(key)),
  };
  wire($("cr-all"), ctx);
  wire($("bulk"), ctx);
  wire($("en-actions"), ctx);
  $("cr-all").addEventListener("click", (e) => {
    const t = e.target.closest("[data-tab]");
    if (t) { selected.clear(); dropPeek(); set({ tab: t.dataset.tab, sort: "spend", dir: "desc", peek: "" }); }
    if (e.target.closest("#vs")) set({ vs: !state.vs }, true);
  });
  $("cr-all").addEventListener("change", (e) => { if (e.target.id === "range-pick") { rememberRange(e.target.value); set({ range: e.target.value }, true); } });
  // Back / Forward: show what the URL says, the view first, then the quick look.
  addEventListener("popstate", () => {
    const next = UrlState.read(KEYS);
    const viewChanged = Object.keys(KEYS).some((k) => k !== "peek" && next[k] !== state[k]);
    if (!next.peek && state.peek) { popping = true; closePeek(); popping = false; }
    if (viewChanged) { selected.clear(); state = next; load(); return; }
    if (next.peek && next.peek !== state.peek && rows) openPeek(next.peek, { fromHistory: true });
  });
  onRefresh(load);
  load();
}
