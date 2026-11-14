// Meta's extra insights (AM-E), read by the Mac's Ads Manager link: how you compare with similar advertisers, Meta's
// match quality per event, what Meta says about an ad and Meta's picture of it. Meta's words are data: everything goes
// through esc(), never a link, never HTML. Each block carries the link's source line (ui.linkNote).
import { esc, icon, linkNote } from "./ui.js";

const VERDICT = { better: ["good", "✓", "Better"], same: ["same", "≈", "About the same"], worse: ["bad", "!", "Worse"] };

export function verdictHtml(v) {
  const x = VERDICT[v];
  if (!x) return '<span class="muted small">Meta didn\'t say</span>';
  return `<span class="mx-verdict is-${x[0]}"><span class="mx-glyph" aria-hidden="true">${x[1]}</span>${x[2]}</span>`;
}

// The comparison table (cards on phones): Label · You · Similar advertisers · a word, then the auction rankings.
export function compareHtml(c, { title = "How you compare", id = "mx-compare", head = "h3" } = {}) {
  if (!c) return "";
  const rows = c.rows || [];
  const table = rows.length ? `<table class="table middle mx-cmp"><thead><tr><th scope="col">What</th><th class="num" scope="col">You</th>
      <th class="num" scope="col">Similar advertisers</th><th scope="col">Meta says</th></tr></thead>
    <tbody>${rows.map((r) => `<tr data-metric="${esc(r.metric)}"><th scope="row">${esc(r.label)}${r.note ? `<small class="mx-note">${esc(r.note)}</small>` : ""}</th>
      <td class="num" data-k="You">${esc(r.ours)}</td><td class="num" data-k="Similar advertisers">${esc(r.peers)}</td><td data-k="Meta says">${verdictHtml(r.verdict)}</td></tr>`).join("")}</tbody></table>`
    : '<p class="muted small flush">Meta gave no comparison with similar advertisers in its last read.</p>';
  const ranks = (c.auction || []).length ? `<ul class="mx-ranks">${c.auction.map((a) => `<li><b>${esc(a.name)}</b> <span>${esc(a.words)}</span></li>`).join("")}</ul>` : "";
  return `<div class="mx-block" id="${esc(id)}"><${head} class="mx-h">${esc(title)}</${head}>${table}${ranks ? `<p class="mx-sub flush">Auction rankings</p>${ranks}` : ""}${linkNote(c.source)}</div>`;
}

// Settings → Tracking health: Meta's match quality per event, a 0–10 bar with its number and Meta's advice.
export function qualityHtml(q) {
  if (!q) return "";
  const rows = (q.rows || []).map((r) => `<li class="mx-q is-${esc(r.band)}"><div class="mx-q-top"><b>${esc(r.event)}</b><span>${esc(r.words)}</span></div>
      <span class="mx-bar" role="img" aria-label="${esc(r.words)}"><i data-w="${Number(r.pct) || 0}"></i></span>
      ${r.advice ? `<p class="flush small muted">${esc(r.advice)}</p>` : ""}</li>`).join("");
  return `<div class="mx-block" id="mx-quality"><h3 class="mx-h">Meta's match quality per event, as Ads Manager shows it</h3>
    <p class="flush small muted">How well Meta can match the people behind each event to its users (6 or more is good). Your Mac reads this from Ads Manager, so it can differ a little from the dataset's score above, which is read at another time.</p>
    ${rows ? `<ul class="mx-qs">${rows}</ul>` : '<p class="muted small flush">Meta gave no scores in its last read.</p>'}${linkNote(q.source)}</div>`;
}

// The ad page's status card: what Meta says about this ad, Meta's summary in bold, the message folded past 3 lines.
// `diagnose`: leave room for Diagnose with Claude (owner and account admins; the page fills it).
export function errorsHtml(e, { diagnose = false } = {}) {
  if (!e || !(e.items || []).length) return "";
  const blocking = e.items.some((i) => i.blocking);
  return `<div class="mx-errs${blocking ? " is-blocking" : ""}" id="mx-errors"><h3 class="mx-h">What Meta says</h3>
    ${blocking ? '<p class="mx-stop flush"><b>This ad can\'t deliver until it\'s fixed.</b></p>' : ""}
    <ul class="mx-err-list">${e.items.map((i, n) => `<li class="mx-err${i.blocking ? " is-blocking" : ""}">
      <p class="flush"><b class="mx-err-sum">${esc(i.summary)}</b></p>
      ${i.message ? `<div class="mx-msg"><p class="mx-msg-text flush" id="mx-msg-${n}">${esc(i.message)}</p>
        <button type="button" class="link-btn mx-more" aria-expanded="false" aria-controls="mx-msg-${n}" hidden>Show all</button></div>` : ""}
      ${i.fix ? `<p class="flush small"><span class="muted">What to do:</span> ${esc(i.fix)}</p>` : ""}
      <p class="flush mx-meta">${i.since_words ? `${esc(i.since_words)}` : ""}${i.code ? `${i.since_words ? " · " : ""}code ${esc(i.code)}` : ""}</p></li>`).join("")}</ul>
    ${diagnose ? '<div class="row al-acts" id="mx-diag"></div>' : ""}
    ${linkNote(e.source)}</div>`;
}

// Meta's picture of the ad, as Ads Manager renders it (the Overview's second view beside the live preview).
export function pictureHtml(p, adId) {
  const get = p.can_get ? `<button type="button" class="btn btn-small" id="mx-get">${icon("refresh")}<span>Get Meta's picture</span></button>` : "";
  const why = !p.can_get && p.why_not ? `<p class="muted small flush" id="mx-why">${esc(p.why_not)}</p>` : "";
  if (!p.has) {
    const words = p.pruned ? "Meta's picture is older than 30 days, so it was removed." : "No picture from Ads Manager yet. Your Mac reads one each day for the ads that are on.";
    return `<div class="mx-pic is-empty" id="mx-pic"><p class="flush">${esc(words)}${p.can_get ? " Get it now:" : ""}</p>
      <div class="row">${get}</div>${why}<p class="flush small muted" id="mx-wait" hidden></p>${p.source ? linkNote(p.source) : ""}</div>`;
  }
  const src = `/api/ads/ad/${encodeURIComponent(adId)}/screenshot?v=${encodeURIComponent(p.v || "")}`;
  return `<div class="mx-pic" id="mx-pic"><div class="mx-frame"><img id="mx-img" src="${esc(src)}" alt="Meta's picture of the ad as Ads Manager shows it"
      ${p.width && p.height ? `data-ratio="${p.width}/${p.height}"` : ""} loading="lazy"></div>
    ${linkNote(p.source)}<div class="row">${get}</div>${why}<p class="flush small muted" id="mx-wait" hidden></p></div>`;
}

// Bars and ratios through CSSOM (the CSP allows no style attributes); "Show all" only under a message that is cut.
export function sizeExtras(root = document) {
  root.querySelectorAll(".mx-bar [data-w]").forEach((i) => { i.style.width = `${Math.max(0, Math.min(100, Number(i.dataset.w)))}%`; });
  root.querySelectorAll("img[data-ratio]").forEach((img) => { img.style.aspectRatio = img.dataset.ratio; });
  root.querySelectorAll(".mx-msg").forEach((m) => {
    const text = m.querySelector(".mx-msg-text");
    const more = m.querySelector(".mx-more");
    if (!text || !more) return;
    if (!m.classList.contains("is-open")) more.hidden = text.scrollHeight <= text.clientHeight + 1;
    more.onclick = () => {
      const open = m.classList.toggle("is-open");
      more.setAttribute("aria-expanded", String(open));
      more.textContent = open ? "Show less" : "Show all";
    };
  });
}
