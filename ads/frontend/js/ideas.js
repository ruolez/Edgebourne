// Creative › Ideas (UX-AUDIT 9.5): the ads' idea tags (hook, angle, who it's for, format, offer) as groups, each
// with the pictures of its biggest spenders and what it earned (GET /api/concepts, pure backend/concepts.py). A group
// is judged only with 3 leads and twice the target cost spent; the cheapest judged one says how sure that is. A
// group links to the Gallery filtered on it. ?by=&range=&tag= (a tag named elsewhere marks its group).
import { api, startLoad } from "./api.js";
import { boot, emptyState, entityLink, esc, onRefresh, rememberList, showLoadError } from "./ui.js";
import { EXPLAIN, RANGES, WORDS, count, money, rangeSelect, rememberRange, sharedRange } from "./format.js";
import * as UrlState from "./urlstate.js";

const $ = (id) => document.getElementById(id);
const DIMS = [["hook", "Hook"], ["angle", "Angle"], ["persona", "Who it's for"], ["format", "Format"], ["offer", "Offer"]];
const DEFAULTS = { by: "hook", range: "30", tag: "" };
const KEEP = { ...DEFAULTS, range: "" };  // the address always carries the dates
const UNTAGGED = "Not tagged";
const PICTURES = 6;
const NAMES = 4;

let state = UrlState.read(DEFAULTS);
if (!new URLSearchParams(location.search).has("range")) state.range = sharedRange(DEFAULTS.range);
if (!RANGES.some(([k]) => k === state.range)) state.range = DEFAULTS.range;
if (!DIMS.some(([k]) => k === state.by)) state.by = DEFAULTS.by;
let me = null;
let marked = false;  // the tag from the address has been scrolled to once

const ratePct = (v) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
const sameTag = (a, b) => a.toLowerCase() === b.toLowerCase();
const galleryHref = (value) => `/gallery.html?${new URLSearchParams({ dim: state.by, tag: value, range: state.range })}`;

function save() {
  UrlState.write(state, KEEP);
  const kept = UrlState.query({ ...state, tag: "" }, KEEP);
  rememberList(`/ideas.html${kept ? `?${kept}` : ""}`);
}

function set(patch) {
  state = { ...state, ...patch };
  save();
  load();
}

function verdict(d) {
  const best = d.groups.find((g) => g.best);
  const what = DIMS.find(([k]) => k === d.by)[1].toLowerCase();
  if (!best) return `<p class="note">Too early to say which ${esc(what)} works best: each group needs 3 or more leads and twice the target cost in spend.</p>`;
  return d.best_is_clear ? `<p class="note ok"><b>${esc(best.value)}</b> brings the cheapest leads, ${d.best_confidence}% sure.</p>`
    : `<p class="note"><b>${esc(best.value)}</b> is cheapest so far, but only ${d.best_confidence}% sure: the difference could be chance. Keep the ideas running side by side.</p>`;
}

function pictures(g) {
  const shown = g.pictures || [];
  const more = g.members.length - shown.length;
  // The names below link each ad; the pictures are a second, mouse-only way to the same pages.
  return `<div class="idea-thumbs" aria-hidden="true">${shown.map((m) => `<a class="idea-th" href="/ad.html?id=${encodeURIComponent(m.id)}" tabindex="-1" title="${esc(m.name)}"><img src="${esc(m.thumb)}" alt="" loading="lazy" referrerpolicy="no-referrer"></a>`).join("")}
    ${!shown.length ? '<span class="idea-th ph"></span>' : ""}${more > 0 && shown.length ? `<span class="idea-more">+${count(more)}</span>` : ""}</div>`;
}

function names(g) {
  const list = g.members.slice(0, NAMES).map((m) => entityLink("ad", m.id, m.name)).join(", ");
  const more = g.members.length > NAMES ? ` and ${count(g.members.length - NAMES)} more` : "";
  return `<p class="idea-ads">${list}${more}</p>`;
}

function group(g) {
  const untagged = g.value === UNTAGGED;
  const mark = state.tag && sameTag(g.value, state.tag);
  const cpl = g.cpl_cents == null ? "—" : money(g.cpl_cents, { exact: true });
  const pills = `${g.best ? '<span class="pill ok">Cheapest</span>' : ""}${!g.enough && !untagged ? '<span class="pill" title="Fewer than 3 leads or less than twice the target cost spent">Too early</span>' : ""}`;
  const gallery = untagged ? "" : ` · <a class="idea-gal" href="${esc(galleryHref(g.value))}">See in Gallery</a>`;
  return `<article class="idea-grp${g.best ? " is-best" : ""}${untagged ? " is-untagged" : ""}${mark ? ` is-marked${marked ? "" : " flash"}` : ""}" data-idea-row="${esc(g.value)}">
    <div class="idea-head">
      <h3><span class="idea-name">${esc(g.value)}</span>${pills}</h3>
      <p class="idea-sub">${count(g.ads)} ad${g.ads === 1 ? "" : "s"}${gallery}</p>
      ${names(g)}
    </div>
    ${pictures(g)}
    <dl class="idea-nums">
      <div class="idea-cpl"><dt>${WORDS.cpl}</dt><dd class="${g.enough ? "" : "early"}">${cpl}</dd></div>
      <div><dt>${WORDS.leads}</dt><dd>${count(g.leads)}</dd></div>
      <div><dt>${WORDS.spend}</dt><dd>${money(g.spend_cents)}</dd></div>
      <div title="${esc(EXPLAIN.hook)}"><dt>${WORDS.hook}</dt><dd>${ratePct(g.hook_rate)}</dd></div>
      <div title="${esc(EXPLAIN.hold)}"><dt>${WORDS.hold}</dt><dd>${ratePct(g.hold_rate)}</dd></div>
      <div title="Qualified or won ÷ leads"><dt>Qualified rate</dt><dd>${ratePct(g.qualified_rate)}</dd></div>
    </dl></article>`;
}

function render(d) {
  const dims = DIMS.map(([k, l]) => `<button type="button" data-idea="${k}" aria-pressed="${k === state.by}">${esc(l)}</button>`).join("");
  const bar = `<div class="cr-toolbar idea-bar"><div class="format-scroll"><div class="segmented" id="idea-by" role="group" aria-label="Group by">${dims}</div></div></div>
    <p class="muted small flush idea-when">${esc(d.range.label)} · complete days · ${esc(d.dimensions[d.by][1])}</p>`;
  if (!d.groups.length) {
    $("ideas").innerHTML = bar + emptyState({ title: "No ad spent money in these dates", body: "Ideas show here once tagged ads have spent. Pick longer dates above.", variant: "center" });
    return;
  }
  const missing = state.tag && !d.groups.some((g) => sameTag(g.value, state.tag))
    ? `<p class="muted small flush">No ad tagged “${esc(state.tag)}” spent money in these dates.</p>` : "";
  const how = me.role === "client" ? "" : me.role === "admin" ? ': tag them under "The idea" on each ad\'s page, or ask Claude to' : ': tag them under "The idea" on each ad\'s page';
  const untagged = d.untagged_ads ? `<p class="muted small flush">${count(d.untagged_ads)} ad${d.untagged_ads === 1 ? " has" : "s have"} no ${esc(d.dimensions[d.by][0].toLowerCase())} yet${how}.</p>` : "";
  $("ideas").innerHTML = `${bar}${verdict(d)}${missing}<h2 class="sr-only" id="idea-list-h">Ideas by ${esc(d.dimensions[d.by][0].toLowerCase())}</h2><section class="panel idea-list" aria-labelledby="idea-list-h">${d.groups.map(group).join("")}</section>${untagged}`;
  if (state.tag && !marked) {
    marked = true;
    document.querySelector(".idea-grp.is-marked")?.scrollIntoView({ block: "center" });
  }
}

async function load() {
  if ($("range-pick")) $("range-pick").value = state.range; else $("range-box").outerHTML = rangeSelect("range-pick", state.range);
  const superseded = startLoad("ideas");
  let d;
  try { d = await api(`/api/concepts?${new URLSearchParams({ by: state.by, range: state.range })}`); }
  catch (err) { if (!superseded()) showLoadError($("ideas"), err, load); return; }
  if (superseded()) return;
  render(d);
}

me = await boot({ page: "ideas" });
if (me) {
  save();
  $("ideas").addEventListener("click", (e) => {
    const b = e.target.closest("#idea-by [data-idea]");
    if (b && b.dataset.idea !== state.by) set({ by: b.dataset.idea, tag: "" });
  });
  document.querySelector(".page-head").addEventListener("change", (e) => {
    if (e.target.id !== "range-pick") return;
    rememberRange(e.target.value);
    set({ range: e.target.value });
  });
  addEventListener("popstate", () => { state = { ...DEFAULTS, ...UrlState.read(DEFAULTS) }; load(); });
  onRefresh(load);
  load();
}
