// The Claude page's main view: requests sorted into trays on the left, and on the right either one
// request (what you asked, Claude's answer, its suggestions) or every waiting suggestion together.
import { esc, icon, when } from "./ui.js";
import { renderMarkdown } from "./markdown.js";
import { scorecardHtml } from "./tasks.js";
import { RUN_WORDS, firstLine, proposalRow, suggestion, suggestionType } from "./board.js";

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const pendingIn = (t) => t.proposals.filter((p) => p.status === "pending");
const byType = (a, b) => suggestionType(a).rank - suggestionType(b).rank || a.id - b.id;

export const requestTitle = (t) => (t.options && t.options.schedule) || firstLine(t.prompt);
const kindWord = (t) => (t.options && t.options.schedule ? "Scheduled" : RUN_WORDS[t.kind] || t.kind);

function duration(fromIso, toIso) {
  const mins = Math.max(0, Math.round(((toIso ? new Date(toIso) : Date.now()) - new Date(fromIso)) / 60000));
  if (mins < 1) return "under a minute";
  return mins < 60 ? `${mins} min` : `${Math.floor(mins / 60)} h ${mins % 60} min`;
}

// ---------------------------------------------------------------- trays

function row(t, sel, { mark, end = "", sub, tools = "" }) {
  return `<li class="rq-wrap">
    <a class="rq" href="#r/${t.id}" data-row="${t.id}" ${sel === t.id ? 'aria-current="true"' : ""}>
      <span class="rq-mark ${mark}" aria-hidden="true">${mark === "pos" ? esc(sub.pos) : ""}</span>
      <span class="rq-text"><b>${esc(requestTitle(t))}</b><small>${esc(sub.text)}</small></span>
      ${end}
    </a>${tools ? `<span class="rq-tools">${tools}</span>` : ""}
  </li>`;
}

function tray(title, ids, rows, action = "", note = "") {
  if (!ids.length) return "";
  return `<section class="tray">
    <header class="tray-head"><h2>${esc(title)}</h2><span class="tray-n">${ids.length}</span>${action}</header>
    ${note}<ul class="rq-list">${rows}</ul>
  </section>`;
}

export function traysHtml(data, ix, sel, showCleared) {
  const b = data.board;
  const T = (id) => ix.tasks.get(id);
  const waiting = data.tasks.filter((t) => pendingIn(t).length);
  const total = waiting.reduce((n, t) => n + pendingIn(t).length, 0);
  const all = total ? `<a class="rq-all" href="#decide" ${sel === "decide" ? 'aria-current="true"' : ""}>
      <span class="rq-all-n">${total}</span>
      <span class="rq-text"><b>Review all suggestions</b><small>From ${plural(waiting.length, "request")}</small></span>
    </a>` : "";
  const needs = tray("Needs you", b.needs_you, b.needs_you.map((id) => {
    const t = T(id);
    return row(t, sel, { mark: "needs", end: `<span class="n claude">${pendingIn(t).length}</span>`, sub: { text: `${kindWord(t)} · ${when(t.finished_at || t.created_at)}` } });
  }).join(""));
  const working = tray("On your Mac", b.working, b.working.map((id) => {
    const t = T(id);
    return row(t, sel, { mark: "working", sub: { text: t.progress || "Starting…" },
      tools: data.bridge.can_stop ? `<button class="btn btn-small btn-quiet" type="button" data-stop="${t.id}">Stop</button>` : "" });
  }).join(""));
  const offline = !data.bridge.online && b.next.length ? '<p class="tray-note">Your Mac is offline. These start when it’s back.</p>' : "";
  const next = tray("Up next", b.next, b.next.map((id, i) => {
    const t = T(id);
    return row(t, sel, { mark: "pos", sub: { pos: i + 1, text: `${kindWord(t)} · asked ${when(t.created_at)}` },
      tools: `${i ? `<button class="btn btn-small btn-quiet" type="button" data-next="${t.id}">Run next</button>` : ""}<button class="btn btn-small btn-quiet" type="button" data-cancel="${t.id}">Cancel</button>` });
  }).join(""), `<button class="tray-act" type="button" data-clear="queue">Clear queue</button>`, offline);
  const finished = tray("Finished", b.finished, b.finished.map((id) => {
    const t = T(id);
    const fresh = b.fresh.includes(id);
    return row(t, sel, { mark: t.status === "failed" ? "failed" : fresh ? "fresh" : "done",
      end: fresh ? '<span class="rq-new">New</span>' : "", sub: { text: `${t.status === "failed" ? "Didn’t finish" : kindWord(t)} · ${when(t.finished_at)}` } });
  }).join(""), `<button class="tray-act" type="button" data-clear="finished">Clear all</button>`);
  const cleared = b.cleared.length ? `<section class="tray cleared">
      <button class="tray-toggle" type="button" data-show-cleared aria-expanded="${showCleared}">Cleared <span class="tray-n">${b.cleared.length}</span></button>
      ${showCleared ? `<ul class="rq-list">${b.cleared.map((id) => {
        const t = T(id);
        return row(t, sel, { mark: t.status === "cancelled" ? "off" : "done", sub: { text: `${t.status === "cancelled" ? "Cancelled" : kindWord(t)} · ${when(t.finished_at)}` } });
      }).join("")}</ul>` : ""}
    </section>` : "";
  const empty = data.tasks.length ? "" : '<p class="tray-note">Nothing asked yet. What you ask Claude shows up here, from waiting to finished.</p>';
  return all + needs + working + next + finished + cleared + empty;
}

// ---------------------------------------------------------------- suggestions

function suggestionRows(list, ix, ctx) {
  const defaultOpen = ctx.total <= 3;
  return list.slice().sort(byType).map((p) => suggestion(p, ix, {
    open: ctx.openRows.has(p.id) ? ctx.openRows.get(p.id) : defaultOpen,
    picked: ctx.picked.has(p.id),
  })).join("");
}

// ---------------------------------------------------------------- every waiting suggestion

export function decideHtml(data, ix, ctx) {
  const tasks = data.tasks.filter((t) => pendingIn(t).length);
  const total = tasks.reduce((n, t) => n + pendingIn(t).length, 0);
  if (!total) {
    return `<div class="clear-state"><h2>Nothing is waiting for you</h2>
      <p>When Claude suggests a change it lands here, under the question it came from.</p>
      <button class="btn btn-claude-outline" type="button" data-ask>Ask Claude</button></div>`;
  }
  const group = (t) => {
    const list = pendingIn(t);
    return `<section class="dg" data-group="${t.id}">
      <header class="dg-head">
        <label class="sg-tick"><input type="checkbox" data-pick-task="${t.id}" aria-label="Select all from this request"></label>
        <div class="dg-asked">
          <span class="step-label">You asked</span>
          <a class="dg-prompt" href="#r/${t.id}">${esc(requestTitle(t))}</a>
          <small>${esc(kindWord(t))} · ${esc(when(t.created_at))}${t.options && t.options.ad_name ? ` · ${esc(t.options.ad_name)}` : ""}</small>
          ${t.summary ? `<p class="dg-answer"><span class="step-label by-claude">Claude</span> ${esc(t.summary)}</p>` : ""}
        </div>
        ${tasks.length > 1 && list.length > 1 ? `<button class="btn btn-small btn-claude-outline" type="button" data-accept-task="${t.id}">Accept these ${list.length}</button>` : ""}
      </header>
      <div class="sg-list">${suggestionRows(list, ix, { ...ctx, total })}</div>
    </section>`;
  };
  return `<header class="detail-head">
      ${backLink}
      <div class="dh-title"><h2>${plural(total, "suggestion")} waiting</h2><p>From ${plural(tasks.length, "request")}, grouped by what you asked</p></div>
      <div class="dh-do">
        <label class="pick-all"><input type="checkbox" data-pick-all> Select all</label>
        <button class="btn btn-quiet" type="button" data-decline-all>Decline all</button>
        <button class="btn btn-claude" type="button" data-accept-all>Accept all ${total}</button>
      </div>
    </header>
    ${tasks.map(group).join("")}`;
}

const backLink = `<a class="detail-back" href="#requests">${icon("back")}Requests</a>`;

// ---------------------------------------------------------------- one request

function status(t, data) {
  if (t.status === "queued") return ["warn", `Up next · #${data.board.next.indexOf(t.id) + 1} in line`];
  if (t.status === "claimed" || t.status === "running") return ["claude", "Working on your Mac"];
  if (t.status === "failed") return ["bad", "Didn’t finish"];
  if (t.status === "cancelled") return ["", "Cancelled"];
  const n = pendingIn(t).length;
  return n ? ["claude", `${n} to decide`] : ["ok", "Finished"];
}

function requestActions(t, data) {
  const pending = pendingIn(t).length;
  if (t.status === "queued") {
    return `${data.board.next[0] !== t.id ? `<button class="btn btn-small" type="button" data-next="${t.id}">Run next</button>` : ""}<button class="btn btn-small" type="button" data-cancel="${t.id}">Cancel</button>`;
  }
  if (t.status === "claimed" || t.status === "running") return data.bridge.can_stop ? `<button class="btn btn-small" type="button" data-stop="${t.id}">Stop</button>` : "";
  return `<button class="btn btn-small" type="button" data-again="${t.id}">Ask again</button>
    ${t.archived_at && !pending ? `<button class="btn btn-small" type="button" data-restore="${t.id}">Put back</button>` : pending ? "" : `<button class="btn btn-small" type="button" data-clear-task="${t.id}">Clear</button>`}`;
}

function answer(t, data, openReports) {
  if (t.status === "queued") {
    const pos = data.board.next.indexOf(t.id);
    return `<p class="step-wait">${pos ? `${plural(pos, "request")} ahead of this one.` : "This one is next."} ${data.bridge.online ? "Your Mac runs one at a time." : "Your Mac is offline, so it starts when the Mac is back."}</p>`;
  }
  if (t.status === "claimed" || t.status === "running") {
    return `<p class="progress"><span class="dot" aria-hidden="true"></span>${esc(t.progress || "Starting…")}</p><p class="step-wait">Working for ${esc(duration(t.claimed_at || t.created_at))}.</p>`;
  }
  const took = t.claimed_at && t.finished_at && t.status === "done" ? `<p class="step-meta">Took ${esc(duration(t.claimed_at, t.finished_at))} · finished ${esc(when(t.finished_at))}</p>` : "";
  const score = t.scorecard && t.scorecard.passes
    ? `<details class="report"><summary>Scorecard: ${esc(t.scorecard.overall ?? "—")}/5 on ${t.scorecard.passes.length} checks</summary>${scorecardHtml(t.scorecard)}</details>` : "";
  const reports = t.reports.map((r, i) => `<details class="report" data-report="${r.id}" ${openReports.has(r.id) || (i === 0 && !t.proposals.length) ? "open" : ""}><summary>${esc(r.title)}</summary><div class="md">${renderMarkdown(r.body)}</div></details>`).join("");
  return `${t.summary ? `<p class="step-answer">${esc(t.summary)}</p>` : ""}${t.error ? `<p class="note bad flush">${esc(t.error)}</p>` : ""}${!t.summary && !t.error ? '<p class="step-wait">No answer came back.</p>' : ""}${took}${score}${reports}`;
}

export function requestHtml(t, data, ix, ctx) {
  const [cls, label] = status(t, data);
  const pending = pendingIn(t);
  const decided = t.proposals.filter((p) => p.status !== "pending");
  const parent = t.options && t.options.from_task && ix.tasks.get(t.options.from_task);
  const meta = [kindWord(t), t.options && t.options.ad_name, t.campaign_name, when(t.created_at), t.created_by_name].filter(Boolean).map(esc).join(" · ");
  return `<header class="detail-head request">${backLink}
      <span class="pill ${cls}">${esc(label)}</span>
      <div class="dh-do">${requestActions(t, data)}</div>
    </header>
    <ol class="thread">
      <li class="th-step">
        <span class="step-label">You asked</span>
        <p class="step-prompt">${esc(t.prompt)}</p>
        <p class="step-meta">${meta}${parent ? ` · from <a href="#r/${parent.id}">${esc(requestTitle(parent))}</a>` : ""}</p>
      </li>
      <li class="th-step th-reply">
        <span class="step-label by-claude">Claude</span>
        ${answer(t, data, ctx.openReports)}
      </li>
      ${t.proposals.length ? `<li class="th-step th-ideas">
        <header class="step-head">
          ${pending.length ? `<label class="sg-tick"><input type="checkbox" data-pick-task="${t.id}" aria-label="Select all from this request"></label>` : ""}
          <span class="step-label">Suggestions${pending.length ? ` · ${pending.length} waiting` : ""}</span>
          ${pending.length ? `<span class="spacer"></span><button class="btn btn-small btn-quiet" type="button" data-decline-task="${t.id}">Decline all</button>
            <button class="btn btn-small btn-claude" type="button" data-accept-task="${t.id}">Accept all ${pending.length}</button>` : ""}
        </header>
        ${pending.length ? `<div class="sg-list">${suggestionRows(pending, ix, { ...ctx, total: pending.length })}</div>` : ""}
        ${decided.length ? `<ul class="prows">${decided.map((p) => proposalRow(p, ix)).join("")}</ul>` : ""}
      </li>` : ""}
    </ol>`;
}

export function emptyDetail() {
  return `<div class="clear-state"><h2>Pick a request</h2><p>Or ask Claude something new.</p>
    <button class="btn btn-claude-outline" type="button" data-ask>Ask Claude</button></div>`;
}
