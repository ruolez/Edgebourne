// A larger look at an ad: Meta's own preview, per placement, optionally next to what runs now.
import { api } from "./api.js";
import { esc, icon, previewSkeleton, showPreviewFrame } from "./ui.js";

export const PLACEMENTS = [["MOBILE_FEED_STANDARD", "Facebook feed"], ["INSTAGRAM_STANDARD", "Instagram feed"], ["INSTAGRAM_REELS", "Reels"], ["INSTAGRAM_STORY", "Stories"]];
const cache = new Map();

async function fill(box, url, title) {
  box.innerHTML = previewSkeleton();
  try {
    if (!cache.has(url)) cache.set(url, await api(url));
    const p = cache.get(url);
    showPreviewFrame(box, p, { title, height: p.height || 560 });
  } catch (err) {
    cache.delete(url);
    box.innerHTML = `<p class="preview-error">${esc(err.message)}</p>`;
  }
}

function shell(title, inner) {
  const dlg = document.createElement("dialog");
  dlg.className = "viewer";
  dlg.innerHTML = `<header class="viewer-head"><h2>${esc(title)}</h2><button class="icon-btn" type="button" data-viewer-close aria-label="Close">${icon("close")}</button></header>${inner}`;
  document.body.appendChild(dlg);
  dlg.addEventListener("click", (e) => { if (e.target === dlg || e.target.closest("[data-viewer-close]")) dlg.close(); });
  dlg.addEventListener("close", () => dlg.remove());
  dlg.showModal();
  return dlg;
}

// panes: [{ label, url(format) }]
export function openViewer({ title, panes, format = PLACEMENTS[0][0], link, placements = PLACEMENTS }) {
  const dlg = shell(title, `
    ${placements.length > 1 ? `<div class="viewer-tabs" role="tablist" aria-label="Placement" data-tabpanel="viewer-panes">${placements.map(([f, l]) => `<button type="button" role="tab" data-f="${f}" aria-selected="${f === format}">${esc(l)}</button>`).join("")}</div>` : ""}
    <div class="viewer-panes ${panes.length > 1 ? "two" : ""}" id="viewer-panes">${panes.map((p, i) => `<figure>${panes.length > 1 ? `<figcaption>${esc(p.label)}</figcaption>` : ""}<div class="decision-preview" data-pane="${i}"></div></figure>`).join("")}</div>
    ${link ? `<p class="viewer-foot"><a href="${esc(link.href)}">${esc(link.label)}</a></p>` : ""}`);
  const show = (f) => panes.forEach((p, i) => fill(dlg.querySelector(`[data-pane="${i}"]`), p.url(f), `${title}: ${p.label}`));
  dlg.addEventListener("click", (e) => {
    const b = e.target.closest("[data-f]");
    if (!b) return;
    dlg.querySelectorAll("[data-f]").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
    show(b.dataset.f);
  });
  show(format);
}

export function openSwipe(s) {
  shell(s.page_name, `<div class="viewer-swipe">
    ${s.media_url ? `<img src="${esc(s.media_url)}" alt="">` : ""}
    <div>${s.title ? `<h3>${esc(s.title)}</h3>` : ""}${s.body ? `<p>${esc(s.body)}</p>` : ""}
      <p class="muted small">${[s.running_label, s.cta].filter(Boolean).map(esc).join(" · ")}</p>
      ${s.notes ? `<p class="small">${esc(s.notes)}</p>` : ""}
      ${s.library_url ? `<p><a href="${esc(s.library_url)}" target="_blank" rel="noopener noreferrer">Open in Meta’s Ad Library</a></p>` : ""}</div>
  </div>`);
}
