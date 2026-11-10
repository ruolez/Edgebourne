// Pieces of the Claude page: one suggestion, and each ad's story.
// Data comes from /api/desk: tasks (with proposals carrying about_ad, state, result_ad),
// ads (by id) and families (an ad plus every ad made from it).
import { api } from "./api.js";
import { esc, icon, showPreviewFrame, when } from "./ui.js";
import { statusOf } from "./format.js";
import { renderMarkdown } from "./markdown.js";
import { KIND_LABELS, scoreClass } from "./tasks.js";

const STATE_PILL = {
  waiting: "claude", working: "claude", live: "ok", off: "", review: "warn", archived: "", deleted: "",
  applied: "ok", approved: "ok", done: "ok", declined: "", expired: "", failed: "bad",
};
export const RUN_WORDS = { advice: "Meta's advice", polish: "Polish", render: "New version", question: "Question", review: "Results review", research: "Competitor research", creative: "New ad ideas" };
const ACTIVE = new Set(["queued", "claimed", "running"]);

export function index(data) {
  const proposals = new Map();
  const taskOf = new Map();
  data.tasks.forEach((t) => t.proposals.forEach((p) => { proposals.set(p.id, p); taskOf.set(p.id, t); }));
  return { proposals, taskOf, tasks: new Map(data.tasks.map((t) => [t.id, t])), ads: data.ads || {} };
}

const pill = (state) => `<span class="pill ${STATE_PILL[state[0]] ?? ""}">${esc(state[1])}</span>`;

// "N1 - One simple system · v2" inside N1's family reads as "v2".
function shortName(ad, root) {
  if (!ad) return "";
  if (root && ad.id === root.id) return "Original";
  const prefix = root ? `${root.name} · ` : "";
  return root && ad.name.startsWith(prefix) ? ad.name.slice(prefix.length) : ad.name;
}

function thumb(ad) {
  const src = ad && (ad.thumbnail_url || ad.image_url);
  return src ? `<img class="fam-thumb" src="${esc(src)}" alt="" loading="lazy">` : `<span class="fam-thumb empty">${icon("ads")}</span>`;
}

function adLink(ad, label) {
  return `<a href="/ad.html?id=${encodeURIComponent(ad.id)}">${esc(label || ad.name)}</a>`;
}

function familyHead(fam, ix) {
  if (!fam.root) {
    return `<header class="fam-head"><div class="fam-title"><h2>Not about one ad</h2><p class="muted small flush">Questions, results reviews and research</p></div></header>`;
  }
  const root = ix.ads[fam.root] || { id: fam.root, name: "Ad" };
  const versions = fam.ads.map((id) => ix.ads[id]).filter(Boolean).map((ad) => {
    const [cls, label] = statusOf(ad.effective_status);
    return `<li>${adLink(ad, shortName(ad, root))} <span class="pill ${cls}">${esc(label)}</span></li>`;
  }).join("");
  return `<header class="fam-head">${thumb(root)}
    <div class="fam-title"><h2>${adLink(root)}</h2>
      ${fam.ads.length > 1 ? `<ul class="versions" aria-label="Versions of this ad">${versions}</ul>` : `<p class="flush">${(() => { const [c, l] = statusOf(root.effective_status); return `<span class="pill ${c}">${esc(l)}</span>`; })()}</p>`}
    </div></header>`;
}

// ---------------------------------------------------------------- what changes

const TEST_METRICS = { cpl: "Cost per lead", cpql: "Cost per qualified lead", ctr: "Click rate", hook: "Hook rate" };

export function firstLine(text) {
  return String(text || "").split("\n")[0];
}

function changeList(p, ix) {
  const pl = p.payload || {};
  const from = ix.ads[p.about_ad] || {};
  if (p.kind === "creative" && pl.update_ad) {
    return `<dl class="facts changes"><div><dt>Ad</dt><dd>${esc(from.name || pl.template_ad_id)} <span class="muted">(updated, not copied)</span></dd></div>
      <div><dt>Reels, Stories</dt><dd><ins>New 9:16 video Claude made</ins></dd></div>
      <div><dt>Feeds</dt><dd class="muted">Same 4:5 video as now</dd></div>
      <div><dt>Words, button, form</dt><dd class="muted">Same as now</dd></div></dl>`;
  }
  if (p.kind === "creative") {
    const rows = [];
    const same = (a, b) => String(a || "").trim() === String(b || "").trim();
    rows.push(same(pl.title, from.title)
      ? `<div><dt>Headline</dt><dd>${esc(pl.title)} <span class="muted">(same as now)</span></dd></div>`
      : `<div><dt>Headline</dt><dd>${from.title ? `<del>${esc(from.title)}</del> → ` : ""}<ins>${esc(pl.title)}</ins></dd></div>`);
    rows.push(same(pl.body, from.body)
      ? `<div><dt>Text</dt><dd class="muted">Same as now</dd></div>`
      : `<div><dt>Text</dt><dd><details class="fulltext"><summary><ins>${esc(firstLine(pl.body))}</ins></summary><p class="v-body">${esc(pl.body)}</p>${from.body ? `<p class="muted small">Now: ${esc(from.body)}</p>` : ""}</details></dd></div>`);
    const media = pl.media && pl.media.kind !== "same";
    rows.push(`<div><dt>${pl.media && pl.media.kind === "image" ? "Image" : "Video"}</dt><dd>${media ? `<ins>New ${esc(pl.media.kind)} Claude made</ins>` : '<span class="muted">Same as now</span>'}</dd></div>`);
    if (pl.name) rows.push(`<div><dt>Name</dt><dd>${esc(pl.name)}</dd></div>`);
    return `<dl class="facts changes">${rows.join("")}</dl>`;
  }
  if (p.kind === "tags" && p.payload) {
    const DIM = { hook: "Hook", angle: "Angle", persona: "Who it's for", format: "Format", offer: "Offer" };
    return `<dl class="facts changes">${Object.entries(p.payload.tags).map(([d, v]) => `<div><dt>${esc(DIM[d] || d)}</dt><dd><ins>${esc(v)}</ins></dd></div>`).join("")}</dl>`;
  }
  if (p.kind === "experiment" && p.payload) {
    const arm = (a) => (a.names || []).join(", ") || "an ad";
    const rows = (pl.arms || []).map((a) => `<div><dt>${esc(a.label)}</dt><dd>${esc(arm(a))}</dd></div>`);
    rows.push(`<div><dt>Decided by</dt><dd>${esc(TEST_METRICS[pl.metric] || pl.metric)}</dd></div>`);
    const day = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    rows.push(`<div><dt>Dates</dt><dd>From ${esc(day(pl.start_day))}${pl.end_day ? ` to ${esc(day(pl.end_day))}` : ", no end set"}</dd></div>`);
    if (pl.hypothesis) rows.push(`<div><dt>Idea</dt><dd>${esc(pl.hypothesis)}</dd></div>`);
    return `<dl class="facts changes">${rows.join("")}</dl>`;
  }
  const rows = [];
  if (p.entity_name) rows.push(`<div><dt>On</dt><dd>${esc(p.entity_name)}</dd></div>`);
  if (p.current_value || p.proposed_value) rows.push(`<div><dt>${esc(p.field ? p.field.charAt(0).toUpperCase() + p.field.slice(1) : "Change")}</dt><dd>${p.current_value ? `<del>${esc(p.current_value)}</del> → ` : ""}<ins>${esc(p.proposed_value || "")}</ins></dd></div>`);
  if (p.expected) rows.push(`<div><dt>Then</dt><dd>${esc(p.expected)}</dd></div>`);
  if (p.rollback) rows.push(`<div><dt>Undo</dt><dd>${esc(p.rollback)}</dd></div>`);
  return rows.length ? `<dl class="facts changes">${rows.join("")}</dl>` : "";
}

function sourceLine(p, ix) {
  const t = ix.taskOf.get(p.id);
  if (!t) return "";
  const score = t.scorecard && t.scorecard.overall != null ? ` · scored ${t.scorecard.overall}/5` : "";
  const asked = p.requested_by ? "The new version you asked for · " : "";
  const story = p.kind === "experiment" || !p.about_ad ? "" : ` · <a href="#ads" data-goto-run="${t.id}">See this ad's story</a>`;
  return `<p class="source muted small flush">${asked}From the ${esc((RUN_WORDS[t.kind] || KIND_LABELS[t.kind] || t.kind).toLowerCase())} run, ${esc(when(t.created_at))}${score}${story}</p>`;
}

function changeSummary(p, ix) {
  const pl = p.payload || {};
  if (p.kind === "tags") return "Labels the ad's idea so Results can compare ideas. Nothing changes on Meta.";
  if (p.kind === "experiment") return `Tracks “${pl.name || p.title}” on the Tests page. Nothing changes on Meta.`;
  if (p.kind === "creative" && pl.update_ad) return `Updates “${p.entity_name || (ix && ix.ads && ix.ads[pl.template_ad_id] || {}).name || "the ad"}” on Meta: Reels and Stories show Claude's 9:16 video, feeds keep the 4:5 one. Same words and form.`;
  if (p.kind === "creative") return `New ad “${pl.name || p.title}”, created switched off${pl.media && pl.media.kind !== "same" ? ", with Claude's new " + pl.media.kind : ""}.`;
  if (p.kind === "status") return [p.entity_name, /^(paused|off|pause)$/i.test(p.proposed_value || "") ? "turns off" : /^(active|on|resume)$/i.test(p.proposed_value || "") ? "turns on" : p.proposed_value].filter(Boolean).join(" · ");
  return [p.entity_name, p.field && `${p.field}: ${p.current_value || "—"} → ${p.proposed_value || "—"}`].filter(Boolean).join(" · ");
}

const isVersion = (p) => /^make a new version/i.test(p.title || "");

// What kind of suggestion this is, as a short label; `rank` keeps the same kinds together.
export function suggestionType(p) {
  const pl = p.payload || {};
  if (isVersion(p)) return { label: "New version", rank: 3 };
  if (p.kind === "budget") return { label: "Budget", rank: 0 };
  if (p.kind === "status") return { label: "On / off", rank: 1 };
  if (p.kind === "creative") return pl.update_ad ? { label: "Update ad", rank: 2 } : { label: "New ad", rank: 2 };
  if (p.kind === "targeting") return { label: "Targeting", rank: 4 };
  if (p.kind === "experiment") return { label: "Test", rank: 5 };
  if (p.kind === "tags") return { label: "Labels", rank: 6 };
  return { label: "Note", rank: 7 };
}

// One suggestion: a line you can tick, accept or decline, which opens to the reason and Meta's preview.
export function suggestion(p, ix, { open, picked }) {
  const hasPreview = p.kind === "creative" && p.payload;
  const editable = hasPreview && !p.payload.update_ad;
  const change = changeSummary(p, ix);
  return `<article class="sg" id="p-${p.id}" data-proposal="${p.id}" data-title="${esc(p.title)}" data-change="${esc(change)}">
    <div class="sg-head">
      <label class="sg-tick"><input type="checkbox" data-pick="${p.id}" ${picked ? "checked" : ""} aria-label="Select: ${esc(p.title)}"></label>
      <button type="button" class="sg-open" data-toggle="${p.id}" aria-expanded="${open}" aria-controls="sg-body-${p.id}">
        <span class="sg-type">${esc(suggestionType(p).label)}</span>
        <span class="sg-text"><b>${esc(p.title)}</b>${change ? `<small>${esc(change)}</small>` : ""}</span>
        <svg class="sg-chev" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9.5l6 6 6-6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
      <span class="sg-do">
        <button class="btn btn-small btn-claude-outline" type="button" data-accept="${p.id}">Accept</button>
        <button class="btn btn-small btn-quiet" type="button" data-decline="${p.id}">Decline</button>
      </span>
    </div>
    <div class="sg-body${hasPreview ? " with-preview" : ""}" id="sg-body-${p.id}" ${open ? "" : "hidden"}>
      ${hasPreview ? `<div class="decision-preview" data-preview="${p.id}"${p.payload.update_ad ? ' data-format="INSTAGRAM_REELS"' : ""} aria-label="Preview of the ad as Meta shows it"><div class="preview-skeleton"><span></span><span></span><span></span><p>Loading Meta's preview…</p></div></div>` : ""}
      <div class="sg-why">
        ${p.rationale ? `<p class="why">${esc(p.rationale)}</p>` : ""}
        ${changeList(p, ix)}
        ${isVersion(p) ? '<p class="muted small flush">Claude rebuilds the video on your Mac (10–40 minutes) and brings it back here for a yes or no. Nothing changes on the live ad.</p>' : ""}
        ${editable ? `<p class="flush"><a class="btn btn-small" href="/new-ad.html?proposal=${p.id}">Edit first</a></p>` : ""}
        ${sourceLine(p, ix)}
      </div>
    </div>
  </article>`;
}

// ---------------------------------------------------------------- views

function outcome(p, ix) {
  const made = p.result_ad && ix.ads[p.result_ad];
  if (made) return ` → ${adLink(made, made.name)}`;
  const q = p.made_proposal && ix.proposals.get(p.made_proposal);
  if (q && q.result_ad && ix.ads[q.result_ad]) return ` → ${adLink(ix.ads[q.result_ad])}`;
  return "";
}

export function proposalRow(p, ix) {
  const decide = p.status === "pending" ? ` <a class="decide-link" href="#p/${p.id}">Decide</a>` : "";
  const run = p.followup_task && ix.tasks.get(p.followup_task);
  if (run && run.status === "done") {
    // A "make a new version" request: what it made is shown on the run that made it.
    return `<li class="prow">${pill(["done", "Made"])}<span class="prow-title">${esc(p.title)} → <a href="#ads" data-goto-run="${run.id}">made in the New version run, ${esc(when(run.created_at))}</a></span></li>`;
  }
  return `<li class="prow">${pill(p.state)}<span class="prow-title">${esc(p.title)}${outcome(p, ix)}${decide}</span></li>`;
}

function runItem(t, ix, openReports) {
  const score = t.scorecard && t.scorecard.overall != null
    ? `<span class="score-chip ${scoreClass(t.scorecard.overall)}">${esc(t.scorecard.overall)}/5</span>` : "";
  const status = t.status === "done" ? "" : `<span class="pill ${ACTIVE.has(t.status) ? "claude" : t.status === "failed" ? "bad" : ""}">${esc({ queued: "Waiting for your Mac", claimed: "Starting", running: "Working", failed: "Didn't finish", cancelled: "Cancelled" }[t.status] || t.status)}</span>`;
  const reports = t.reports.map((r) => `<details class="report" data-report="${r.id}" ${openReports.has(r.id) ? "open" : ""}><summary>Read the report: ${esc(r.title)}</summary><div class="md">${renderMarkdown(r.body)}</div></details>`).join("");
  const props = t.proposals.length ? `<ul class="prows">${t.proposals.map((p) => proposalRow(p, ix)).join("")}</ul>` : "";
  return `<li class="run" id="run-${t.id}">
    <div class="run-when"><b>${esc((t.options && t.options.schedule) || RUN_WORDS[t.kind] || KIND_LABELS[t.kind] || t.kind)}</b><span class="muted small">${esc(when(t.created_at))}</span></div>
    <div class="run-body">
      ${score || status ? `<div class="row tight">${score}${status}</div>` : ""}
      <p class="run-summary">${esc(t.summary || t.error || firstLine(t.prompt))}</p>
      ${props}${reports}
    </div>
  </li>`;
}

export function adsView(data, ix, openReports) {
  if (!data.families.length) return `<section class="panel empty"><h3>Nothing yet</h3><p>Each ad Claude works on gets its own story here: reviews, ideas, and what became of them.</p></section>`;
  return data.families.map((f) => `<section class="panel family" data-family="${esc(f.root || "account")}">
    <div class="panel-body">
      ${familyHead(f, ix)}
      <ol class="runs">${f.tasks.map((id) => runItem(ix.tasks.get(id), ix, openReports)).join("")}${
        // proposals about this ad that came from runs filed elsewhere (e.g. a results review)
        (() => {
          const stray = f.proposals.map((id) => ix.proposals.get(id)).filter((p) => p && !f.tasks.includes(ix.taskOf.get(p.id).id));
          return stray.length ? `<li class="run"><div class="run-when"><b>From other runs</b></div><div class="run-body"><ul class="prows">${stray.map((p) => proposalRow(p, ix)).join("")}</ul></div></li>` : "";
        })()}</ol>
    </div>
  </section>`).join("");
}

// ---------------------------------------------------------------- previews

const previewCache = new Map();
let observer;

async function fillPreview(box) {
  const id = box.dataset.preview;
  try {
    let p = previewCache.get(id);
    const fmt = box.dataset.format || "MOBILE_FEED_STANDARD";
    if (!p) { p = await api(`/api/proposals/${id}/preview?format=${fmt}`); previewCache.set(id, p); }
    showPreviewFrame(box, p, { title: box.dataset.format ? "How Reels will show it, from Meta" : "New ad preview from Meta", height: p.height || 560 });
  } catch (err) {
    box.innerHTML = `<p class="preview-error">${esc(err.message)}</p>`;
  }
}

export function loadPreviews(root) {
  if (observer) observer.disconnect();
  observer = new IntersectionObserver((entries) => entries.forEach((e) => {
    if (!e.isIntersecting) return;
    observer.unobserve(e.target);
    fillPreview(e.target);
  }), { rootMargin: "300px" });
  root.querySelectorAll("[data-preview]").forEach((el) => observer.observe(el));
}
