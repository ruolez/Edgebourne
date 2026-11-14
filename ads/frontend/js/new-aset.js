import { api } from "./api.js";
import { boot, cancelLink, confirmDialog, esc, fieldError, icon, toast, guardLeaving, markSaved, returnCrumbs, withFrom } from "./ui.js";
import { money } from "./format.js";
import { placeLabel, placesHtml, placesWidget } from "./places.js";
import { builder } from "./builder.js";
import { draftNoteHtml, draftParam, loadDraftSpec } from "./drafts.js";
import { audPicker, audPickHtml, audWords, savedSelectHtml } from "./audpick.js";

const $ = (id) => document.getElementById(id);
let opts;
let hints = [];
const locations_ = () => places.get();

let places;
let steps = null;
// AM-D: audiences to include / leave out, and the saved audience the places and ages were filled from (its hints go along).
let aud = null;
let savedId = null;
// AM-B: filled in from an Ads Manager draft (?draft=<id>): its id goes with Create, its audience hints when no ad set is the start.
const draftP = draftParam();
let draft = null;
let draftFlex = [];
const label = placeLabel;

function spec() {
  const n = (id) => ($(id).value === "" ? null : Number($(id).value));
  const dollars = $("budget").value.trim();
  return {
    name: $("name").value, locations: locations_(), age_min: n("age_min"), age_max: n("age_max"),
    suggest_min: $("advantage").checked ? n("suggest_min") : null, suggest_max: $("advantage").checked ? n("suggest_max") : null,
    advantage: $("advantage").checked, keep_hints: $("keep_hints").checked, flexible_spec: $("template").value ? [] : draftFlex,
    start_day: $("start_day").value || null, start_hour: 0, end_day: $("end_day").value || null, end_hour: 23,
    daily_budget_cents: dollars ? Math.round(Number(dollars) * 100) : null,
    include_audiences: aud ? aud.get().include : [], exclude_audiences: aud ? aud.get().exclude : [], saved_audience_id: savedId,
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
  if (aud) aud.redraw();
  $("age-hint").textContent = on ? `Hard limits. With Advantage+ audience the minimum can be at most ${opts.advantage_max_age_min}.` : "Only people in this range see it.";
}

function whoLine() {
  const s = spec();
  const parts = [`Ages ${s.age_min ?? 18}–${s.age_max ?? 65}${(s.age_max ?? 65) >= 65 ? "+" : ""}`];
  const locations = locations_();
  if (locations.length) parts.push(locations.length <= 3 ? locations.map((l) => `${label(l)}${l.radius ? ` (${l.radius} mi)` : ""}`).join(", ") : `${locations.length} places`);
  if (s.keep_hints && hints.length) parts.push(`Hints: ${hints.slice(0, 3).join(", ")}${hints.length > 3 ? ` +${hints.length - 3}` : ""}`);
  if (s.advantage) parts.push("Advantage+ audience");
  const a = aud ? audWords(aud.names()) : "";
  if (a) parts.push(a[0].toUpperCase() + a.slice(1));
  return parts.join(" · ");
}

// The server's own check (POST /api/adsets/check), so the steps and the fields say what Create would refuse.
async function check() {
  const r = await api("/api/adsets/check", { method: "POST", body: { campaign_id: $("campaign").value, template_adset_id: $("template").value, spec: spec() } });
  return r.problems;
}

function summary() {
  const c = campaign();
  const s = spec();
  const tpl = $("template").selectedOptions[0];
  const dates = s.start_day || s.end_day ? `${s.start_day ? `from ${s.start_day}` : "from when it's turned on"}${s.end_day ? ` to ${s.end_day}` : ""}` : "Runs while it's on";
  const money_ = c && c.daily_budget_cents != null ? "shares the campaign's budget" : s.daily_budget_cents ? `${money(s.daily_budget_cents, { exact: true })} a day` : "";
  return {
    where: c ? `${s.name.trim() || "Unnamed"} · in ${c.name}${tpl && tpl.value ? ` · from ${tpl.textContent}` : ""}` : "",
    who: places.get().length ? whoLine() : "",
    when: [dates, money_].filter(Boolean).join(" · "),
  };
}

function ready(problems) {
  const n = problems.length;
  $("ready").textContent = n ? `${n} ${n === 1 ? "thing" : "things"} to finish first.` : "Ready to create. It starts switched off and empty.";
  $("ready").dataset.ok = String(!n);
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

function changed() { estimateSoon(); if (steps) steps.soon(); }

// AM-D: Start from a saved audience fills places, ages, hints and its audiences; nothing is sent until Create.
function applySaved() {
  const s = (opts.saved_audiences || []).find((x) => x.id === $("as-saved").value);
  savedId = s ? s.id : null;
  if (s) {
    const b = s.builder;
    places.set(b.locations); hints = b.hints;
    $("age_min").value = b.age_min; $("age_max").value = b.age_max;
    $("suggest_min").value = b.suggest_min ?? ""; $("suggest_max").value = b.suggest_max ?? "";
    $("advantage").checked = b.advantage; $("keep_hints").checked = hints.length > 0;
    $("hints").textContent = hints.join(", "); $("hints-row").hidden = !hints.length;
    aud.set(b.include_audiences, b.exclude_audiences);
    syncAdvantage();
  }
  changed();
}

async function loadTemplate() {
  try {
    const t = $("template").value ? await api(`/api/adsets/template/${encodeURIComponent($("template").value)}`)
      : { locations: [], hints: [], age_min: 25, age_max: 65, suggest_min: null, suggest_max: null, advantage: true, keep_hints: false };
    places.set(t.locations); hints = t.hints;
    if (aud) aud.set(t.include_audiences || [], t.exclude_audiences || []);
    savedId = null;
    if ($("as-saved")) $("as-saved").value = "";
    $("age_min").value = t.age_min; $("age_max").value = t.age_max;
    $("suggest_min").value = t.suggest_min ?? ""; $("suggest_max").value = t.suggest_max ?? "";
    $("advantage").checked = t.advantage; $("keep_hints").checked = t.keep_hints && hints.length > 0;
    $("hints").textContent = hints.join(", ");
    $("hints-row").hidden = !hints.length;
    syncAdvantage(); changed();
  } catch (err) { toast(err.message, "bad"); }
}

// AM-B: the page filled in from an Ads Manager draft of a new ad set in a running campaign. Only the fields change.
async function fillFromDraft() {
  draft = await loadDraftSpec(draftP);
  $("as-form").insertAdjacentHTML("afterbegin", draftNoteHtml(draft));
  if (draft.error || draft.page !== "new-adset") return;
  const { campaign_id: cid, spec: f } = draft.spec;
  if (opts.campaigns.some((c) => c.id === cid)) { $("campaign").value = cid; syncCampaign(); }
  $("template").value = "";
  $("name").value = f.name;
  places.set(f.locations);
  hints = f.hints; draftFlex = f.flexible_spec;
  $("age_min").value = f.age_min; $("age_max").value = f.age_max;
  $("suggest_min").value = f.suggest_min ?? ""; $("suggest_max").value = f.suggest_max ?? "";
  $("advantage").checked = f.advantage;
  $("keep_hints").checked = f.keep_hints && hints.length > 0;
  $("hints").textContent = hints.join(", "); $("hints-row").hidden = !hints.length;
  $("start_day").value = f.start_day || ""; $("end_day").value = f.end_day || "";
  if (f.daily_budget_cents) $("budget").value = (f.daily_budget_cents / 100).toFixed(2);
  syncAdvantage(); changed();
}

const me = await boot({ page: "new-adset", admin: true });
if (me) guardLeaving();
if (me) {
  $("crumb").innerHTML = `${icon("back")}<span>Back</span>`;
  const back = returnCrumbs("New ad set");
  $("create")?.insertAdjacentHTML("afterend", cancelLink(back));
  try { opts = await api("/api/adsets/new/options"); } catch (err) { toast(err.message, "bad"); }
  if (!opts || !opts.campaigns.length || !opts.adsets.length) {
    document.querySelector(".new-ad-layout").innerHTML = `<section class="panel empty"><h3>Nothing to build on yet</h3><p>A new ad set starts from an existing one. Once your campaigns are synced from Meta, come back here.</p><a class="btn" href="/ads.html">Back to ads</a></section>`;
  } else {
    $("places-box").innerHTML = placesHtml("pl");
    places = placesWidget("pl", { cityRadius: opts.city_radius, pinRadius: opts.pin_radius, onChange: changed });
    $("aud-box").innerHTML = audPickHtml("aud");
    aud = audPicker("aud", { audiences: opts.audiences || [], words: opts.audience_words || {}, onChange: changed,
      special: () => ((campaign() || {}).special_ad_categories || []).length > 0, advantage: () => $("advantage").checked });
    $("as-saved-box").innerHTML = savedSelectHtml("as-saved", opts.saved_audiences);
    if ($("as-saved")) $("as-saved").addEventListener("change", applySaved);
    $("campaign").innerHTML = opts.campaigns.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}${c.effective_status === "ACTIVE" ? "" : " (off)"}</option>`).join("");
    const want = new URLSearchParams(location.search).get("campaign");
    if (want && opts.campaigns.some((c) => c.id === want)) $("campaign").value = want;
    else if (want) {
      // A deleted or archived campaign can't take new ad sets: never quietly build in another one (audit A3-105).
      $("campaign").insertAdjacentHTML("afterbegin", '<option value="" disabled>Pick a campaign</option>');
      $("campaign").value = "";
    }
    steps = builder({ form: $("as-form"), nav: $("stepper"), check, summary, onCheck: ready,
      steps: [{ id: "where", name: "Where it goes" }, { id: "who", name: "Who sees it" }, { id: "when", name: "When and how much" }] });
    syncCampaign();
    if (want && !campaign()) $("budget-note").textContent = "The campaign you came from is deleted or archived, so it can't get new ad sets. Pick one that's still running.";
    await loadTemplate();
    if (draftP) await fillFromDraft();
    $("campaign").addEventListener("change", () => { syncCampaign(); loadTemplate(); aud.redraw(); });
    $("as-form").addEventListener("change", (e) => { if (!["campaign", "template", "as-saved"].includes(e.target.id)) changed(); });
    $("template").addEventListener("change", loadTemplate);
    $("as-form").addEventListener("input", (e) => { if (e.target.id !== "pl-q" && !e.target.closest("[data-aud-q]")) changed(); });
    $("advantage").addEventListener("change", () => { syncAdvantage(); aud.redraw(); changed(); });
    $("as-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const form = $("as-form");
      if ($("create").disabled) return;
      // Checked first, every field marked: the confirmation only opens when there's nothing left to fix.
      $("create").disabled = true;
      let ok = false;
      try { ok = await steps.validate(); } catch (err) { toast(err.message, "bad"); }
      $("create").disabled = false;
      if (!ok) return;
      const c = campaign();
      const s = spec();
      const yes = await confirmDialog({ title: `Create “${s.name || "the ad set"}”?`,
        body: `<p>In ${esc(c.name)}, switched off and with no ads yet. ${c.daily_budget_cents != null ? "It shares the campaign's budget once it's on." : `Its budget: ${esc(money(s.daily_budget_cents || 0, { exact: true }))} a day once it's on.`}</p><p class="muted">${esc(whoLine())}</p>`,
        confirm: "Create (off)" });
      if (!yes) return;
      $("create").disabled = true;
      try {
        const r = await api("/api/adsets", { method: "POST", body: { campaign_id: c.id, template_adset_id: $("template").value, spec: s,
          ...(draft && !draft.error ? { draft_id: draft.draft.id, again: Boolean(draftP.again) } : {}) } });
        markSaved();
        // On to its first ad; that page says the ad set was made and links to it. Cancel there still goes back.
        const fromDraft = draft && !draft.error ? `&draft_left=${encodeURIComponent(draft.draft.id)}` : "";
        location.href = withFrom(`/new-ad.html?adset=${encodeURIComponent(r.id)}&made=adset${fromDraft}`, back);
      } catch (err) {
        $("create").disabled = false;
        const field = err.body && err.body.field;
        if (field) {
          fieldError(form, field, err.message);
        } else toast(err.message, "bad");
      }
    });
  }
}
