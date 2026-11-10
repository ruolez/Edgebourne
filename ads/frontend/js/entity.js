// Campaign and ad set pages: their numbers with "vs before", a daily chart, (ad sets) learning progress
// and who sees it, the ad sets / ads inside in the manager table, and one History timeline.
import { api } from "./api.js";
import { boot, esc, icon, onRefresh, setCrumbs, switchHtml, toast, when } from "./ui.js";
import { columnChart } from "./charts.js";
import { count, dayLabel, money } from "./format.js";
import * as UrlState from "./urlstate.js";
import { bulkBarHtml, closePeek, figuresHtml, flatten, listHtml, narrow, peek, statusCell, tableHtml, wire } from "./manager.js";

const $ = (id) => document.getElementById(id);
const LEVEL = document.body.dataset.level;
const id = new URLSearchParams(location.search).get("id");
const DEFAULTS = { id: "", tab: LEVEL === "campaign" ? "adsets" : "ads", range: "14", vs: true, sort: "spend", dir: "desc" };
const RANGES = [["7", "7 days"], ["14", "14 days"], ["30", "30 days"], ["mtd", "This month"], ["lastmonth", "Last month"]];
let state = UrlState.read({ ...DEFAULTS, id });
let data = null, me = null, rows = null;
const selected = new Set();

const childLevel = () => (state.tab === "adsets" ? "adset" : "ad");
const children = () => (rows ? rows[childLevel()] : []);
const picked = () => children().filter((r) => selected.has(r.id));

function learningCard(s) {
  const l = s.learning || {};
  const stage = l.status || s.learning_stage;
  if (!stage) return "";
  const got = l.conversions;
  const edited = l.last_sig_edit_ts ? new Date(l.last_sig_edit_ts * 1000) : null;
  const words = stage === "SUCCESS" ? "Finished learning: delivery is stable."
    : stage === "FAIL" ? "Learning limited: too few results for Meta to settle. Usually fewer ad sets, a bigger budget or a broader audience help; avoid frequent edits."
    : "Learning: Meta is still working out who to show it to. Results wobble until about 50 results in a week.";
  const pct = got != null ? Math.min(100, Math.round((got / 50) * 100)) : null;
  return `<section class="panel learn"><div class="panel-head"><h2>Learning</h2><p>${esc(words)}</p></div><div class="panel-body">
    ${got != null ? `<div class="learn-row"><b class="tnum">${count(got)} of 50</b><span class="muted">results since the last big edit</span></div><span class="bar ${stage === "FAIL" ? "warn" : ""}"><i data-w="${pct}"></i></span>` : ""}
    ${edited ? `<p class="muted small">Last edit that restarted learning: ${esc(when(edited.toISOString()))}.</p>` : ""}
    ${s.targeting_summary ? `<p class="small"><b>Who sees it:</b> ${esc(s.targeting_summary)}</p>` : ""}
    <p class="muted small" id="estimate"></p></div></section>`;
}

function render() {
  const e = data.entity;
  const canControl = e.can_control ?? data.campaign.can_control;
  $("en-title").textContent = e.name;
  document.title = `${e.name} | Edge Bourne Ads`;
  $("en-sub").innerHTML = `${statusCell({ ...e, level: LEVEL })} <span class="sep-dot">·</span> ${esc(data.range.label)}${state.vs && data.prev_range ? ` vs ${esc(data.prev_range.label)}` : ""}`;
  const budget = e.daily_budget_cents ? (canControl ? `<button type="button" class="chip" data-budget="${LEVEL}:${e.id}" data-current="${e.daily_budget_cents}" data-name="${esc(e.name)}">${money(e.daily_budget_cents, { exact: true })}/day</button>` : `<span class="chip">${money(e.daily_budget_cents, { exact: true })}/day</span>`) : "";
  $("en-actions").innerHTML = `${budget}
    ${me.role === "admin" ? (LEVEL === "campaign" ? `<a class="btn" href="/new-adset.html?campaign=${encodeURIComponent(e.id)}">${icon("plus")}New ad set</a>` : `<a class="btn" href="/new-ad.html?adset=${encodeURIComponent(e.id)}">${icon("plus")}New ad</a>`) : ""}
    ${me.role === "admin" ? `<a class="btn btn-claude-outline" href="/desk.html?ask=1&campaign=${encodeURIComponent(data.campaign.id)}">${icon("spark")}Ask Claude</a>` : ""}
    ${canControl && ["ACTIVE", "PAUSED"].includes(e.status) ? `<span class="pk-sw">${switchHtml(e.status === "ACTIVE", `data-toggle="${LEVEL}:${e.id}" data-name="${esc(e.name)}"`, `${e.name} on or off`)} ${e.status === "ACTIVE" ? "On" : "Off"}</span>` : ""}`;
  const tabs = [...(LEVEL === "campaign" ? [["adsets", "Ad sets", rows.adset.length]] : []), ["ads", "Ads", rows.ad.length], ["history", "History", data.timeline.length]];
  const list = children();
  const body = state.tab === "history"
    ? `<section class="panel"><div class="panel-body">${data.timeline.length ? `<ol class="tl">${data.timeline.map((i) => `<li class="tl-${i.tone || "n"}"><span class="tl-dot"></span><span class="tl-w">${esc(when(i.at))}</span><span class="tl-t"><b>${esc(i.title)}</b>${i.sub ? `<small>${esc(i.sub)}</small>` : ""}${i.by ? `<small>${esc(i.by)}</small>` : ""}</span></li>`).join("")}</ol>` : '<p class="muted">Nothing recorded yet.</p>'}</div></section>`
    : list.length && narrow() ? listHtml({ rows: list.map((r) => (state.vs ? r : { ...r, prev: null })), selected, sort: state.sort, dir: state.dir })
    : list.length ? tableHtml({ level: childLevel(), rows: list.map((r) => (state.vs ? r : { ...r, prev: null })), cols: "results", sort: state.sort, dir: state.dir, selected, selectable: true })
    : `<div class="panel empty"><h3>Nothing here yet</h3><p>${LEVEL === "campaign" ? "This campaign has no ad sets." : "This ad set has no ads."}</p></div>`;
  $("cr-all").innerHTML = `${figuresHtml(e.m, state.vs ? e.prev : null, data.target_qualified_cents)}
    <div class="charts"><section class="panel"><div class="panel-head"><h2>Spend per day</h2></div><div class="chart" id="c-spend"></div></section>
      <section class="panel"><div class="panel-head"><h2>Leads per day</h2></div><div class="chart" id="c-leads"></div></section></div>
    ${LEVEL === "adset" ? learningCard(e) : ""}
    <div class="cr-toolbar"><div class="tabs-inline" role="tablist">${tabs.map(([k, l, n]) => `<button type="button" role="tab" class="view-chip" data-tab="${k}" aria-selected="${state.tab === k}">${l}<span>${n}</span></button>`).join("")}</div>
      <span class="spacer"></span>
      <select class="input tool" id="range-pick" aria-label="Dates">${RANGES.map(([k, l]) => `<option value="${k}" ${k === state.range ? "selected" : ""}>${l}</option>`).join("")}</select>
      <button type="button" class="tool-tg" id="vs" aria-pressed="${state.vs}">vs before</button></div>
    ${body}
    <p class="muted small flush">Complete days only (${esc(dayLabel(data.range.start))} to ${esc(dayLabel(data.range.end))}).</p>`;
  document.querySelectorAll("#cr-all [data-w]").forEach((i) => { i.style.width = `${i.dataset.w}%`; });
  columnChart({ el: $("c-spend"), series: data.series, key: "spend_cents", color: "var(--chart-spend)", title: "Spend per day", height: 170,
    format: (v) => money(v, { exact: true }), axisFormat: (v) => `$${Math.round(v / 100)}` });
  columnChart({ el: $("c-leads"), series: data.series, key: "leads", color: "var(--chart-leads)", title: "Leads per day", integer: true, height: 170,
    format: (v) => `${v} lead${v === 1 ? "" : "s"}`, axisFormat: (v) => String(Math.round(v)) });
  if (LEVEL === "adset" && $("estimate")) api(`/api/insights/adset/${encodeURIComponent(e.id)}/estimate`).then((x) => { if (x.lower && x.upper) $("estimate").textContent = `Meta estimates ${count(x.lower)}–${count(x.upper)} people could see these ads.`; }).catch(() => {});
  $("bulk").innerHTML = bulkBarHtml(childLevel(), picked(), canControl);
  document.body.classList.toggle("has-bulk", selected.size > 0);
}

async function load() {
  try {
    data = await api(`/api/${LEVEL === "campaign" ? "campaigns" : "adsets"}/${encodeURIComponent(id)}?range=${encodeURIComponent(state.range)}${state.vs ? "&vs=prev" : ""}`);
  } catch (err) {
    $("cr-all").innerHTML = `<section class="panel empty"><h3>Not found</h3><p>${esc(err.message)}</p><a class="btn" href="/ads.html">Back to Ads</a></section>`;
    return;
  }
  rows = flatten({ campaigns: data.campaigns });
  if (LEVEL === "adset") { rows.ad = rows.ad.filter((a) => a.adset.id === id); rows.adset = rows.adset.filter((s) => s.id === id); }
  data.entity = LEVEL === "campaign" ? rows.campaign[0] : rows.adset[0];
  setCrumbs([{ label: "Ads", href: "/ads.html" },
    ...(LEVEL === "adset" ? [{ label: data.campaign.name, href: `/campaign.html?id=${encodeURIComponent(data.campaign.id)}` }] : []),
    { label: data.entity.name, href: location.pathname + location.search }]);
  render();
}

const set = (patch, reload = false) => { state = { ...state, ...patch }; UrlState.write(state, { ...DEFAULTS, id }); if (reload) load(); else render(); };

me = await boot({ page: LEVEL });
if (me) {
  const ctx = {
    reload: () => { selected.clear(); load(); }, level: childLevel, range: () => state.range, picked,
    clear: () => { selected.clear(); render(); },
    pick: (rid, on) => { if (on) selected.add(rid); else selected.delete(rid); render(); },
    pickAll: (on) => { children().forEach((r) => (on ? selected.add(r.id) : selected.delete(r.id))); render(); },
    sortBy: (key) => set({ sort: key, dir: state.sort === key && state.dir === "desc" ? "asc" : "desc" }),
    peek: (key) => { const [lv, rid] = key.split(":"); const r = (rows[lv] || []).find((x) => x.id === rid); if (r) peek(r, { onClose: (changed) => { if (changed) load(); } }); },
  };
  wire($("cr-all"), ctx);
  wire($("bulk"), ctx);
  wire($("en-actions"), ctx);
  $("cr-all").addEventListener("click", (e) => {
    const t = e.target.closest("[data-tab]");
    if (t) { selected.clear(); closePeek(); set({ tab: t.dataset.tab, sort: "spend", dir: "desc" }); }
    if (e.target.closest("#vs")) set({ vs: !state.vs }, true);
  });
  $("cr-all").addEventListener("change", (e) => { if (e.target.id === "range-pick") set({ range: e.target.value }, true); });
  onRefresh(load);
  load();
}
