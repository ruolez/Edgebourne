// What a conversation shows: the pictures, videos and pages Claude made (`desk attach` on the Mac), under its
// answer with Upload as draft (a person's tap: media library, then New ad with it picked, created off) and
// Change it, and the files a person sent with a message, in that message. Each opens in the full-screen viewer
// (lightbox.js). Served same origin from /api/desk/attachments/<id>, so the CSP's img-src / media-src 'self' holds;
// a page comes from …/<id>/page with scripts off (its own sandboxing policy).
import { esc, icon } from "./ui.js";
import { fileUrl, mediaTitle } from "./lightbox.js";

const seconds = (ms) => `${Math.round(ms / 100) / 10} s`;
const bigger = (a) => `<button class="att-zoom" type="button" data-att-open="${a.id}" aria-label="Open larger" title="Open larger">${icon("expand")}</button>`;

function media(a) {
  const ratio = a.width && a.height ? `data-ratio="${a.width} / ${a.height}"` : "";
  const label = esc(mediaTitle(a));
  if (a.kind === "video") return `<div class="att-shell"><video class="att-media" src="${fileUrl(a)}" controls playsinline preload="metadata" ${ratio} aria-label="${label}"></video>${bigger(a)}</div>`;
  if (a.kind === "page") {
    return `<div class="att-frame"><div class="att-frame-bar">${icon("file")}<b>${label}</b><button class="cv-tool" type="button" data-att-open="${a.id}" aria-label="Open larger" title="Open larger">${icon("expand")}</button></div>
      <iframe src="${fileUrl(a)}" sandbox="" loading="lazy" referrerpolicy="no-referrer" title="${label}"></iframe></div>`;
  }
  return `<button class="att-open" type="button" data-att-open="${a.id}" aria-label="Open larger: ${label}"><img class="att-media" src="${fileUrl(a)}" alt="${label}" loading="lazy" ${ratio}></button>`;
}

function item(a) {
  const words = esc(mediaTitle(a)) + (a.kind === "video" && a.duration_ms ? ` <span class="att-len">· ${seconds(a.duration_ms)}</span>` : "");
  // Meta's media library takes pictures and videos: a page has no Upload as draft.
  const draft = a.pruned || a.kind === "page" ? ""
    : a.drafted && a.next ? `<a class="btn btn-small" href="${esc(a.next)}">Uploaded · Open New ad</a>`
      : `<button class="btn btn-small" type="button" data-att-draft="${a.id}">Upload as draft</button>`;
  return `<figure class="att-item ${a.kind === "page" ? "is-page" : ""}" data-att="${a.id}">
    ${a.pruned ? '<p class="att-gone">Removed after 30 days.</p>' : media(a)}
    <div class="att-foot">${a.kind === "page" && !a.pruned ? "" : `<figcaption>${words}</figcaption>`}
      <div class="att-acts">${draft}<button class="btn btn-small" type="button" data-att-change="${a.id}">Change it</button></div></div>
  </figure>`;
}

export function attachmentsHtml(t) {
  const list = t.attachments || [];
  if (!list.length) return "";
  // One picture or video is shown large, two share the row, more make a grid; a page always takes a row of its own.
  const tiles = list.filter((a) => a.kind !== "page").length;
  return `<section class="att-list" data-n="${Math.min(tiles, 3)}" aria-label="${list.length === 1 ? "Preview" : `${list.length} previews`}">${list.map(item).join("")}</section>`;
}

// The files a person sent with a message, as small tiles inside it.
export function sentFilesHtml(t) {
  const list = t.files || [];
  if (!list.length) return "";
  return `<div class="cv-sent">${list.map((a) => {
    const label = esc(mediaTitle(a));
    if (a.pruned) return `<span class="cv-file" title="${label}: removed after 30 days">${icon(a.kind === "video" ? "play" : "image")}<small>Removed</small></span>`;
    return `<button class="cv-file" type="button" data-att-open="${a.id}" aria-label="Open ${label}" title="${label}">${
      a.kind === "image" ? `<img src="${fileUrl(a)}" alt="" loading="lazy">` : `${icon("play")}<small>${a.duration_ms ? seconds(a.duration_ms) : "Video"}</small>`}</button>`;
  }).join("")}</div>`;
}

// Width and height come from the bytes (server side); the box keeps that shape before the picture loads.
export function sizeAttachments(root) {
  root.querySelectorAll(".att-media[data-ratio]").forEach((el) => { el.style.aspectRatio = el.dataset.ratio; });
}

export const attachmentKey = (t) => (t.attachments || []).map((a) => [a.id, a.pruned, a.drafted]);

// Everything a conversation shows, oldest first: what the viewer steps through.
export function threadMedia(th, ix) {
  return th.turns.flatMap((id) => { const t = ix.tasks.get(id); return [...(t.files || []), ...(t.attachments || [])]; });
}
