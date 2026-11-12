// Desk tasks and Claude's proposals, rendered the same way on Desk, Research and ad pages.
import { api } from "./api.js";
import { confirmDialog, esc, toast, when } from "./ui.js";
import { renderMarkdown } from "./markdown.js";
import { money } from "./format.js";
import { lastChangeWords, spendBody, spendWords } from "./controls.js";
import { suggestionCard } from "./suggest.js";

export const KIND_LABELS = { question: "Question", review: "Review results", research: "Research competitors", creative: "New ad ideas", polish: "Polish", render: "New version", advice: "Meta's advice", diagnose: "Diagnosis" };
const STATUS = {
  queued: ["warn", "Waiting for your Mac"], claimed: ["claude", "Claude picked it up"], running: ["claude", "Claude is working"],
  done: ["ok", "Done"], failed: ["bad", "Didn't finish"], cancelled: ["", "Cancelled"],
};
export const ACTIVE = new Set(["queued", "claimed", "running"]);
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

// Claude's suggestions on the ad page and Research: the one Suggestion card (suggest.js).
// `ix.ads` holds the ad it is about, so the card names it and shows what stays the same.
export const proposalCard = (p, task = null, ix = null) => suggestionCard(p, { ix, place: "inline", task: task && task.options ? task : null });

export function taskCard(t, openReports = new Set(), ix = null) {
  const [cls, label] = STATUS[t.status] || ["", t.status];
  const meta = [(t.options && t.options.schedule) || KIND_LABELS[t.kind] || t.kind, t.kind === "diagnose" && t.options && t.options.alert ? t.options.alert.title : "", t.campaign_name, when(t.created_at), t.created_by_name || (t.options && t.options.schedule ? "on schedule" : "")].filter(Boolean).map(esc).join(" · ");
  const working = ACTIVE.has(t.status) && t.status !== "queued" && t.progress ? `<p class="progress"><span class="dot" aria-hidden="true"></span>${esc(t.progress)}</p>` : "";
  const reports = t.reports.map((r) => `
    <details class="report" data-report="${r.id}" ${openReports.has(r.id) ? "open" : ""}>
      <summary>${esc(r.title)}</summary>
      <div class="md">${renderMarkdown(r.body)}</div>
    </details>`).join("");
  const proposals = t.proposals.length ? `
    <div class="sg-list">
      <p class="muted small flush">Claude's suggestions. Accepting an on/off or budget change applies it on Meta right away; other kinds are recorded for the next step.</p>
      ${t.proposals.map((p) => proposalCard(p, t, ix)).join("")}
    </div>` : "";
  const actions = [
    t.status === "queued" ? `<button class="btn btn-small" type="button" data-cancel="${t.id}">Cancel</button>` : "",
    ["claimed", "running"].includes(t.status) ? `<button class="btn btn-small" type="button" data-stop-task="${t.id}">Stop</button>` : "",
    ["failed", "cancelled", "done"].includes(t.status) ? `<a class="btn btn-small" href="/desk.html#r/${t.id}">Reply</a><button class="btn btn-small" type="button" data-again="${t.id}">Ask again</button>` : "",
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

// The confirmation for accepting a suggestion, from the server's fresh read of Meta (audit A1, A20):
// a budget shows today's live budget → the new one in dollars; turning on shows the daily spend.
function approvalDialog(card, plan) {
  const title = `Accept “${card.dataset.title}”?`;
  if (plan.kind === "unclear") { toast(plan.problem, "bad"); return null; }
  if (plan.kind === "budget") {
    if (plan.problem && !plan.big) { toast(plan.problem, "bad"); return null; }
    const pct = plan.pct == null ? "" : ` (${plan.pct > 0 ? "+" : ""}${plan.pct}%)`;
    // A raise under 3 days after the last change needs the same knowing yes as everywhere else (rule 6).
    const recent = !!plan.recent;
    return {
      dialog: {
        title, claude: true, danger: !!plan.big || recent, confirm: recent ? "Raise anyway" : plan.big ? "Change it anyway" : "Change the budget",
        body: `<p>Daily budget of <b>${esc(plan.name)}</b> on Meta, read just now:</p>
          <p class="big-change"><del>${money(plan.from, { exact: true })}</del> → <ins>${money(plan.to, { exact: true })}</ins> a day${pct}</p>
          <p class="muted small">About ${money(plan.to * 30)} a month. Meta may spend up to 75% more on a busy day and evens it out over the week.</p>
          ${plan.big ? '<p class="note warn"><b>More than +20% in one step.</b> Meta may restart learning and results can wobble for a few days. The rule here is +20% at most, three days apart.</p>' : ""}
          ${recent ? `<p class="note warn"><b>Less than 3 days since the last change.</b> Meta is still adjusting to it; another raise now makes results hard to read.</p><p class="muted small">${lastChangeWords(plan.last)}</p>` : ""}`,
      },
      body: { from_cents: plan.from, to_cents: plan.to, accept_big: !!plan.big, ...(recent ? { accept_recent: true } : {}) },
    };
  }
  if (plan.kind === "status" && plan.to === "ACTIVE") {
    return {
      dialog: {
        title, claude: true, confirm: "Turn it on",
        body: `<p><b>${esc(plan.name)}</b> starts delivering${spendWords(plan.spend)}.</p>${plan.already ? '<p class="muted small">Meta already shows it on.</p>' : ""}`,
      },
      body: spendBody(plan.spend),
    };
  }
  if (plan.kind === "status" && plan.already) {
    return {
      dialog: { title, claude: true, confirm: "Accept", body: `<p><b>${esc(plan.name)}</b> is already off on Meta (read just now), so nothing is sent. Accepting records it.</p>` },
      body: {},
    };
  }
  if (plan.kind === "vertical") {
    return {
      dialog: {
        title, claude: true, confirm: "Update the ad",
        body: `<p><b>${esc(plan.name)}</b> is updated on Meta: feeds keep its 4:5 video, Reels and Stories show Claude's 9:16 one. Same words, same form.</p>
          <p class="muted small">Meta reviews the ad again before the new version runs${plan.live ? " (usually minutes, sometimes up to a day)" : ""}, and a creative change can restart learning. The console checks Meta's copy first; if anything is off, the ad isn't touched.</p>`,
      },
      body: {},
    };
  }
  if (plan.kind === "update") {
    return {
      dialog: {
        title, claude: true, confirm: "Update the ad",
        body: `<p><b>${esc(plan.name)}</b> gets this version on Meta. It stays the same ad and keeps its results.</p>
          <ul class="muted small"><li>Meta reviews it again${plan.live ? " (usually minutes, sometimes up to a day), and it may not show until that's done" : ""}. ${plan.live ? "Once Meta approves it, it runs by itself, with no switch to flip." : "It stays off until you turn it on."}</li>
          <li>Learning can restart, and earlier comments and likes may no longer be visible.</li>
          <li>You can switch back from the ad's Overview. The console checks Meta's copy first; if anything is off, the ad isn't touched.</li></ul>`,
      },
      body: {},
    };
  }
  const words = { status: "It's switched off on Meta right away. Nothing is deleted.", create: "The new ad is created switched off; nothing spends until you turn it on.",
    experiment: "It starts tracking on the Tests page. Nothing changes on Meta.", tags: "The labels are saved. Nothing changes on Meta.",
    record: "Claude picks it up on your Mac and answers in the conversation." };
  return {
    dialog: { title, claude: true, confirm: "Accept", body: `<p>${esc(card.dataset.change || "")}</p><p class="muted">${words[plan.kind] || ""}</p>` },
    body: {},
  };
}

// Click handling for conversations and suggestion cards; onChange reloads the page data.
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
        body: "<p>Claude rebuilds the creative on your Mac with these fixes (10–40 minutes), uploads it to your media library and sends it back as a suggestion. Nothing changes on the live ad until you accept it.</p>",
        confirm: "Make it", claude: true,
      });
      if (!yes) return;
      try {
        await api(`/api/ads/ad/${encodeURIComponent(render.dataset.renderAd)}/render`, { method: "POST",
          body: { from_task: Number(render.dataset.renderTask), from_proposal: Number(card.dataset.proposal), direction: render.dataset.renderNote } });
        await api(`/api/proposals/${card.dataset.proposal}/approve`, { method: "POST" });
        toast("Sent to Claude. The new version shows up here as a suggestion.");
        onChange();
      } catch (err) { toast(err.message, "bad"); }
      return;
    }
    const decline = e.target.closest("[data-decline]");
    const stopTask = e.target.closest("[data-stop-task]");
    try {
      if (stopTask) {
        const yes = await confirmDialog({ title: "Stop Claude here?", body: "<p>Your Mac ends this within a few seconds. The conversation stays, and nothing changes on your ads.</p>", confirm: "Stop it", danger: true });
        if (yes) { await api(`/api/desk/tasks/${stopTask.dataset.stopTask}/stop`, { method: "POST" }); toast("Stopped"); onChange(); }
        return;
      }
      if (cancel) { await api(`/api/desk/tasks/${cancel.dataset.cancel}/cancel`, { method: "POST" }); toast("Cancelled"); onChange(); }
      if (again) { await api(`/api/desk/tasks/${again.dataset.again}/again`, { method: "POST" }); toast("Asked again"); onChange(); }
      if (approve || decline) {
        const card = (approve || decline).closest("[data-proposal]");
        const id = card.dataset.proposal;
        if (decline) {
          const yes = await confirmDialog({ title: `Decline “${card.dataset.title}”?`, body: "<p>Nothing changes on Meta.</p>", confirm: "Decline" });
          if (!yes) return;
          await api(`/api/proposals/${id}/decline`, { method: "POST" });
          toast("Declined");
          onChange();
          return;
        }
        approve.disabled = true;
        let plan;
        const as = approve.dataset.as;
        try { plan = await api(`/api/proposals/${id}/check${as ? `?as=${as}` : ""}`); }
        catch (err) { approve.disabled = false; throw err; }
        const ask = approvalDialog(as === "new" ? { dataset: { title: card.dataset.title, change: "A separate new ad with this version. The current ad stays as it is." } } : card, plan);
        if (!ask) { approve.disabled = false; return; }
        const yes = await confirmDialog(ask.dialog);
        if (!yes) { approve.disabled = false; return; }
        let r;
        try { r = await api(`/api/proposals/${id}/approve`, { method: "POST", body: as ? { ...ask.body, apply_as: as } : ask.body }); }
        catch (err) { approve.disabled = false; throw err; }
        if (r.experiment_id) { toast("Tracking it. Opening the test…"); location.href = `/experiments.html#${r.experiment_id}`; return; }
        if (r.ad_id) { toast("Ad created (off). Opening it…"); location.href = `/ad.html?id=${encodeURIComponent(r.ad_id)}&created=1`; return; }
        if (r.updated_ad) { toast("Ad updated. Meta reviews it next."); onChange(); return; }
        toast(r.status === "applied" ? "Accepted and applied on Meta" : r.status === "approved" ? (r.note || "Accepted") : "Declined");
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
