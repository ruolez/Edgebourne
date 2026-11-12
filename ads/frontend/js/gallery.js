// Creative › Gallery (UX-AUDIT 9.5): every ad as people see it with what it earned, copies of one ad as one
// card (backend/gallery.py). Views Top, Just launched and Tired; filters by status, idea tag and the shared
// dates; Compare from the cards picked (each card's top-spending ad). Everything is in the URL.
import { api, startLoad } from "./api.js";
import { boot, emptyState, entityLink, esc, icon, onRefresh, rememberList, showLoadError, withFrom } from "./ui.js";
import { EXPLAIN, RANGES, WORDS, count, dayLabel, money, rangeSelect, rememberRange, sharedRange, statusOf } from "./format.js";
import * as UrlState from "./urlstate.js";
import { track, trackLegend } from "./manager.js";

const $ = (id) => document.getElementById(id);
const DEFAULTS = { view: "top", status: "", dim: "", tag: "", range: "7" };
const KEEP = { ...DEFAULTS, range: "" };  // links and the way back always carry the dates
const VIEWS = [["top", "Top"], ["launched", "Just launched"], ["tired", "Tired"]];
const STATUSES = [["", "Any status"], ["delivering", "Delivering"], ["review", "In review"], ["problem", "Rejected or has a problem"], ["off", "Off"], ["deleted", "Deleted"]];
const SHOWN_TAGS = ["hook", "angle"];
const MAX_COMPARE = 6;

let state = UrlState.read(DEFAULTS);
if (!new URLSearchParams(location.search).has("range")) state.range = sharedRange(state.range);
if (!RANGES.some(([k]) => k === state.range)) state.range = DEFAULTS.range;
let data = null, me = null;
const picked = new Map();  // card key → its card, kept across filters while the card is still shown

const listHere = () => { const q = UrlState.query(state, KEEP); return `/gallery.html${q ? `?${q}` : ""}`; };
function save() {
  UrlState.write(state, KEEP);
  rememberList(listHere());
  const add = $("gal-new");
  if (add) add.href = withFrom("/new-ad.html", listHere());
}

function set(patch) {
  state = { ...state, ...patch };
  save();
  load();
}

const tagKey = (dim, value) => `${dim}:${value}`;
function tagPick(d) {
  const groups = Object.entries(d.known).filter(([, values]) => values.length);
  if (!groups.length && !d.tag) return "";
  const now = state.dim && state.tag ? tagKey(state.dim, state.tag) : "";
  const options = groups.map(([dim, values]) => `<optgroup label="${esc(d.dimensions[dim])}">${values.map((v) => `<option value="${esc(tagKey(dim, v))}" ${tagKey(dim, v) === now ? "selected" : ""}>${esc(v)}</option>`).join("")}</optgroup>`).join("");
  return `<select class="input tool" id="tag-pick" aria-label="Idea"><option value="">Every idea</option>${options}</select>`;
}
function statusPick(d) {
  return `<select class="input tool" id="status-pick" aria-label="Status">${STATUSES.map(([k, label]) => `<option value="${k}" ${k === state.status ? "selected" : ""}>${esc(label)}${k === "deleted" && d.deleted ? ` (${d.deleted})` : ""}</option>`).join("")}</select>`;
}

function viewNote(d) {
  if (state.view === "launched") return `<p class="note">Ads that started showing in the last ${d.launch_days} days, newest first. Too early to judge until one has 3 leads and has spent twice your target cost per lead.</p>`;
  if (state.view === "tired") {
    if (!d.fatigue_on) {
      const where = me.role === "admin" ? '<a href="/settings.html#alerts">Settings › Alerts</a>' : "Settings › Alerts";
      return `<p class="note warn">The tired check is switched off in ${where}, so nothing is marked tired here.</p>`;
    }
    return '<p class="note">Ads people have seen too often: each person sees them more and more while clicks fall and costs rise. The same check sends the "looks tired" alert.</p>';
  }
  return '<p class="muted small flush">Cheapest cost per lead first among ads with enough to judge (3 leads and twice your target spent); the rest follow by what they spent.</p>';
}

function copiesLine(g) {
  if (g.ads.length < 2) return "";
  const first = g.ads.slice(0, 3).map((a) => entityLink("ad", a.id, a.name)).join(", ");
  const more = g.ads.length > 3 ? ` and ${g.ads.length - 3} more` : "";
  return `<p class="gal-copies">Runs as ${count(g.ads.length)} ads: ${first}${more}</p>`;
}

// Every copy's hook and angle, each once, so the idea being filtered on is always on the card.
const cardTags = (g) => g.tags_all.filter(([dim]) => SHOWN_TAGS.includes(dim)).sort(([a], [b]) => SHOWN_TAGS.indexOf(a) - SHOWN_TAGS.indexOf(b));

function copyNotes(g) {
  const lines = [];
  if (g.problems) lines.push(`<p class="gal-copies bad-text">${count(g.problems)} ${g.problems === 1 ? "copy is" : "copies are"} rejected or ${g.problems === 1 ? "has" : "have"} a problem</p>`);
  if (g.in_review) lines.push(`<p class="gal-copies">${count(g.in_review)} ${g.in_review === 1 ? "copy is" : "copies are"} waiting for Meta's review</p>`);
  if (g.version_since) {
    lines.push(`<p class="gal-copies gal-since">Changed on ${esc(dayLabel(g.version_since))}: numbers and bars count only the days it showed this version.
      <a href="/ad.html?id=${encodeURIComponent(g.version_ad)}#fold=versions">See versions</a></p>`);
  }
  if (g.just_launched && g.launched_on) lines.push(`<p class="gal-copies gal-started">Started ${esc(dayLabel(g.launched_on))}</p>`);
  return lines.join("");
}

function card(g) {
  const [cls, label] = statusOf(g.effective_status);
  const sel = picked.has(g.key);
  const tags = cardTags(g).map(([dim, value]) => {
    const on = state.dim === dim && state.tag === value;
    return `<button type="button" class="chip gal-tag" data-tag="${esc(tagKey(dim, value))}" aria-pressed="${on}" title="${on ? "Show every idea again" : `Only ads with this ${esc(data.dimensions[dim].toLowerCase())}`}">${esc(value)}</button>`;
  }).join("");
  const cpl = g.cpl_cents == null ? "—" : money(g.cpl_cents, { exact: true });
  return `<article class="cr-card gal-card${sel ? " is-picked" : ""}${g.bucket === "problem" ? " has-issue" : ""}" data-key="${esc(g.key)}">
    <a class="cr-media" href="/ad.html?id=${encodeURIComponent(g.top_ad_id)}" aria-label="Open ${esc(g.name)}">
      ${g.image_url ? `<img src="${esc(g.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '<span class="ph"></span>'}
      ${g.kind === "video" ? `<span class="play">${icon("play")}</span>` : ""}</a>
    <label class="gal-tick"><input type="checkbox" data-pick="${esc(g.key)}" aria-label="Select ${esc(g.name)}" ${sel ? "checked" : ""}></label>
    <div class="cr-body">
      ${entityLink("ad", g.top_ad_id, g.name, { cls: "cr-name" })}
      ${copiesLine(g)}
      <div class="gal-status">${track(g)}<span class="pill ${cls}">${esc(label)}</span>${g.tired ? '<span class="pill warn">Tired</span>' : ""}</div>
      ${copyNotes(g)}
      <div class="gal-kpi"><span>${WORDS.cpl}</span><b class="${g.enough ? "" : "early"}"${g.enough ? "" : ' title="Fewer than 3 leads or less than twice your target spent: too early to judge"'}>${cpl}</b>${g.enough ? "" : '<span class="pill">Too early</span>'}</div>
      <dl class="cr-stats gal-stats"><div><dt>${WORDS.spend}</dt><dd>${money(g.spend_cents, { exact: true })}</dd></div><div><dt>${WORDS.leads}</dt><dd>${count(g.leads)}</dd></div>
        ${g.kind === "video" ? `<div title="${esc(EXPLAIN.hook)}"><dt>${WORDS.hook}</dt><dd>${g.hook_rate == null ? "—" : `${(g.hook_rate * 100).toFixed(1)}%`}</dd></div>` : ""}</dl>
      ${tags ? `<div class="chips gal-tags">${tags}</div>` : ""}
    </div></article>`;
}

function trayHtml() {
  if (!picked.size) return "";
  const list = [...picked.values()];
  const n = list.length;
  const ok = n >= 2 && n <= MAX_COMPARE;
  const film = list.slice(0, MAX_COMPARE).map((g) => (g.image_url ? `<img class="tbl-th" src="${esc(g.image_url)}" alt="" referrerpolicy="no-referrer">` : '<span class="tbl-th"></span>')).join("");
  const why = ok ? "" : `<span class="gal-why" id="gal-why">${n < 2 ? `Pick 2 to ${MAX_COMPARE} to compare` : `Compare takes ${MAX_COMPARE} at most`}</span>`;
  return `<div class="bk" role="toolbar" aria-label="${n} selected"><span class="bk-n"><b>${n}</b> selected</span><span class="bk-film">${film}</span>
    <span class="bk-acts">${why}<button type="button" class="btn btn-primary btn-small" data-tray="compare" ${ok ? "" : 'disabled aria-describedby="gal-why"'}>${icon("compare")}<span>Compare</span></button></span>
    <button type="button" class="icon-btn bk-x" data-tray="clear" aria-label="Clear the selection">×</button></div>`;
}

// The tray sits over the bottom of the page, so the page gets room below its last row while it shows.
function drawTray() {
  $("gal-tray").innerHTML = trayHtml();
  document.body.classList.toggle("has-bulk", picked.size > 0);
}

function render() {
  const d = data;
  const filtered = state.status || (state.dim && state.tag);
  const chips = VIEWS.map(([k, label]) => `<button type="button" class="view-chip" data-gview="${k}" aria-pressed="${state.view === k}">${label}<span>${count(d.counts[k])}</span></button>`).join("");
  const toolbar = `<div class="cr-toolbar gal-bar"><div class="views" role="group" aria-label="Show">${chips}</div><span class="spacer"></span>
    ${statusPick(d)}${tagPick(d)}${rangeSelect("range-pick", state.range)}</div>
    <p class="muted small flush gal-when">${esc(d.range.label)} · complete days${d.groups.length ? ` · ${count(d.groups.length)} ${d.groups.length === 1 ? "card" : "cards"}` : ""}</p>`;
  let body;
  if (!d.groups.length) {
    const clear = filtered ? '<button type="button" class="btn" data-clear-filters>Clear filters</button>' : "";
    const add = me.role !== "client" ? `<a class="btn btn-primary" href="${esc(withFrom("/new-ad.html", listHere()))}">New ad</a>` : "";
    const empty = !d.total ? { title: "No ads to show yet", body: "Ads show here once they deliver or spend in the dates picked.", actions: add }
      : state.view === "tired" ? { title: "Nothing looks tired", body: d.fatigue_on ? "No ad shows the signs right now." : "The tired check is off.", actions: clear }
      : state.view === "launched" ? { title: `Nothing started in the last ${d.launch_days} days`, body: "New ads show here from the day they first spend.", actions: clear }
      : { title: "Nothing matches", body: "No ad has this status or idea in these dates.", actions: clear };
    body = emptyState({ ...empty, variant: "center" });
  } else {
    body = `<div class="cr-grid gal-grid">${d.groups.map(card).join("")}</div>${d.groups.some((g) => g.track.length) ? trackLegend() : ""}`;
  }
  $("gal").innerHTML = `${toolbar}${viewNote(d)}${body}`;
  drawTray();
}

async function load() {
  const superseded = startLoad("gallery");
  const q = new URLSearchParams({ view: state.view, range: state.range });
  if (state.status) q.set("status", state.status);
  if (state.dim && state.tag) { q.set("dim", state.dim); q.set("tag", state.tag); }
  let d;
  try { d = await api(`/api/gallery?${q}`); } catch (err) { if (!superseded()) showLoadError($("gal"), err, load); return; }
  if (superseded()) return;
  data = d;
  const shown = new Map(d.groups.map((g) => [g.key, g]));
  for (const key of [...picked.keys()]) { if (shown.has(key)) picked.set(key, shown.get(key)); else picked.delete(key); }
  render();
}

me = await boot({ page: "gallery" });
if (me) {
  if (me.role !== "client") {
    $("gal-new").innerHTML = `${icon("plus")}<span>New ad</span>`;
    $("gal-new").hidden = false;
  }
  save();
  const root = $("gal");
  root.addEventListener("click", (e) => {
    const v = e.target.closest("[data-gview]");
    if (v) { if (v.dataset.gview !== state.view) set({ view: v.dataset.gview }); return; }
    const t = e.target.closest("[data-tag]");
    if (t) {
      const [dim, ...rest] = t.dataset.tag.split(":");
      const tag = rest.join(":");
      set(state.dim === dim && state.tag === tag ? { dim: "", tag: "" } : { dim, tag });
      return;
    }
    if (e.target.closest("[data-clear-filters]")) set({ status: "", dim: "", tag: "" });
  });
  root.addEventListener("change", (e) => {
    const pick = e.target.closest("[data-pick]");
    if (pick) {
      const g = data.groups.find((x) => x.key === pick.dataset.pick);
      if (pick.checked && g) picked.set(g.key, g); else picked.delete(pick.dataset.pick);
      pick.closest(".gal-card")?.classList.toggle("is-picked", pick.checked);
      drawTray();
      return;
    }
    if (e.target.id === "range-pick") { rememberRange(e.target.value); set({ range: e.target.value }); }
    if (e.target.id === "status-pick") set({ status: e.target.value });
    if (e.target.id === "tag-pick") {
      const [dim, ...rest] = e.target.value.split(":");
      set(e.target.value ? { dim, tag: rest.join(":") } : { dim: "", tag: "" });
    }
  });
  $("gal-tray").addEventListener("click", (e) => {
    const b = e.target.closest("[data-tray]");
    if (!b) return;
    if (b.dataset.tray === "clear") { picked.clear(); render(); return; }
    const ids = [...picked.values()].map((g) => g.top_ad_id);
    location.href = `/compare.html?ids=${ids.map(encodeURIComponent).join(",")}&range=${encodeURIComponent(state.range)}&vs=1`;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && picked.size && !document.querySelector("dialog[open]")) { picked.clear(); render(); }
  });
  addEventListener("popstate", () => { state = UrlState.read(DEFAULTS); load(); });
  onRefresh(load);
  load();
}
