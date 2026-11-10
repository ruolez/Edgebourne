import { api } from "./api.js";
import { boot, confirmDialog, esc, fieldError, icon, toast } from "./ui.js";
import { CTA_LABELS, money } from "./format.js";
import { placesHtml, placesWidget } from "./places.js";

const CLIENT_KEY = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);

const $ = (id) => document.getElementById(id);
let opts;
let places;
let hints = [];
let media = [];
let ads = [];

const STEP_NAMES = { goal: "Goal", budget: "Budget", adset: "Who sees it", form: "Lead form", ads: "Ads" };
const STATUS = { ACTIVE: ["ok", "On"], PAUSED: ["", "Off"], CAMPAIGN_PAUSED: ["", "Off (campaign off)"], ADSET_PAUSED: ["", "Off (ad set off)"],
  IN_PROCESS: ["warn", "In review"], PENDING_REVIEW: ["warn", "In review"], DISAPPROVED: ["bad", "Rejected"], WITH_ISSUES: ["bad", "Has issues"] };
const pill = (s) => { const [c, l] = STATUS[s] || ["", s ? s.toLowerCase().replace(/_/g, " ") : "Syncing…"]; return `<span class="pill ${c}">${esc(l)}</span>`; };

// ---------------------------------------------------------------- ads step

function blankAd() {
  const t = opts.templates[0];
  if (!t) {  // a new account: words and media of its own
    const m = media[0];
    return { name: "", title: "", body: "", template_ad_id: "", cta_type: "SIGN_UP",
      media: m ? (m.kind === "image" ? { kind: "image", hash: m.hash } : { kind: "video", video_id: m.video_id }) : { kind: "none" } };
  }
  return { name: "", title: t.title || "", body: t.body || "", template_ad_id: t.id || "", cta_type: t.cta_type || "SIGN_UP", media: { kind: "same" } };
}

function mediaOptions(ad) {
  const v = ad.media.kind === "same" ? "same" : `${ad.media.kind}:${ad.media.hash || ad.media.video_id}`;
  const same = ad.template_ad_id ? `<option value="same" ${v === "same" ? "selected" : ""}>Same image or video as the starting ad</option>`
    : (media.length ? "" : '<option value="">Upload one in New ad first (Ads → New ad)</option>');
  return same +
    media.map((m) => { const k = `${m.kind}:${m.hash || m.video_id}`; return `<option value="${esc(k)}" ${k === v ? "selected" : ""}>${m.kind === "video" ? "Video" : "Image"}: ${esc(m.name || k)}</option>`; }).join("");
}

function adCard(ad, i) {
  return `<fieldset class="cr-card" data-ad="${i}"><legend>Ad ${i + 1}</legend>
    <div class="grid-2">
      <div class="field"><label for="a-tpl-${i}">Starts from</label><select class="input" id="a-tpl-${i}" data-k="template_ad_id"><option value="" ${ad.template_ad_id ? "" : "selected"}>Nothing: new words and media</option>${opts.templates.map((t) => `<option value="${esc(t.id)}" ${t.id === ad.template_ad_id ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select></div>
      <div class="field"><label for="a-media-${i}">Image or video</label><select class="input" id="a-media-${i}" data-k="media">${mediaOptions(ad)}</select></div>
    </div>
    <div class="field"><label for="a-body-${i}">Primary text</label><textarea class="input" id="a-body-${i}" data-k="body" rows="4">${esc(ad.body)}</textarea></div>
    <div class="grid-2">
      <div class="field"><label for="a-title-${i}">Headline</label><input class="input" id="a-title-${i}" data-k="title" value="${esc(ad.title)}" maxlength="255"></div>
      <div class="field"><label for="a-cta-${i}">Button</label><select class="input" id="a-cta-${i}" data-k="cta_type">${opts.cta_types.map((c) => `<option value="${c}" ${c === ad.cta_type ? "selected" : ""}>${esc(CTA_LABELS[c] || c)}</option>`).join("")}</select></div>
    </div>
    <div class="row"><div class="field grow"><label for="a-name-${i}">Ad name <span class="muted">(only you see this)</span></label><input class="input" id="a-name-${i}" data-k="name" value="${esc(ad.name)}" placeholder="N6 - What it's about" maxlength="200"></div>
      ${ads.length > 1 ? `<button type="button" class="btn btn-quiet btn-small" data-ad-remove="${i}">Remove</button>` : ""}</div>
  </fieldset>`;
}

function renderAds() {
  $("cr-list").innerHTML = ads.map(adCard).join("");
  $("cr-add").hidden = ads.length >= opts.max_ads;
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
      keep_hints: $("s-hints").checked, start_day: $("s-start").value || null, start_hour: 0, end_day: $("s-end").value || null, end_hour: 23 },
    ads,
  };
}

function reviewHtml(r) {
  return `<b>Review</b>
    <dl class="facts review-facts">
      <div><dt>Campaign</dt><dd>${esc(r.campaign)}</dd></div>
      <div><dt>Ad set</dt><dd>${esc(r.adset)}</dd></div>
      <div><dt>Form</dt><dd>${esc(r.form)}</dd></div>
      <div><dt>Ads</dt><dd>${r.ads.map((a) => `<p class="flush"><b>${esc(a.name)}</b> · “${esc(a.title)}” · ${esc(a.media)}${a.starts_from ? ` from ${esc(a.starts_from)}` : ""}</p>${a.warnings.map((w) => `<p class="note warn small-note">${esc(w)}</p>`).join("")}`).join("")}</dd></div>
    </dl>
    <div class="note ok">Ready to create. Everything starts switched off.</div>`;
}

let seq = 0;
let timer;
function checkSoon() {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const mine = ++seq;
    try {
      const r = await api("/api/builds/check", { method: "POST", body: spec() });
      if (mine !== seq) return;
      const groups = {};
      r.problems.forEach((p) => { (groups[p.step] = groups[p.step] || []).push(p.message); });
      $("review").innerHTML = r.problems.length
        ? `<b>Still to do</b>${Object.entries(groups).map(([s, ms]) => `<div class="todo"><span class="label">${esc(STEP_NAMES[s] || s)}</span><ul>${ms.map((m) => `<li>${esc(m)}</li>`).join("")}</ul></div>`).join("")}`
        : reviewHtml(r.review);
      $("nc-create").disabled = r.problems.length > 0;
    } catch (err) { /* advisory */ }
  }, 350);
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

function changed() { checkSoon(); }

async function loadTemplate() {
  try {
    const t = $("s-template").value ? await api(`/api/adsets/template/${encodeURIComponent($("s-template").value)}`)
      // From scratch: Advantage+ audience with the minimum age Meta allows for it (25) and 65.
      : { locations: [], hints: [], age_min: 25, age_max: 65, suggest_min: null, suggest_max: null, advantage: true, keep_hints: false };
    places.set(t.locations); hints = t.hints;
    $("s-age-min").value = t.age_min; $("s-age-max").value = t.age_max;
    $("s-sug-min").value = t.suggest_min ?? ""; $("s-sug-max").value = t.suggest_max ?? "";
    $("s-advantage").checked = t.advantage; $("s-hints").checked = t.keep_hints && hints.length > 0;
    $("s-hints-text").textContent = hints.join(", "); $("s-hints-row").hidden = !hints.length;
    $("s-suggest").hidden = !t.advantage;
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
        <div class="field"><label for="pub-typed">Type the daily budget to confirm</label><span class="money-input">$<input class="input" id="pub-typed" name="typed" inputmode="decimal" autocomplete="off"></span></div>
        <div class="row"><button class="btn btn-primary" type="submit">Publish</button><span class="muted small">Check each ad's preview first (links above).</span></div>
      </form></section>`
    : b.status === "partial" ? `<section class="panel"><div class="panel-body stack tight"><p class="note bad flush">${esc(b.error || "It stopped halfway.")}</p>
        <p class="muted flush">What was made stays, switched off. Fix the cause (often in Ads Manager or Settings), then finish: nothing is made twice.</p>
        <div class="row"><button type="button" class="btn btn-primary" id="resume">Finish creating</button></div></div></section>`
    : `<section class="panel"><div class="panel-body"><p class="note ok flush">Published. Meta is reviewing the ads; they start delivering once approved. Follow it on <a href="/ads.html">Ads</a>.</p></div></section>`;
  $("build").innerHTML = `<section class="panel"><div class="panel-head"><h2>${b.status === "published" ? "Published" : b.status === "created" ? "Created, switched off" : "Partly created"}</h2></div>
      <div class="panel-body"><table class="table middle build-table"><tbody>${rows.map(([kind, what, id, isAd]) => `<tr>
        <th scope="row">${esc(kind)}</th><td>${esc(what)}</td><td>${id ? pill(s[id]) : '<span class="pill">Not made yet</span>'}</td>
        <td class="row-actions">${id && isAd ? `<a class="btn btn-quiet btn-small" href="/ad.html?id=${encodeURIComponent(id)}" target="_blank" rel="noopener">Preview</a>` : ""}</td></tr>`).join("")}</tbody></table></div></section>
    ${publishBox}`;
  $("wizard").hidden = true;
  $("build").hidden = false;
  $("title").textContent = r.campaign.split(" · ")[0];
  const pf = $("pub-form");
  if (pf) pf.addEventListener("submit", async (e) => {
    e.preventDefault();
    fieldError(pf, null);
    const yes = await confirmDialog({ title: "Publish now?", body: `<p>Turns on everything in this campaign at up to ${esc(money(r.budget_cents, { exact: true }))} a day.</p>`, confirm: "Publish" });
    if (!yes) return;
    try { buildView(await api(`/api/builds/${b.id}/publish`, { method: "POST", body: { typed: $("pub-typed").value } })); toast("Published"); }
    catch (err) { if (err.body && err.body.field) fieldError(pf, "typed", err.message); else toast(err.message, "bad"); }
  });
  const rb = $("resume");
  if (rb) rb.addEventListener("click", async () => {
    rb.disabled = true;
    try { buildView(await api(`/api/builds/${b.id}/resume`, { method: "POST" })); } catch (err) { toast(err.message, "bad"); rb.disabled = false; }
  });
}

// ---------------------------------------------------------------- start

const me = await boot({ page: "ads", admin: true });
if (me) {
  $("crumb").innerHTML = `${icon("back")}<span>Ads</span>`;
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
      $("s-template").innerHTML = opts.adsets.map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("")
        + '<option value="">Nothing: start from scratch</option>';
      $("budget-hint").textContent = `Shared by everything in the campaign. What runs now: ${money(opts.running_daily_cents, { exact: true })} a day.`;
      ads = [blankAd()];
      renderAds();
      await loadForms();
      await loadTemplate();
      $("s-template").addEventListener("change", loadTemplate);
      $("s-advantage").addEventListener("change", () => { $("s-suggest").hidden = !$("s-advantage").checked; });
      $("f-reload").addEventListener("click", loadForms);
      $("nc-form").addEventListener("input", (e) => { if (e.target.id !== "nc-q") { changed(); if (e.target.closest('[data-step="adset"]')) estimateSoon(); } });
      $("nc-form").addEventListener("change", (e) => {
        const tpl = e.target.closest('[data-k="template_ad_id"]');
        if (tpl) {
          readAds();
          const ad = ads[Number(tpl.closest("[data-ad]").dataset.ad)];
          const t = opts.templates.find((x) => x.id === tpl.value) || {};
          Object.assign(ad, { template_ad_id: tpl.value, title: t.title || ad.title, body: t.body || ad.body, cta_type: opts.cta_types.includes(t.cta_type) ? t.cta_type : ad.cta_type });
          if (!tpl.value && ad.media.kind === "same") { const m = media[0]; ad.media = m ? (m.kind === "image" ? { kind: "image", hash: m.hash } : { kind: "video", video_id: m.video_id }) : { kind: "none" }; }
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
          history.replaceState(null, "", `?build=${b.id}`);
          buildView(b);
          toast(b.status === "created" ? "Created, switched off" : "Stopped halfway; see below", b.status === "created" ? "" : "bad");
        } catch (err) {
          $("nc-create").disabled = false; $("nc-create").textContent = "Create everything (off)";
          toast(err.message, "bad");
        }
      });
    }
  }
}
