import { api } from "./api.js";
import { boot, cancelLink, confirmDialog, entityLink, esc, fieldError, icon, toast, guardLeaving, markSaved, returnCrumbs } from "./ui.js";
import { STATUS as FORMAT_STATUS, CTA_LABELS, money, currencySymbol } from "./format.js";
import { placesHtml, placesWidget } from "./places.js";
import { mountUploader, waitReady } from "./uploader.js";
import { builder } from "./builder.js";
import { draftLeftHtml, draftNoteHtml, draftParam, loadDraftSpec } from "./drafts.js";
import { audPicker, audPickHtml, audWords, savedSelectHtml } from "./audpick.js";

const CLIENT_KEY = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);

const $ = (id) => document.getElementById(id);
let opts;
let places;
let hints = [];
let media = [];
let ads = [];
let steps = null;
let lastReview = null;
// AM-B: filled in from an Ads Manager draft (?draft=<id>): its id goes with Create, and its audience hints when no ad set is the start.
const draftP = draftParam();
let draft = null;
let draftFlex = [];
const videoPolls = new Map();  // video id → stops waiting for Meta to process it
// AM-D: audiences to include / leave out in the ad set, and the saved audience its places and ages came from.
let aud = null;
let savedId = null;

const STEPS = [{ id: "goal", name: "Goal" }, { id: "budget", name: "Budget" }, { id: "adset", name: "Who sees it" }, { id: "form", name: "Lead form" }, { id: "ads", name: "Ads" }];
const STATUS = FORMAT_STATUS;
const pill = (s) => { const [c, l] = STATUS[s] || ["", s ? s.toLowerCase().replace(/_/g, " ") : "Syncing…"]; return `<span class="pill ${c}">${esc(l)}</span>`; };

// ---------------------------------------------------------------- ads step

function blankAd() {
  const t = opts.templates[0];
  if (!t) return { name: "", title: "", body: "", template_ad_id: "", cta_type: "SIGN_UP", media: { kind: "none" } };  // a new account: its own words and media
  return { name: "", title: t.title || "", body: t.body || "", template_ad_id: t.id || "", cta_type: t.cta_type || "SIGN_UP", media: { kind: "same" } };
}

const mediaKey = (m) => `${m.kind}:${m.hash || m.video_id}`;
const asChoice = (m) => (m.kind === "image" ? { kind: "image", hash: m.hash } : { kind: "video", video_id: m.video_id });

function mediaOptions(ad) {
  const v = ad.media.kind === "same" ? "same" : ad.media.kind === "none" ? "" : `${ad.media.kind}:${ad.media.hash || ad.media.video_id}`;
  const same = ad.template_ad_id ? `<option value="same" ${v === "same" ? "selected" : ""}>Same image or video as the starting ad</option>` : "";
  const none = v === "" ? `<option value="" selected>${media.length ? "Choose an image or video" : "Upload one below first"}</option>` : "";
  return none + same +
    media.map((m) => { const k = mediaKey(m); return `<option value="${esc(k)}" ${k === v ? "selected" : ""}>${m.kind === "video" ? "Video" : "Image"}: ${esc(m.name || k)}${m.kind === "video" && m.ready === false ? " (Meta is processing it)" : ""}</option>`; }).join("");
}

function adCard(ad, i) {
  return `<fieldset class="cw-card" data-ad="${i}"><legend>Ad ${i + 1}</legend>
    <div class="grid-2">
      <div class="field"><label for="a-tpl-${i}">Starts from</label><select class="input" id="a-tpl-${i}" name="ad${i}-template" data-k="template_ad_id"><option value="" ${ad.template_ad_id ? "" : "selected"}>Nothing: new words and media</option>${opts.templates.map((t) => `<option value="${esc(t.id)}" ${t.id === ad.template_ad_id ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select></div>
      <div class="field"><label for="a-media-${i}">Image or video</label><select class="input" id="a-media-${i}" name="ad${i}-media" data-k="media">${mediaOptions(ad)}</select></div>
    </div>
    <div class="field"><label for="a-body-${i}">Primary text</label><textarea class="input" id="a-body-${i}" name="ad${i}-body" data-k="body" rows="4">${esc(ad.body)}</textarea></div>
    <div class="grid-2">
      <div class="field"><label for="a-title-${i}">Headline</label><input class="input" id="a-title-${i}" name="ad${i}-title" data-k="title" value="${esc(ad.title)}" maxlength="255"></div>
      <div class="field"><label for="a-cta-${i}">Button</label><select class="input" id="a-cta-${i}" name="ad${i}-cta" data-k="cta_type">${opts.cta_types.map((c) => `<option value="${c}" ${c === ad.cta_type ? "selected" : ""}>${esc(CTA_LABELS[c] || c)}</option>`).join("")}</select></div>
    </div>
    <div class="row"><div class="field grow"><label for="a-name-${i}">Ad name <span class="muted">(only you see this)</span></label><input class="input" id="a-name-${i}" name="ad${i}-name" data-k="name" value="${esc(ad.name)}" placeholder="N6 - What it's about" maxlength="200"></div>
      ${ads.length > 1 ? `<button type="button" class="btn btn-quiet btn-small" data-ad-remove="${i}">Remove</button>` : ""}</div>
  </fieldset>`;
}

function renderAds() {
  $("cr-list").innerHTML = ads.map(adCard).join("");
  $("cr-add").hidden = ads.length >= opts.max_ads;
}

// Only each ad's media list is rewritten when an upload lands or a video is ready: the words someone is
// typing (and where the caret is) are left alone.
function refreshMediaLists() {
  ads.forEach((ad, i) => { const sel = $(`a-media-${i}`); if (sel) sel.innerHTML = mediaOptions(ad); });
}

function readAds() {
  document.querySelectorAll("[data-ad]").forEach((card) => {
    const ad = ads[Number(card.dataset.ad)];
    card.querySelectorAll("[data-k]").forEach((el) => {
      if (el.dataset.k === "media") {
        const [kind, id] = el.value.split(":");
        ad.media = kind === "same" ? { kind: "same" } : kind === "image" ? { kind, hash: id } : kind === "video" ? { kind, video_id: id } : { kind: "none" };
      } else ad[el.dataset.k] = el.value;
    });
  });
}

// ---------------------------------------------------------------- spec, check, review

function spec() {
  readAds();
  const n = (id) => ($(id).value === "" ? null : Number($(id).value));
  const dollars = $("c-budget").value.trim();
  return {
    name: $("c-name").value, daily_budget_cents: dollars ? Math.round(Number(dollars) * 100) : null, form_id: $("f-form").value,
    adset: { template_adset_id: $("s-template").value, name: $("s-name").value, locations: places.get(), age_min: n("s-age-min"), age_max: n("s-age-max"),
      advantage: $("s-advantage").checked, suggest_min: $("s-advantage").checked ? n("s-sug-min") : null, suggest_max: $("s-advantage").checked ? n("s-sug-max") : null,
      keep_hints: $("s-hints").checked, flexible_spec: $("s-template").value ? [] : draftFlex,
      start_day: $("s-start").value || null, start_hour: 0, end_day: $("s-end").value || null, end_hour: 23,
      include_audiences: aud ? aud.get().include : [], exclude_audiences: aud ? aud.get().exclude : [], saved_audience_id: savedId },
    ads,
    ...(draft && !draft.error ? { draft_id: draft.draft.id, again: Boolean(draftP.again) } : {}),
  };
}

function reviewHtml(r) {
  return `<dl class="facts review-facts">
      <div><dt>Campaign</dt><dd>${esc(r.campaign)}</dd></div>
      <div><dt>Ad set</dt><dd>${esc(r.adset)}</dd></div>
      <div><dt>Form</dt><dd>${esc(r.form)}</dd></div>
      <div><dt>Ads</dt><dd>${r.ads.map((a) => `<p class="flush"><b>${esc(a.name)}</b> · “${esc(a.title)}” · ${esc(a.media)}${a.starts_from ? ` from ${esc(a.starts_from)}` : ""}</p>${a.warnings.map((w) => `<p class="note warn small-note">${esc(w)}</p>`).join("")}`).join("")}</dd></div>
    </dl>`;
}

// The server's check (POST /api/builds/check) plus what only this page knows: a chosen video Meta is
// still processing can't go in an ad yet.
async function check() {
  const s = spec();
  const r = await api("/api/builds/check", { method: "POST", body: s });
  const waiting = s.ads.flatMap((a, i) => {
    const m = a.media.kind === "video" && media.find((x) => x.video_id === a.media.video_id);
    return m && m.ready === false ? [{ step: "ads", field: `ad${i}-media`, message: `Ad ${i + 1}: Meta is still processing its video; give it a minute` }] : [];
  });
  lastReview = r.review || null;
  return [...r.problems, ...waiting];
}

function summary() {
  const n = (v) => (v === "" ? null : Number(v));
  const dollars = $("c-budget").value.trim();
  const places_ = places.get();
  const form = $("f-form").selectedOptions[0];
  const named = ads.map((a) => a.name.trim()).filter(Boolean);
  return {
    goal: $("c-name").value.trim(),
    budget: dollars && Number(dollars) > 0 ? `${money(Math.round(Number(dollars) * 100), { exact: true })} a day` : "",
    adset: places_.length ? `${$("s-name").value.trim() || "Unnamed"} · ${places_.length === 1 ? "1 place" : `${places_.length} places`} · ages ${n($("s-age-min").value) ?? 18}–${n($("s-age-max").value) ?? 65}${aud && audWords(aud.names()) ? ` · ${audWords(aud.names())}` : ""}` : "",
    form: form && form.value ? form.textContent : "",
    ads: named.length ? named.join(", ") : "",
  };
}

function ready(problems) {
  const n = problems.length;
  $("ready").textContent = n ? `${n} ${n === 1 ? "thing" : "things"} to finish first.` : "Ready to create. Everything starts switched off.";
  $("ready").dataset.ok = String(!n);
  $("review-facts").innerHTML = !n && lastReview ? reviewHtml(lastReview) : "";
}

let estSeq = 0;
let estTimer;
function estimateSoon() {
  clearTimeout(estTimer);
  estTimer = setTimeout(async () => {
    const mine = ++estSeq;
    const s = spec();
    if (!s.adset.locations.length) { $("s-estimate").textContent = "—"; return; }
    try {
      const e = await api("/api/adsets/estimate", { method: "POST", body: { template_adset_id: s.adset.template_adset_id, spec: s.adset } });
      const m = (v) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${Math.round(v / 1e3)}K` : String(v));
      if (mine === estSeq) $("s-estimate").textContent = e.lower ? `${m(e.lower)} – ${m(e.upper)} people a month` : "—";
    } catch (err) { if (mine === estSeq) $("s-estimate").textContent = "—"; }
  }, 450);
}

function changed() { readAds(); if (steps) steps.soon(); }

// AM-D: Start from a saved audience fills the ad set's places, ages, hints and audiences; nothing is sent until Create.
function applySaved() {
  const s = (opts.saved_audiences || []).find((x) => x.id === $("s-saved").value);
  savedId = s ? s.id : null;
  if (s) {
    const b = s.builder;
    places.set(b.locations); hints = b.hints;
    $("s-age-min").value = b.age_min; $("s-age-max").value = b.age_max;
    $("s-sug-min").value = b.suggest_min ?? ""; $("s-sug-max").value = b.suggest_max ?? "";
    $("s-advantage").checked = b.advantage; $("s-suggest").hidden = !b.advantage;
    $("s-hints").checked = hints.length > 0;
    $("s-hints-text").textContent = hints.join(", "); $("s-hints-row").hidden = !hints.length;
    aud.set(b.include_audiences, b.exclude_audiences);
  }
  changed(); estimateSoon();
}

async function loadTemplate() {
  try {
    const t = $("s-template").value ? await api(`/api/adsets/template/${encodeURIComponent($("s-template").value)}`)
      // From scratch: Advantage+ audience with the minimum age Meta allows for it (25) and 65.
      : { locations: [], hints: [], age_min: 25, age_max: 65, suggest_min: null, suggest_max: null, advantage: true, keep_hints: false };
    places.set(t.locations); hints = t.hints;
    if (aud) aud.set(t.include_audiences || [], t.exclude_audiences || []);
    savedId = null;
    if ($("s-saved")) $("s-saved").value = "";
    $("s-age-min").value = t.age_min; $("s-age-max").value = t.age_max;
    $("s-sug-min").value = t.suggest_min ?? ""; $("s-sug-max").value = t.suggest_max ?? "";
    $("s-advantage").checked = t.advantage; $("s-hints").checked = t.keep_hints && hints.length > 0;
    $("s-hints-text").textContent = hints.join(", "); $("s-hints-row").hidden = !hints.length;
    $("s-suggest").hidden = !t.advantage;
    if (aud) aud.redraw();
    changed(); estimateSoon();
  } catch (err) { toast(err.message, "bad"); }
}

async function loadForms() {
  const keep = $("f-form").value;
  try { opts.forms = (await api("/api/forms")).items.filter((f) => f.status !== "ARCHIVED"); } catch (err) { /* keep the old list */ }
  $("f-form").innerHTML = '<option value="">Pick a form</option>' + opts.forms.map((f) => `<option value="${esc(f.id)}">${esc(f.name)}</option>`).join("");
  if (keep) $("f-form").value = keep;
  else if (opts.forms.length === 1) $("f-form").value = opts.forms[0].id;
}

// AM-B: the page filled in from an Ads Manager draft. Only the fields change: everything is checked as typing is, and
// Create still asks first and makes everything off.
async function fillFromDraft() {
  draft = await loadDraftSpec(draftP);
  $("nc-form").insertAdjacentHTML("afterbegin", draftNoteHtml(draft));
  if (draft.error || draft.page !== "new-campaign") return;
  const f = draft.spec;
  const a = f.adset;
  $("c-name").value = f.name;
  $("c-budget").value = f.daily_budget_cents ? (f.daily_budget_cents / 100).toFixed(2) : "";
  $("s-template").value = "";
  $("s-name").value = a.name;
  places.set(a.locations);
  hints = a.hints; draftFlex = a.flexible_spec;
  $("s-age-min").value = a.age_min; $("s-age-max").value = a.age_max;
  $("s-sug-min").value = a.suggest_min ?? ""; $("s-sug-max").value = a.suggest_max ?? "";
  $("s-advantage").checked = a.advantage; $("s-suggest").hidden = !a.advantage;
  $("s-hints").checked = a.keep_hints && hints.length > 0;
  $("s-hints-text").textContent = hints.join(", "); $("s-hints-row").hidden = !hints.length;
  $("s-start").value = a.start_day || ""; $("s-end").value = a.end_day || "";
  $("f-form").value = f.form_id && [...$("f-form").options].some((o) => o.value === f.form_id) ? f.form_id : "";
  // The draft's picture or video joins each ad's list even when this page's library didn't list it.
  for (const ad of f.ads) {
    const m = ad.media;
    if (m.kind !== "none" && !media.some((x) => mediaKey(x) === mediaKey(m))) {
      media.push({ ...m, name: m.kind === "video" ? "Video from the draft" : "Picture from the draft", ready: true });
    }
  }
  ads = f.ads.length ? f.ads.map((x) => ({ ...x, media: { ...x.media } })) : [blankAd()];
  renderAds();
  changed(); estimateSoon();
}

// ---------------------------------------------------------------- after creating

function buildView(b) {
  const m = b.made;
  const s = b.entity_status;
  const r = b.review;
  const rows = [
    ["Campaign", r.campaign, m.campaign_id],
    ["Ad set", r.adset, m.adset_id],
    ...r.ads.map((a, i) => ["Ad", `${a.name} · “${a.title}”`, (m.ads || {})[String(i)], true]),
  ];
  const publishBox = b.status === "created" ? `<section class="panel publish-card">
      <div class="panel-head"><h2>Publish</h2><p>Turns on the ads, then the ad set, then the campaign last, so nothing spends until everything is on.</p></div>
      <form class="panel-body stack tight" id="pub-form" novalidate>
        <p class="flush">It will spend up to <b>${esc(money(r.budget_cents, { exact: true }))} a day</b> (Meta may go up to 75% over on a good day and evens out over the week). Meta reviews the ads first, usually within a day.</p>
        <div class="field"><label for="pub-typed">Type the daily budget to confirm</label><span class="money-input">${currencySymbol()}<input class="input" id="pub-typed" name="typed" inputmode="decimal" autocomplete="off"></span></div>
        <div class="row"><button class="btn btn-primary" type="submit">Publish</button><span class="muted small">Check each ad's preview first (links above).</span></div>
      </form></section>`
    : b.status === "partial" ? `<section class="panel"><div class="panel-body stack tight"><p class="note bad flush">${esc(b.error || "It stopped halfway.")}</p>
        <p class="muted flush">What was made stays, switched off. Fix the cause (often in Ads Manager or Settings), then finish: nothing is made twice.</p>
        <div class="row"><button type="button" class="btn btn-primary" id="resume">Finish creating</button></div></div></section>`
    : `<section class="panel"><div class="panel-body"><p class="note ok flush">Published. Meta is reviewing the ads; they start delivering once approved. Follow it on ${m.campaign_id ? `its campaign page: ${entityLink("campaign", m.campaign_id, r.campaign.split(" · ")[0])}` : '<a href="/ads.html">Ads</a>'}.</p></div></section>`;
  $("build").innerHTML = `<section class="panel"><div class="panel-head"><h2>${b.status === "published" ? "Published" : b.status === "created" ? "Created, switched off" : "Partly created"}</h2></div>
      <div class="panel-body"><table class="table middle build-table"><tbody>${rows.map(([kind, what, id, isAd]) => `<tr>
        <th scope="row">${esc(kind)}</th><td>${id && !isAd ? entityLink(kind === "Campaign" ? "campaign" : "adset", id, what) : esc(what)}</td><td>${id ? pill(s[id]) : '<span class="pill">Not made yet</span>'}</td>
        <td class="row-actions">${id && isAd ? `<a class="btn btn-quiet btn-small" href="/ad.html?id=${encodeURIComponent(id)}" target="_blank" rel="noopener">Preview</a>` : ""}</td></tr>`).join("")}</tbody></table></div></section>
    ${b.draft && b.status !== "published" ? draftLeftHtml(b.draft) : ""}
    ${publishBox}`;
  $("wizard").hidden = true;
  $("build").hidden = false;
  $("title").textContent = r.campaign.split(" · ")[0];
  const pf = $("pub-form");
  if (pf) pf.addEventListener("submit", async (e) => {
    e.preventDefault();
    fieldError(pf, null);
    const btn = pf.querySelector("button[type=submit]");
    if (btn.disabled) return;
    const yes = await confirmDialog({ title: "Publish now?", body: `<p>Turns on everything in this campaign at up to ${esc(money(r.budget_cents, { exact: true }))} a day.</p>`, confirm: "Publish" });
    if (!yes) return;
    btn.disabled = true;
    try { buildView(await api(`/api/builds/${b.id}/publish`, { method: "POST", body: { typed: $("pub-typed").value } })); markSaved(); toast("Published"); }
    catch (err) { btn.disabled = false; if (err.body && err.body.field) fieldError(pf, "typed", err.message); else toast(err.message, "bad"); }
  });
  const rb = $("resume");
  if (rb) rb.addEventListener("click", async () => {
    rb.disabled = true;
    try { buildView(await api(`/api/builds/${b.id}/resume`, { method: "POST" })); markSaved(); } catch (err) { toast(err.message, "bad"); rb.disabled = false; }
  });
}

// ---------------------------------------------------------------- start

const me = await boot({ page: "new-campaign", admin: true });
if (me) guardLeaving();
if (me) {
  $("crumb").innerHTML = `${icon("back")}<span>Back</span>`;
  const back = returnCrumbs("New campaign");
  $("nc-create")?.insertAdjacentHTML("afterend", cancelLink(back));
  const buildId = new URLSearchParams(location.search).get("build");
  if (buildId) {
    try { buildView(await api(`/api/builds/${encodeURIComponent(buildId)}`)); } catch (err) { toast(err.message, "bad"); }
  } else {
    try { [opts, media] = await Promise.all([api("/api/builds/options"), api("/api/media").then((d) => d.items).catch(() => [])]); }
    catch (err) { toast(err.message, "bad"); }
    if (!opts) {
      $("wizard").innerHTML = '<section class="panel empty"><h3>Couldn\'t load the wizard</h3><p>Check this account\'s Meta connection in Settings.</p><a class="btn" href="/settings.html#meta">Open Settings</a></section>';
    } else {
      $("places-box").innerHTML = placesHtml("nc");
      places = placesWidget("nc", { cityRadius: opts.city_radius, pinRadius: opts.pin_radius, onChange: () => { changed(); estimateSoon(); } });
      $("s-aud-box").innerHTML = audPickHtml("s-aud");
      aud = audPicker("s-aud", { audiences: opts.audiences || [], words: opts.audience_words || {}, special: () => false,
        advantage: () => $("s-advantage").checked, onChange: () => { changed(); estimateSoon(); } });
      $("s-saved-box").innerHTML = savedSelectHtml("s-saved", opts.saved_audiences);
      if ($("s-saved")) $("s-saved").addEventListener("change", applySaved);
      $("s-template").innerHTML = opts.adsets.map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("")
        + '<option value="">Nothing: start from scratch</option>';
      $("budget-hint").textContent = `Shared by everything in the campaign. What runs now: ${money(opts.running_daily_cents, { exact: true })} a day.`;
      ads = [blankAd()];
      renderAds();
      steps = builder({ form: $("nc-form"), nav: $("stepper"), steps: STEPS, check, summary, onCheck: ready });
      // One uploader for every ad: what goes up joins each ad's list and fills the first ad that has nothing yet.
      mountUploader($("nc-uploader"), { id: "nc-file", onDone: (m) => {
        readAds();
        media = [m, ...media.filter((x) => mediaKey(x) !== mediaKey(m))];
        const empty = ads.find((a) => a.media.kind === "none");
        if (empty) empty.media = asChoice(m);
        refreshMediaLists();
        changed();
        toast(m.kind === "video" ? "Uploaded. Meta is processing the video." : "Image uploaded");
        if (m.kind === "video" && !videoPolls.has(m.video_id)) {
          videoPolls.set(m.video_id, waitReady(m.video_id, () => {
            videoPolls.delete(m.video_id);
            media.forEach((x) => { if (x.video_id === m.video_id) x.ready = true; });
            readAds(); refreshMediaLists(); changed();
          }));
        }
      } });
      $("s-template").addEventListener("change", loadTemplate);
      $("s-advantage").addEventListener("change", () => { $("s-suggest").hidden = !$("s-advantage").checked; aud.redraw(); });
      $("f-reload").addEventListener("click", loadForms);
      $("nc-form").addEventListener("input", (e) => { if (e.target.id !== "nc-q" && !e.target.closest("[data-aud-q]")) { changed(); if (e.target.closest('[data-step="adset"]')) estimateSoon(); } });
      $("nc-form").addEventListener("change", (e) => {
        const tpl = e.target.closest('[data-k="template_ad_id"]');
        if (tpl) {
          readAds();
          const ad = ads[Number(tpl.closest("[data-ad]").dataset.ad)];
          const t = opts.templates.find((x) => x.id === tpl.value) || {};
          Object.assign(ad, { template_ad_id: tpl.value, title: t.title || ad.title, body: t.body || ad.body, cta_type: opts.cta_types.includes(t.cta_type) ? t.cta_type : ad.cta_type });
          // Its own picture is picked (or uploaded) on purpose, never the newest one in the library by chance.
          if (!tpl.value && ad.media.kind === "same") ad.media = { kind: "none" };
          renderAds();
        }
        changed();
      });
      $("cr-add").addEventListener("click", () => { readAds(); ads.push(blankAd()); renderAds(); changed(); $(`a-name-${ads.length - 1}`).focus(); });
      $("cr-list").addEventListener("click", (e) => {
        const rm = e.target.closest("[data-ad-remove]");
        if (rm) { readAds(); ads.splice(Number(rm.dataset.adRemove), 1); renderAds(); changed(); }
      });
      $("nc-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        if ($("nc-create").disabled) return;
        // Checked first, every field marked: the confirmation only opens when nothing is left to fix.
        $("nc-create").disabled = true;
        let ok = false;
        try { ok = await steps.validate(); } catch (err) { toast(err.message, "bad"); }
        $("nc-create").disabled = false;
        if (!ok) return;
        const s = spec();
        const yes = await confirmDialog({ title: "Create everything, switched off?",
          body: `<p>A new campaign at ${esc(money(s.daily_budget_cents || 0, { exact: true }))} a day, one ad set and ${ads.length} ad${ads.length === 1 ? "" : "s"}. All switched off: nothing spends until you publish.</p>`,
          confirm: "Create (off)" });
        if (!yes) return;
        $("nc-create").disabled = true;
        $("nc-create").textContent = "Creating…";
        try {
          // One key per wizard: a double click or a retry after a timeout returns the same build.
          const b = await api("/api/builds", { method: "POST", body: { ...s, client_key: CLIENT_KEY } });
          markSaved();
          videoPolls.forEach((stop) => stop()); videoPolls.clear();
          const keep = new URLSearchParams(location.search).get("from");
          history.replaceState(null, "", `?build=${b.id}${keep ? `&from=${encodeURIComponent(keep)}` : ""}`);
          buildView(b);
          toast(b.status === "created" ? "Created, switched off" : "Stopped halfway; see below", b.status === "created" ? "" : "bad");
        } catch (err) {
          $("nc-create").disabled = false; $("nc-create").textContent = "Create everything (off)";
          toast(err.message, "bad");
        }
      });
      // Listening first, then filling in: a quick choice (or Enter) while the lists load is never missed.
      await loadForms();
      await loadTemplate();
      if (draftP) await fillFromDraft();
    }
  }
}
