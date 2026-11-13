// The one Suggestion card (UX-AUDIT 9.2): what Claude suggests, what would change, why, and what you
// can do about it. The Claude page (`place: "claude"`) accepts through the Accept sheet; the ad page and
// Research (`place: "inline"`) through the confirmation in tasks.js. Both read the same card.
import { entityLink, esc, icon, previewSkeleton, when } from "./ui.js";
import { WORDS } from "./format.js";
import { outcomeLine } from "./outcome.js";

const isVersion = (p) => /^make a new version/i.test(p.title || "");
const TEST_METRICS = { cpl: WORDS.cpl, cpql: WORDS.cpql, ctr: WORDS.ctr, hook: WORDS.hook };
const firstLine = (text) => String(text || "").split("\n")[0];

// What became of a decided suggestion, in the console's words.
const DECIDED = {
  applied: ["ok", "Accepted and applied"], approved: ["ok", "Accepted"], declined: ["", "Declined"],
  failed: ["bad", "Accepted, but Meta refused"], expired: ["", "Expired"], applying: ["claude", "Being applied on Meta…"],
  revised: ["", "Sent back to Claude"], unknown: ["warn", "Meta didn't answer: check Ads Manager"],
};
// The console's own read-back check stopped it (audit A3-109): Meta refused nothing.
export const decidedOf = (p) => (p.status === "failed" && p.checked ? ["bad", "Not applied: the copy Meta stored didn't match"] : DECIDED[p.status]);

// The ad a suggestion is about, wherever the row says so.
const aboutId = (p) => p.about_ad || (p.payload && p.payload.template_ad_id) || (p.entity_type === "ad" ? p.entity_id : null);

// What kind of suggestion this is, as a short label; `rank` keeps the same kinds together.
export function suggestionType(p) {
  const pl = p.payload || {};
  if (isVersion(p)) return { label: "New version", rank: 3 };
  if (p.kind === "budget") return { label: "Budget", rank: 0 };
  if (p.kind === "status") return { label: "On / off", rank: 1 };
  if (p.kind === "spend_limit") return { label: "Spending limit", rank: 0 };
  if (p.kind === "creative") return pl.update_ad || pl.vertical ? { label: "Update ad", rank: 2 } : { label: "New ad", rank: 2 };
  if (p.kind === "targeting") return { label: "Targeting", rank: 4 };
  if (p.kind === "experiment") return { label: "Test", rank: 5 };
  if (p.kind === "tags") return { label: "Labels", rank: 6 };
  return { label: "Note", rank: 7 };
}

export function changeList(p, ix) {
  const pl = p.payload || {};
  const from = ((ix && ix.ads) || {})[aboutId(p)] || {};
  const adName = from.name || p.entity_name || "this ad";  // a name, never Meta's id
  const adLink = aboutId(p) && (from.name || p.entity_name) ? entityLink("ad", aboutId(p), adName) : esc(adName);
  if (p.kind === "creative" && pl.vertical) {
    return `<dl class="facts changes"><div><dt>Ad</dt><dd>${adLink} <span class="muted">(updated, not copied)</span></dd></div>
      <div><dt>Reels, Stories</dt><dd><ins>New 9:16 video Claude made</ins></dd></div>
      <div><dt>Feeds</dt><dd class="muted">Same 4:5 video as now</dd></div>
      <div><dt>Words, button, form</dt><dd class="muted">Same as now</dd></div></dl>`;
  }
  if (p.kind === "creative") {
    const rows = [];
    if (pl.update_ad) rows.push(`<div><dt>Ad</dt><dd>${adLink} <span class="muted">(updated, not copied)</span></dd></div>`);
    const same = (a, b) => String(a || "").trim() === String(b || "").trim();
    rows.push(same(pl.title, from.title)
      ? `<div><dt>Headline</dt><dd>${esc(pl.title)} <span class="muted">(same as now)</span></dd></div>`
      : `<div><dt>Headline</dt><dd>${from.title ? `<del>${esc(from.title)}</del> → ` : ""}<ins>${esc(pl.title)}</ins></dd></div>`);
    rows.push(same(pl.body, from.body)
      ? `<div><dt>Text</dt><dd class="muted">Same as now</dd></div>`
      : `<div><dt>Text</dt><dd><details class="fulltext"><summary><ins>${esc(firstLine(pl.body))}</ins></summary><p class="v-body">${esc(pl.body)}</p>${from.body ? `<p class="muted small">Now: ${esc(from.body)}</p>` : ""}</details></dd></div>`);
    const media = pl.media && pl.media.kind !== "same";
    rows.push(`<div><dt>${pl.media && pl.media.kind === "image" ? "Image" : "Video"}</dt><dd>${media ? `<ins>New ${esc(pl.media.kind)} Claude made</ins>` : '<span class="muted">Same as now</span>'}</dd></div>`);
    if (pl.name && !pl.update_ad) rows.push(`<div><dt>Name</dt><dd>${esc(pl.name)}</dd></div>`);
    return `<dl class="facts changes">${rows.join("")}</dl>`;
  }
  if (p.kind === "spend_limit") {
    const to = pl.remove ? "No limit" : p.proposed_value || "";
    return `<dl class="facts changes"><div><dt>Account spending limit</dt><dd>${p.current_value ? `<del>${esc(p.current_value)}</del> → ` : ""}<ins>${esc(to)}</ins></dd></div>${
      p.expected ? `<div><dt>Then</dt><dd>${esc(p.expected)}</dd></div>` : ""}</dl>`;
  }
  if (p.kind === "tags" && p.payload) {
    const DIM = { hook: "Hook", angle: "Angle", persona: "Who it's for", format: "Format", offer: "Offer" };
    return `<dl class="facts changes">${Object.entries(p.payload.tags || {}).map(([d, v]) => `<div><dt>${esc(DIM[d] || d)}</dt><dd><ins>${esc(v)}</ins></dd></div>`).join("")}</dl>`;
  }
  if (p.kind === "experiment" && p.payload) {
    // Names line up with ad_ids when Claude wrote both: then each links to its ad.
    const arm = (a) => {
      const names = a.names || [], ids = a.ad_ids || [];
      if (!names.length) return "an ad";
      return names.map((n, i) => (ids.length === names.length ? entityLink("ad", ids[i], n) : esc(n))).join(", ");
    };
    const rows = (pl.arms || []).map((a) => `<div><dt>${esc(a.label)}</dt><dd>${arm(a)}</dd></div>`);
    rows.push(`<div><dt>Decided by</dt><dd>${esc(TEST_METRICS[pl.metric] || pl.metric)}</dd></div>`);
    const day = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    if (pl.start_day) rows.push(`<div><dt>Dates</dt><dd>From ${esc(day(pl.start_day))}${pl.end_day ? ` to ${esc(day(pl.end_day))}` : ", no end set"}</dd></div>`);
    if (pl.hypothesis) rows.push(`<div><dt>Idea</dt><dd>${esc(pl.hypothesis)}</dd></div>`);
    return `<dl class="facts changes">${rows.join("")}</dl>`;
  }
  const rows = [];
  if (p.entity_name) rows.push(`<div><dt>On</dt><dd>${p.entity_type ? `${esc(p.entity_type.replace("adset", "ad set"))} · ` : ""}${entityLink(p.entity_type, p.entity_id, p.entity_name)}</dd></div>`);
  if (p.current_value || p.proposed_value) rows.push(`<div><dt>${esc(p.field ? p.field.charAt(0).toUpperCase() + p.field.slice(1) : "Change")}</dt><dd>${p.current_value ? `<del>${esc(p.current_value)}</del> → ` : ""}<ins>${esc(p.proposed_value || "")}</ins></dd></div>`);
  if (p.expected) rows.push(`<div><dt>Then</dt><dd>${esc(p.expected)}</dd></div>`);
  if (p.rollback) rows.push(`<div><dt>Undo</dt><dd>${esc(p.rollback)}</dd></div>`);
  return rows.length ? `<dl class="facts changes">${rows.join("")}</dl>` : "";
}

// One line saying what accepting does; the confirmations quote it.
export function changeSummary(p, ix) {
  const pl = p.payload || {};
  if (p.kind === "tags") return "Labels the ad's idea so Results can compare ideas. Nothing changes on Meta.";
  if (p.kind === "experiment") return `Tracks “${pl.name || p.title}” on the Tests page. Nothing changes on Meta.`;
  const adName = p.entity_name || (((ix && ix.ads) || {})[pl.template_ad_id] || {}).name || "the ad";
  if (p.kind === "creative" && pl.vertical) return `Updates “${adName}” on Meta: Reels and Stories show Claude's 9:16 video, feeds keep the 4:5 one. Same words and form.`;
  if (p.kind === "creative" && pl.update_ad) return `Updates “${adName}” on Meta with this version. It stays the same ad and keeps its results.`;
  if (p.kind === "creative") return `New ad “${pl.name || p.title}”, created switched off${pl.media && pl.media.kind !== "same" ? ", with Claude's new " + pl.media.kind : ""}.`;
  if (p.kind === "spend_limit") return pl.remove ? "Removes the account spending limit" : `Spending limit ${p.current_value || "—"} → ${p.proposed_value || "—"}`;
  if (p.kind === "status") return [p.entity_name, /^(paused|off|pause)$/i.test(p.proposed_value || "") ? "turns off" : /^(active|on|resume)$/i.test(p.proposed_value || "") ? "turns on" : p.proposed_value].filter(Boolean).join(" · ");
  return [p.entity_name, p.field && `${p.field}: ${p.current_value || "—"} → ${p.proposed_value || "—"}`].filter(Boolean).join(" · ");
}

const PREVIEW_TABS = [["MOBILE_FEED_STANDARD", "Feed"], ["INSTAGRAM_REELS", "Reels"], ["INSTAGRAM_STORY", "Stories"]];

// What the card shows beside its words on the Claude page: Meta's preview of a new ad, or the ad it would change.
function media(p, ix) {
  if (p.kind === "creative" && p.payload) {
    const reels = p.payload.vertical;
    return `<div class="sg-media">
      ${reels ? '<p class="sg-media-label">How Reels will show it</p>' : `<div class="segmented fill" role="tablist" aria-label="Placement" data-tabpanel="sgp-${p.id}">${PREVIEW_TABS.map(([f, l], i) => `<button type="button" role="tab" data-pf="${f}" aria-selected="${!i}">${l}</button>`).join("")}</div>`}
      <div class="decision-preview" id="sgp-${p.id}" data-preview="${p.id}"${reels ? ' data-format="INSTAGRAM_REELS"' : ""} aria-label="Preview of the ad as Meta shows it">${previewSkeleton()}</div>
      <div class="sg-media-do"><button class="btn btn-small btn-quiet" type="button" data-view-proposal="${p.id}">Larger</button>${ix.ads[p.about_ad] ? `<button class="btn btn-small btn-quiet" type="button" data-compare="${p.id}">Compare with now</button>` : ""}</div>
    </div>`;
  }
  const ad = ix.ads[p.about_ad];
  const src = ad && (ad.thumbnail_url || ad.image_url);
  return ad ? `<button class="sg-thumb" type="button" data-view-cr="${esc(ad.id)}" aria-label="Preview ${esc(ad.name)}">${src ? `<img src="${esc(src)}" alt="" loading="lazy">` : icon("image")}</button>` : "";
}

// The buttons. Claude page: Accept opens the Accept sheet. Inline: the confirmation in tasks.js.
function actions(p, place, task) {
  const pl = p.payload || {};
  const creative = p.kind === "creative" && p.payload;
  const other = creative && !pl.vertical && pl.template_ad_id ? (pl.update_ad ? ["new", "Make a new ad instead"] : ["update", "Update the ad instead"]) : null;
  const edit = creative && !pl.update_ad && !pl.vertical ? `<a class="btn btn-small" href="/new-ad.html?proposal=${p.id}">Edit first</a>` : "";
  const instead = other ? `<button class="btn btn-small btn-quiet" type="button" data-approve="${p.id}" data-as="${other[0]}">${other[1]}</button>` : "";
  if (place === "claude") {
    return `<button class="btn btn-small btn-claude" type="button" data-accept="${p.id}">${WORDS.accept}</button>
      <button class="btn btn-small" type="button" data-revise="${p.id}">Ask to change</button>${edit}${instead}
      <button class="btn btn-small btn-quiet" type="button" data-decline-one="${p.id}">Decline</button>`;
  }
  const adId = task && task.options && task.options.ad_id;
  if (isVersion(p) && adId) {
    return `<button class="btn btn-claude btn-small" type="button" data-render-ad="${esc(adId)}" data-render-task="${task.id}" data-render-note="${esc(p.rationale || p.title)}">Make it now</button>
      <button class="btn btn-small" type="button" data-decline="${p.id}">Not now</button>`;
  }
  const main = !creative ? WORDS.accept : pl.vertical || pl.update_ad ? "Update this ad" : "Create this ad (off)";
  return `<button class="btn btn-claude btn-small" type="button" data-approve="${p.id}">${main}</button>${edit}${instead}
    <button class="btn btn-small" type="button" data-decline="${p.id}">Decline</button>`;
}

// suggestionCard(p, { ix, place: "claude" | "inline", task }) → the card's HTML.
export function suggestionCard(p, { ix = null, place = "inline", task = null } = {}) {
  const index = ix || { ads: {} };
  const change = changeSummary(p, index);
  const side = place === "claude" ? media(p, index) : "";
  const big = place === "claude" && p.kind === "creative" && p.payload;
  const decided = p.status !== "pending" && decidedOf(p);
  const foot = p.status === "pending"
    ? `<div class="sg-do">${actions(p, place, task)}</div>`
    : `<p class="flush"><span class="pill ${decided ? decided[0] : ""}">${esc(decided ? decided[1] : p.status)}</span>${p.decided_at ? ` <span class="muted small">${esc(when(p.decided_at))}</span>` : ""}</p>${
      p.check ? `<div class="sg-result">${outcomeLine(p.check, { changeId: p.check.change_id, canUndo: Boolean(p.check.can_undo), expect: p.check.expected || p.check.expected_text, label: p.title })}</div>` : ""}`;
  return `<article class="sg ${big ? "with-media" : side ? "with-thumb" : ""}" id="p-${p.id}" data-kind="${esc(p.kind)}" data-proposal="${p.id}" data-title="${esc(p.title)}" data-change="${esc(change)}">
    ${side}
    <div class="sg-main">
      <header class="sg-top"><span class="sg-type">${esc(suggestionType(p).label)}</span><b>${esc(p.title)}</b></header>
      ${changeList(p, index)}
      ${p.rationale ? `<p class="why">${esc(p.rationale)}</p>` : ""}
      ${p.kind === "tags" || p.kind === "experiment" ? `<p class="muted small flush">${esc(change)}</p>` : ""}
      ${isVersion(p) ? '<p class="muted small flush">Claude rebuilds the video on your Mac (10–40 minutes) and brings it back here for a yes or no. Nothing changes on the live ad until you say yes.</p>' : ""}
      ${foot}
    </div>
  </article>`;
}
