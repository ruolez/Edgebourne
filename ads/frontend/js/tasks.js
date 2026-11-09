// Desk tasks and Claude's proposals, rendered the same way on Desk, Research and ad pages.
import { api } from "./api.js";
import { confirmDialog, esc, toast, when } from "./ui.js";
import { renderMarkdown } from "./markdown.js";

export const KIND_LABELS = { question: "Question", review: "Review results", research: "Research competitors", creative: "New ad ideas" };
const STATUS = {
  queued: ["warn", "Waiting for your Mac"], claimed: ["claude", "Claude picked it up"], running: ["claude", "Claude is working"],
  done: ["ok", "Done"], failed: ["bad", "Didn't finish"], cancelled: ["", "Cancelled"],
};
export const ACTIVE = new Set(["queued", "claimed", "running"]);
const DECIDED = {
  applied: ["ok", "Approved and applied"], approved: ["ok", "Approved"], declined: ["", "Declined"],
  failed: ["bad", "Approved, but Meta refused"], expired: ["", "Expired"],
};

export function proposalCard(p) {
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
      ${t.proposals.map(proposalCard).join("")}
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
    const decline = e.target.closest("[data-decline]");
    try {
      if (cancel) { await api(`/api/desk/tasks/${cancel.dataset.cancel}/cancel`, { method: "POST" }); toast("Cancelled"); onChange(); }
      if (again) { await api(`/api/desk/tasks/${again.dataset.again}/again`, { method: "POST" }); toast("Asked again"); onChange(); }
      if (approve || decline) {
        const card = (approve || decline).closest("[data-proposal]");
        const id = card.dataset.proposal;
        const yes = await confirmDialog(approve ? {
          title: `Approve “${card.dataset.title}”?`,
          body: `<p>${esc(card.dataset.change || "")}</p><p class="muted">If this is an on/off or budget change, it's applied on Meta as soon as you approve. Anything else is recorded as approved.</p>`,
          confirm: "Approve", claude: true,
        } : { title: `Decline “${card.dataset.title}”?`, body: "<p>Nothing changes on Meta.</p>", confirm: "Decline" });
        if (!yes) return;
        const r = await api(`/api/proposals/${id}/${approve ? "approve" : "decline"}`, { method: "POST" });
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
