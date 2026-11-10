// The Claude page's three views: decisions waiting, each ad's story, every run.
// Data comes from /api/desk: tasks (with proposals carrying about_ad, state, result_ad),
// ads (by id) and families (an ad plus every ad made from it).
import { api } from "./api.js";
import { esc, icon, showPreviewFrame, when } from "./ui.js";
import { statusOf } from "./format.js";
import { renderMarkdown } from "./markdown.js";
import { KIND_LABELS, scoreClass, taskCard } from "./tasks.js";

const STATE_PILL = {
  waiting: "claude", working: "claude", live: "ok", off: "", review: "warn", archived: "", deleted: "",
  applied: "ok", approved: "ok", done: "ok", declined: "", expired: "", failed: "bad",
};
const RUN_WORDS = { polish: "Polish", render: "New version", question: "Question", review: "Results review", research: "Competitor research", creative: "New ad ideas" };
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

function firstLine(text) {
  return String(text || "").split("\n")[0];
}

function changeList(p, ix) {
  const pl = p.payload || {};
  const from = ix.ads[p.about_ad] || {};
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
  const story = p.kind === "experiment" ? "" : ` · <a href="#ads" data-goto-run="${t.id}">See this ad's story</a>`;
  return `<p class="source muted small flush">${asked}From the ${esc((RUN_WORDS[t.kind] || KIND_LABELS[t.kind] || t.kind).toLowerCase())} run, ${esc(when(t.created_at))}${score}${story}</p>`;
}

function actions(p, ix) {
  if (p.kind === "experiment" && p.payload) {
    return `<div class="row decide"><button class="btn btn-claude" type="button" data-approve="${p.id}">Track this test</button>
      <button class="btn btn-quiet" type="button" data-decline="${p.id}">Decline</button></div>`;
  }
  if (p.kind === "creative" && p.payload) {
    return `<div class="row decide"><button class="btn btn-claude" type="button" data-approve="${p.id}">Create this ad (off)</button>
      <a class="btn" href="/new-ad.html?proposal=${p.id}">Edit first</a>
      <button class="btn btn-quiet" type="button" data-decline="${p.id}">Decline</button></div>`;
  }
  const t = ix.taskOf.get(p.id);
  const adId = p.about_ad;
  if (adId && /^make a new version/i.test(p.title || "")) {
    return `<div class="row decide"><button class="btn btn-claude" type="button" data-render-ad="${esc(adId)}" data-render-task="${t.id}" data-render-note="${esc(p.rationale || p.title)}">Make it now</button>
      <button class="btn btn-quiet" type="button" data-decline="${p.id}">Not now</button></div>`;
  }
  return `<div class="row decide"><button class="btn btn-claude" type="button" data-approve="${p.id}">Approve</button>
    <button class="btn btn-quiet" type="button" data-decline="${p.id}">Decline</button></div>`;
}

function changeSummary(p) {
  const pl = p.payload || {};
  if (p.kind === "experiment") return `Tracks “${pl.name || p.title}” on the Tests page. Nothing changes on Meta.`;
  if (p.kind === "creative") return `New ad “${pl.name || p.title}”, created switched off${pl.media && pl.media.kind !== "same" ? ", with Claude's new " + pl.media.kind : ""}.`;
  return [p.entity_name, p.field && `${p.field}: ${p.current_value || "—"} → ${p.proposed_value || "—"}`].filter(Boolean).join(" · ");
}

export function decisionCard(p, ix) {
  const hasPreview = p.kind === "creative" && p.payload;
  const isRender = /^make a new version/i.test(p.title || "");
  return `<article class="decision${hasPreview ? " with-preview" : ""}" id="p-${p.id}" data-proposal="${p.id}" data-title="${esc(p.title)}" data-change="${esc(changeSummary(p))}">
    ${hasPreview ? `<div class="decision-preview" data-preview="${p.id}" aria-label="Preview of the new ad as Meta shows it"><div class="preview-skeleton"><span></span><span></span><span></span><p>Loading Meta's preview…</p></div></div>` : ""}
    <div class="decision-body">
      <h3>${esc(p.title)}</h3>
      ${p.rationale ? `<p class="why">${esc(p.rationale)}</p>` : ""}
      ${changeList(p, ix)}
      ${isRender ? '<p class="muted small flush">Claude rebuilds the video on your Mac (10–40 minutes) and brings it back here for a yes or no. Nothing changes on the live ad.</p>' : ""}
      ${actions(p, ix)}
      ${sourceLine(p, ix)}
    </div>
  </article>`;
}

// ---------------------------------------------------------------- views

export function workingStrip(data) {
  const busy = data.tasks.filter((t) => ACTIVE.has(t.status));
  if (!busy.length) return "";
  return `<section class="working-strip" aria-label="Claude is working">${busy.map((t) => `
    <p class="progress"><span class="dot" aria-hidden="true"></span><b>${esc(t.status === "queued" ? "Waiting for your Mac" : "Claude is working")}:</b> ${esc(firstLine(t.prompt))}${t.progress ? ` <span class="muted">· ${esc(t.progress)}</span>` : ""}
    ${t.status === "queued" ? `<button class="btn btn-small btn-quiet" type="button" data-cancel="${t.id}">Cancel</button>` : ""}</p>`).join("")}</section>`;
}

export function waitingView(data, ix) {
  const fams = data.families.filter((f) => f.pending);
  if (!fams.length) {
    return `<section class="panel empty"><h3>Nothing is waiting for you</h3>
      <p>When Claude suggests a change, it lands here with a preview and a yes or no. Ask for a review of an ad, or for new ad ideas, to get some.</p>
      <p><button class="btn btn-claude-outline" type="button" data-ask>Ask Claude</button></p></section>`;
  }
  return fams.map((f) => {
    const pending = f.proposals.map((id) => ix.proposals.get(id)).filter((p) => p && p.status === "pending");
    return `<section class="family" data-family="${esc(f.root || "account")}">
      ${familyHead(f, ix)}
      <div class="stack">${pending.map((p) => decisionCard(p, ix)).join("")}</div>
    </section>`;
  }).join("");
}

function outcome(p, ix) {
  const made = p.result_ad && ix.ads[p.result_ad];
  if (made) return ` → ${adLink(made, made.name)}`;
  const q = p.made_proposal && ix.proposals.get(p.made_proposal);
  if (q && q.result_ad && ix.ads[q.result_ad]) return ` → ${adLink(ix.ads[q.result_ad])}`;
  return "";
}

function proposalRow(p, ix) {
  const decide = p.status === "pending" ? ` <a class="decide-link" href="#waiting" data-goto-proposal="${p.id}">Decide</a>` : "";
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

export function runsView(data, ix, openReports) {
  if (!data.tasks.length) return `<section class="panel empty"><h3>Nothing asked yet</h3><p>Use Ask Claude for a question, a results review, competitor research or new ad ideas.</p></section>`;
  return data.tasks.map((t) => taskCard(t, openReports, { rows: (p) => proposalRow(p, ix), foldScore: true })).join("");
}

// ---------------------------------------------------------------- previews

const previewCache = new Map();
let observer;

async function fillPreview(box) {
  const id = box.dataset.preview;
  try {
    let p = previewCache.get(id);
    if (!p) { p = await api(`/api/proposals/${id}/preview?format=MOBILE_FEED_STANDARD`); previewCache.set(id, p); }
    showPreviewFrame(box, p, { title: "New ad preview from Meta", height: p.height || 560 });
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
