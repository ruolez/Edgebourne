// Compare 2–6 ads side by side: the creative on top, one row per metric with the best marked and the
// change against the period before, a verdict that waits for enough data, and one chart with a line
// per ad. Reached from the Ads manager's selection bar (Compare) or Insights → Compare.
import { api, startLoad } from "./api.js";
import { boot, entityLink, esc, icon, onRefresh, sourceNote, toast, errorState } from "./ui.js";
import { lineChart, marksPanel } from "./charts.js";
import { count, money, per, statusOf, statusPill, moneyWhole, rangeSelect, rememberCampaign, rememberRange, sharedCampaign, sharedRange } from "./format.js";
import * as UrlState from "./urlstate.js";

const $ = (id) => document.getElementById(id);
// The dates picked last on Ads, Results or any campaign, ad set or ad, unless the link names its own.
const DEFAULTS = { ids: "", range: sharedRange(), vs: true, chart: "leads" };
const LOWER = { cpl_cents: 1, cpq_cents: 1, cpm_cents: 1, cpb_cents: 1 };
let state = UrlState.read(DEFAULTS);
let data = null, all = null, allRange = null, campaigns = [];
// The campaign picked last on Results or here, unless the link names one: the picker shows its ads.
const q0 = new URLSearchParams(location.search);
let campaign = q0.has("campaign") ? q0.get("campaign") : sharedCampaign();
const MAX = 6;
const ids = () => state.ids.split(",").filter(Boolean);
// What's ticked in the picker, kept while the campaign or the dates change, so ads from two campaigns can be compared.
const picked = new Set(ids());
const save = () => UrlState.write(state, DEFAULTS);

const FMT = {
  spend_cents: (v) => money(v, { exact: true }), leads: count, qualified: count, booked: count,
  cpl_cents: (v) => money(v, { exact: true }), cpq_cents: (v) => money(v, { exact: true }), cpm_cents: (v) => money(v, { exact: true }),
  cpb_cents: (v) => money(v, { exact: true }),
  ctr: (v) => `${(v * 100).toFixed(2)}%`, hook: (v) => `${(v * 100).toFixed(1)}%`, hold: (v) => `${(v * 100).toFixed(1)}%`,
  frequency: (v) => v.toFixed(2),
};
// Each ad's key: a number in its colour, with the line's own dash, so the lines read without colour too.
const DASH = ["", "7 4", "2 4", "10 4 2 4", "1 5", "14 6"];
const keyHtml = (i, line = false) => `<span class="cmp-n s${i + 1}"><span class="sr-only">Line </span>${line ? `<svg viewBox="0 0 22 6" aria-hidden="true"><line x1="1" y1="3" x2="21" y2="3" class="ln s${i + 1}"${DASH[i] ? ` stroke-dasharray="${DASH[i]}"` : ""}/></svg>` : ""}<b>${i + 1}</b></span>`;
const TAGS = [["hook", "Hook"], ["angle", "Angle"], ["persona", "Persona"], ["format", "Format"], ["offer", "Offer"]];

function deltaHtml(key, d) {
  if (d == null) return "";
  if (!d) return '<span class="delta d-mute">0%</span>';
  const good = LOWER[key] ? d < 0 : key === "spend_cents" || key === "frequency" ? null : d > 0;
  return `<span class="delta ${good == null ? "d-mute" : good ? "d-good" : "d-bad"}">${d > 0 ? "+" : "−"}${Math.abs(d)}%</span>`;
}

function verdictHtml() {
  const v = data.verdict;
  const what = v.metric === "cpq_cents" ? "cost per qualified lead" : "cost per lead";
  if (!v.need_spend_cents) return `<div class="note">Set a target in Settings → Targets to have a winner named once there's enough data.</div>`;
  if (v.ready && v.leader) {
    const lead = data.items.find((i) => i.id === v.leader);
    return `<div class="note ok"><b>${esc(lead.name)} leads on ${what}.</b> Every ad has spent at least ${money(v.need_spend_cents)} and has ${v.need_results}+ ${v.result === "qualified" ? "qualified leads" : "leads"}, so this is a fair call.</div>`;
  }
  const behind = data.items.filter((i) => i.m.spend_cents < v.need_spend_cents || (i.m[v.result] || 0) < v.need_results).map((i) => esc(i.name));
  return `<div class="note warn"><b>Too early to name a winner.</b> Each ad needs ${money(v.need_spend_cents)} spent (2× your target) and ${v.need_results} ${v.result === "qualified" ? "qualified leads" : "leads"} before it's judged; not there yet: ${behind.join(", ")}.</div>`;
}

function tableHtml() {
  const items = data.items;
  const head = `<tr><th class="cmp-corner">${esc(data.range.label)}${data.prev_range ? `<small>vs ${esc(data.prev_range.label)}</small>` : ""}</th>${items.map((it, i) => {
    const [cls, label] = statusOf(it.effective_status);
    const img = it.image_url || it.thumbnail_url;
    return `<th><div class="cmp-h">${img ? `<img class="cmp-th" src="${esc(img)}" alt="" referrerpolicy="no-referrer">` : '<span class="cmp-th ph"></span>'}
      ${entityLink("ad", it.id, it.name, { cls: "tbl-link" })}<span class="pill ${cls}">${esc(label)}</span>
      <span class="cmp-key">${keyHtml(i)}${ids().length > 2 ? `<button type="button" class="link-btn small" data-drop="${esc(it.id)}">Remove</button>` : ""}</span></div></th>`;
  }).join("")}</tr>`;
  const rows = data.rows.map((r) => `<tr><th scope="row">${esc(r.label)}</th>${r.cells.map((c, i) => {
    const best = r.best === i;
    return `<td class="${best ? "win" : ""}"><b>${c.value == null ? "—" : esc(FMT[r.key](c.value))}</b><span class="cmp-sub">${state.vs ? deltaHtml(r.key, c.delta_pct) : ""}${best ? `<span class="best">${LOWER[r.key] ? "Lowest" : "Highest"}</span>` : ""}</span></td>`;
  }).join("")}</tr>`).join("");
  const tags = TAGS.filter(([k]) => items.some((it) => it.tags[k])).map(([k, label]) => `<tr class="cmp-tag"><th scope="row">${label}</th>${items.map((it) => `<td>${it.tags[k] ? entityLink("tag", it.tags[k], it.tags[k], { cls: "chip", dim: k }) : '<span class="muted">—</span>'}</td>`).join("")}</tr>`).join("");
  return `<div class="tbl-wrap"><table class="cmp"><thead>${head}</thead><tbody>${rows}${tags}</tbody></table></div>`;
}

function chartSeries() {
  const k = state.chart;
  return data.items.map((it, i) => {
    let run = 0;
    const points = it.series.map((d) => {
      if (k === "leads") { run += d.leads; return { day: d.day, value: run }; }
      if (k === "spend") return { day: d.day, value: d.spend_cents };
      return { day: d.day, value: d.leads ? d.spend_cents / d.leads : null };
    });
    return { label: it.name, cls: `s${i + 1}`, key: String(i + 1), points };
  });
}

function render() {
  const n = data.items.length;
  $("cmp-title").textContent = `Compare ${n} ads`;
  $("cmp-sub").textContent = `${data.range.label}${state.vs && data.prev_range ? ` vs the ${data.prev_range.label} before` : ""} · complete days only`;
  $("cmp-actions").innerHTML = `${rangeSelect("cmp-range", state.range)}
    <button type="button" class="view-chip" id="cmp-vs" aria-pressed="${state.vs}">vs before</button>
    ${n < MAX && all ? `<select class="input tool" id="cmp-add" aria-label="Add an ad"><option value="">+ Add an ad</option>${all.filter((a) => !ids().includes(a.id)).map((a) => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join("")}</select>` : ""}
    ${window.ebadsMe?.role === "admin" ? `<a class="btn btn-claude-outline" href="/desk.html?ask=1">${icon("spark")}Ask Claude which to keep</a>` : ""}`;
  const charts = [["leads", "Leads, running total"], ["cpl", "Cost per lead"], ["spend", "Spent per day"]];
  $("cmp").innerHTML = `${verdictHtml()}
    <div class="cmp-grid">${tableHtml()}
      <section class="panel"><div class="panel-head"><h2>${esc(charts.find(([k]) => k === state.chart)[1])}</h2><span class="spacer"></span>
        <div class="segmented" role="group" aria-label="Chart">${charts.map(([k, l]) => `<button type="button" data-chart="${k}" aria-pressed="${state.chart === k}">${l.split(",")[0]}</button>`).join("")}</div></div>
        <div class="chart" id="cmp-chart"></div>
        <ul class="cmp-legend">${data.items.map((it, i) => `<li>${keyHtml(i, true)}${esc(it.name)}</li>`).join("")}</ul></section></div>
    <div class="fig-foot"><div class="fig-src" id="fig-src"></div><div class="fig-marks" id="chg-panel"></div></div>
    <p class="muted small flush">“Lowest” and “Highest” describe this window only; the verdict above says when the difference is big enough to act on.</p>`;
  const money2 = (v) => money(v, { exact: true });
  lineChart({ el: $("cmp-chart"), series: chartSeries(), title: charts.find(([k]) => k === state.chart)[1], height: 240, integer: state.chart === "leads", dashes: DASH,
    format: state.chart === "leads" ? (v) => `${v} leads` : money2,
    axisFormat: state.chart === "leads" ? (v) => String(Math.round(v)) : (v) => moneyWhole(v), marks: data.marks || [], marksSummary: data.marks_summary || "" });
  marksPanel($("chg-panel"), data.marks || [], data.marks_summary || "", data.marks_list);
  $("fig-src").innerHTML = sourceNote(data.source);
}

// No ads yet (or one): pick 2 to 6, each shown with its picture and its numbers for the dates, biggest spend first.
function pickerHtml() {
  const list = (all || []).filter((a) => !campaign || a.campaign_id === campaign || picked.has(a.id));
  $("cmp-title").textContent = "Compare ads";
  $("cmp-sub").textContent = `Pick 2 to ${MAX} ads · numbers for ${rangeLabel()}. Tip: in Ads, tick the ads and press Compare.`;
  $("cmp-actions").innerHTML = `${rangeSelect("cmp-range", state.range)}${campaigns.length > 1 ? `<select class="input tool" id="cmp-camp" aria-label="Campaign"><option value="">All campaigns</option>${campaigns.map((c) => `<option value="${esc(c.id)}" ${c.id === campaign ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>` : ""}`;
  const card = (a) => {
    const m = a.m || {};
    const img = a.image_url || a.thumbnail_url;
    return `<li><label class="cmp-opt">
      <input type="checkbox" value="${esc(a.id)}" ${picked.has(a.id) ? "checked" : ""}>
      ${img ? `<img class="cmp-opt-img" src="${esc(img)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '<span class="cmp-opt-img ph"></span>'}
      <span class="cmp-opt-t"><b>${esc(a.name)}</b>${statusPill(a.effective_status)}
        <span class="cmp-opt-m"><span>${money(m.spend_cents || 0)} spent</span><span>${count(m.leads || 0)} lead${m.leads === 1 ? "" : "s"}</span><span>${m.leads ? `${per(m.spend_cents || 0, m.leads)} per lead` : "no leads yet"}</span></span></span>
    </label></li>`;
  };
  $("cmp").innerHTML = `<form class="panel cmp-pick" id="cmp-pick"><div class="panel-body">
      ${list.length ? `<ul class="cmp-opts">${list.map(card).join("")}</ul>` : `<p class="muted flush">No ads ${campaign ? "in this campaign " : ""}to compare yet.</p>`}
      <div class="row cmp-pick-foot"><button class="btn btn-primary" type="submit" id="cmp-go">Compare</button><span class="muted small" id="cmp-count" aria-live="polite"></span></div>
    </div></form>`;
  const form = $("cmp-pick");
  const sync = () => {
    const n = picked.size;
    $("cmp-count").textContent = n < 2 ? `${n} picked: pick ${2 - n} more` : `${n} of ${MAX} picked`;
    $("cmp-go").disabled = n < 2;
    form.querySelectorAll("input:not(:checked)").forEach((i) => { i.disabled = n >= MAX; });
  };
  sync();
  form.addEventListener("change", (e) => {
    if (e.target.type !== "checkbox") return;
    if (e.target.checked) picked.add(e.target.value); else picked.delete(e.target.value);
    sync();
  });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const chosen = [...picked].slice(0, MAX);
    if (chosen.length < 2) { toast("Pick at least 2 ads", "bad"); return; }
    state.ids = chosen.join(","); save(); load();
  });
}

const rangeLabel = () => ({ 7: "the last 7 days", 14: "the last 14 days", 30: "the last 30 days", mtd: "this month", lastmonth: "last month" }[state.range] || "these dates");

async function load() {
  const superseded = startLoad("compare");
  if (!all || allRange !== state.range) {
    try {
      const tree = await api(`/api/ads?range=${encodeURIComponent(state.range)}`);
      campaigns = tree.campaigns.map((c) => ({ id: c.id, name: c.name }));
      all = tree.campaigns.flatMap((c) => c.adsets.flatMap((s) => s.ads.map((a) => ({ ...a, campaign_id: a.campaign_id || c.id }))))
        .filter((a) => a.effective_status !== "DELETED")
        .sort((a, b) => ((b.m || {}).spend_cents || 0) - ((a.m || {}).spend_cents || 0));
      allRange = state.range;
      for (const id of picked) if (!all.some((x) => x.id === id)) picked.delete(id);
    } catch (e) { all = []; campaigns = []; }
  }
  if (superseded()) return;
  if (campaign && !campaigns.some((c) => c.id === campaign)) campaign = "";
  if (ids().length < 2) { pickerHtml(); return; }
  try {
    const d = await api(`/api/compare?ids=${encodeURIComponent(state.ids)}&range=${encodeURIComponent(state.range)}${state.vs ? "&vs=prev" : ""}`);
    if (superseded()) return;
    data = d;
    render();
  } catch (err) { if (!superseded()) errorState($("cmp"), err, load); }
}

const me = await boot({ page: "compare" });
if (me) {
  document.addEventListener("click", (e) => {
    const c = e.target.closest("[data-chart]");
    if (c) { state.chart = c.dataset.chart; save(); render(); }
    if (e.target.closest("#cmp-vs")) { state.vs = !state.vs; save(); load(); }
    const d = e.target.closest("[data-drop]");
    if (d) { state.ids = ids().filter((x) => x !== d.dataset.drop).join(","); save(); load(); }
  });
  document.addEventListener("change", (e) => {
    if (e.target.id === "cmp-range") { state.range = e.target.value; rememberRange(state.range); save(); load(); }
    if (e.target.id === "cmp-camp") { campaign = e.target.value; rememberCampaign(campaign); pickerHtml(); return; }
    if (e.target.id === "cmp-add" && e.target.value) { state.ids = [...ids(), e.target.value].join(","); save(); load(); }
  });
  onRefresh(load);
  load();
}
