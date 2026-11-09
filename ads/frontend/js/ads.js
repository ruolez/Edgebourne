import { api } from "./api.js";
import { boot, esc, icon, switchHtml, toast, when } from "./ui.js";
import { editBudget, toggleEntity } from "./controls.js";
import { count, dayLabel, money, pct, per, plural, statusOf } from "./format.js";

const $ = (id) => document.getElementById(id);
let range = "7";
try { range = localStorage.getItem("ebads-range") || "7"; } catch (e) {}
let data;
const prefs = (() => { try { return JSON.parse(localStorage.getItem("ebads-adsview") || "{}"); } catch (e) { return {}; } })();
let view = prefs.view || "cards";
let sortBy = prefs.sort || "spend";
let filter = prefs.filter || "all";
const savePrefs = () => { try { localStorage.setItem("ebads-adsview", JSON.stringify({ view, sort: sortBy, filter })); } catch (e) {} };

const rate = (a, b) => (b ? a / b : null);
const SORTS = {
  spend: ["Most spent", (a) => -a.m.spend_cents],
  leads: ["Most leads", (a) => -(a.m.leads || 0)],
  cpl: ["Cheapest per lead", (a) => (a.m.leads ? a.m.spend_cents / a.m.leads : Infinity)],
  ctr: ["Best click rate", (a) => -(rate(a.m.link_clicks, a.m.impressions) || 0)],
  hook: ["Best hook rate", (a) => -(rate(a.m.video_3s, a.m.impressions) || 0)],
  newest: ["Newest", (a) => -new Date(a.created_time || 0).getTime()],
  name: ["Name", (a) => a.name.toLowerCase()],
};
const FILTERS = {
  all: ["All", () => true],
  on: ["On", (a) => a.status === "ACTIVE"],
  off: ["Off", (a) => a.status === "PAUSED"],
  attention: ["Needs attention", (a) => ["DISAPPROVED", "WITH_ISSUES"].includes(a.effective_status) || (a.effective_status === "ACTIVE" && !a.lifetime_impressions) || a.pending_proposals > 0],
};

function spark(series) {
  const max = Math.max(...series.map((d) => d.spend_cents), 1);
  const w = 100 / series.length;
  return `<svg class="spark" viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden="true">${series.map((d, i) => {
    const h = (d.spend_cents / max) * 20;
    return `<rect x="${i * w + w * 0.15}" y="${24 - h}" width="${w * 0.7}" height="${h}" rx="0.8"/>${d.leads ? `<circle cx="${i * w + w / 2}" cy="${Math.max(3, 24 - h - 3)}" r="1.6"/>` : ""}`;
  }).join("")}</svg>`;
}

const LEARNING = { LEARNING: ["warn", "Learning"], SUCCESS: ["ok", "Learning done"], FAIL: ["bad", "Learning limited"] };
const isOn = (s) => s === "ACTIVE";

function figures(m) {
  return `<dl class="mini-figs">
    <div><dt>Spent</dt><dd>${money(m.spend_cents)}</dd></div>
    <div><dt>Leads</dt><dd>${count(m.leads)}</dd></div>
    <div><dt>Per lead</dt><dd>${per(m.spend_cents, m.leads)}</dd></div>
    <div><dt>Qualified</dt><dd>${count(m.qualified)}</dd></div>
  </dl>`;
}

function budgetChip(level, row, canControl) {
  const cents = row.daily_budget_cents;
  if (!cents) return "";
  const label = `${money(cents, { exact: cents % 100 !== 0 })}/day`;
  return canControl
    ? `<button type="button" class="chip" data-budget="${level}:${row.id}" data-current="${cents}" data-name="${esc(row.name)}" title="Change the daily budget">${esc(label)} <span class="edit">Edit</span></button>`
    : `<span class="chip">${esc(label)}</span>`;
}

function adCard(ad, canControl) {
  const [cls, label] = statusOf(ad.effective_status);
  const m = ad.m;
  const img = ad.image_url || ad.thumbnail_url;
  const issue = ad.effective_status === "DISAPPROVED" || ad.effective_status === "WITH_ISSUES";
  const notShown = ad.effective_status === "ACTIVE" && !ad.lifetime_impressions;
  return `<article class="ad-card ${issue ? "has-issue" : ""}">
    <a class="ad-media" href="/ad.html?id=${encodeURIComponent(ad.id)}" aria-label="Open ${esc(ad.name)}">
      ${img ? `<img src="${esc(img)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '<span class="ph"></span>'}
      ${ad.object_type === "VIDEO" ? `<span class="play">${icon("play")}</span>` : ""}
      <span class="pill ${cls} on-media">${esc(label)}</span>
      ${ad.pending_proposals ? `<span class="badge-claude" title="Claude has a proposal for this ad">${icon("spark")}</span>` : ""}
    </a>
    <div class="ad-body">
      <div class="ad-title-row">
        <a class="ad-name" href="/ad.html?id=${encodeURIComponent(ad.id)}">${esc(ad.name)}</a>
        ${canControl && ["ACTIVE", "PAUSED"].includes(ad.status) ? switchHtml(isOn(ad.status), `data-toggle="ad:${ad.id}" data-name="${esc(ad.name)}"`, `${ad.name} on or off`) : ""}
      </div>
      ${ad.title ? `<p class="ad-headline">${esc(ad.title)}</p>` : ""}
      ${notShown ? '<p class="ad-note">Not shown to anyone yet</p>' : ""}
      <dl class="ad-stats">
        <div><dt>Spent</dt><dd>${money(m.spend_cents, { exact: true })}</dd></div>
        <div><dt>Leads</dt><dd>${count(m.leads)}</dd></div>
        <div><dt>Per lead</dt><dd>${per(m.spend_cents, m.leads)}</dd></div>
        <div><dt>${ad.object_type === "VIDEO" ? "Hook rate" : "Click rate"}</dt><dd>${ad.object_type === "VIDEO" ? pct(m.video_3s, m.impressions) : pct(m.link_clicks, m.impressions)}</dd></div>
      </dl>
      ${ad.spark && ad.spark.some((d) => d.spend_cents) ? `<div class="spark-wrap" title="Spend per day; dots mark days with leads">${spark(ad.spark)}</div>` : ""}
    </div>
  </article>`;
}

function adRow(ad, canControl) {
  const [cls, label] = statusOf(ad.effective_status);
  const m = ad.m;
  const img = ad.image_url || ad.thumbnail_url;
  return `<tr>
    <td><a class="ad-cell" href="/ad.html?id=${encodeURIComponent(ad.id)}">${img ? `<img src="${esc(img)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '<span class="ph"></span>'}<b>${esc(ad.name)}</b></a></td>
    <td><span class="pill ${cls}">${esc(label)}</span></td>
    <td>${canControl && ["ACTIVE", "PAUSED"].includes(ad.status) ? switchHtml(isOn(ad.status), `data-toggle="ad:${ad.id}" data-name="${esc(ad.name)}"`, `${ad.name} on or off`) : ""}</td>
    <td class="num">${money(m.spend_cents, { exact: true })}</td>
    <td class="num">${count(m.leads)}</td>
    <td class="num">${per(m.spend_cents, m.leads)}</td>
    <td class="num">${pct(m.link_clicks, m.impressions)}</td>
    <td class="num">${ad.object_type === "VIDEO" ? pct(m.video_3s, m.impressions) : "—"}</td>
    <td class="num">${ad.object_type === "VIDEO" ? pct(m.thruplays, m.video_3s) : "—"}</td>
    <td class="num">${count(m.qualified)}</td>
    <td class="spark-cell">${ad.spark ? spark(ad.spark) : ""}</td>
  </tr>`;
}

function adsBlock(ads, canControl) {
  const list = ads.filter(FILTERS[filter][1]).sort((a, b) => {
    const ka = SORTS[sortBy][1](a), kb = SORTS[sortBy][1](b);
    return ka < kb ? -1 : ka > kb ? 1 : 0;
  });
  if (!list.length) return `<p class="muted">No ads match “${esc(FILTERS[filter][0])}”.</p>`;
  if (view === "table") {
    return `<div class="scroll-x"><table class="table middle ads-table">
      <thead><tr><th>Ad</th><th>Status</th><th>On</th><th class="num">Spent</th><th class="num">Leads</th><th class="num">Per lead</th>
        <th class="num">Click rate</th><th class="num" title="3-second views ÷ impressions">Hook</th><th class="num" title="ThruPlays ÷ 3-second views">Hold</th><th class="num">Qualified</th><th>Spend per day</th></tr></thead>
      <tbody>${list.map((a) => adRow(a, canControl)).join("")}</tbody></table></div>`;
  }
  return `<div class="ad-grid">${list.map((a) => adCard(a, canControl)).join("")}</div>`;
}

function toolbar() {
  return `<div class="ads-toolbar">
    <div class="segmented" id="filters" role="group" aria-label="Show">${Object.entries(FILTERS).map(([k, [l, fn]]) => {
      const n = data.campaigns.flatMap((c) => c.adsets.flatMap((s) => s.ads)).filter(fn).length;
      return `<button type="button" data-filter="${k}" aria-pressed="${k === filter}">${esc(l)} <span class="n">${n}</span></button>`;
    }).join("")}</div>
    <span class="spacer"></span>
    <label class="sort"><span class="muted small">Sort</span><select class="input" id="sort">${Object.entries(SORTS).map(([k, [l]]) => `<option value="${k}" ${k === sortBy ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
    <div class="segmented icon-seg" id="view" role="group" aria-label="View">
      <button type="button" data-view="cards" aria-pressed="${view === "cards"}" title="Cards">${icon("grid")}<span class="sr-only">Cards</span></button>
      <button type="button" data-view="table" aria-pressed="${view === "table"}" title="Table">${icon("table")}<span class="sr-only">Table</span></button>
    </div>
  </div>`;
}

function render() {
  $("synced").textContent = data.last_sync ? `Updated ${when(data.last_sync)}` : "Not synced yet";
  if (!data.campaigns.length) {
    $("ads").innerHTML = `<section class="panel empty"><h3>No ads yet</h3><p>Once Meta is connected in Settings, your campaigns, ad sets and ads appear here. Use Refresh from Meta after connecting.</p></section>`;
    return;
  }
  $("ads").innerHTML = toolbar() + data.campaigns.map((c) => {
    const [cc, cl] = statusOf(c.effective_status);
    const sets = c.adsets.map((s) => {
      const [sc, sl] = statusOf(s.effective_status);
      const learn = LEARNING[s.learning_stage];
      return `<section class="adset">
        <header class="adset-head">
          <div class="adset-title">
            <span class="level">Ad set</span>
            <h3>${esc(s.name)}</h3>
            <span class="pill ${sc}">${esc(sl)}</span>
            ${learn ? `<span class="pill ${learn[0]}" title="Meta's learning phase: results settle after about 50 results a week">${esc(learn[1])}</span>` : ""}
            ${budgetChip("adset", s, c.can_control)}
          </div>
          ${c.can_control ? switchHtml(isOn(s.status), `data-toggle="adset:${s.id}" data-name="${esc(s.name)}"`, `${s.name} on or off`) : ""}
        </header>
        ${s.targeting_summary ? `<p class="adset-target">${esc(s.targeting_summary)}</p>` : ""}
        ${s.ads.length ? adsBlock(s.ads, c.can_control) : '<p class="muted">No ads in this ad set.</p>'}
        <p class="adset-estimate muted small" data-estimate="${esc(s.id)}"></p>
      </section>`;
    }).join("");
    return `<section class="panel campaign">
      <header class="campaign-head">
        <div class="campaign-title">
          <span class="level">Campaign</span>
          <h2>${esc(c.name)}</h2>
          <div class="row tight-row"><span class="pill ${cc}">${esc(cl)}</span>${budgetChip("campaign", c, c.can_control)}
            ${c.pending_proposals ? `<span class="pill claude">${plural(c.pending_proposals, "proposal")}</span>` : ""}</div>
        </div>
        ${figures(c.m)}
        ${c.can_control ? switchHtml(isOn(c.status), `data-toggle="campaign:${c.id}" data-name="${esc(c.name)}"`, `${c.name} on or off`) : ""}
      </header>
      ${sets}
    </section>`;
  }).join("") + `<p class="muted small flush">Results are complete days only (${esc(dayLabel(data.range.start))} to ${esc(dayLabel(data.range.end))}). Today is left out because Meta reports late.</p>`;
}

async function load() {
  document.querySelectorAll("#range button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.range === range)));
  try { data = await api(`/api/ads?range=${range}`); render(); loadEstimates(); } catch (err) { toast(err.message, "bad"); }
}

function loadEstimates() {
  document.querySelectorAll("[data-estimate]").forEach(async (el) => {
    try {
      const e = await api(`/api/insights/adset/${encodeURIComponent(el.dataset.estimate)}/estimate`);
      if (e.lower && e.upper) el.textContent = `Meta estimates ${count(e.lower)}–${count(e.upper)} people could see these ads.`;
    } catch (err) { /* no estimate: leave it blank */ }
  });
}

const me = await boot({ page: "ads" });
if (me) {
  $("new-ad").innerHTML = `${icon("plus")}<span>New ad</span>`;
  $("range").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-range]");
    if (!b) return;
    range = b.dataset.range;
    try { localStorage.setItem("ebads-range", range); } catch (err) {}
    load();
  });
  $("ads").addEventListener("change", (e) => {
    if (e.target.id === "sort") { sortBy = e.target.value; savePrefs(); render(); loadEstimates(); }
  });
  $("ads").addEventListener("click", (e) => {
    const fb = e.target.closest("[data-filter]");
    if (fb) { filter = fb.dataset.filter; savePrefs(); render(); loadEstimates(); return; }
    const vb = e.target.closest("[data-view]");
    if (vb) { view = vb.dataset.view; savePrefs(); render(); loadEstimates(); return; }
    const t = e.target.closest("[data-toggle]");
    if (t) { toggleEntity(t, load); return; }
    const b = e.target.closest("[data-budget]");
    if (b) {
      const [level, id] = b.dataset.budget.split(":");
      editBudget({ level, id, name: b.dataset.name, current: Number(b.dataset.current) }, load);
    }
  });
  $("refresh").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Refreshing…";
    try { await api("/api/ads/sync", { method: "POST" }); toast("Up to date with Meta"); load(); }
    catch (err) { toast(err.message, "bad"); }
    finally { btn.disabled = false; btn.textContent = "Refresh from Meta"; }
  });
  load();
}
