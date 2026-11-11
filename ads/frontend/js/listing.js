// Ads page: the manager table at three levels with views, saved views, range + "vs before",
// columns, search, selection → bulk bar / compare, and a peek drawer. Everything is in the URL.
import { api } from "./api.js";
import { boot, confirmDialog, esc, icon, onRefresh, toast, showLoadError } from "./ui.js";
import { count, dayLabel } from "./format.js";
import * as UrlState from "./urlstate.js";
import { COLUMN_SETS, LEVEL_WORDS, VIEWS, bulkBarHtml, cardsHtml, closePeek, figuresHtml, flatten, listHtml, narrow, peek, tableHtml, wire } from "./manager.js";

const $ = (id) => document.getElementById(id);
const DEFAULTS = { level: "ad", view: "all", range: "7", vs: true, cols: "results", sort: "spend", dir: "desc", q: "", campaign: "", archived: false, display: "table", peek: "" };
const RANGES = [["7", "7 days"], ["14", "14 days"], ["30", "30 days"], ["mtd", "This month"], ["lastmonth", "Last month"]];
// One-time move of the old saved preferences into the URL defaults.
try {
  const old = JSON.parse(localStorage.getItem("ebads-adsview") || "null");
  if (old && !location.search) { if (old.view === "cards") DEFAULTS.display = "cards"; localStorage.removeItem("ebads-adsview"); }
  const r = localStorage.getItem("ebads-range");
  if (r && RANGES.some(([k]) => k === r)) DEFAULTS.range = r;
} catch (e) { /* storage off */ }
let state = UrlState.read(DEFAULTS);
let data = null, rows = null, me = null, saved = [];
const selected = new Set();
let lastPicked = null;

const save = () => UrlState.write(state, DEFAULTS);

function visibleRows() {
  const all = rows[state.level] || [];
  const fn = (VIEWS[state.view] || VIEWS.all)[1];
  const q = state.q.trim().toLowerCase();
  return all.filter((r) => fn(r) && (!state.campaign || (r.level === "campaign" ? r.id : r.campaign?.id) === state.campaign)
    && (!q || r.name.toLowerCase().includes(q) || (r.adset?.name || "").toLowerCase().includes(q)));
}

function picked() { return (rows[state.level] || []).filter((r) => selected.has(r.id)); }

function headerFigures() {
  const camps = (rows.campaign || []).filter((c) => !state.campaign || c.id === state.campaign);
  const sum = (key, which) => camps.reduce((n, c) => n + ((c[which] || {})[key] || 0), 0);
  const keys = ["spend_cents", "leads", "qualified", "impressions", "reach", "link_clicks", "video_3s", "thruplays"];
  const m = Object.fromEntries(keys.map((k) => [k, sum(k, "m")]));
  const prev = state.vs && data.prev_range ? Object.fromEntries(keys.map((k) => [k, sum(k, "prev")])) : null;
  // People: unique across the whole account from Meta, not the campaigns added up.
  if (!state.campaign && data.reach_total != null) m.reach = data.reach_total;
  if (prev && !state.campaign && data.prev_reach_total != null) prev.reach = data.prev_reach_total;
  const camp = state.campaign ? camps[0] : null;
  return figuresHtml(m, prev, data.target_qualified_cents, camp ? { today: camp.today, ever: camp.ever } : { today: data.today_total, ever: data.ever_total });
}

function toolbar() {
  const level = rows[state.level] || [];
  const views = Object.entries(VIEWS).map(([k, [label, fn]]) => {
    const n = level.filter(fn).length;
    if (k !== "all" && k !== state.view && !n) return "";
    return `<button type="button" class="view-chip" data-view="${k}" aria-pressed="${state.view === k}">${label}<span>${n}</span></button>`;
  }).join("");
  const mine = saved.map((v) => `<span class="sv"><button type="button" class="view-chip" data-saved="${v.id}" aria-pressed="${location.search.replace(/^\?/, "") === v.query}">${esc(v.name)}</button>${v.mine ? `<button type="button" class="sv-x" data-unsave="${v.id}" aria-label="Remove the view ${esc(v.name)}">×</button>` : ""}</span>`).join("");
  const camps = rows.campaign || [];
  return `<div class="cr-toolbar">
    <div class="views" role="group" aria-label="Show">${views}${mine}<button type="button" class="view-chip add" id="save-view">${icon("plus")}Save view</button></div>
    <span class="spacer"></span>
    ${camps.length > 1 ? `<select class="input tool" id="camp-pick" aria-label="Campaign"><option value="">All campaigns</option>${camps.map((c) => `<option value="${esc(c.id)}" ${c.id === state.campaign ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>` : ""}
    <label class="tool-search">${icon("search")}<input class="input" id="cr-search" type="search" placeholder="Filter by name" value="${esc(state.q)}" aria-label="Filter by name"></label>
    <select class="input tool" id="range-pick" aria-label="Dates">${RANGES.map(([k, l]) => `<option value="${k}" ${k === state.range ? "selected" : ""}>${l}</option>`).join("")}</select>
    <button type="button" class="tool-tg" id="vs" aria-pressed="${state.vs}" title="Compare with the same number of days before">vs before</button>
    ${state.display === "table" ? `<select class="input tool" id="cols-pick" aria-label="Columns">${Object.entries(COLUMN_SETS).map(([k, [l]]) => `<option value="${k}" ${k === state.cols ? "selected" : ""}>Columns: ${l}</option>`).join("")}</select>` : ""}
    ${data.archived ? `<button type="button" class="tool-tg" id="archived" aria-pressed="${state.archived}">${state.archived ? "Hide" : "Show"} archived <span class="n">${data.archived}</span></button>` : ""}
    ${state.level === "ad" ? `<div class="segmented icon-seg" role="group" aria-label="Display">
      <button type="button" data-display="table" aria-pressed="${state.display === "table"}" title="Table">${icon("table")}<span class="sr-only">Table</span></button>
      <button type="button" data-display="cards" aria-pressed="${state.display === "cards"}" title="Cards">${icon("grid")}<span class="sr-only">Cards</span></button></div>` : ""}
  </div>`;
}

function render() {
  const canControl = me.role !== "client";
  document.querySelectorAll("#level [data-level]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.level === state.level)));
  $("cr-sub").textContent = `${count((rows.campaign || []).length)} ${(rows.campaign || []).length === 1 ? "campaign" : "campaigns"} · ${count((rows.adset || []).length)} ad sets · ${count((rows.ad || []).length)} ads · ${data.range.label}${state.vs && data.prev_range ? ` vs ${data.prev_range.label}` : ""}`;
  if (!data.campaigns.length) {
    $("cr-all").innerHTML = `<section class="panel empty"><h3>No ads yet</h3><p>Once Meta is connected in Settings, your campaigns, ad sets and ads appear here.</p></section>`;
    return;
  }
  const list = visibleRows();
  const body = !list.length ? `<div class="panel empty"><h3>Nothing here</h3><p>No ${LEVEL_WORDS[state.level][1]} match “${esc((VIEWS[state.view] || VIEWS.all)[0])}”${state.q ? ` and “${esc(state.q)}”` : ""}.</p></div>`
    : state.level === "ad" && state.display === "cards" ? cardsHtml(list)
    : narrow() ? listHtml({ rows: list.map((r) => (state.vs ? r : { ...r, prev: null })), selected, sort: state.sort, dir: state.dir })
    : tableHtml({ level: state.level, rows: list.map((r) => (state.vs ? r : { ...r, prev: null })), cols: state.cols, sort: state.sort, dir: state.dir, selected, selectable: true });
  $("cr-all").innerHTML = buildsNote() + headerFigures() + toolbar() + body
    + `<p class="muted small flush cr-foot">Complete days only (${esc(dayLabel(data.range.start))} to ${esc(dayLabel(data.range.end))}); today is left out because Meta reports late. Click a row for a quick look.</p>`;
  if (state.level === "campaign" && me.role === "admin") {
    document.querySelectorAll('#cr-all tr[data-row^="campaign:"] .c-name small').forEach((sm) => {
      const id = sm.closest("tr").dataset.row.split(":")[1];
      sm.insertAdjacentHTML("afterend", `<a class="campaign-add" href="/new-adset.html?campaign=${encodeURIComponent(id)}">+ New ad set</a>`);
    });
  }
  const all = document.querySelector("#cr-all [data-all]");
  if (all && all.dataset.mixed) all.indeterminate = true;
  $("bulk").innerHTML = bulkBarHtml(state.level, picked(), canControl);
  document.body.classList.toggle("has-bulk", selected.size > 0);
}

async function loadSaved() {
  try { saved = (await api("/api/views?page=ads")).views; } catch (e) { saved = []; }
}

let openBuilds = [];
async function loadOpenBuilds() {
  if (me.role !== "admin") return;
  try { openBuilds = (await api("/api/builds/open")).items; } catch (e) { openBuilds = []; }
}
const buildsNote = () => (openBuilds.length ? `<p class="note">Not finished: ${openBuilds.map((b) => `<a href="/new-campaign.html?build=${b.id}">${esc(b.name || "Untitled campaign")}</a>`).join(", ")}. Open to finish or publish.</p>` : "");

async function load() {
  try {
    data = await api(`/api/ads?range=${encodeURIComponent(state.range)}${state.vs ? "&vs=prev" : ""}${state.archived ? "&archived=1" : ""}`);
  } catch (err) { showLoadError($("cr-all"), err, load); return; }
  rows = flatten(data);
  for (const id of [...selected]) if (!(rows[state.level] || []).some((r) => r.id === id)) selected.delete(id);
  render();
  if (state.peek) openPeek(state.peek);
}

function openPeek(key) {
  const [level, id] = key.split(":");
  const r = (rows[level] || []).find((x) => x.id === id);
  if (!r) return;
  state.peek = key; save();
  document.querySelectorAll("#cr-all tr.is-peek").forEach((tr) => tr.classList.remove("is-peek"));
  document.querySelector(`#cr-all [data-row="${CSS.escape(key)}"]`)?.classList.add("is-peek");
  peek(r, { onClose: (changed) => { state.peek = ""; save(); document.querySelectorAll("#cr-all .is-peek").forEach((tr) => tr.classList.remove("is-peek")); if (changed) load(); } });
}

function set(patch, reload = false) {
  state = { ...state, ...patch };
  save();
  if (reload) load(); else render();
}

me = await boot({ page: "ads" });
if (me) {
  $("new-ad").innerHTML = `${icon("plus")}<span>New ad</span>`;
  $("new-menu").hidden = me.role !== "admin";
  $("level").addEventListener("click", (e) => {
    const b = e.target.closest("[data-level]");
    if (!b || b.dataset.level === state.level) return;
    selected.clear(); closePeek();
    set({ level: b.dataset.level, sort: "spend", dir: "desc", display: b.dataset.level === "ad" ? state.display : "table" });
  });
  const root = $("cr-all");
  wire(root, {
    reload: load,
    level: () => state.level,
    range: () => state.range,
    picked,
    clear: () => { selected.clear(); render(); },
    pick: (id, on, shift) => {
      const list = visibleRows().map((r) => r.id);
      if (shift && lastPicked && list.includes(lastPicked)) {
        const [a, b] = [list.indexOf(lastPicked), list.indexOf(id)].sort((x, y) => x - y);
        list.slice(a, b + 1).forEach((x) => (on ? selected.add(x) : selected.delete(x)));
      } else if (on) selected.add(id); else selected.delete(id);
      lastPicked = id;
      render();
    },
    pickAll: (on) => { visibleRows().forEach((r) => (on ? selected.add(r.id) : selected.delete(r.id))); render(); },
    sortBy: (key) => set({ sort: key, dir: state.sort === key && state.dir === "desc" ? "asc" : "desc" }),
    peek: (key) => (state.peek === key ? closePeek() : openPeek(key)),
  });
  wire($("bulk"), { reload: () => { selected.clear(); load(); }, level: () => state.level, range: () => state.range, picked, clear: () => { selected.clear(); render(); }, pick() {}, pickAll() {}, sortBy() {}, peek() {} });
  root.addEventListener("click", async (e) => {
    const v = e.target.closest("[data-view]");
    if (v) { selected.clear(); set({ view: v.dataset.view }); return; }
    const d = e.target.closest("[data-display]");
    if (d) { set({ display: d.dataset.display }); return; }
    if (e.target.closest("#vs")) { set({ vs: !state.vs }, true); return; }
    if (e.target.closest("#archived")) { set({ archived: !state.archived }, true); return; }
    const sv = e.target.closest("[data-saved]");
    if (sv) {
      const view = saved.find((x) => String(x.id) === sv.dataset.saved);
      history.replaceState(null, "", `${location.pathname}?${view.query}`);
      state = UrlState.read(DEFAULTS); selected.clear(); load(); return;
    }
    const un = e.target.closest("[data-unsave]");
    if (un) {
      try { await api(`/api/views/${un.dataset.unsave}`, { method: "DELETE" }); await loadSaved(); render(); } catch (err) { toast(err.message, "bad"); }
      return;
    }
    if (e.target.closest("#save-view")) {
      const name = await confirmDialog({ title: "Save this view", confirm: "Save",
        body: "<p>Keeps the level, filter, dates and columns you see now, so you can come back in one click.</p>",
        field: { label: "Name", value: (VIEWS[state.view] || VIEWS.all)[0] + (state.q ? ` · ${state.q}` : ""), validate: (x) => (x.trim() ? null : "Give it a name") } });
      if (!name) return;
      try { await api("/api/views", { method: "POST", body: { page: "ads", name: name.trim(), query: UrlState.query(state, DEFAULTS) } }); await loadSaved(); render(); toast("View saved"); }
      catch (err) { toast(err.message, "bad"); }
    }
  });
  root.addEventListener("change", (e) => {
    if (e.target.id === "range-pick") { try { localStorage.setItem("ebads-range", e.target.value); } catch (err) {} set({ range: e.target.value }, true); }
    if (e.target.id === "cols-pick") set({ cols: e.target.value });
    if (e.target.id === "camp-pick") { selected.clear(); set({ campaign: e.target.value }); }
  });
  let typing;
  root.addEventListener("input", (e) => {
    if (e.target.id !== "cr-search") return;
    clearTimeout(typing);
    typing = setTimeout(() => {
      const pos = e.target.selectionStart;
      set({ q: e.target.value });
      const input = $("cr-search"); input.focus(); input.setSelectionRange(pos, pos);
    }, 180);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && selected.size && !document.querySelector("dialog[open]")) { selected.clear(); render(); }
  });
  let wasNarrow = narrow();
  addEventListener("resize", () => { if (narrow() !== wasNarrow && rows) { wasNarrow = narrow(); render(); } });
  onRefresh(load);
  await loadSaved();
  load();
}
