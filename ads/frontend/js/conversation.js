// The Claude page's conversations: the list on the left, one conversation on the right.
// A conversation is one or more runs (data.board.threads); each run is what you said and Claude's answer.
// Everything is said once: the list names a conversation, the message carries its words, the answer its result.
import { emptyState, esc, icon, when } from "./ui.js";
import { renderMarkdown } from "./markdown.js";
import { acctDay, clock as acctClock, dayWords } from "./format.js";
import { scorecardHtml } from "./tasks.js";
import { RUN_WORDS, firstLine, proposalRow, suggestion, suggestionType } from "./board.js";
import { adStatus, reportParts } from "./reading.js";
import { attachmentKey, attachmentsHtml, sentFilesHtml } from "./attach.js";
import { showsHtml } from "./shows.js";

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const pendingIn = (t) => t.proposals.filter((p) => p.status === "pending");
const byType = (a, b) => suggestionType(a).rank - suggestionType(b).rank || a.id - b.id;
const isLive = (t) => t.status === "claimed" || t.status === "running";
const OFF_STATES = ["offline", "not_set_up", "sign_in"];
const TYPED = new Set(["question", "review", "research", "creative"]);

// A diagnosis is named after the alert it looks into (its prompt starts with the same line every time).
export const turnTitle = (t) => (t.options && t.options.schedule)
  || (t.kind === "diagnose" && t.options && t.options.alert ? `Diagnosis: ${t.options.alert.title}` : firstLine(t.prompt));
const kindWord = (t) => (t.options && t.options.schedule ? "Scheduled" : RUN_WORDS[t.kind] || t.kind);
// Where a conversation came from is worth a word only when nobody typed it here: a schedule, an alert, a polish.
const originWord = (t) => (t.options && t.options.schedule ? "Scheduled" : TYPED.has(t.kind) ? "" : RUN_WORDS[t.kind] || "");
export const threadTitle = (th, ix) => turnTitle(ix.tasks.get(th.turns[0]));
export const liveTurn = (th, ix) => th.turns.map((id) => ix.tasks.get(id)).find(isLive);
export const queuedTurn = (th, ix) => th.turns.map((id) => ix.tasks.get(id)).find((t) => t.status === "queued");

export const clock = (secs) => `${Math.floor(secs / 60)}:${String(Math.max(0, Math.floor(secs % 60))).padStart(2, "0")}`;

function took(fromIso, toIso) {
  const mins = Math.max(0, Math.round((new Date(toIso) - new Date(fromIso)) / 60000));
  if (mins < 1) return "under a minute";
  return mins < 60 ? `${mins} min` : `${Math.floor(mins / 60)} h ${mins % 60} min`;
}

// Today / Yesterday on the account's clock (FU-C), whatever zone the browser is in.
function dayOf(iso) {
  const day = acctDay(new Date(iso)), today = acctDay();
  const y = new Date(`${today}T12:00:00Z`);
  y.setUTCDate(y.getUTCDate() - 1);
  return day >= today ? "Today" : day === y.toISOString().slice(0, 10) ? "Yesterday" : "Earlier";
}

function shortWhen(iso) {
  const day = dayOf(iso);
  if (day === "Today") return acctClock(iso);
  return day === "Yesterday" ? day : dayWords(iso);
}

// ---------------------------------------------------------------- the list

function row(th, data, ix, ctx) {
  const first = ix.tasks.get(th.turns[0]);
  const live = liveTurn(th, ix);
  const fresh = th.fresh.length > 0;
  let dot = fresh ? "fresh" : "";
  let sub = esc(originWord(first));
  let side = `<time class="cl-time">${esc(shortWhen(th.last_at))}</time>`;
  let tools = `<span class="cl-tools on-hover"><button class="cl-x" type="button" data-clear-thread="${th.id}" aria-label="Clear this conversation" title="Clear">${icon("close")}</button></span>`;
  if (th.cleared) {
    tools = `<span class="cl-tools"><button class="btn btn-small btn-quiet" type="button" data-restore-thread="${th.id}">Put back</button></span>`;
    side = "";
  } else if (th.state === "working") {
    dot = "working";
    sub = `<i>${esc(live.progress || "Starting…")}</i>`;
    side = "";
    const sure = ctx.stopSure === th.id;
    tools = data.bridge.can_stop ? `<span class="cl-tools"><button class="btn btn-small ${sure ? "btn-danger" : ""} cl-stop" type="button" data-stop="${th.id}"><span class="sq" aria-hidden="true"></span>${sure ? "Stop it?" : "Stop"}</button></span>` : "";
  } else if (th.state === "needs") {
    dot = "needs";
    sub = `<i>${th.waiting} to decide</i>`;
  } else if (th.state === "failed") {
    dot = "failed";
    sub = "<em>Didn’t finish</em>";
  } else if (th.state === "stopped") {
    dot = "off";
    sub = "Stopped";
  }
  return `<li class="cl-item">
    <a class="cl-row ${fresh ? "is-fresh" : ""}" href="#r/${th.id}" ${ctx.sel === th.id ? 'aria-current="true"' : ""}>
      <span class="cl-dot ${dot}" aria-hidden="true"></span>
      <span class="cl-text"><b>${esc(threadTitle(th, ix))}</b>${sub ? `<small>${sub}</small>` : ""}${fresh ? '<span class="sr-only">New answer</span>' : ""}</span>
      ${side}
    </a>${tools}
  </li>`;
}

// One thing waiting on the Mac. A follow-up shows which conversation it belongs to.
function queueRow(t, i, data, ix, ctx) {
  const key = t.thread_id || t.id;
  const th = data.board.threads[key];
  const sub = t.thread_id ? `Follow-up in: ${esc(threadTitle(th, ix))}` : esc(originWord(t));
  return `<li class="cl-item">
    <a class="cl-row" href="#r/${t.id}" ${ctx.sel === key ? 'aria-current="true"' : ""}>
      <span class="cl-dot pos" aria-hidden="true">${i + 1}</span>
      <span class="cl-text"><b>${esc(turnTitle(t))}</b>${sub ? `<small>${sub}</small>` : ""}</span>
    </a><span class="cl-tools">${i ? `<button class="cl-x" type="button" data-next="${t.id}" aria-label="Run this next" title="Run next">↑</button>` : ""}<button class="cl-x" type="button" data-cancel="${t.id}" aria-label="Cancel this one" title="Cancel">${icon("close")}</button></span>
  </li>`;
}

function matches(th, ix, q) {
  if (!q) return true;
  return th.turns.some((id) => { const t = ix.tasks.get(id); return `${t.prompt} ${t.summary || ""}`.toLowerCase().includes(q); });
}

export function listHtml(data, ix, ctx) {
  const b = data.board;
  const T = (id) => b.threads[id];
  const shown = (ids) => ids.map(T).filter((th) => matches(th, ix, ctx.query));
  const total = Object.values(b.threads).reduce((n, th) => n + th.waiting, 0);
  const decide = total ? `<a class="cl-decide" href="#decide" ${ctx.sel === "decide" ? 'aria-current="true"' : ""}><b>${total}</b><span>${total === 1 ? "suggestion" : "suggestions"} to decide</span>${icon("chev")}</a>` : "";
  const working = b.working.map(T);
  const busy = working.length || b.queue.length;
  // What the Mac is on and what waits for it. The Mac's own status is said once, in the sidebar; here it shows
  // only when it explains why the line isn't moving (the server's words, desk_view.mac_status).
  const m = data.bridge.status || {};
  const stuck = busy && OFF_STATES.includes(m.state) ? `<p class="cl-note" data-mac="${m.state}"><b>${esc(m.title)}.</b> ${esc(m.detail)}</p>` : "";
  const now = busy ? `<section class="cl-group cl-now">
      <header class="cl-head"><h2>${working.length ? "Working now" : "In line"}</h2>${b.queue.length > 1 ? '<button type="button" data-clear="queue">Clear the line</button>' : ""}</header>
      ${stuck}
      <ul>${working.map((th) => row(th, data, ix, ctx)).join("")}${b.queue.map((id, i) => queueRow(ix.tasks.get(id), i, data, ix, ctx)).join("")}</ul>
    </section>` : "";
  const recent = shown(b.recent);
  const days = ["Today", "Yesterday", "Earlier"].map((day) => {
    const group = recent.filter((th) => dayOf(th.last_at) === day);
    if (!group.length) return "";
    const clearable = group.filter((th) => !th.waiting);
    return `<section class="cl-group">
      <header class="cl-head"><h2>${day}</h2>${clearable.length ? `<button type="button" data-clear-day="${clearable.map((th) => th.id).join(",")}">Clear ${clearable.length === 1 ? "" : `all ${clearable.length}`}</button>` : ""}</header>
      <ul>${group.map((th) => row(th, data, ix, ctx)).join("")}</ul>
    </section>`;
  }).join("");
  const cleared = b.cleared.length ? `<section class="cl-group">
      <button class="cl-toggle" type="button" data-show-cleared aria-expanded="${ctx.showCleared}">Cleared <span>${b.cleared.length}</span></button>
      ${ctx.showCleared ? `<ul>${shown(b.cleared).map((th) => row(th, data, ix, ctx)).join("")}</ul>` : ""}
    </section>` : "";
  const none = !data.tasks.length ? '<p class="cl-note muted">What you ask Claude shows up here.</p>'
    : ctx.query && !recent.length ? '<p class="cl-note muted">No conversation matches that.</p>' : "";
  return decide + now + days + cleared + none;
}

// ---------------------------------------------------------------- one turn

// The steps of a run. While it works only the last few stay in view; the earlier ones fold into one line.
const TRAIL_SHOWN = 3;
function trail(t, live, open) {
  const steps = t.steps || [];
  const end = live ? null : t.finished_at;
  const fold = live && !open && steps.length > TRAIL_SHOWN + 1 ? steps.length - TRAIL_SHOWN : 0;
  const rows = steps.map((s, i) => {
    const next = steps[i + 1] ? steps[i + 1].at : end;
    const running = live && i === steps.length - 1;
    const secs = next ? (new Date(next) - new Date(s.at)) / 1000 : 0;
    return `<li class="${running ? "now" : ""}" ${i < fold ? "hidden" : ""}><span class="tick" aria-hidden="true">${running ? "●" : "✓"}</span><b>${esc(s.text)}</b><time ${running ? `data-since="${new Date(s.at).getTime()}"` : ""}>${running ? "" : clock(secs)}</time></li>`;
  });
  const earlier = fold ? `<li class="cv-earlier"><button class="cv-link" type="button" data-earlier="${t.id}">${plural(fold, "earlier step")}</button></li>` : "";
  return `<ul class="cv-trail">${earlier}${rows.join("")}</ul>`;
}

function asked(t, th) {
  const o = t.options || {};
  const auto = o.schedule || o.accepted || ["polish", "render", "advice"].includes(t.kind);
  const long = t.prompt.length > 480 || o.schedule;
  const body = long
    ? `<details class="cv-more"><summary>${esc(turnTitle(t))}</summary><p>${esc(t.prompt)}</p></details>`
    : `<p class="cv-said">${esc(t.prompt)}</p>`;
  // A diagnosis shows the request as Eugene sent it, with the alert it came from (W1a).
  const alert = t.kind === "diagnose" && o.alert;
  const notes = [
    // The campaign a conversation was limited to, said once on its first message.
    t.id === th.turns[0] && t.campaign_name && !o.ad_name && TYPED.has(t.kind) && !o.schedule ? `<span class="cv-about">Only ${esc(t.campaign_name)}</span>` : "",
    o.about ? `<span class="cv-about">About: ${esc(o.about.title)}</span>` : "",
    o.about_attachment ? `<span class="cv-about">About this preview: ${esc(o.about_attachment.title || "")}</span>` : "",
    alert ? `<span class="cv-about">From an alert: ${alert.alert_id ? `<a href="/inbox.html#item=${encodeURIComponent(`alert:${alert.alert_id}`)}">${esc(alert.title)}</a>` : esc(alert.title)}</span>` : "",
  ].join("");
  return `<div class="cv-you ${auto ? "auto" : ""}">${sentFilesHtml(t)}${notes}${body}</div>`;
}

// A message that hasn't started says why under itself, with what you can do about it.
function waitLine(t, th, data) {
  const ahead = data.board.queue.indexOf(t.id);
  const m = data.bridge.status || {};
  const off = OFF_STATES.includes(m.state);
  // A message behind a run in its own conversation waits for that run, whatever else is going on.
  const behind = th.state === "working";
  const words = behind ? "Runs as soon as Claude finishes this one."
    : off ? `${m.title}. ${m.waits || ""}`
      : ahead > 0 ? `${ahead} ahead of this one in line.`
        : data.board.working.length ? "Next, as soon as Claude finishes the current one." : "Starting…";
  return `<p class="cv-wait ${off && !behind ? "warn" : ""}"><span>${esc(words)}</span>${ahead > 0 ? `<button class="cv-link" type="button" data-next="${t.id}">Run next</button>` : ""}<button class="cv-link" type="button" data-cancel="${t.id}">Cancel</button></p>`;
}

// The ads an answer names, as chips that open Meta's preview. What the answer already shows large is left out.
function adsIn(t, ix) {
  const large = new Set((t.shows || []).filter((s) => s.type === "ad").map((s) => s.id));
  const ids = [...new Set([t.options && t.options.ad_id, ...(t.mentions || [])].filter(Boolean))].filter((id) => ix.ads[id] && !large.has(id));
  if (!ids.length) return "";
  return `<section class="cv-crs" aria-label="Ads in this answer">${ids.map((id) => {
    const ad = ix.ads[id];
    const src = ad.thumbnail_url || ad.image_url;
    const [cls, label] = adStatus(ad);
    return `<button class="cv-cr" type="button" data-view-cr="${esc(id)}" aria-label="Preview ${esc(ad.name)}">
      <span class="cv-cr-img">${src ? `<img src="${esc(src)}" alt="" loading="lazy">` : icon("image")}</span>
      <b>${esc(ad.name)}</b><small class="${cls}">${esc(label)}</small></button>`;
  }).join("")}</section>`;
}

function swipesIn(t) {
  if (!t.swipes || !t.swipes.length) return "";
  return `<section class="cv-block" aria-label="Ads Claude found"><h3 class="cv-label">Ads Claude found <span>${t.swipes.length}</span></h3><div class="cv-swipes">${t.swipes.map((s) => `
    <button class="cv-swipe" type="button" data-view-swipe="${s.id}">
      <span class="cv-swipe-img">${s.media_url ? `<img src="${esc(s.media_url)}" alt="" loading="lazy">` : icon("image")}</span>
      <b>${esc(s.page_name)}</b>${s.running_label ? `<small class="${s.long_running ? "long" : ""}">${esc(s.running_label)}</small>` : ""}
      <span class="cv-swipe-text">${esc(s.title || s.body || "")}</span>
    </button>`).join("")}</div></section>`;
}

function documentHtml(r, t, ctx, withSuggestions) {
  const { intro, sections } = reportParts(r.body, t.summary);
  const open = (s, i) => {
    const key = `${r.id}:${i}`;
    if (ctx.openSecs.has(key)) return ctx.openSecs.get(key);
    return !/^(data used|sources?|method)/i.test(s.title) && (!withSuggestions || i === 0);
  };
  const head = `<header class="cv-doc-head">${icon("table")}<h3>${esc(r.title)}</h3></header>`;
  const lead = intro ? `<div class="md cv-doc-intro">${renderMarkdown(intro)}</div>` : "";
  const body = sections.map((s, i) => `<details class="cv-sec" data-sec="${r.id}:${i}" ${open(s, i) ? "open" : ""}>
      <summary>${esc(s.title)}</summary><div class="md">${renderMarkdown(s.body)}</div></details>`).join("");
  return `<section class="cv-doc">${head}${lead}${body}</section>`;
}

function suggestionsHtml(t, ix) {
  if (!t.proposals.length) return "";
  const pending = pendingIn(t).sort(byType);
  const decided = t.proposals.filter((p) => p.status !== "pending");
  // Accepting always goes through the Accept sheet, which says what changes: the list needs no reassurance of its own.
  const head = pending.length ? `<header class="cv-sg-head"><h3 class="cv-label">${plural(pending.length, "suggestion")}</h3>
      ${pending.length > 1 ? `<button class="btn btn-small btn-quiet" type="button" data-decline-task="${t.id}">Decline all</button><button class="btn btn-small btn-claude-outline" type="button" data-accept-task="${t.id}">Accept all ${pending.length}</button>` : ""}</header>` : "";
  return `<section class="cv-block" aria-label="Suggestions">
    ${head}
    ${pending.length ? `<div class="sg-list">${pending.map((p) => suggestion(p, ix)).join("")}</div>` : ""}
    ${decided.length ? `<ul class="prows">${decided.map((p) => proposalRow(p, ix)).join("")}</ul>` : ""}
  </section>`;
}

function answer(t, data, ix, ctx) {
  if (isLive(t)) {
    const since = new Date(t.claimed_at || t.created_at).getTime();
    return `<div class="cv-live"><p class="cv-live-head"><span>Working</span><time data-since="${since}"></time></p>
      ${(t.steps || []).length ? trail(t, true, ctx.openSteps.has(t.id)) : `<p class="cv-progress"><span class="dot" aria-hidden="true"></span>${esc(t.progress || "Starting…")}</p>`}</div>`;
  }
  if (t.status === "failed") return `<p class="cv-note bad">${esc(t.error || "It stopped without saying why.")}</p><div class="cv-acts"><button class="btn btn-small" type="button" data-again="${t.id}">Try again</button></div>`;
  if (t.status === "cancelled") {
    return `<p class="cv-note">${t.claimed_at ? `You stopped this after ${esc(took(t.claimed_at, t.finished_at))}.` : "Cancelled before it started."} Nothing changed on your ads. Reply below to pick it up with new directions.</p>`;
  }
  const hasIdeas = t.proposals.length > 0;
  const score = t.scorecard && t.scorecard.passes ? `<section class="cv-score">${scorecardHtml(t.scorecard)}</section>` : "";
  const shown = attachmentsHtml(t) + showsHtml(t, ix);
  return `${t.summary ? `<p class="cv-lead">${esc(t.summary)}</p>` : ""}
    ${!t.summary && !t.reports.length && !shown ? '<p class="cv-note">No answer came back.</p>' : ""}
    ${shown}${adsIn(t, ix)}${swipesIn(t)}${score}
    ${t.reports.map((r) => documentHtml(r, t, ctx, hasIdeas)).join("")}
    ${suggestionsHtml(t, ix)}`;
}

// FU-D: how a turn ran, for the owner who can turn full access on (nobody else sees any of it). Only what is worth
// knowing is said: that it ran with full access, or why it didn't when it was meant to.
function ranWith(t) {
  const me = window.ebadsMe;
  if (!me || !me.full_access || !me.full_access.allowed || !t.claimed_at) return { tag: "", note: "" };
  if (t.access === "full") return { tag: '<span class="fa-tag">Full access</span>', note: "" };
  return { tag: "", note: t.access_note ? `<p class="fa-why">${esc(t.access_note)}</p>` : "" };
}

// Under a finished answer: when, how long it took, its steps on request, and what you can do with it.
function metaRow(t, th, ctx) {
  const steps = t.steps || [];
  const open = ctx.openSteps.has(t.id);
  const ran = ranWith(t);
  const facts = [shortWhen(t.finished_at || t.created_at), t.status === "done" && t.claimed_at && t.finished_at ? took(t.claimed_at, t.finished_at) : ""].filter(Boolean).map(esc).join(" · ");
  const stepsBtn = steps.length ? `<button class="cv-link" type="button" data-steps="${t.id}" aria-expanded="${open}">${plural(steps.length, "step")}</button>` : "";
  const hasText = t.status === "done" && (t.summary || t.reports.length);
  const copy = hasText ? `<button class="cv-tool" type="button" data-copy-turn="${t.id}" aria-label="Copy this answer" title="Copy">${icon("copy")}</button>` : "";
  const remove = th.turns.length > 1 && !pendingIn(t).length && !th.cleared
    ? `<button class="cv-tool cv-remove" type="button" data-clear-turn="${t.id}" aria-label="Remove this reply" title="Remove this reply">${icon("close")}</button>` : "";
  return `${ran.note}<footer class="cv-meta"><span>${facts}</span>${stepsBtn}${ran.tag}<span class="cv-meta-do">${copy}${remove}</span></footer>
    ${steps.length ? `<div data-steps-for="${t.id}" ${open ? "" : "hidden"}>${trail(t, false, true)}</div>` : ""}`;
}

export function turnHtml(t, th, data, ix, ctx) {
  if (t.status === "queued") return `${asked(t, th)}${waitLine(t, th, data)}`;
  return `${asked(t, th)}
    <article class="cv-claude" aria-label="Claude's answer"><span class="sr-only">Claude</span><span class="cv-mark" aria-hidden="true">${icon("spark")}</span>
      ${answer(t, data, ix, ctx)}
      ${isLive(t) ? "" : metaRow(t, th, ctx)}
    </article>`;
}

export function turnKey(t, th, data) {
  return JSON.stringify([t.status, t.progress, t.summary, t.error, t.mentions, t.access, t.access_note, attachmentKey(t), (t.files || []).map((f) => f.id), t.shows,
    (t.steps || []).length, (t.swipes || []).length, t.scorecard && t.scorecard.overall,
    t.proposals.map((p) => [p.id, p.status, p.state]), t.reports.map((r) => r.id), data.board.queue.indexOf(t.id), data.board.working.length, th.state, th.turns.length,
    data.bridge.online, data.bridge.status && data.bridge.status.state]);
}

// The words of an answer, for the clipboard.
export function answerText(t) {
  return [t.summary, ...t.reports.map((r) => `${r.title}\n\n${r.body}`)].filter(Boolean).join("\n\n");
}

// ---------------------------------------------------------------- every waiting suggestion

export function decideHtml(data, ix) {
  const tasks = data.tasks.filter((t) => pendingIn(t).length);
  if (!tasks.length) {
    return emptyState({ title: "Nothing to decide", body: "When Claude suggests a change it shows up here too, under the question it came from.", tag: "div", panel: false, variant: "center" });
  }
  return tasks.map((t) => `<section class="cv-group" data-group="${t.id}">
      <header><a class="cv-group-q" href="#r/${t.id}">${esc(turnTitle(t))}</a><small>${esc(kindWord(t))} · ${esc(when(t.created_at))}</small>
      ${t.summary ? `<p>${esc(t.summary)}</p>` : ""}</header>
      <div class="sg-list">${pendingIn(t).sort(byType).map((p) => suggestion(p, ix)).join("")}</div>
    </section>`).join("");
}

export function decideKey(data) {
  return JSON.stringify(data.tasks.filter((t) => pendingIn(t).length).map((t) => [t.id, t.summary, t.proposals.map((p) => [p.id, p.status])]));
}

// A conversation's header: what phones show above it (wide screens have the list beside it instead), and the
// review of every suggestion with its Accept all / Decline all.
export function headHtml(sel, data, ix) {
  const back = `<a class="cv-back" href="#list">${icon("back")}<span>All</span></a>`;
  if (sel === "new") return `${back}<h1>New conversation</h1>`;
  if (sel === "decide") {
    const total = Object.values(data.board.threads).reduce((n, th) => n + th.waiting, 0);
    return `${back}<h1>${total ? `${plural(total, "suggestion")} to decide` : "Nothing to decide"}</h1>
      ${total ? `<span class="cv-head-do"><button class="btn btn-small btn-quiet" type="button" data-decline-all>Decline all</button><button class="btn btn-small btn-claude" type="button" data-accept-all>Accept all ${total}</button></span>` : ""}`;
  }
  const th = data.board.threads[sel];
  const elsewhere = data.board.working.filter((id) => id !== sel).length + data.board.queue.length;
  const now = elsewhere ? `<a class="cv-now" href="#list"><span class="cl-dot working" aria-hidden="true"></span>${data.board.working.length ? "Working" : "In line"}${data.board.queue.length ? ` · ${data.board.queue.length}` : ""}</a>` : "";
  const busy = th.state === "working" || th.state === "queued";
  return `${back}<h1>${esc(threadTitle(th, ix))}</h1>${now}
    <span class="cv-head-do">${th.cleared ? `<button class="btn btn-small" type="button" data-restore-thread="${th.id}">Put back</button>` : busy ? "" : `<button class="btn btn-small" type="button" data-clear-thread="${th.id}">Clear</button>`}</span>`;
}
