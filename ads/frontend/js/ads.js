import { api } from "./api.js";
import { boot, esc, icon, switchHtml, toast, when } from "./ui.js";
import { editBudget, toggleEntity } from "./controls.js";
import { count, dayLabel, money, pct, per, plural, statusOf } from "./format.js";

const $ = (id) => document.getElementById(id);
let range = "7";
try { range = localStorage.getItem("ebads-range") || "7"; } catch (e) {}
let data;

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
        <div><dt>Click rate</dt><dd>${pct(m.link_clicks, m.impressions)}</dd></div>
      </dl>
    </div>
  </article>`;
}

function render() {
  $("synced").textContent = data.last_sync ? `Updated ${when(data.last_sync)}` : "Not synced yet";
  if (!data.campaigns.length) {
    $("ads").innerHTML = `<section class="panel empty"><h3>No ads yet</h3><p>Once Meta is connected in Settings, your campaigns, ad sets and ads appear here. Use Refresh from Meta after connecting.</p></section>`;
    return;
  }
  $("ads").innerHTML = data.campaigns.map((c) => {
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
        <div class="ad-grid">${s.ads.map((a) => adCard(a, c.can_control)).join("") || '<p class="muted">No ads in this ad set.</p>'}</div>
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
  try { data = await api(`/api/ads?range=${range}`); render(); } catch (err) { toast(err.message, "bad"); }
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
  $("ads").addEventListener("click", (e) => {
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
