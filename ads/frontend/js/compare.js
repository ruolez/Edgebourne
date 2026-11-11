// Compare 2–6 ads side by side: the creative on top, one row per metric with the best marked and the
// change against the period before, a verdict that waits for enough data, and one chart with a line
// per ad. Reached from the Ads manager's selection bar (Compare) or Insights → Compare.
import { api } from "./api.js";
import { boot, esc, icon, onRefresh, toast, errorState } from "./ui.js";
import { lineChart } from "./charts.js";
import { count, money, statusOf, moneyWhole } from "./format.js";
import * as UrlState from "./urlstate.js";

const $ = (id) => document.getElementById(id);
const DEFAULTS = { ids: "", range: "14", vs: true, chart: "leads" };
const RANGES = [["7", "7 days"], ["14", "14 days"], ["30", "30 days"], ["mtd", "This month"], ["lastmonth", "Last month"]];
const LOWER = { cpl_cents: 1, cpq_cents: 1, cpm_cents: 1 };
let state = UrlState.read(DEFAULTS);
let data = null, all = null;
const ids = () => state.ids.split(",").filter(Boolean);
const save = () => UrlState.write(state, DEFAULTS);

const FMT = {
  spend_cents: (v) => money(v, { exact: true }), leads: count, qualified: count,
  cpl_cents: (v) => money(v, { exact: true }), cpq_cents: (v) => money(v, { exact: true }), cpm_cents: (v) => money(v, { exact: true }),
  ctr: (v) => `${(v * 100).toFixed(2)}%`, hook: (v) => `${(v * 100).toFixed(1)}%`, hold: (v) => `${(v * 100).toFixed(1)}%`,
  frequency: (v) => v.toFixed(2),
};
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
      <a href="/ad.html?id=${encodeURIComponent(it.id)}" class="tbl-link">${esc(it.name)}</a><span class="st st-${cls || "mute"}">${esc(label)}</span>
      <span class="cmp-key"><i class="sw s${i + 1}"></i>${ids().length > 2 ? `<button type="button" class="link-btn small" data-drop="${esc(it.id)}">Remove</button>` : ""}</span></div></th>`;
  }).join("")}</tr>`;
  const rows = data.rows.map((r) => `<tr><th scope="row">${esc(r.label)}</th>${r.cells.map((c, i) => {
    const best = r.best === i;
    return `<td class="${best ? "win" : ""}"><b>${c.value == null ? "—" : esc(FMT[r.key](c.value))}</b><span class="cmp-sub">${state.vs ? deltaHtml(r.key, c.delta_pct) : ""}${best ? `<span class="best">${LOWER[r.key] ? "Lowest" : "Highest"}</span>` : ""}</span></td>`;
  }).join("")}</tr>`).join("");
  const tags = TAGS.filter(([k]) => items.some((it) => it.tags[k])).map(([k, label]) => `<tr class="cmp-tag"><th scope="row">${label}</th>${items.map((it) => `<td>${it.tags[k] ? `<span class="chip">${esc(it.tags[k])}</span>` : '<span class="muted">—</span>'}</td>`).join("")}</tr>`).join("");
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
    return { label: it.name, cls: `s${i + 1}`, points };
  });
}

function render() {
  const n = data.items.length;
  $("cmp-title").textContent = `Compare ${n} ads`;
  $("cmp-sub").textContent = `${data.range.label}${state.vs && data.prev_range ? ` vs the ${data.prev_range.label} before` : ""} · complete days only`;
  $("cmp-actions").innerHTML = `<select class="input tool" id="cmp-range" aria-label="Dates">${RANGES.map(([k, l]) => `<option value="${k}" ${k === state.range ? "selected" : ""}>${l}</option>`).join("")}</select>
    <button type="button" class="tool-tg" id="cmp-vs" aria-pressed="${state.vs}">vs before</button>
    ${n < 6 && all ? `<select class="input tool" id="cmp-add" aria-label="Add an ad"><option value="">+ Add an ad</option>${all.filter((a) => !ids().includes(a.id)).map((a) => `<option value="${esc(a.id)}">${esc(a.name)}</option>`).join("")}</select>` : ""}
    ${window.ebadsMe?.role === "admin" ? `<a class="btn btn-claude-outline" href="/desk.html?ask=1">${icon("spark")}Ask Claude which to keep</a>` : ""}`;
  const charts = [["leads", "Leads, running total"], ["cpl", "Cost per lead"], ["spend", "Spent per day"]];
  $("cmp").innerHTML = `${verdictHtml()}
    <div class="cmp-grid">${tableHtml()}
      <section class="panel"><div class="panel-head"><h2>${esc(charts.find(([k]) => k === state.chart)[1])}</h2><span class="spacer"></span>
        <div class="segmented" role="group" aria-label="Chart">${charts.map(([k, l]) => `<button type="button" data-chart="${k}" aria-pressed="${state.chart === k}">${l.split(",")[0]}</button>`).join("")}</div></div>
        <div class="chart" id="cmp-chart"></div>
        <ul class="cmp-legend">${data.items.map((it, i) => `<li><i class="sw s${i + 1}"></i>${esc(it.name)}</li>`).join("")}</ul></section></div>
    <p class="muted small flush">“Lowest” and “Highest” describe this window only; the verdict above says when the difference is big enough to act on.</p>`;
  const money2 = (v) => money(v, { exact: true });
  lineChart({ el: $("cmp-chart"), series: chartSeries(), title: "Compare chart", height: 240, integer: state.chart === "leads",
    format: state.chart === "leads" ? (v) => `${v} leads` : money2,
    axisFormat: state.chart === "leads" ? (v) => String(Math.round(v)) : (v) => moneyWhole(v) });
}

async function pickerHtml() {
  const list = all || [];
  $("cmp-title").textContent = "Compare ads";
  $("cmp-sub").textContent = "Pick 2 to 6 ads. Tip: in Ads, tick the ads and press Compare.";
  $("cmp").innerHTML = `<form class="panel cmp-pick" id="cmp-pick"><div class="panel-body"><ul class="check-list">${list.map((a) => `<li><label class="check"><input type="checkbox" value="${esc(a.id)}" ${ids().includes(a.id) ? "checked" : ""}> <span>${esc(a.name)} <small class="muted">${esc(statusOf(a.effective_status)[1])}</small></span></label></li>`).join("")}</ul>
    <div class="row"><button class="btn btn-primary" type="submit">Compare</button></div></div></form>`;
  $("cmp-pick").addEventListener("submit", (e) => {
    e.preventDefault();
    const picked = [...e.target.querySelectorAll("input:checked")].map((i) => i.value).slice(0, 6);
    if (picked.length < 2) { toast("Pick at least 2 ads", "bad"); return; }
    state.ids = picked.join(","); save(); load();
  });
}

async function load() {
  if (!all) {
    try {
      const tree = await api("/api/ads?range=30");
      all = tree.campaigns.flatMap((c) => c.adsets.flatMap((s) => s.ads)).filter((a) => a.effective_status !== "DELETED");
    } catch (e) { all = []; }
  }
  if (ids().length < 2) { pickerHtml(); return; }
  try {
    data = await api(`/api/compare?ids=${encodeURIComponent(state.ids)}&range=${encodeURIComponent(state.range)}${state.vs ? "&vs=prev" : ""}`);
    render();
  } catch (err) { errorState($("cmp"), err, load); }
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
    if (e.target.id === "cmp-range") { state.range = e.target.value; save(); load(); }
    if (e.target.id === "cmp-add" && e.target.value) { state.ids = [...ids(), e.target.value].join(","); save(); load(); }
  });
  onRefresh(load);
  load();
}
