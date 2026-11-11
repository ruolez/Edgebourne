import { api } from "./api.js";
import { boot, confirmDialog, esc, fieldError, icon, toast, guardLeaving, markSaved } from "./ui.js";
import { money } from "./format.js";
import { placeLabel, placesHtml, placesWidget } from "./places.js";

const $ = (id) => document.getElementById(id);
let opts;
let hints = [];
const locations_ = () => places.get();

let places;
const label = placeLabel;

function spec() {
  const n = (id) => ($(id).value === "" ? null : Number($(id).value));
  const dollars = $("budget").value.trim();
  return {
    name: $("name").value, locations: locations_(), age_min: n("age_min"), age_max: n("age_max"),
    suggest_min: $("advantage").checked ? n("suggest_min") : null, suggest_max: $("advantage").checked ? n("suggest_max") : null,
    advantage: $("advantage").checked, keep_hints: $("keep_hints").checked,
    start_day: $("start_day").value || null, start_hour: 0, end_day: $("end_day").value || null, end_hour: 23,
    daily_budget_cents: dollars ? Math.round(Number(dollars) * 100) : null,
  };
}

function campaign() { return opts.campaigns.find((c) => c.id === $("campaign").value); }

function syncCampaign() {
  const c = campaign();
  const cbo = c && c.daily_budget_cents != null;
  $("budget-field").hidden = cbo;
  $("budget-note").textContent = c ? (cbo ? `Its ${money(c.daily_budget_cents, { exact: true })} a day is shared by all its ad sets.` : "Each ad set has its own budget.") : "";
  $("budget-hint").textContent = "Meta may spend up to 75% more on a good day, and evens it out over the week.";
  const sets = opts.adsets.filter((s) => s.campaign_id === $("campaign").value);
  const all = sets.length ? sets : opts.adsets;
  const keep = $("template").value;
  const chosenScratch = $("template").options.length > 0 && keep === "";  // only when picked, not on first fill
  $("template").innerHTML = all.map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("")
    + '<option value="">Nothing: start from scratch</option>';
  if (all.some((s) => s.id === keep) || chosenScratch) $("template").value = keep;
}

function syncAdvantage() {
  const on = $("advantage").checked;
  $("suggest-field").hidden = !on;
  $("age-hint").textContent = on ? `Hard limits. With Advantage+ audience the minimum can be at most ${opts.advantage_max_age_min}.` : "Only people in this range see it.";
}

function summary() {
  const s = spec();
  const parts = [`Ages ${s.age_min ?? 18}–${s.age_max ?? 65}${(s.age_max ?? 65) >= 65 ? "+" : ""}`];
  const locations = locations_();
  if (locations.length) parts.push(locations.length <= 3 ? locations.map((l) => `${label(l)}${l.radius ? ` (${l.radius} mi)` : ""}`).join(", ") : `${locations.length} places`);
  if (s.keep_hints && hints.length) parts.push(`Hints: ${hints.slice(0, 3).join(", ")}${hints.length > 3 ? ` +${hints.length - 3}` : ""}`);
  if (s.advantage) parts.push("Advantage+ audience");
  $("summary").textContent = parts.join(" · ");
}

let estSeq = 0;
let estTimer;
function estimateSoon() {
  clearTimeout(estTimer);
  estTimer = setTimeout(async () => {
    const mine = ++estSeq;
    if (!locations_().length) { $("estimate").textContent = "—"; return; }
    $("estimate").classList.add("loading");
    try {
      const e = await api("/api/adsets/estimate", { method: "POST", body: { template_adset_id: $("template").value, spec: spec() } });
      if (mine !== estSeq) return;
      const m = (v) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${Math.round(v / 1e3)}K` : String(v));
      $("estimate").textContent = e.lower ? `${m(e.lower)} – ${m(e.upper)}` : "—";
      $("estimate-note").textContent = "People a month Meta could show it to. Updates as you change places and ages.";
    } catch (err) {
      if (mine === estSeq) { $("estimate").textContent = "—"; $("estimate-note").textContent = err.message; }
    } finally { if (mine === estSeq) $("estimate").classList.remove("loading"); }
  }, 400);
}

function changed() { summary(); estimateSoon(); }

async function loadTemplate() {
  try {
    const t = $("template").value ? await api(`/api/adsets/template/${encodeURIComponent($("template").value)}`)
      : { locations: [], hints: [], age_min: 25, age_max: 65, suggest_min: null, suggest_max: null, advantage: true, keep_hints: false };
    places.set(t.locations); hints = t.hints;
    $("age_min").value = t.age_min; $("age_max").value = t.age_max;
    $("suggest_min").value = t.suggest_min ?? ""; $("suggest_max").value = t.suggest_max ?? "";
    $("advantage").checked = t.advantage; $("keep_hints").checked = t.keep_hints && hints.length > 0;
    $("hints").textContent = hints.join(", ");
    $("hints-row").hidden = !hints.length;
    syncAdvantage(); changed();
  } catch (err) { toast(err.message, "bad"); }
}

const me = await boot({ page: "new-adset", admin: true });
if (me) guardLeaving();
if (me) {
  $("crumb").innerHTML = `${icon("back")}<span>Ads</span>`;
  try { opts = await api("/api/adsets/new/options"); } catch (err) { toast(err.message, "bad"); }
  if (!opts || !opts.campaigns.length || !opts.adsets.length) {
    document.querySelector(".new-ad-layout").innerHTML = `<section class="panel empty"><h3>Nothing to build on yet</h3><p>A new ad set starts from an existing one. Once your campaigns are synced from Meta, come back here.</p><a class="btn" href="/ads.html">Back to ads</a></section>`;
  } else {
    $("places-box").innerHTML = placesHtml("pl");
    places = placesWidget("pl", { cityRadius: opts.city_radius, pinRadius: opts.pin_radius, onChange: changed });
    $("campaign").innerHTML = opts.campaigns.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}${c.effective_status === "ACTIVE" ? "" : " (off)"}</option>`).join("");
    const want = new URLSearchParams(location.search).get("campaign");
    if (want && opts.campaigns.some((c) => c.id === want)) $("campaign").value = want;
    else if (want) {
      // A deleted or archived campaign can't take new ad sets: never quietly build in another one (audit A3-105).
      $("campaign").insertAdjacentHTML("afterbegin", '<option value="" disabled>Pick a campaign</option>');
      $("campaign").value = "";
    }
    syncCampaign();
    if (want && !campaign()) $("budget-note").textContent = "The campaign you came from is deleted or archived, so it can't get new ad sets. Pick one that's still running.";
    await loadTemplate();
    $("campaign").addEventListener("change", () => { syncCampaign(); loadTemplate(); });
    $("template").addEventListener("change", loadTemplate);
    $("as-form").addEventListener("input", (e) => { if (e.target.id !== "pl-q") changed(); });
    $("advantage").addEventListener("change", () => { syncAdvantage(); changed(); });
    $("as-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const form = $("as-form");
      fieldError(form, null);
      const c = campaign();
      if (!c) { fieldError(form, "campaign", "Pick the campaign it goes in"); return; }
      const s = spec();
      const yes = await confirmDialog({ title: `Create “${s.name || "the ad set"}”?`,
        body: `<p>In ${esc(c.name)}, switched off and with no ads yet. ${c.daily_budget_cents != null ? "It shares the campaign's budget once it's on." : `Its budget: ${esc(money(s.daily_budget_cents || 0, { exact: true }))} a day once it's on.`}</p><p class="muted">${esc($("summary").textContent)}</p>`,
        confirm: "Create (off)" });
      if (!yes) return;
      $("create").disabled = true;
      try {
        const r = await api("/api/adsets", { method: "POST", body: { campaign_id: c.id, template_adset_id: $("template").value, spec: s } });
        toast("Ad set created, switched off. Add an ad to it next.");
        markSaved();
        location.href = `/new-ad.html?adset=${encodeURIComponent(r.id)}`;
      } catch (err) {
        $("create").disabled = false;
        const field = err.body && err.body.field;
        if (field) {
          const target = { name: "name", locations: "locations", age: "age", end: "end", budget: "budget", campaign: "campaign" }[field];
          fieldError(form, target, err.message);
        } else toast(err.message, "bad");
      }
    });
  }
}
