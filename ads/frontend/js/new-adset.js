import { api } from "./api.js";
import { boot, confirmDialog, esc, fieldError, icon, toast } from "./ui.js";
import { money } from "./format.js";

const $ = (id) => document.getElementById(id);
let opts;
let locations = [];
let hints = [];

const label = (l) => (l.kind === "pin" ? `${l.name || "Map pin"}` : l.name);
const kindWord = { pin: "Area", city: "City", region: "State", zip: "ZIP" };

function renderPlaces() {
  $("places").innerHTML = locations.length ? locations.map((l, i) => `<li>
      <span class="place-kind">${kindWord[l.kind]}</span><b>${esc(label(l))}</b>
      ${l.kind === "pin" || l.kind === "city" ? `<label class="sr-only" for="r-${i}">Radius for ${esc(label(l))}</label>
        <select class="input radius" id="r-${i}" data-radius="${i}">${radii(l).map((r) => `<option value="${r}" ${r === Number(l.radius) ? "selected" : ""}>+ ${r} mi</option>`).join("")}</select>` : ""}
      <button type="button" class="btn btn-quiet btn-small" data-remove="${i}" aria-label="Remove ${esc(label(l))}">Remove</button>
    </li>`).join("") : '<li class="muted">No places yet. Add one below.</li>';
}

function radii(l) {
  const [lo, hi] = l.kind === "city" ? opts.city_radius : opts.pin_radius;
  const set = new Set([lo, 10, 15, 20, 25, 30, 40, hi, Number(l.radius)].filter((r) => r >= lo && r <= hi));
  return [...set].sort((a, b) => a - b);
}

function spec() {
  const n = (id) => ($(id).value === "" ? null : Number($(id).value));
  const dollars = $("budget").value.trim();
  return {
    name: $("name").value, locations, age_min: n("age_min"), age_max: n("age_max"),
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
  $("template").innerHTML = all.map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("");
  if (all.some((s) => s.id === keep)) $("template").value = keep;
}

function syncAdvantage() {
  const on = $("advantage").checked;
  $("suggest-field").hidden = !on;
  $("age-hint").textContent = on ? `Hard limits. With Advantage+ audience the minimum can be at most ${opts.advantage_max_age_min}.` : "Only people in this range see it.";
}

function summary() {
  const s = spec();
  const parts = [`Ages ${s.age_min ?? 18}–${s.age_max ?? 65}${(s.age_max ?? 65) >= 65 ? "+" : ""}`];
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
    if (!locations.length) { $("estimate").textContent = "—"; return; }
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
    const t = await api(`/api/adsets/template/${encodeURIComponent($("template").value)}`);
    locations = t.locations; hints = t.hints;
    $("age_min").value = t.age_min; $("age_max").value = t.age_max;
    $("suggest_min").value = t.suggest_min ?? ""; $("suggest_max").value = t.suggest_max ?? "";
    $("advantage").checked = t.advantage; $("keep_hints").checked = t.keep_hints && hints.length > 0;
    $("hints").textContent = hints.join(", ");
    $("hints-row").hidden = !hints.length;
    renderPlaces(); syncAdvantage(); changed();
  } catch (err) { toast(err.message, "bad"); }
}

// Place search: Meta's own place list, so every key is one Meta accepts.
let searchSeq = 0;
let searchTimer;
let results = [];
function showResults(list) {
  results = list;
  const box = $("place-results");
  box.innerHTML = list.map((p, i) => `<li role="option" id="pr-${i}" data-pick="${i}" tabindex="-1"><span class="place-kind">${kindWord[p.kind]}</span>${esc(p.name)}</li>`).join("")
    || '<li class="muted" role="option" aria-disabled="true">Nothing found</li>';
  box.hidden = false;
  $("place-q").setAttribute("aria-expanded", "true");
}
function hideResults() { $("place-results").hidden = true; $("place-q").setAttribute("aria-expanded", "false"); }
function pick(i) {
  const p = results[i];
  if (!p) return;
  if (!locations.some((l) => l.key === p.key && l.kind === p.kind)) locations.push({ ...p, ...(p.kind === "city" ? { radius: 25 } : {}) });
  $("place-q").value = ""; hideResults(); renderPlaces(); changed(); $("place-q").focus();
}

const me = await boot({ page: "ads", admin: true });
if (me) {
  $("crumb").innerHTML = `${icon("back")}<span>Ads</span>`;
  try { opts = await api("/api/adsets/new/options"); } catch (err) { toast(err.message, "bad"); }
  if (!opts || !opts.campaigns.length || !opts.adsets.length) {
    document.querySelector(".new-ad-layout").innerHTML = `<section class="panel empty"><h3>Nothing to build on yet</h3><p>A new ad set starts from an existing one. Once your campaigns are synced from Meta, come back here.</p><a class="btn" href="/ads.html">Back to ads</a></section>`;
  } else {
    $("campaign").innerHTML = opts.campaigns.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}${c.effective_status === "ACTIVE" ? "" : " (off)"}</option>`).join("");
    const want = new URLSearchParams(location.search).get("campaign");
    if (want && opts.campaigns.some((c) => c.id === want)) $("campaign").value = want;
    syncCampaign();
    await loadTemplate();
    $("campaign").addEventListener("change", () => { syncCampaign(); loadTemplate(); });
    $("template").addEventListener("change", loadTemplate);
    $("as-form").addEventListener("input", (e) => { if (e.target.id !== "place-q") changed(); });
    $("advantage").addEventListener("change", () => { syncAdvantage(); changed(); });
    $("places").addEventListener("change", (e) => {
      const r = e.target.closest("[data-radius]");
      if (r) { locations[Number(r.dataset.radius)].radius = Number(r.value); changed(); }
    });
    $("places").addEventListener("click", (e) => {
      const b = e.target.closest("[data-remove]");
      if (b) { locations.splice(Number(b.dataset.remove), 1); renderPlaces(); changed(); }
    });
    $("place-q").addEventListener("input", () => {
      clearTimeout(searchTimer);
      const q = $("place-q").value.trim();
      if (q.length < 2) { hideResults(); return; }
      searchTimer = setTimeout(async () => {
        const mine = ++searchSeq;
        try { const r = await api(`/api/adsets/places?q=${encodeURIComponent(q)}`); if (mine === searchSeq) showResults(r.items); }
        catch (err) { if (mine === searchSeq) toast(err.message, "bad"); }
      }, 250);
    });
    $("place-q").addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" && results.length) { e.preventDefault(); $("pr-0")?.focus(); }
      if (e.key === "Escape") hideResults();
      if (e.key === "Enter") { e.preventDefault(); if (results.length) pick(0); }
    });
    $("place-results").addEventListener("keydown", (e) => {
      const li = e.target.closest("[data-pick]");
      if (!li) return;
      const i = Number(li.dataset.pick);
      if (e.key === "Enter") { e.preventDefault(); pick(i); }
      if (e.key === "ArrowDown") { e.preventDefault(); $(`pr-${i + 1}`)?.focus(); }
      if (e.key === "ArrowUp") { e.preventDefault(); (i ? $(`pr-${i - 1}`) : $("place-q")).focus(); }
      if (e.key === "Escape") { hideResults(); $("place-q").focus(); }
    });
    $("place-results").addEventListener("click", (e) => { const li = e.target.closest("[data-pick]"); if (li) pick(Number(li.dataset.pick)); });
    document.addEventListener("click", (e) => { if (!e.target.closest(".place-add")) hideResults(); });

    $("as-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const form = $("as-form");
      fieldError(form, null);
      const c = campaign();
      const s = spec();
      const yes = await confirmDialog({ title: `Create “${s.name || "the ad set"}”?`,
        body: `<p>In ${esc(c.name)}, switched off and with no ads yet. ${c.daily_budget_cents != null ? "It shares the campaign's budget once it's on." : `Its budget: ${esc(money(s.daily_budget_cents || 0, { exact: true }))} a day once it's on.`}</p><p class="muted">${esc($("summary").textContent)}</p>`,
        confirm: "Create (off)" });
      if (!yes) return;
      $("create").disabled = true;
      try {
        const r = await api("/api/adsets", { method: "POST", body: { campaign_id: c.id, template_adset_id: $("template").value, spec: s } });
        toast("Ad set created, switched off. Add an ad to it next.");
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
