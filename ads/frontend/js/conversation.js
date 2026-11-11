// The Claude page's conversations: the list on the left, one conversation on the right.
// A conversation is one or more runs (data.board.threads); each run is what you said and Claude's answer.
import { esc, icon, when } from "./ui.js";
import { renderMarkdown } from "./markdown.js";
import { scorecardHtml } from "./tasks.js";
import { RUN_WORDS, firstLine, proposalRow, suggestion, suggestionType } from "./board.js";
import { adStatus, reportParts } from "./reading.js";

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const pendingIn = (t) => t.proposals.filter((p) => p.status === "pending");
const byType = (a, b) => suggestionType(a).rank - suggestionType(b).rank || a.id - b.id;
const isLive = (t) => t.status === "claimed" || t.status === "running";

export const turnTitle = (t) => (t.options && t.options.schedule) || firstLine(t.prompt);
const kindWord = (t) => (t.options && t.options.schedule ? "Scheduled" : RUN_WORDS[t.kind] || t.kind);
export const threadTitle = (th, ix) => turnTitle(ix.tasks.get(th.turns[0]));
export const liveTurn = (th, ix) => th.turns.map((id) => ix.tasks.get(id)).find(isLive);
export const queuedTurn = (th, ix) => th.turns.map((id) => ix.tasks.get(id)).find((t) => t.status === "queued");

export const clock = (secs) => `${Math.floor(secs / 60)}:${String(Math.max(0, Math.floor(secs % 60))).padStart(2, "0")}`;

function took(fromIso, toIso) {
  const mins = Math.max(0, Math.round((new Date(toIso) - new Date(fromIso)) / 60000));
  if (mins < 1) return "under a minute";
  return mins < 60 ? `${mins} min` : `${Math.floor(mins / 60)} h ${mins % 60} min`;
}

function dayOf(iso) {
  const d = new Date(iso);
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const days = Math.floor((start - d) / 86400000) + 1;
  return days <= 0 ? "Today" : days === 1 ? "Yesterday" : "Earlier";
}

function shortWhen(iso) {
  const d = new Date(iso);
  const day = dayOf(iso);
  if (day === "Today") return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return day === "Yesterday" ? day : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ---------------------------------------------------------------- the list

function row(th, data, ix, ctx, pos) {
  const last = ix.tasks.get(th.turns.at(-1));
  const live = liveTurn(th, ix);
  const queued = queuedTurn(th, ix);
  const at = shortWhen(th.last_at);
  const fresh = th.fresh.length > 0;
  let dot = fresh ? "fresh" : "";
  let sub = `${esc(kindWord(last))} · ${esc(at)}`;
  let tools = `<button class="cl-x" type="button" data-clear-thread="${th.id}" aria-label="Clear this conversation" title="Clear">${icon("close")}</button>`;
  if (th.cleared) {
    tools = `<button class="btn btn-small btn-quiet" type="button" data-restore-thread="${th.id}">Put back</button>`;
  } else if (th.state === "working") {
    dot = "working";
    sub = `<i>${esc(live.progress || "Starting…")}</i>`;
    const sure = ctx.stopSure === th.id;
    tools = data.bridge.can_stop ? `<button class="btn btn-small ${sure ? "btn-danger" : ""} cl-stop" type="button" data-stop="${th.id}"><span class="sq" aria-hidden="true"></span>${sure ? "Stop it?" : "Stop"}</button>` : "";
  } else if (th.state === "queued") {
    dot = "pos";
    sub = `${esc(kindWord(queued))} · asked ${esc(shortWhen(queued.created_at))}`;
    tools = `<button class="btn btn-small" type="button" data-cancel="${queued.id}">Cancel</button>`;
  } else if (th.state === "needs") {
    dot = "needs";
    sub = `<i>${th.waiting} to decide</i> · ${esc(at)}`;
  } else if (th.state === "failed") {
    dot = "failed";
    sub = `<em>Didn’t finish</em> · ${esc(at)}`;
  } else if (th.state === "stopped") {
    dot = "off";
    sub = `Stopped · ${esc(at)}`;
  }
  return `<li class="cl-item">
    <a class="cl-row" href="#r/${th.id}" ${ctx.sel === th.id ? 'aria-current="true"' : ""}>
      <span class="cl-dot ${dot}" aria-hidden="true">${dot === "pos" ? pos : ""}</span>
      <span class="cl-text"><b>${esc(threadTitle(th, ix))}</b><small>${sub}</small></span>
      ${fresh ? '<span class="cl-new-tag">New</span>' : ""}
    </a>${tools ? `<span class="cl-tools">${tools}</span>` : ""}
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
  const decide = total ? `<a class="cl-decide" href="#decide" ${ctx.sel === "decide" ? 'aria-current="true"' : ""}><b>${total}</b><span>${total === 1 ? "suggestion" : "suggestions"} to decide</span></a>` : "";
  const working = shown(b.working);
  const line = shown(b.line);
  const onMac = working.length || line.length ? `<section class="cl-group">
      <header class="cl-head"><h2>On your Mac</h2>${b.line.length ? '<button type="button" data-clear="queue">Clear the line</button>' : ""}</header>
      ${!data.bridge.online && line.length ? '<p class="cl-note">Your Mac is offline. These start when it’s back.</p>' : ""}
      <ul>${working.map((th) => row(th, data, ix, ctx)).join("")}${line.map((th) => row(th, data, ix, ctx, b.line.indexOf(th.id) + 1)).join("")}</ul>
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
    : ctx.query && !working.length && !line.length && !recent.length ? '<p class="cl-note muted">No conversation matches that.</p>' : "";
  return decide + onMac + days + cleared + none;
}

// ---------------------------------------------------------------- one turn

function trail(t, live) {
  const steps = t.steps || [];
  const end = live ? null : t.finished_at;
  const rows = steps.map((s, i) => {
    const next = steps[i + 1] ? steps[i + 1].at : end;
    const running = live && i === steps.length - 1;
    const secs = next ? (new Date(next) - new Date(s.at)) / 1000 : 0;
    return `<li class="${running ? "now" : ""}"><span class="tick" aria-hidden="true">${running ? "●" : "✓"}</span><b>${esc(s.text)}</b><time ${running ? `data-since="${new Date(s.at).getTime()}"` : ""}>${running ? "" : clock(secs)}</time></li>`;
  });
  return `<ul class="cv-trail">${rows.join("")}</ul>`;
}

function asked(t) {
  const about = t.options && t.options.about;
  const auto = (t.options && t.options.schedule) || ["polish", "render", "advice"].includes(t.kind);
  const long = t.prompt.length > 360 || (t.options && t.options.schedule);
  const body = long
    ? `<details class="cv-more"><summary>${esc(turnTitle(t))}</summary><p>${esc(t.prompt)}</p></details>`
    : esc(t.prompt);
  return `<div class="cv-you ${auto ? "auto" : ""}">${about ? `<span class="cv-about">About: ${esc(about.title)}</span>` : ""}${body}</div>`;
}

function adsIn(t, ix) {
  const ids = [...new Set([t.options && t.options.ad_id, ...(t.mentions || [])].filter(Boolean))].filter((id) => ix.ads[id]);
  if (!ids.length) return "";
  return `<section class="cv-block" aria-label="Ads in this answer"><h3 class="cv-label">In this answer</h3><div class="cv-crs">${ids.map((id) => {
    const ad = ix.ads[id];
    const src = ad.thumbnail_url || ad.image_url;
    const [cls, label] = adStatus(ad);
    return `<button class="cv-cr" type="button" data-view-cr="${esc(id)}" aria-label="Preview ${esc(ad.name)}">
      <span class="cv-cr-img">${src ? `<img src="${esc(src)}" alt="" loading="lazy">` : icon("image")}<span class="cv-play" aria-hidden="true">${icon("play")}</span></span>
      <b>${esc(ad.name)}</b><small class="${cls}">${esc(label)}</small></button>`;
  }).join("")}</div></section>`;
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
  const multiple = pending.length > 1;
  return `<section class="cv-block" aria-label="Suggestions">
    ${pending.length ? `<header class="cv-sg-head"><h3 class="cv-label">Suggestions <span>${pending.length}</span></h3><p>Nothing changes until you accept.</p>
      ${multiple ? `<button class="btn btn-small btn-quiet" type="button" data-decline-task="${t.id}">Decline all</button><button class="btn btn-small btn-claude-outline" type="button" data-accept-task="${t.id}">Accept all ${pending.length}</button>` : ""}</header>` : ""}
    ${pending.length ? `<div class="sg-list">${pending.map((p) => suggestion(p, ix)).join("")}</div>` : ""}
    ${decided.length ? `<ul class="prows">${decided.map((p) => proposalRow(p, ix)).join("")}</ul>` : ""}
  </section>`;
}

function answer(t, th, data, ix, ctx) {
  if (t.status === "queued") {
    const ahead = data.board.queue.indexOf(t.id);
    const working = data.board.working.length > 0;
    return `<p class="cv-note">${ahead > 0 ? `${plural(ahead, "request")} ahead of this one. Your Mac runs one at a time.` : working ? "This one is next, as soon as the current job finishes." : data.bridge.online ? "Starting…" : "Your Mac is offline, so this starts when it’s back."}</p>`;
  }
  if (isLive(t)) return (t.steps || []).length ? trail(t, true) : `<p class="cv-progress"><span class="dot" aria-hidden="true"></span>${esc(t.progress || "Starting…")}</p>`;
  if (t.status === "failed") return `<p class="cv-note bad">${esc(t.error || "It stopped without saying why.")}</p><div class="cv-acts"><button class="btn btn-small" type="button" data-again="${t.id}">Try again</button></div>`;
  if (t.status === "cancelled") {
    return `${(t.steps || []).length ? trail(t, false) : ""}<p class="cv-note">${t.claimed_at ? `You stopped this after ${esc(took(t.claimed_at, t.finished_at))}.` : "Cancelled before it started."} Nothing changed on your ads. Reply below to pick it up with new directions.</p>`;
  }
  const hasIdeas = t.proposals.length > 0;
  const score = t.scorecard && t.scorecard.passes ? `<section class="cv-score">${scorecardHtml(t.scorecard)}</section>` : "";
  return `${t.summary ? `<p class="cv-lead">${esc(t.summary)}</p>` : ""}
    ${!t.summary && !t.reports.length ? '<p class="cv-note">No answer came back.</p>' : ""}
    ${adsIn(t, ix)}${swipesIn(t)}${score}
    ${t.reports.map((r) => documentHtml(r, t, ctx, hasIdeas)).join("")}
    ${suggestionsHtml(t, ix)}`;
}

export function turnHtml(t, th, data, ix, ctx) {
  const finished = !["queued", "claimed", "running"].includes(t.status);
  const duration = t.status === "done" && t.claimed_at && t.finished_at ? `took ${took(t.claimed_at, t.finished_at)}` : "";
  const running = isLive(t) ? `<time data-since="${new Date(t.claimed_at || t.created_at).getTime()}"></time>` : "";
  const stepsLink = t.status === "done" && (t.steps || []).length
    ? `<details class="cv-steps"><summary>${plural(t.steps.length, "step")}</summary>${trail(t, false)}</details>` : "";
  const remove = finished && th.turns.length > 1 && !pendingIn(t).length && !th.cleared
    ? `<button class="cv-remove" type="button" data-clear-turn="${t.id}" aria-label="Remove this reply" title="Remove this reply">${icon("close")}</button>` : "";
  return `${asked(t)}
    <article class="cv-claude">
      <header class="cv-who">${icon("spark")}<b>Claude</b>${duration ? `<span>· ${esc(duration)}</span>` : ""}${running ? `<span>· working ${running}</span>` : ""}${remove}</header>
      ${stepsLink}
      ${answer(t, th, data, ix, ctx)}
    </article>`;
}

export function turnKey(t, data) {
  return JSON.stringify([t.status, t.progress, t.summary, t.error, t.mentions, (t.steps || []).length, (t.swipes || []).length, t.scorecard && t.scorecard.overall,
    t.proposals.map((p) => [p.id, p.status, p.state]), t.reports.map((r) => r.id), data.board.queue.indexOf(t.id), data.board.working.length, data.bridge.online]);
}

// ---------------------------------------------------------------- every waiting suggestion

export function decideHtml(data, ix) {
  const tasks = data.tasks.filter((t) => pendingIn(t).length);
  if (!tasks.length) {
    return `<div class="cv-empty"><h2>Nothing to decide</h2><p>When Claude suggests a change it shows up here too, under the question it came from.</p></div>`;
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

export function headHtml(sel, data, ix) {
  const back = `<a class="cv-back" href="#list">${icon("back")}<span>All</span></a>`;
  if (sel === "new") return `${back}<h1>New conversation</h1>`;
  if (sel === "decide") {
    const total = Object.values(data.board.threads).reduce((n, th) => n + th.waiting, 0);
    return `${back}<h1>${total ? `${plural(total, "suggestion")} to decide` : "Nothing to decide"}</h1>
      ${total ? `<span class="cv-head-do"><button class="btn btn-small btn-quiet" type="button" data-decline-all>Decline all</button><button class="btn btn-small btn-claude" type="button" data-accept-all>Accept all ${total}</button></span>` : ""}`;
  }
  const th = data.board.threads[sel];
  const first = ix.tasks.get(th.turns[0]);
  const context = [first.options && first.options.ad_name, first.campaign_name].filter(Boolean).join(" · ") || kindWord(first);
  const busy = th.state === "working" || th.state === "queued";
  return `${back}<h1>${esc(threadTitle(th, ix))}</h1><span class="cv-ctx">${esc(context)}</span>
    <span class="cv-head-do">${th.cleared ? `<button class="btn btn-small" type="button" data-restore-thread="${th.id}">Put back</button>` : busy ? "" : `<button class="btn btn-small" type="button" data-clear-thread="${th.id}">Clear</button>`}</span>`;
}
