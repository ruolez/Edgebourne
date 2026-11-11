import { api } from "./api.js";
import { boot, esc, icon, toast, guardLeaving, markSaved } from "./ui.js";
import { CTA_LABELS } from "./format.js";

const $ = (id) => document.getElementById(id);
let options;
let media = null; // { kind, hash | video_id, url, name, ready }
let pollTimer;

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
  if (!$("aset-pick").dataset.touched && t.adset_id) $("aset-pick").value = t.adset_id;
  ["body", "title"].forEach((id) => $(id).dispatchEvent(new Event("input")));
}

function useSame() {
  const t = options.templates.find((x) => x.id === $("template").value);
  if (!t) { media = null; showChosen(); pickTab("library"); return; }
  media = { kind: "same", name: `Same as “${t ? t.name : "the starting ad"}”`, url: t && t.image_url, ready: true };
  showChosen();
}

function pickTab(name) {
  document.querySelectorAll("#media-tabs button").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.tab === name)));
  $("tab-upload").hidden = name !== "upload";
  $("tab-library").hidden = name !== "library";
  $("tab-same").hidden = name !== "same";
  if (name === "library") loadLibrary();
  if (name === "same") useSame();
}

function showChosen() {
  const el = $("chosen");
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
  $("clear-media").addEventListener("click", () => { media = null; clearTimeout(pollTimer); showChosen(); });
}

async function pollVideo() {
  clearTimeout(pollTimer);
  if (!media || media.kind !== "video" || media.ready) return;
  try {
    const s = await api(`/api/media/video/${media.video_id}`);
    if (s.ready) { media.ready = true; showChosen(); return; }
  } catch (err) { /* keep waiting */ }
  pollTimer = setTimeout(pollVideo, 4000);
}

function upload(file) {
  const okType = ["image/jpeg", "image/png", "video/mp4", "video/quicktime"].includes(file.type);
  if (!okType) { toast("Use a JPG or PNG image, or an MP4 or MOV video", "bad"); return; }
  const isVideo = file.type.startsWith("video/");
  if (file.size > (isVideo ? 250 : 30) * 1024 * 1024) { toast(`That file is too big (${isVideo ? "250" : "30"} MB max)`, "bad"); return; }
  const bar = $("up-progress");
  const fill = bar.querySelector("i");
  const label = bar.querySelector("span");
  bar.hidden = false;
  fill.style.width = "0%";
  label.textContent = "Uploading…";
  const form = new FormData();
  form.append("file", file);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/media/upload");
  xhr.setRequestHeader("X-Requested-With", "ebads");
  xhr.upload.addEventListener("progress", (e) => {
    if (!e.lengthComputable) return;
    const p = Math.round((e.loaded / e.total) * 100);
    fill.style.width = `${p}%`;
    label.textContent = p < 100 ? `Uploading… ${p}%` : "Sending to Meta…";
  });
  xhr.addEventListener("load", () => {
    let body = {};
    try { body = JSON.parse(xhr.responseText); } catch (e) {}
    if (xhr.status >= 300) { label.textContent = body.error || "Upload failed"; toast(body.error || "Upload failed", "bad"); return; }
    bar.hidden = true;
    media = { ...body, preview: URL.createObjectURL(file), ready: body.kind === "image" };
    showChosen();
    pollVideo();
    toast(isVideo ? "Uploaded. Meta is processing the video." : "Image uploaded");
  });
  xhr.addEventListener("error", () => { label.textContent = "Upload failed: check your connection"; });
  xhr.send(form);
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
  $("crumb").innerHTML = `${icon("back")}<span>Ads</span>`;
  $("drop-icon").innerHTML = icon("upload");
  if (me.role === "admin") $("claude-tip").hidden = false;
  try { options = await api("/api/ads/new/options"); } catch (err) { toast(err.message, "bad"); options = { adsets: [], templates: [], cta_types: [] }; }
  if (!options.adsets.length || (!options.templates.length && me.role !== "admin")) {
    document.querySelector(".new-ad-layout").innerHTML = `<section class="panel empty"><h3>No ad set to put it in yet</h3><p>An ad goes inside an ad set.${me.role === "admin" ? " Start with a new campaign: it makes the ad set and its first ads." : " Ask an admin to set up the campaign first."}</p>${me.role === "admin" ? '<a class="btn btn-primary" href="/new-campaign.html">New campaign</a>' : '<a class="btn" href="/ads.html">Back to ads</a>'}</section>`;
  } else {
    $("aset-pick").innerHTML = options.adsets.map((s) => `<option value="${esc(s.id)}">${esc(s.name)} · ${esc(s.campaign_name)}</option>`).join("");
    // Admins can also start from nothing: the account's Page, the lead form they pick, their own media.
    $("template").innerHTML = options.templates.map((t) => `<option value="${esc(t.id)}">${esc(t.name)}</option>`).join("")
      + (me.role === "admin" ? '<option value="">Nothing: a new ad with its own words and media</option>' : "");
    $("cta").innerHTML = options.cta_types.map((c) => `<option value="${c}">${esc(CTA_LABELS[c] || c)}</option>`).join("");
    const wantSet = new URLSearchParams(location.search).get("adset");
    if (wantSet && options.adsets.some((s) => s.id === wantSet)) { $("aset-pick").value = wantSet; $("aset-pick").dataset.touched = "1"; }
    const from = new URLSearchParams(location.search).get("from");
    if (from && options.templates.some((t) => t.id === from)) $("template").value = from;
    counter($("body"), $("body-count"), 125);
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
    if (q.get("from")) pickTab("same");
    if (q.get("proposal")) {
      try {
        const p = await api(`/api/proposals/${encodeURIComponent(q.get("proposal"))}`);
        const pl = p.payload || {};
        if (pl.template_ad_id && options.templates.some((t) => t.id === pl.template_ad_id)) $("template").value = pl.template_ad_id;
        if (pl.adset_id) $("aset-pick").value = pl.adset_id;
        ["body", "title", "name"].forEach((k) => { if (pl[k]) { $(k).value = pl[k]; $(k).dataset.fromTemplate = "0"; $(k).dispatchEvent(new Event("input")); } });
        if (pl.cta_type) $("cta").value = pl.cta_type;
        if (!pl.media || pl.media.kind === "same") pickTab("same");
        else { media = { ...pl.media, name: `Claude's new ${pl.media.kind}`, ready: pl.media.kind === "image" }; showChosen(); pollVideo(); }
        toast("Filled in from Claude's proposal. Edit anything, then create.");
      } catch (err) { toast(err.message, "bad"); }
    }
    $("file").addEventListener("change", (e) => { if (e.target.files[0]) upload(e.target.files[0]); e.target.value = ""; });
    const drop = $("drop");
    ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
    drop.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) upload(f); });

    $("new-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = $("name").value.trim();
      const problems = [];
      if (!media) problems.push("choose an image or video");
      if (!$("body").value.trim()) problems.push("write the primary text");
      if (!$("title").value.trim()) problems.push("write a headline");
      if (!name) problems.push("name the ad");
      if (problems.length) { toast(`Almost: ${problems.join(", ")}.`, "bad"); return; }
      if (media.kind === "video" && !media.ready) { toast("Meta is still processing the video. Give it a minute.", "bad"); return; }
      const btn = $("create");
      btn.disabled = true;
      btn.textContent = "Creating…";
      try {
        const r = await api("/api/ads/new", { method: "POST", body: {
          adset_id: $("aset-pick").value, template_ad_id: $("template").value, name,
          body: $("body").value, title: $("title").value, cta_type: $("cta").value, form_id: $("form").value || null,
          media: media.kind === "same" ? { kind: "same" } : { kind: media.kind, hash: media.hash, video_id: media.video_id },
        } });
        markSaved();
        location.href = `/ad.html?id=${encodeURIComponent(r.id)}&created=1`;
      } catch (err) { toast(err.message, "bad"); btn.disabled = false; btn.textContent = "Create ad (off)"; }
    });
  }
}
