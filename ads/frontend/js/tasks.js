// Desk tasks and Claude's proposals, rendered the same way on Desk, Research and ad pages.
import { api } from "./api.js";
import { confirmDialog, esc, toast, when } from "./ui.js";
import { renderMarkdown } from "./markdown.js";

export const KIND_LABELS = { question: "Question", review: "Review results", research: "Research competitors", creative: "New ad ideas", polish: "Polish", render: "New version" };
const STATUS = {
  queued: ["warn", "Waiting for your Mac"], claimed: ["claude", "Claude picked it up"], running: ["claude", "Claude is working"],
  done: ["ok", "Done"], failed: ["bad", "Didn't finish"], cancelled: ["", "Cancelled"],
};
export const ACTIVE = new Set(["queued", "claimed", "running"]);
const DECIDED = {
  applied: ["ok", "Approved and applied"], approved: ["ok", "Approved"], declined: ["", "Declined"],
  failed: ["bad", "Approved, but Meta refused"], expired: ["", "Expired"],
};

const SCORE_WORDS = { 5: "Ready", 4: "Small polish", 3: "Worth fixing", 2: "Hurting results", 1: "Blocking" };
export const scoreClass = (n) => (n >= 5 ? "s5" : n >= 4 ? "s4" : n >= 3 ? "s3" : "s2");

export function scorecardHtml(card) {
  if (!card || !card.passes) return "";
  const rows = card.passes.map((p) => `
    <details class="score-row ${scoreClass(p.score)}">
      <summary>
        <span class="score-name">${esc(p.label)}</span>
        <span class="score-bar" aria-hidden="true">${[1, 2, 3, 4, 5].map((i) => `<i class="${i <= (p.score || 0) ? "on" : ""}"></i>`).join("")}</span>
        <span class="score-num">${p.score ? `${p.score}/5` : "—"}</span>
        <span class="score-verdict">${esc(p.verdict || SCORE_WORDS[p.score] || "")}</span>
      </summary>
      <div class="score-detail">
        ${p.findings.length ? `<b>What Claude saw</b><ul>${p.findings.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}
        ${p.fixes.length ? `<b>Fixes</b><ul class="fixes">${p.fixes.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}
      </div>
    </details>`).join("");
  return `<section class="scorecard">
    <header><span class="overall ${scoreClass(card.overall)}"><b>${card.overall ?? "—"}</b><small>/5</small></span>
      <div><b>Polish score</b><p>${esc(card.headline || "")}</p></div></header>
    <div class="score-rows">${rows}</div>
  </section>`;
}

function creativeProposal(p) {
  const pl = p.payload || {};
  const decided = DECIDED[p.status];
  const foot = p.status === "pending"
    ? `<div class="row"><button class="btn btn-claude btn-small" type="button" data-approve="${p.id}">Create this ad (off)</button>
       <a class="btn btn-small" href="/new-ad.html?proposal=${p.id}">Edit first</a><button class="btn btn-small" type="button" data-decline="${p.id}">Decline</button></div>`
    : `<p class="flush"><span class="pill ${decided ? decided[0] : ""}">${esc(decided ? decided[1] : p.status)}</span></p>`;
  return `<article class="proposal variant" data-proposal="${p.id}" data-title="${esc(p.title)}" data-change="${esc(`New ad “${pl.name || ""}”, switched off, ${pl.media && pl.media.kind !== "same" ? "with new media" : "same image or video"}`)}">
    <header><span class="tag">new ad</span><b>${esc(p.title)}</b></header>
    <div class="variant-copy">
      <p class="v-headline">${esc(pl.title || "")}</p>
      <p class="v-body">${esc(pl.body || "")}</p>
      <p class="muted small flush">${pl.media && pl.media.kind !== "same" ? `New ${esc(pl.media.kind)} from Claude` : "Same image or video"}${pl.name ? ` · named “${esc(pl.name)}”` : ""}</p>
    </div>
    ${p.rationale ? `<p class="muted small flush">${esc(p.rationale)}</p>` : ""}
    ${foot}
  </article>`;
}

export function proposalCard(p, task = null) {
  if (p.kind === "creative" && p.payload) return creativeProposal(p);
  const adId = task && task.options && task.options.ad_id;
  if (p.status === "pending" && adId && /^make a new version/i.test(p.title || "")) {
    return `<article class="proposal" data-proposal="${p.id}" data-title="${esc(p.title)}">
      <header><span class="tag">new version</span><b>${esc(p.title)}</b></header>
      ${p.rationale ? `<p class="muted small">${esc(p.rationale)}</p>` : ""}
      <div class="row"><button class="btn btn-claude btn-small" type="button" data-render-ad="${esc(adId)}" data-render-task="${task.id}" data-render-note="${esc(p.rationale || p.title)}">Make it now</button>
        <button class="btn btn-small" type="button" data-decline="${p.id}">Not now</button></div>
    </article>`;
  }
  const change = p.field || p.current_value || p.proposed_value
    ? `<div><dt>Change</dt><dd>${esc(p.field || "")}${p.field ? ": " : ""}${esc(p.current_value || "—")} → <b>${esc(p.proposed_value || "—")}</b></dd></div>` : "";
  const row = (label, v) => (v ? `<div><dt>${label}</dt><dd>${esc(v)}</dd></div>` : "");
  const decided = DECIDED[p.status];
  const foot = p.status === "pending"
    ? `<div class="row"><button class="btn btn-claude btn-small" type="button" data-approve="${p.id}">Approve</button><button class="btn btn-small" type="button" data-decline="${p.id}">Decline</button></div>`
    : `<p class="flush"><span class="pill ${decided ? decided[0] : ""}">${esc(decided ? decided[1] : p.status)}</span>${p.decided_at ? ` <span class="muted small">${esc(when(p.decided_at))}</span>` : ""}</p>`;
  return `<article class="proposal" data-proposal="${p.id}" data-title="${esc(p.title)}" data-change="${esc([p.entity_name, p.field && `${p.field}: ${p.current_value || "—"} → ${p.proposed_value || "—"}`].filter(Boolean).join(" · "))}">
    <header><span class="tag">${esc(p.kind)}</span><b>${esc(p.title)}</b></header>
    <dl class="facts">
      ${row("On", [p.entity_type, p.entity_name].filter(Boolean).join(" · "))}
      ${change}${row("Why", p.rationale)}${row("Expected", p.expected)}${row("Undo", p.rollback)}
    </dl>
    ${foot}
  </article>`;
}

export function taskCard(t, openReports = new Set()) {
  const [cls, label] = STATUS[t.status] || ["", t.status];
  const meta = [KIND_LABELS[t.kind] || t.kind, t.campaign_name, when(t.created_at), t.created_by_name].filter(Boolean).map(esc).join(" · ");
  const working = ACTIVE.has(t.status) && t.status !== "queued" && t.progress ? `<p class="progress"><span class="dot" aria-hidden="true"></span>${esc(t.progress)}</p>` : "";
  const reports = t.reports.map((r) => `
    <details class="report" data-report="${r.id}" ${openReports.has(r.id) ? "open" : ""}>
      <summary>${esc(r.title)}</summary>
      <div class="md">${renderMarkdown(r.body)}</div>
    </details>`).join("");
  const proposals = t.proposals.length ? `
    <div class="proposals stack tight">
      <p class="muted small flush">Claude's proposals. Approving an on/off or budget change applies it on Meta right away; other kinds are recorded for the next step.</p>
      ${t.proposals.map((p) => proposalCard(p, t)).join("")}
    </div>` : "";
  const actions = [
    t.status === "queued" ? `<button class="btn btn-small" type="button" data-cancel="${t.id}">Cancel</button>` : "",
    ["failed", "cancelled", "done"].includes(t.status) ? `<button class="btn btn-small" type="button" data-again="${t.id}">Ask again</button>` : "",
  ].join("");
  return `<article class="panel task ${t.status}">
    <div class="panel-body stack tight">
      <header class="task-head"><span class="pill ${cls}">${esc(label)}</span><span class="muted small">${meta}</span><span class="spacer"></span>${actions}</header>
      <p class="prompt">${esc(t.prompt)}</p>
      ${working}
      ${t.summary ? `<p class="summary">${esc(t.summary)}</p>` : ""}
      ${scorecardHtml(t.scorecard)}
      ${t.error ? `<p class="note bad flush">${esc(t.error)}</p>` : ""}
      ${reports}${proposals}
    </div>
  </article>`;
}

// Click handling for task lists and proposal cards; onChange reloads the page data.
export function wireTaskActions(root, onChange, openReports) {
  root.addEventListener("click", async (e) => {
    const cancel = e.target.closest("[data-cancel]");
    const again = e.target.closest("[data-again]");
    const approve = e.target.closest("[data-approve]");
    const render = e.target.closest("[data-render-ad]");
    if (render) {
      const card = render.closest("[data-proposal]");
      const yes = await confirmDialog({
        title: "Make the new version now?",
        body: "<p>Claude rebuilds the creative on your Mac with these fixes (10–40 minutes), uploads it to your media library and sends it back as a new ad for you to approve. Nothing changes on the live ad.</p>",
        confirm: "Make it", claude: true,
      });
      if (!yes) return;
      try {
        await api(`/api/ads/ad/${encodeURIComponent(render.dataset.renderAd)}/render`, { method: "POST",
          body: { from_task: Number(render.dataset.renderTask), direction: render.dataset.renderNote } });
        await api(`/api/proposals/${card.dataset.proposal}/approve`, { method: "POST" });
        toast("Sent to Claude. The new version shows up under Runs.");
        onChange();
      } catch (err) { toast(err.message, "bad"); }
      return;
    }
    const decline = e.target.closest("[data-decline]");
    try {
      if (cancel) { await api(`/api/desk/tasks/${cancel.dataset.cancel}/cancel`, { method: "POST" }); toast("Cancelled"); onChange(); }
      if (again) { await api(`/api/desk/tasks/${again.dataset.again}/again`, { method: "POST" }); toast("Asked again"); onChange(); }
      if (approve || decline) {
        const card = (approve || decline).closest("[data-proposal]");
        const id = card.dataset.proposal;
        const yes = await confirmDialog(approve ? {
          title: `Approve “${card.dataset.title}”?`,
          body: `<p>${esc(card.dataset.change || "")}</p><p class="muted">On/off, budget and new-ad proposals are applied on Meta as soon as you approve (new ads are created switched off). Anything else is recorded as approved.</p>`,
          confirm: "Approve", claude: true,
        } : { title: `Decline “${card.dataset.title}”?`, body: "<p>Nothing changes on Meta.</p>", confirm: "Decline" });
        if (!yes) return;
        const r = await api(`/api/proposals/${id}/${approve ? "approve" : "decline"}`, { method: "POST" });
        if (r.ad_id) { toast("Ad created (off). Opening it…"); location.href = `/ad.html?id=${encodeURIComponent(r.ad_id)}&created=1`; return; }
        toast(r.status === "applied" ? "Approved and applied on Meta" : r.status === "approved" ? (r.note || "Approved") : "Declined");
        onChange();
      }
    } catch (err) { toast(err.message, "bad"); onChange(); }
  });
  if (openReports) {
    root.addEventListener("toggle", (e) => {
      const d = e.target.closest("details[data-report]");
      if (!d) return;
      const id = Number(d.dataset.report);
      if (d.open) openReports.add(id); else openReports.delete(id);
    }, true);
  }
}
