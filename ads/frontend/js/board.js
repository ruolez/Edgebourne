// Pieces of the Claude page: one suggestion, and each ad's story.
// Data comes from /api/desk: tasks (with proposals carrying about_ad, state, result_ad),
// ads (by id) and families (an ad plus every ad made from it).
import { api } from "./api.js";
import { esc, icon, showPreviewFrame, when } from "./ui.js";
import { statusPill } from "./format.js";
import { renderMarkdown } from "./markdown.js";
import { KIND_LABELS, scoreClass } from "./tasks.js";
import { suggestionCard, suggestionType } from "./suggest.js";

const STATE_PILL = {
  waiting: "claude", working: "claude", live: "ok", off: "", review: "warn", archived: "", deleted: "",
  applied: "ok", approved: "ok", done: "ok", declined: "", expired: "", failed: "bad", unknown: "warn",
};
export const RUN_WORDS = { advice: "Meta's advice", diagnose: "Diagnosis", polish: "Polish", render: "New version", question: "Question", review: "Results review", research: "Competitor research", creative: "New ad ideas" };
const ACTIVE = new Set(["queued", "claimed", "running"]);

export function index(data) {
  const proposals = new Map();
  const taskOf = new Map();
  const swipes = new Map();
  data.tasks.forEach((t) => {
    t.proposals.forEach((p) => { proposals.set(p.id, p); taskOf.set(p.id, t); });
    (t.swipes || []).forEach((s) => swipes.set(s.id, s));
  });
  return { proposals, taskOf, swipes, tasks: new Map(data.tasks.map((t) => [t.id, t])), ads: data.ads || {} };
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
    return `<li>${adLink(ad, shortName(ad, root))} ${statusPill(ad.effective_status)}</li>`;
  }).join("");
  return `<header class="fam-head">${thumb(root)}
    <div class="fam-title"><h2>${adLink(root)}</h2>
      ${fam.ads.length > 1 ? `<ul class="versions" aria-label="Versions of this ad">${versions}</ul>` : `<p class="flush">${statusPill(root.effective_status)}</p>`}
    </div></header>`;
}

export function firstLine(text) {
  return String(text || "").split("\n")[0];
}


// The suggestion card itself lives in suggest.js (one card for every page).
export const suggestion = (p, ix) => suggestionCard(p, { ix, place: "claude" });
export { suggestionType };

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
  const look = p.kind === "creative" && p.payload ? ` <button class="prow-look" type="button" data-view-proposal="${p.id}">Preview</button>` : "";
  const go = p.can_continue ? ` <button class="prow-look" type="button" data-continue="${p.id}">Have Claude do this</button>` : "";
  const why = p.failure ? `<small class="prow-why">${esc(p.failure)}</small>` : "";
  return `<li class="prow">${pill(p.state)}<span class="prow-title">${esc(p.title)}${outcome(p, ix)}${decide}${look}${go}${why}</span></li>`;
}

// One Suggestion card everywhere (9.4e): what still waits for a decision is the same card as in the
// conversation and on the ad page; decided ones stay one line each.
function proposalsHtml(list, ix) {
  const waiting = list.filter((p) => p.status === "pending");
  const decided = list.filter((p) => p.status !== "pending");
  return `${waiting.length ? `<div class="sg-list">${waiting.map((p) => suggestion(p, ix)).join("")}</div>` : ""}${
    decided.length ? `<ul class="prows">${decided.map((p) => proposalRow(p, ix)).join("")}</ul>` : ""}`;
}

function runItem(t, ix, openReports) {
  const score = t.scorecard && t.scorecard.overall != null
    ? `<span class="score-chip ${scoreClass(t.scorecard.overall)}">${esc(t.scorecard.overall)}/5</span>` : "";
  const status = t.status === "done" ? "" : `<span class="pill ${ACTIVE.has(t.status) ? "claude" : t.status === "failed" ? "bad" : ""}">${esc({ queued: "Waiting for your Mac", claimed: "Starting", running: "Working", failed: "Didn't finish", cancelled: "Cancelled" }[t.status] || t.status)}</span>`;
  const reports = t.reports.map((r) => `<details class="report" data-report="${r.id}" ${openReports.has(r.id) ? "open" : ""}><summary>Read the report: ${esc(r.title)}</summary><div class="md">${renderMarkdown(r.body)}</div></details>`).join("");
  const props = proposalsHtml(t.proposals, ix);
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
          return stray.length ? `<li class="run"><div class="run-when"><b>From other conversations</b></div><div class="run-body">${proposalsHtml(stray, ix)}</div></li>` : "";
        })()}</ol>
    </div>
  </section>`).join("");
}

// ---------------------------------------------------------------- previews

const previewCache = new Map();
const watch = (root) => {
  const obs = new IntersectionObserver((entries) => entries.forEach((e) => {
    if (!e.isIntersecting) return;
    obs.unobserve(e.target);
    fillPreview(e.target);
  }), { root, rootMargin: "900px 0px" });
  return obs;
};
// Conversations scroll in their own box; By ad scrolls with the page.
const scroller = document.getElementById("cv-scroll");
const observer = watch(scroller);
const pageObserver = watch(null);

export async function fillPreview(box) {
  const id = box.dataset.preview;
  const fmt = box.dataset.format || "MOBILE_FEED_STANDARD";
  const key = `${id}:${fmt}`;
  try {
    let p = previewCache.get(key);
    if (!p) { p = await api(`/api/proposals/${id}/preview?format=${fmt}`); previewCache.set(key, p); }
    if ((box.dataset.format || "MOBILE_FEED_STANDARD") !== fmt) return;
    showPreviewFrame(box, p, { title: "New ad preview from Meta", height: p.height || 560 });
  } catch (err) {
    box.innerHTML = `<p class="preview-error">${esc(err.message)}</p>`;
  }
}

export function loadPreviews(root) {
  root.querySelectorAll("[data-preview]").forEach((el) => (scroller && scroller.contains(el) ? observer : pageObserver).observe(el));
}
