// A full-screen look at what a conversation shows: pictures, videos and pages, one at a time, with the others
// a key press away (← →), so two versions can be flipped between. The page that opens it passes the list and
// what its buttons do; nothing here talks to the server.
import { esc, icon } from "./ui.js";

export const fileUrl = (a) => (a.kind === "page" ? `/api/desk/attachments/${a.id}/page` : `/api/desk/attachments/${a.id}`);
export const mediaTitle = (a) => a.caption || a.name || "Preview";
const WIDTHS = [["phone", "Phone"], ["wide", "Desktop"]];

function stage(a, width) {
  if (a.pruned) return '<p class="lb-gone">Removed after 30 days.</p>';
  const label = esc(mediaTitle(a));
  if (a.kind === "video") return `<video class="lb-media" src="${fileUrl(a)}" controls playsinline preload="metadata" aria-label="${label}"></video>`;
  if (a.kind === "page") return `<iframe class="lb-page" data-width="${width}" src="${fileUrl(a)}" sandbox="" referrerpolicy="no-referrer" title="${label}"></iframe>`;
  return `<img class="lb-media" src="${fileUrl(a)}" alt="${label}" draggable="false">`;
}

function thumb(a, on) {
  const inner = a.kind === "image" && !a.pruned ? `<img src="${fileUrl(a)}" alt="" loading="lazy">` : icon(a.kind === "video" ? "play" : a.kind === "page" ? "file" : "image");
  return `<button type="button" class="lb-thumb" data-lb-go="${a.id}" aria-label="${esc(mediaTitle(a))}" aria-current="${on}">${inner}</button>`;
}

// items: [{id, kind, name, caption, pruned, source, drafted, next}]; actions: { change(item), draft(item) } (each optional).
export function openLightbox(items, startId, actions = {}) {
  if (!items.length) return null;
  let at = Math.max(0, items.findIndex((a) => a.id === startId));
  let width = "phone";
  const dlg = document.createElement("dialog");
  dlg.className = "lb";
  dlg.tabIndex = -1;
  dlg.setAttribute("aria-label", "Preview");
  document.body.appendChild(dlg);

  const draw = () => {
    const a = items[at];
    const mine = a.source !== "user" && !a.pruned;
    const draft = !mine || a.kind === "page" || !actions.draft ? ""
      : a.drafted && a.next ? `<a class="lb-btn" href="${esc(a.next)}">Uploaded · Open New ad</a>`
        : '<button type="button" class="lb-btn" data-lb-draft>Upload as draft</button>';
    dlg.innerHTML = `<header class="lb-bar">
        <div class="lb-title"><b>${esc(mediaTitle(a))}</b>${items.length > 1 ? `<span>${at + 1} / ${items.length}</span>` : ""}</div>
        ${a.kind === "page" && !a.pruned ? `<div class="segmented lb-widths" role="tablist" aria-label="Width">${WIDTHS.map(([w, l]) => `<button type="button" role="tab" data-lb-width="${w}" aria-selected="${w === width}">${l}</button>`).join("")}</div>` : ""}
        <div class="lb-do">
          ${mine && actions.change ? '<button type="button" class="lb-btn" data-lb-change>Change it</button>' : ""}${draft}
          ${a.pruned ? "" : `<a class="lb-icon" href="${fileUrl(a)}" ${a.kind === "page" ? 'target="_blank" rel="noopener noreferrer" aria-label="Open in a new tab" title="Open in a new tab"' : `download="${esc(a.name || "preview")}" aria-label="Download" title="Download"`}>${icon(a.kind === "page" ? "external" : "download")}</a>`}
          <button type="button" class="lb-icon" data-lb-close aria-label="Close" title="Close">${icon("close")}</button>
        </div>
      </header>
      <div class="lb-stage" data-kind="${a.kind}">
        ${items.length > 1 ? `<button type="button" class="lb-nav prev" data-lb-step="-1" aria-label="Previous">${icon("back")}</button>` : ""}
        ${stage(a, width)}
        ${items.length > 1 ? `<button type="button" class="lb-nav next" data-lb-step="1" aria-label="Next">${icon("chev")}</button>` : ""}
      </div>
      ${items.length > 1 ? `<nav class="lb-strip" aria-label="Everything shown in this conversation">${items.map((x, i) => thumb(x, i === at)).join("")}</nav>` : ""}`;
    dlg.querySelector(".lb-strip [aria-current='true']")?.scrollIntoView({ block: "nearest", inline: "center" });
    // Redrawing removed whatever had the keyboard: it stays in the viewer, so ← → and Esc keep working.
    if (dlg.open && !dlg.contains(document.activeElement)) dlg.focus();
  };
  const go = (i) => { at = (i + items.length) % items.length; draw(); };

  dlg.addEventListener("click", (e) => {
    const hit = (name) => e.target.closest(`[${name}]`);
    let el;
    if (hit("data-lb-close") || e.target === dlg) { dlg.close(); return; }
    if ((el = hit("data-lb-step"))) { go(at + Number(el.dataset.lbStep)); return; }
    if ((el = hit("data-lb-go"))) { go(items.findIndex((a) => String(a.id) === el.dataset.lbGo)); return; }
    if ((el = hit("data-lb-width"))) { width = el.dataset.lbWidth; draw(); return; }
    if (hit("data-lb-change")) { const a = items[at]; dlg.close(); actions.change(a); return; }
    if ((el = hit("data-lb-draft"))) { const a = items[at]; dlg.close(); actions.draft(a); return; }
    // A picture toggles between fitting the screen and its real size; the empty stage around it closes.
    if (e.target.matches("img.lb-media")) { e.target.classList.toggle("zoomed"); return; }
    if (e.target.classList.contains("lb-stage")) dlg.close();
  });
  dlg.addEventListener("keydown", (e) => {
    if (e.target.closest("video")) return;  // the player's own keys
    if (e.key === "ArrowRight" && items.length > 1) { e.preventDefault(); go(at + 1); }
    if (e.key === "ArrowLeft" && items.length > 1) { e.preventDefault(); go(at - 1); }
  });
  let downX = null;
  dlg.addEventListener("touchstart", (e) => { downX = e.touches.length === 1 ? e.touches[0].clientX : null; }, { passive: true });
  dlg.addEventListener("touchend", (e) => {
    if (downX == null || items.length < 2 || dlg.querySelector(".lb-media.zoomed")) return;
    const dx = e.changedTouches[0].clientX - downX;
    if (Math.abs(dx) > 60) go(at + (dx < 0 ? 1 : -1));
    downX = null;
  }, { passive: true });
  dlg.addEventListener("close", () => dlg.remove());
  draw();
  dlg.showModal();
  return dlg;
}
