// The one uploader (9.4e), used by New ad and New campaign: drop or choose an image or video, watch it go
// up, cancel it while it uploads, try again after a failure (the same file, no need to pick it again).
// Videos then wait for Meta to process them (waitReady).
import { api } from "./api.js";
import { esc, icon } from "./ui.js";

const TYPES = ["image/jpeg", "image/png", "video/mp4", "video/quicktime"];
const MAX_MB = { image: 30, video: 250 };

// A file the server would refuse anyway, in words; null when it may go.
export function fileProblem(file) {
  if (!TYPES.includes(file.type)) return "Use a JPG or PNG image, or an MP4 or MOV video";
  const kind = file.type.startsWith("video/") ? "video" : "image";
  if (file.size > MAX_MB[kind] * 1024 * 1024) return `That file is too big (${kind === "video" ? "videos up to 250 MB" : "images up to 30 MB"})`;
  return null;
}

// Polls Meta until an uploaded video can be used; returns a function that stops polling.
export function waitReady(videoId, onReady) {
  let timer;
  let stopped = false;
  const poll = async () => {
    try {
      const s = await api(`/api/media/video/${encodeURIComponent(videoId)}`);
      if (s.ready) { if (!stopped) onReady(s); return; }
    } catch (err) { /* keep waiting */ }
    if (!stopped) timer = setTimeout(poll, 4000);
  };
  poll();
  return () => { stopped = true; clearTimeout(timer); };
}

// mountUploader(box, { id, name, onDone }) draws the uploader into `box`. `id` is the file input's id,
// `name` its form name (field errors point at it). onDone(media) gets { kind, hash | video_id, url, name,
// preview, ready }. Returns { busy() }.
export function mountUploader(box, { id, name = "", onDone, hint = "JPG or PNG up to 30 MB · MP4 or MOV up to 250 MB · 4:5 or 9:16 works best" }) {
  box.innerHTML = `<div class="upl" data-state="idle">
      <label class="drop" for="${esc(id)}">
        <input type="file" id="${esc(id)}" ${name ? `name="${esc(name)}"` : ""} accept="${TYPES.join(",")}" class="sr-only">
        <span class="drop-icon">${icon("upload")}</span>
        <b>Drop an image or video here, or choose a file</b>
        <span class="muted small">${esc(hint)}</span>
      </label>
      <div class="upl-status" role="status" aria-live="polite" hidden>
        <div class="progress-bar"><i></i><span></span></div>
        <div class="upl-acts"></div>
      </div>
    </div>`;
  const wrap = box.querySelector(".upl");
  const input = box.querySelector("input[type=file]");
  const drop = box.querySelector(".drop");
  const status = box.querySelector(".upl-status");
  const fill = status.querySelector("i");
  const label = status.querySelector(".progress-bar span");
  const acts = status.querySelector(".upl-acts");
  let xhr = null;
  let last = null;

  // `buttons` null keeps the ones shown (a focused Cancel stays focused while the bar moves).
  const show = (state, text, pct, buttons = "") => {
    wrap.dataset.state = state;
    // One upload at a time: a second file can't be chosen until this one is done or cancelled.
    input.disabled = state === "sending" || state === "meta";
    status.hidden = state === "idle";
    fill.style.width = `${pct}%`;
    label.textContent = text;
    if (buttons !== null) acts.innerHTML = buttons;
  };

  const send = (file) => {
    const bad = fileProblem(file);
    last = file;
    if (bad) { show("failed", bad, 0, '<button type="button" class="btn btn-small" data-upl="another">Choose another file</button>'); return; }
    const form = new FormData();
    form.append("file", file);
    xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/media/upload");
    xhr.setRequestHeader("X-Requested-With", "ebads");
    show("sending", `Uploading ${file.name}…`, 0, '<button type="button" class="btn btn-small" data-upl="cancel">Cancel</button>');
    xhr.upload.addEventListener("progress", (e) => {
      if (!e.lengthComputable) return;
      const p = Math.round((e.loaded / e.total) * 100);
      // Once the file is on the server it goes on to Meta, which can't be called back: no Cancel then.
      if (p < 100) show("sending", `Uploading ${file.name}… ${p}%`, p, null);
      else show("meta", "Sending to Meta…", 100);
    });
    const req = xhr;
    req.addEventListener("load", () => {
      let body = {};
      try { body = JSON.parse(req.responseText) || {}; } catch (e) { /* not JSON */ }
      xhr = null;
      if (req.status >= 300 || !(body.hash || body.video_id)) { failed(body.error || "The upload didn't go through"); return; }
      show("idle", "", 0);
      onDone({ ...body, preview: URL.createObjectURL(file), ready: body.kind === "image" });
    });
    req.addEventListener("error", () => { xhr = null; failed("The upload stopped: check the connection"); });
    req.addEventListener("abort", () => {
      xhr = null;
      show("failed", `Upload of ${file.name} cancelled.`, 0,
        '<button type="button" class="btn btn-small" data-upl="again">Upload it again</button><button type="button" class="btn btn-small btn-quiet" data-upl="another">Choose another file</button>');
      acts.querySelector("button")?.focus();
    });
    req.send(form);
  };

  const failed = (message) => show("failed", message, 0,
    '<button type="button" class="btn btn-small" data-upl="again">Try again</button><button type="button" class="btn btn-small btn-quiet" data-upl="another">Choose another file</button>');

  input.addEventListener("change", () => { if (input.files[0] && !xhr) send(input.files[0]); input.value = ""; });
  ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f && !xhr) send(f); });
  acts.addEventListener("click", (e) => {
    const b = e.target.closest("[data-upl]");
    if (!b) return;
    if (b.dataset.upl === "cancel" && xhr) xhr.abort();
    if (b.dataset.upl === "again" && last) send(last);
    if (b.dataset.upl === "another") { show("idle", "", 0); input.click(); }
  });
  return { busy: () => Boolean(xhr) };
}
