// Files a person adds to a message for Claude (a raw clip, a photo, a screenshot, a reference): picked, pasted or
// dropped, uploaded as they are added, and sent with the message as their ids. The Mac fetches them with
// `desk fetch` when it takes the request.
import { esc, icon } from "./ui.js";

const TYPES = { "image/jpeg": "image", "image/png": "image", "image/webp": "image", "video/mp4": "video", "video/quicktime": "video" };
const MAX_MB = { image: 10, video: 60 };
export const MAX_FILES = 6;
export const FILE_TYPES = Object.keys(TYPES).join(",");

// A file the server would refuse anyway, in words; null when it may go.
export function fileProblem(file) {
  const kind = TYPES[file.type];
  if (!kind) return "Claude takes JPG, PNG or WebP pictures and MP4 or MOV videos";
  if (file.size > MAX_MB[kind] * 1024 * 1024) return `That ${kind === "video" ? "video is too big (up to 60 MB)" : "picture is too big (up to 10 MB)"}`;
  return null;
}

// fileBox(box, { onChange, onProblem }) draws the added files into `box` and keeps them uploaded.
// Returns { add(FileList), ids(), busy(), count(), take() (the sent ones leave the box), drop() (unsent ones are removed) }.
export function fileBox(box, { onChange = () => {}, onProblem = () => {} } = {}) {
  let items = [];
  let seq = 0;

  const draw = () => {
    box.hidden = !items.length;
    box.innerHTML = items.map((it) => `<span class="cv-file" data-state="${it.state}" data-file="${it.key}" title="${esc(it.error || it.file.name)}">
        ${it.kind === "image" ? `<img src="${it.url}" alt="">` : icon("play")}
        ${it.state === "up" ? `<span class="cv-file-bar" aria-hidden="true"><i data-pct="${it.pct}"></i></span>` : `<small>${esc(it.state === "bad" ? "Didn't upload" : it.kind === "video" ? "Video" : "")}</small>`}
        <button class="cv-file-x" type="button" data-file-x="${it.key}" aria-label="Remove ${esc(it.file.name)}">${icon("close")}</button>
      </span>`).join("");
    box.querySelectorAll(".cv-file small:empty").forEach((el) => el.remove());
    // Widths are set from script: the page's CSP allows no inline styles.
    box.querySelectorAll(".cv-file-bar i").forEach((el) => { el.style.width = `${el.dataset.pct}%`; });
    onChange();
  };

  const upload = (it) => {
    const xhr = new XMLHttpRequest();
    it.xhr = xhr;
    xhr.open("POST", "/api/desk/uploads");
    xhr.setRequestHeader("X-Requested-With", "ebads");
    xhr.upload.addEventListener("progress", (e) => {
      if (!e.lengthComputable) return;
      it.pct = Math.round((e.loaded / e.total) * 100);
      const bar = box.querySelector(`[data-file="${it.key}"] .cv-file-bar i`);
      if (bar) bar.style.width = `${it.pct}%`;
    });
    const done = (ok, message, id) => {
      it.xhr = null;
      it.state = ok ? "ok" : "bad";
      it.id = id || null;
      it.error = ok ? "" : message;
      if (!ok) onProblem(message);
      draw();
    };
    xhr.addEventListener("load", () => {
      let body = null;
      try { body = JSON.parse(xhr.responseText); } catch (e) { /* not JSON: an error page */ }
      if (xhr.status === 401) { location.href = `/login.html?next=${encodeURIComponent(location.pathname + location.hash)}`; return; }
      if (xhr.status >= 200 && xhr.status < 300 && body && body.id) done(true, "", body.id);
      else done(false, (body && body.error) || (xhr.status === 413 ? "That file is too big" : "That file didn't upload. Try again."));
    });
    xhr.addEventListener("error", () => done(false, "Can't reach the server. Check your connection and add it again."));
    const form = new FormData();
    form.append("file", it.file, it.file.name);
    xhr.send(form);
  };

  const forget = (it, onServer) => {
    if (it.xhr) it.xhr.abort();
    if (it.url) URL.revokeObjectURL(it.url);
    if (onServer && it.id) fetch(`/api/desk/uploads/${it.id}`, { method: "DELETE", headers: { "X-Requested-With": "ebads" }, credentials: "same-origin" }).catch(() => {});
  };

  box.addEventListener("click", (e) => {
    const x = e.target.closest("[data-file-x]");
    if (!x) return;
    const it = items.find((i) => String(i.key) === x.dataset.fileX);
    if (!it) return;
    forget(it, true);
    items = items.filter((i) => i !== it);
    draw();
  });

  return {
    add(list) {
      for (const file of [...list]) {
        const problem = fileProblem(file);
        if (problem) { onProblem(problem); continue; }
        if (items.length >= MAX_FILES) { onProblem(`A message takes up to ${MAX_FILES} files`); break; }
        const it = { key: ++seq, file, kind: TYPES[file.type], url: TYPES[file.type] === "image" ? URL.createObjectURL(file) : "", state: "up", pct: 0, id: null, error: "" };
        items.push(it);
        upload(it);
      }
      draw();
    },
    ids: () => items.filter((i) => i.state === "ok").map((i) => i.id),
    busy: () => items.some((i) => i.state === "up"),
    failed: () => items.some((i) => i.state === "bad"),
    count: () => items.length,
    // The message went: its files belong to it now, the box is empty again.
    take() { items.forEach((it) => forget(it, false)); items = []; draw(); },
    // Leaving without sending: what was uploaded for this message is removed.
    drop() { items.forEach((it) => forget(it, true)); items = []; draw(); },
  };
}
