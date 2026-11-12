import { api } from "./api.js";
import { boot, cancelLink, entityLink, esc, icon, toast, guardLeaving, markSaved, returnCrumbs, safePath } from "./ui.js";
import { CTA_LABELS } from "./format.js";
import { mountUploader, waitReady } from "./uploader.js";
import { builder } from "./builder.js";

const $ = (id) => document.getElementById(id);
let options;
let media = null; // { kind, hash | video_id, url, name, ready }
let stopWaiting = () => {};
let steps = null;
const changed = () => steps && steps.soon();

// What New ad would send; the server checks it (POST /api/ads/new/check) before anything goes to Meta.
function payload() {
  return {
    adset_id: $("aset-pick").value, template_ad_id: $("template").value, name: $("name").value.trim(),
    body: $("body").value, title: $("title").value, cta_type: $("cta").value, form_id: $("form").value || null,
    media: !media ? null : media.kind === "same" ? { kind: "same" } : { kind: media.kind, hash: media.hash, video_id: media.video_id },
  };
}

async function check() {
  const r = await api("/api/ads/new/check", { method: "POST", body: payload() });
  const waiting = media && media.kind === "video" && !media.ready ? [{ field: "media", message: "Meta is still processing the video. Give it a minute." }] : [];
  return [...r.problems, ...waiting];
}

function summary() {
  const set = options.adsets.find((x) => x.id === $("aset-pick").value);
  const tpl = options.templates.find((x) => x.id === $("template").value);
  const form = $("form").selectedOptions[0];
  return {
    where: set ? `${set.name} · ${tpl ? `from ${tpl.name}` : "a new ad from scratch"}${form && form.value ? ` · form ${form.textContent}` : ""}` : "",
    media: media ? `${media.name || (media.kind === "video" ? "Video" : "Image")}${media.kind === "video" && !media.ready ? " (Meta is processing it)" : ""}` : "",
    words: $("title").value.trim() ? `“${$("title").value.trim()}” · ${CTA_LABELS[$("cta").value] || $("cta").value}` : "",
  };
}

function ready(problems) {
  const n = problems.length;
  $("ready").textContent = n ? `${n} ${n === 1 ? "thing" : "things"} to finish first.` : "Ready to create. It starts switched off.";
  $("ready").dataset.ok = String(!n);
}

function counter(input, out, soft) {
  const update = () => {
    const n = input.value.length;
    out.textContent = soft ? `${n} characters${n > soft ? ` · the first ${soft} show before "See more"` : ""}` : `${n} characters`;
  };
  input.addEventListener("input", update);
  update();
}

function fillFromTemplate() {
  const t = options.templates.find((x) => x.id === $("template").value);
  if (!t) return;
  if (!$("body").value.trim() || $("body").dataset.fromTemplate === "1") { $("body").value = t.body || ""; $("body").dataset.fromTemplate = "1"; }
  if (!$("title").value.trim() || $("title").dataset.fromTemplate === "1") { $("title").value = t.title || ""; $("title").dataset.fromTemplate = "1"; }
  if (t.cta_type) $("cta").value = t.cta_type;
  if (!$("aset-pick").dataset.touched && options.adsets.some((s) => s.id === t.adset_id)) $("aset-pick").value = t.adset_id;
  ["body", "title"].forEach((id) => $(id).dispatchEvent(new Event("input")));
}

function useSame() {
  const t = options.templates.find((x) => x.id === $("template").value);
  if (!t) { media = null; showChosen(); pickTab("upload"); return; }
  media = { kind: "same", name: `Same as “${t ? t.name : "the starting ad"}”`, url: t && t.image_url, ready: true };
  showChosen();
}

function pickTab(name) {
  document.querySelectorAll("#media-tabs button").forEach((x) => x.setAttribute("aria-selected", String(x.dataset.tab === name)));
  $("tab-upload").hidden = name !== "upload";
  $("tab-library").hidden = name !== "library";
  $("tab-same").hidden = name !== "same";
  if (name === "library") loadLibrary();
  if (name === "same") useSame();
}

function showChosen() {
  const el = $("chosen");
  changed();
  if (!media) { el.hidden = true; return; }
  el.hidden = false;
  const waiting = media.kind === "video" && !media.ready;
  el.innerHTML = `
    <div class="chosen-media">${media.preview ? (media.kind === "video" ? `<video src="${esc(media.preview)}" muted playsinline loop autoplay></video>` : `<img src="${esc(media.preview)}" alt="">`) : media.url ? `<img src="${esc(media.url)}" alt="" referrerpolicy="no-referrer">` : ""}</div>
    <div class="stack tight">
      <b>${esc(media.name || (media.kind === "video" ? "Video" : "Image"))}</b>
      <span class="${waiting ? "progress" : "ok-text"}">${waiting ? '<span class="dot"></span>Meta is processing the video… you can fill in the words meanwhile' : "Ready"}</span>
      <button class="link-btn" type="button" id="clear-media">Choose a different one</button>
    </div>`;
  $("clear-media").addEventListener("click", () => { media = null; stopWaiting(); showChosen(); });
}

// A video Meta hasn't finished processing can't go in an ad yet: wait for it, then say it's ready.
function pollVideo() {
  stopWaiting();
  if (!media || media.kind !== "video" || media.ready) return;
  const mine = media;
  stopWaiting = waitReady(mine.video_id, () => { mine.ready = true; if (media === mine) showChosen(); });
}

function uploaded(m) {
  media = m;
  showChosen();
  pollVideo();
  toast(m.kind === "video" ? "Uploaded. Meta is processing the video." : "Image uploaded");
}

async function loadLibrary() {
  try {
    const { items } = await api("/api/media");
    $("library").innerHTML = items.length ? items.map((m, i) => `
      <button type="button" class="media-item" data-i="${i}" title="${esc(m.name || "")}">
        ${m.url ? `<img src="${esc(m.url)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '<span class="ph"></span>'}
        ${m.kind === "video" ? `<span class="play">${icon("play")}</span>` : ""}
        <span class="media-name">${esc(m.name || (m.kind === "video" ? "Video" : "Image"))}</span>
      </button>`).join("") : '<p class="muted">Nothing uploaded yet.</p>';
    $("library").onclick = (e) => {
      const b = e.target.closest(".media-item");
      if (!b) return;
      const m = items[Number(b.dataset.i)];
      media = { ...m, ready: m.kind === "image" || m.ready !== false };
      document.querySelectorAll(".media-item").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      showChosen();
      pollVideo();
    };
  } catch (err) { $("library").innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

// The lead form: the starting ad's by default, or one built on the Lead forms page.
async function loadForms() {
  let list;
  try { list = (await api("/api/forms")).items.filter((f) => f.status !== "ARCHIVED"); } catch (err) { return; }
  const want = new URLSearchParams(location.search).get("form");
  $("form").innerHTML = '<option value="">Same as the starting ad</option>' +
    list.map((f) => `<option value="${esc(f.id)}" ${f.id === want ? "selected" : ""}>${esc(f.name)}</option>`).join("");
  $("form-pick").hidden = false;
}

const me = await boot({ page: "new-ad" });
if (me) guardLeaving();
if (me && me.role === "client") location.replace("/ads.html");
else if (me) {
  $("crumb").innerHTML = `${icon("back")}<span>Back</span>`;
  // ?template=<ad> starts from that ad (older links said ?from=<ad>); ?from=<page> is where Cancel goes.
  const q0 = new URLSearchParams(location.search);
  const templateId = q0.get("template") || (q0.get("from") && !safePath(q0.get("from")) ? q0.get("from") : null);
  const back = returnCrumbs("New ad");
  $("create")?.insertAdjacentHTML("afterend", cancelLink(back));
  mountUploader($("tab-upload"), { id: "file", name: "media", onDone: uploaded });
  if (me.role === "admin") $("claude-tip").hidden = false;
  try { options = await api("/api/ads/new/options"); } catch (err) { toast(err.message, "bad"); options = { adsets: [], templates: [], cta_types: [] }; }
  if (!options.adsets.length || (!options.templates.length && me.role !== "admin")) {
    document.querySelector(".new-ad-layout").innerHTML = `<section class="panel empty"><h3>No ad set to put it in yet</h3><p>An ad goes inside an ad set.${me.role === "admin" ? " Start with a new campaign: it makes the ad set and its first ads." : " Ask an admin to set up the campaign first."}</p>${me.role === "admin" ? '<a class="btn btn-primary" href="/new-campaign.html">New campaign</a>' : '<a class="btn" href="/ads.html">Back to ads</a>'}</section>`;
  } else {
    $("aset-pick").innerHTML = options.adsets.map((s) => `<option value="${esc(s.id)}">${esc(s.name)} · ${esc(s.campaign_name)}${s.effective_status === "ACTIVE" ? "" : " (off)"}</option>`).join("");
    // Admins can also start from nothing: the account's Page, the lead form they pick, their own media.
    $("template").innerHTML = options.templates.map((t) => `<option value="${esc(t.id)}">${esc(t.name)}</option>`).join("")
      + (me.role === "admin" ? '<option value="">Nothing: a new ad with its own words and media</option>' : "");
    $("cta").innerHTML = options.cta_types.map((c) => `<option value="${c}">${esc(CTA_LABELS[c] || c)}</option>`).join("");
    const offered = (id) => options.adsets.some((s) => s.id === id);
    const goneSet = "That ad set was deleted or archived on Meta, so it isn't offered. Pick another.";
    const wantSet = new URLSearchParams(location.search).get("adset");
    if (wantSet && offered(wantSet)) { $("aset-pick").value = wantSet; $("aset-pick").dataset.touched = "1"; }
    else if (wantSet) toast(goneSet, "bad");
    if (templateId && options.templates.some((t) => t.id === templateId)) $("template").value = templateId;
    // Arrived from New ad set: say what was just made, with a link to it.
    const made = wantSet && q0.get("made") === "adset" && options.adsets.find((x) => x.id === wantSet);
    if (made) document.querySelector("#new-form").insertAdjacentHTML("afterbegin", `<p class="note ok flush" id="made-note">Ad set ${entityLink("adset", made.id, made.name)} created, switched off. Add its first ad below.</p>`);
    // Said once: a reload or coming back with Back doesn't announce it again.
    if (q0.has("made")) { const u = new URL(location.href); u.searchParams.delete("made"); history.replaceState(history.state, "", u); }
    counter($("body"), $("body-count"), 125);
    steps = builder({ form: $("new-form"), nav: $("stepper"), check, summary, onCheck: ready,
      steps: [{ id: "where", name: "Where" }, { id: "media", name: "Image or video" }, { id: "words", name: "Words" }] });
    $("new-form").addEventListener("input", changed);
    $("new-form").addEventListener("change", changed);
    counter($("title"), $("title-count"));
    fillFromTemplate();
    $("template").addEventListener("change", fillFromTemplate);
    if (me.role === "admin") loadForms();
    $("aset-pick").addEventListener("change", () => { $("aset-pick").dataset.touched = "1"; });
    ["body", "title"].forEach((id) => $(id).addEventListener("input", (e) => { if (e.isTrusted) $(id).dataset.fromTemplate = "0"; }));

    $("media-tabs").addEventListener("click", (e) => {
      const b = e.target.closest("[data-tab]");
      if (b) pickTab(b.dataset.tab);
    });
    $("template").addEventListener("change", () => { if (media && media.kind === "same") useSame(); });
    const q = new URLSearchParams(location.search);
    if (templateId) pickTab("same");
    if (q.get("proposal")) {
      try {
        const p = await api(`/api/proposals/${encodeURIComponent(q.get("proposal"))}`);
        const pl = p.payload || {};
        if (pl.template_ad_id && options.templates.some((t) => t.id === pl.template_ad_id)) $("template").value = pl.template_ad_id;
        if (pl.adset_id && offered(pl.adset_id)) { $("aset-pick").value = pl.adset_id; $("aset-pick").dataset.touched = "1"; }
        else if (pl.adset_id) toast(goneSet, "bad");
        ["body", "title", "name"].forEach((k) => { if (pl[k]) { $(k).value = pl[k]; $(k).dataset.fromTemplate = "0"; $(k).dispatchEvent(new Event("input")); } });
        if (pl.cta_type) $("cta").value = pl.cta_type;
        if (!pl.media || pl.media.kind === "same") pickTab("same");
        else { media = { ...pl.media, name: `Claude's new ${pl.media.kind}`, ready: pl.media.kind === "image" }; showChosen(); pollVideo(); }
        toast("Filled in from Claude's suggestion. Edit anything, then create.");
      } catch (err) { toast(err.message, "bad"); }
    }
    changed();

    $("new-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = $("create");
      if (btn.disabled) return;
      btn.disabled = true;
      // Every field that needs something is marked first; nothing is sent to Meta until all are filled.
      let ok = false;
      try { ok = await steps.validate(); } catch (err) { toast(err.message, "bad"); }
      if (!ok) { btn.disabled = false; return; }
      btn.textContent = "Creating…";
      try {
        const r = await api("/api/ads/new", { method: "POST", body: payload() });
        markSaved();
        location.href = `/ad.html?id=${encodeURIComponent(r.id)}&created=1`;
      } catch (err) { toast(err.message, "bad"); btn.disabled = false; btn.textContent = "Create ad (off)"; }
    });
  }
}
