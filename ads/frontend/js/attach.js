// FU-D: previews Claude made in a conversation (`desk attach` on the Mac), shown under the turn's answer with
// Upload as draft (a person's tap: media library, then New ad with it picked, created off) and Change it.
// Served same origin from /api/desk/attachments/<id>, so the CSP's img-src / media-src 'self' holds.
import { esc } from "./ui.js";

const seconds = (ms) => `${Math.round(ms / 100) / 10} s`;

function media(a) {
  const src = `/api/desk/attachments/${a.id}`;
  const ratio = a.width && a.height ? `data-ratio="${a.width} / ${a.height}"` : "";
  const label = esc(a.caption || a.name);
  if (a.kind === "video") return `<video class="att-media" src="${src}" controls playsinline preload="metadata" ${ratio} aria-label="${label}"></video>`;
  return `<img class="att-media" src="${src}" alt="${label}" loading="lazy" ${ratio}>`;
}

function item(a) {
  const words = esc(a.caption || a.name) + (a.kind === "video" && a.duration_ms ? ` <span class="att-len">· ${seconds(a.duration_ms)}</span>` : "");
  const draft = a.pruned ? ""
    : a.drafted && a.next ? `<a class="btn btn-small" href="${esc(a.next)}">Uploaded · Open New ad</a>`
      : `<button class="btn btn-small" type="button" data-att-draft="${a.id}">Upload as draft</button>`;
  return `<figure class="att-item" data-att="${a.id}">
    ${a.pruned ? '<p class="att-gone">Preview removed after 30 days.</p>' : media(a)}
    <figcaption>${words}</figcaption>
    <div class="att-acts">${draft}<button class="btn btn-small btn-claude-outline" type="button" data-att-change="${a.id}">Change it</button></div>
  </figure>`;
}

export function attachmentsHtml(t) {
  const list = t.attachments || [];
  if (!list.length) return "";
  return `<section class="cv-block" aria-label="Previews"><h3 class="cv-label">${list.length === 1 ? "Preview" : "Previews"} <span>${list.length}</span></h3>
    <div class="att-list">${list.map(item).join("")}</div></section>`;
}

// Width and height come from the bytes (server side); the box keeps that shape before the picture loads.
export function sizeAttachments(root) {
  root.querySelectorAll(".att-media[data-ratio]").forEach((el) => { el.style.aspectRatio = el.dataset.ratio; });
}

export const attachmentKey = (t) => (t.attachments || []).map((a) => [a.id, a.pruned, a.drafted]);
