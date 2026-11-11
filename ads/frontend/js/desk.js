import { api } from "./api.js";
import { boot, confirmDialog, esc, onRefresh, toast } from "./ui.js";
import { ACTIVE, wireTaskActions } from "./tasks.js";
import { adsView, fillPreview, index, loadPreviews } from "./board.js";
import { clock, decideHtml, decideKey, headHtml, liveTurn, listHtml, queuedTurn, threadTitle, turnHtml, turnKey, turnTitle } from "./conversation.js";
import { acceptSheet, declineMany } from "./decide.js";
import { PLACEMENTS, openSwipe, openViewer } from "./viewer.js";
import { schedulesView, wireSchedules } from "./schedules.js";

const $ = (id) => document.getElementById(id);
const SEEDS = {
  review: "Review the last 7 days against target and tell me what to change.",
  question: "Why did cost per lead change this week?",
  creative: "Three genuinely different new ad ideas, same offer.",
  research: "What are competitors running on Facebook right now?",
};
let kind = "question";
let data = null;
let ix = null;
let scheduleList = null;
let pollTimer;
let freshKey = null;
let lastJson = "";
let lastActive = null;
let view = "chat";
let selected = null;        // "new", "decide", a conversation id, or null for the default
let wantedTask = null;      // a run named in the address, until the data arrives
let wantedProposal = null;
let about = null;           // the suggestion the reply is about
let stopSure = null;
let stopTimer;
let query = "";
let showCleared = false;
let colFor = null;          // what #cv-col holds right now
let decideShown = "";
let undoTimer;
const turnKeys = new Map();
const drafts = new Map();
const openSecs = new Map();
const phone = window.matchMedia("(max-width: 960px)");

const ago = (secs) => {
  if (secs == null) return "never";
  const s = Math.max(0, Math.round(Date.now() / 1000 - secs));
  if (s < 10) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
};

async function loadSchedules() {
  try { scheduleList = (await api("/api/desk/schedules")).schedules; } catch (e) { /* the tab says Loading */ }
  if (view === "schedules") $("view").innerHTML = schedulesView(scheduleList, data && data.bridge);
}

function renderMac(bridge) {
  const b = data ? data.board : null;
  const busy = b ? [b.working.length ? "1 working" : "", b.queue.length ? `${b.queue.length} in line` : ""].filter(Boolean).join(" · ") : "";
  $("mac-led").className = `led ${bridge.online ? "on" : "off"}`;
  $("mac-summary").textContent = !bridge.has_key ? "Set up your Mac" : bridge.online ? `Your Mac is connected${busy ? ` · ${busy}` : ""}`
    : bridge.last_seen ? `Mac offline · last seen ${ago(bridge.last_seen)}` : "Mac not set up yet";
  const keyBox = freshKey ? `
    <div class="note claude-note stack">
      <b>Your Mac key (shown only now)</b>
      <div class="key-row"><code class="key" id="key-text">${esc(freshKey)}</code><button class="btn" type="button" id="copy-key">Copy</button></div>
      <span>On your Mac, open Terminal and run the command below. Paste this key when it asks. The key goes into the Mac's Keychain; don't put it anywhere else.</span>
    </div>` : "";
  $("mac-body").innerHTML = `
    <p class="flush">A small helper on your Mac checks this page for new requests (instantly while the Mac is awake) and runs Claude Code with your Meta ads access. Results land back here.</p>
    <dl class="facts">
      <div><dt>Status</dt><dd>${bridge.online ? "Connected" : bridge.has_key ? "Offline" : "Not set up"}${bridge.host ? ` · ${esc(bridge.host)}` : ""}</dd></div>
      <div><dt>Last check</dt><dd>${esc(ago(bridge.last_seen))}</dd></div>
      <div><dt>Key</dt><dd>${bridge.has_key ? `ends in ${esc(bridge.key_hint || "")}` : "none yet"}</dd></div>
    </dl>
    ${keyBox}
    <div class="stack tight">
      <b>Set up or reinstall on your Mac</b>
      <pre class="cmd"><code>bash ~/Desktop/Dev/edgebourne/ads/bridge/install.sh</code></pre>
    </div>
    <div class="row">
      <button class="btn" type="button" id="new-key">${bridge.has_key ? "Create a new key" : "Create a Mac key"}</button>
      ${bridge.has_key ? '<button class="btn" type="button" id="revoke-key">Disconnect the Mac</button>' : ""}
    </div>`;
  $("new-key").addEventListener("click", async (e) => {
    if (bridge.has_key && !e.currentTarget.dataset.sure) {
      e.currentTarget.dataset.sure = "1";
      e.currentTarget.textContent = "The old key stops working. Click again to confirm";
      return;
    }
    try { const r = await api("/api/desk/key", { method: "POST" }); freshKey = r.key; renderMac(r.bridge); toast("New key created"); }
    catch (err) { toast(err.message, "bad"); }
  });
  const revoke = $("revoke-key");
  if (revoke) revoke.addEventListener("click", async (e) => {
    if (!e.currentTarget.dataset.sure) { e.currentTarget.dataset.sure = "1"; e.currentTarget.textContent = "Click again to disconnect"; return; }
    try { const r = await api("/api/desk/key", { method: "DELETE" }); freshKey = null; renderMac(r.bridge); toast("Mac disconnected"); }
    catch (err) { toast(err.message, "bad"); }
  });
  const copy = $("copy-key");
  if (copy) copy.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(freshKey); toast("Key copied"); } catch (err) { toast("Select the key and copy it", "bad"); }
  });
}

function readHash() {
  const h = location.hash.slice(1);
  wantedTask = null;
  wantedProposal = null;
  if (h === "ads" || h === "schedules") { view = h; return; }
  view = "chat";
  const run = h.match(/^r\/(\d+)/);
  const prop = h.match(/^p\/(\d+)/);
  if (run) wantedTask = Number(run[1]);
  else if (prop) wantedProposal = Number(prop[1]);
  else selected = h === "decide" || h === "waiting" ? "decide" : h === "new" ? "new" : h === "list" ? "list" : null;
}

const threadOf = (t) => t.thread_id || t.id;
const pendingAll = () => data.tasks.flatMap((t) => t.proposals.filter((p) => p.status === "pending"));
const pendingOf = (taskId) => ix.tasks.get(taskId).proposals.filter((p) => p.status === "pending").map((p) => p.id);

function resolveAddress() {
  if (wantedProposal) {
    const t = ix.taskOf.get(wantedProposal);
    if (t) selected = threadOf(t);
  } else if (wantedTask) {
    const t = ix.tasks.get(wantedTask);
    if (t) selected = threadOf(t);
  }
}

// What the right side shows: the choice in the address, else whatever most needs looking at.
function current() {
  const b = data.board;
  if (selected === "list") return null;
  if (selected === "new" || selected === "decide") return selected;
  if (selected != null && b.threads[selected]) return selected;
  if (phone.matches) return null;
  const needs = b.recent.find((id) => b.threads[id].state === "needs");
  const fresh = b.recent.find((id) => b.threads[id].fresh.length);
  return b.working[0] ?? needs ?? fresh ?? "new";
}

function markSeen(th) {
  th.fresh.forEach((id) => {
    ix.tasks.get(id).seen_at = new Date().toISOString();
    api(`/api/desk/tasks/${id}/seen`, { method: "POST" }).catch(() => {});
  });
  th.fresh = [];
}

function scrollToEl(el) {
  const box = $("cv-scroll");
  box.scrollTop = Math.max(0, el.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop - 16);
}

function flash(el) {
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 1600);
}

function syncTurns(th) {
  const col = $("cv-col");
  const opened = colFor !== th.id;
  if (opened) { col.innerHTML = ""; turnKeys.clear(); colFor = th.id; }
  [...col.children].forEach((el) => { if (!th.turns.includes(Number(el.dataset.turn))) el.remove(); });
  th.turns.forEach((id, i) => {
    const t = ix.tasks.get(id);
    const key = turnKey(t, data);
    const old = col.querySelector(`[data-turn="${id}"]`);
    if (old && turnKeys.get(id) === key) return;
    const el = document.createElement("div");
    el.className = "cv-turn";
    el.id = `turn-${id}`;
    el.dataset.turn = id;
    el.innerHTML = turnHtml(t, th, data, ix, { openSecs });
    if (old) old.replaceWith(el); else col.insertBefore(el, col.children[i] || null);
    turnKeys.set(id, key);
    loadPreviews(el);
  });
  return opened;
}

function renderDock(sel) {
  const th = typeof sel === "number" ? data.board.threads[sel] : null;
  const line = $("cv-line");
  const form = $("ask-form");
  const queued = th && th.state === "queued" ? queuedTurn(th, ix) : th && th.state === "working" ? queuedTurn(th, ix) : null;
  $("cv-dock").hidden = sel === "decide" || sel == null;
  $("cv-seeds").hidden = sel !== "new";
  $("campaign").hidden = sel !== "new";
  if (queued) {
    const pos = data.board.queue.indexOf(queued.id);
    line.hidden = false;
    form.hidden = true;
    line.innerHTML = `<span>${th.state === "working" ? "Your follow-up runs as soon as this finishes." : pos ? `${pos + 1}${["st", "nd", "rd"][pos] || "th"} in line. Starts when your Mac is free.` : data.bridge.online ? "Next in line." : "Your Mac is offline. This starts when it’s back."}</span>
      ${pos > 0 ? `<button class="btn btn-small" type="button" data-next="${queued.id}">Run next</button>` : ""}
      <button class="btn btn-small" type="button" data-cancel="${queued.id}">Cancel</button>${th.state === "working" && data.bridge.can_stop ? stopButton(th) : ""}`;
    return;
  }
  line.hidden = true;
  form.hidden = false;
  renderDockFoot(sel, th);
}

const stopButton = (th) => `<button class="btn btn-small cv-stop" type="button" data-stop="${th.id}"><span class="sq" aria-hidden="true"></span>Stop</button>`;

function renderDockFoot(sel, th) {
  const has = $("prompt").value.trim();
  const live = th && th.state === "working";
  const hint = $("cv-hint");
  const btns = $("cv-btns");
  $("prompt").placeholder = sel === "new" ? "Ask anything about your ads…" : about ? "What should Claude change about this?" : live ? "Add something for Claude…" : "Reply to Claude…";
  $("cv-chip").hidden = !about;
  if (about) $("cv-chip").innerHTML = `<span>About: ${esc(about.title)}</span><button type="button" data-unchip aria-label="Remove">×</button>`;
  if (live && stopSure === th.id) {
    hint.textContent = "Stop this job? Nothing changes on your ads.";
    btns.innerHTML = `<button class="btn btn-small btn-quiet" type="button" data-keep>Keep going</button><button class="btn btn-small btn-danger" type="button" data-stop="${th.id}">Stop it</button>`;
    return;
  }
  if (live) {
    const t = liveTurn(th, ix);
    if (has) {
      hint.textContent = "Claude is still working.";
      btns.innerHTML = `${data.bridge.can_stop ? '<button class="btn btn-small" type="button" data-stop-send>Stop and send</button>' : ""}<button class="btn btn-small btn-claude" type="submit">Send when it’s done</button>`;
    } else {
      hint.innerHTML = `Working · <time data-since="${new Date(t.claimed_at || t.created_at).getTime()}"></time>`;
      btns.innerHTML = data.bridge.can_stop ? stopButton(th) : "";
      tick();
    }
    return;
  }
  hint.textContent = sel === "new"
    ? (data.bridge.online ? "It never changes anything without your yes." : "Your Mac is offline, so this waits until it’s on.")
    : !data.bridge.can_reply ? "Your Mac helper needs an update before Claude can pick this up." : data.bridge.online ? "Claude remembers this conversation." : "Your Mac is offline, so this waits until it’s on.";
  btns.innerHTML = `<button class="btn btn-small btn-claude" type="submit" ${has ? "" : "disabled"}>Send</button>`;
}

function renderConv(sel) {
  $("cv").dataset.state = sel === "new" ? "new" : sel === "decide" ? "decide" : sel == null ? "none" : "thread";
  $("convs").dataset.mode = sel == null ? "list" : "conv";
  document.body.classList.toggle("in-conv", sel != null);
  if (sel == null) { colFor = null; return; }
  $("cv-head").innerHTML = headHtml(sel, data, ix);
  const col = $("cv-col");
  if (sel === "new") {
    if (colFor !== "new") {
      colFor = "new";
      col.innerHTML = '<div class="cv-intro"><h2>What should Claude look at?</h2><p>It reads your ads, results and lead stages, and answers here.</p></div>';
      $("cv-scroll").scrollTop = 0;
    }
  } else if (sel === "decide") {
    const key = decideKey(data);
    if (colFor !== "decide" || key !== decideShown) {
      colFor = "decide";
      decideShown = key;
      col.innerHTML = decideHtml(data, ix);
      loadPreviews(col);
    }
  } else {
    const th = data.board.threads[sel];
    const opened = syncTurns(th);
    markSeen(th);
    if (opened) {
      const you = [...col.querySelectorAll(".cv-you")].pop();
      if (you) scrollToEl(you);
    }
  }
  renderDock(sel);
  if (wantedProposal) {
    const el = document.getElementById(`p-${wantedProposal}`);
    if (el) { scrollToEl(el); flash(el); }
  } else if (wantedTask && wantedTask !== sel) {
    // A link to one particular reply; a conversation's own address opens on its latest message.
    const el = document.getElementById(`turn-${wantedTask}`);
    if (el) scrollToEl(el);
  }
  if (wantedProposal && ix.taskOf.has(wantedProposal)) wantedProposal = null;
  if (wantedTask && ix.tasks.has(wantedTask)) wantedTask = null;
}

function renderSubnav() {
  const nav = document.querySelector(".subnav");
  if (!nav) return;
  const mine = nav.querySelector('a[href="/desk.html"]');
  if (mine && !nav.querySelector("[data-sub]")) {
    mine.href = "/desk.html#list";
    mine.textContent = "Conversations";
    mine.dataset.sub = "chat";
    mine.insertAdjacentHTML("afterend", '<a href="/desk.html#ads" data-sub="ads">By ad</a><a href="/desk.html#schedules" data-sub="schedules">Schedules</a>');
  }
  nav.querySelectorAll("[data-sub]").forEach((a) => {
    if (a.dataset.sub === view) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
}

function renderList(sel) {
  $("cl-list").innerHTML = listHtml(data, ix, { sel, query, showCleared, stopSure });
}

function renderView() {
  ix = index(data);
  renderSubnav();
  const chat = view === "chat";
  $("convs").hidden = !chat;
  $("view").hidden = chat;
  document.body.classList.toggle("conv-page", chat);
  if (chat) {
    resolveAddress();
    const sel = current();
    renderConv(sel);
    renderList(sel);
    tick();
    return;
  }
  document.body.classList.remove("in-conv");
  colFor = null;
  if (view === "schedules") { $("view").innerHTML = schedulesView(scheduleList, data.bridge); return; }
  $("view").innerHTML = adsView(data, ix, new Set());
}

function route() {
  const before = selected;
  saveDraft(before);
  readHash();
  about = null;
  stopSure = null;
  if (data) {
    if (view === "chat") { resolveAddress(); restoreDraft(); }
    renderView();
  }
}

function saveDraft(sel) { drafts.set(sel ?? "default", $("prompt").value); }
function restoreDraft() { const v = drafts.get(selected ?? "default") || ""; $("prompt").value = v; fitPrompt(); }
function fitPrompt() { const p = $("prompt"); p.style.height = "auto"; p.style.height = `${Math.min(p.scrollHeight, 180)}px`; }

const reload = () => { lastJson = ""; load(); };

async function act(path, body, message) {
  try { const r = await api(path, { method: "POST", body }); if (message) toast(typeof message === "function" ? message(r) : message); reload(); return r; }
  catch (err) { toast(err.message, "bad"); reload(); return null; }
}

function offerUndo(message, result) {
  const bar = $("undo-bar");
  if (!result || !result.task_ids || !result.task_ids.length) { toast(message); return; }
  bar.innerHTML = `<span>${esc(message)}</span><button type="button" data-undo>Undo</button>`;
  bar.hidden = false;
  bar.querySelector("[data-undo]").addEventListener("click", async () => {
    bar.hidden = true;
    clearTimeout(undoTimer);
    try { await api("/api/desk/restore", { method: "POST", body: { task_ids: result.task_ids, proposal_ids: result.proposal_ids || [] } }); toast("Put back"); }
    catch (err) { toast(err.message, "bad"); }
    reload();
  }, { once: true });
  clearTimeout(undoTimer);
  undoTimer = setTimeout(() => { bar.hidden = true; }, 9000);
}

async function clearThread(id) {
  const th = data.board.threads[id];
  let decline = false;
  if (th.waiting) {
    decline = await confirmDialog({ title: "Clear this conversation?", body: `<p>${th.waiting === 1 ? "1 suggestion is" : `${th.waiting} suggestions are`} still waiting. Clearing declines ${th.waiting === 1 ? "it" : "them"}. Nothing changes on Meta.</p>`, confirm: "Clear and decline", danger: true });
    if (!decline) return;
  }
  try {
    const r = await api(`/api/desk/threads/${id}/clear`, { method: "POST", body: { decline_waiting: decline } });
    if (selected === id) { selected = null; if (location.hash) history.replaceState(null, "", location.pathname + location.search); }
    offerUndo("Conversation cleared", r);
  } catch (err) { toast(err.message, "bad"); }
  reload();
}

function askStop(id) {
  stopSure = id;
  clearTimeout(stopTimer);
  stopTimer = setTimeout(() => { stopSure = null; renderView(); }, 6000);
  renderView();
}

async function doStop(id) {
  clearTimeout(stopTimer);
  stopSure = null;
  const t = liveTurn(data.board.threads[id], ix);
  if (t) await act(`/api/desk/tasks/${t.id}/stop`, undefined, "Stopped");
}

function previewCr(id) {
  const ad = ix.ads[id];
  openViewer({ title: ad ? ad.name : "Ad", panes: [{ label: "Now", url: (f) => `/api/ads/ad/${encodeURIComponent(id)}/preview?format=${f}` }], link: { href: `/ad.html?id=${encodeURIComponent(id)}`, label: "Open the ad" } });
}

function previewProposal(id, compare) {
  const p = ix.proposals.get(id);
  const reels = p.payload.update_ad;
  const proposed = { label: "Proposed", url: (f) => `/api/proposals/${id}/preview?format=${f}` };
  const now = { label: "Running now", url: (f) => `/api/ads/ad/${encodeURIComponent(p.about_ad)}/preview?format=${f}` };
  openViewer({ title: p.title, panes: compare ? [now, proposed] : [proposed], format: reels ? "INSTAGRAM_REELS" : PLACEMENTS[0][0], placements: reels ? [["INSTAGRAM_REELS", "Reels"]] : PLACEMENTS });
}

async function send({ stopFirst = false } = {}) {
  const prompt = $("prompt").value.trim();
  if (!prompt) { $("prompt").focus(); return; }
  const sel = current();
  const btns = $("cv-btns").querySelectorAll("button");
  btns.forEach((b) => { b.disabled = true; });
  try {
    if (sel === "new") {
      const t = await api("/api/desk/tasks", { method: "POST", body: { kind, prompt, campaign_id: $("campaign").value } });
      $("prompt").value = "";
      drafts.delete("new");
      kind = "question";
      fitPrompt();
      selected = t.id;
      await load(true);
      location.hash = `r/${t.id}`;
      return;
    }
    const th = data.board.threads[sel];
    const lastTurn = th.turns.at(-1);
    await api(`/api/desk/tasks/${lastTurn}/reply`, { method: "POST", body: { prompt, about_proposal: about ? about.id : undefined, stop_first: stopFirst } });
    $("prompt").value = "";
    drafts.delete(sel);
    about = null;
    stopSure = null;
    fitPrompt();
    await load(true);
    const you = [...$("cv-col").querySelectorAll(".cv-you")].pop();
    if (you) scrollToEl(you);
  } catch (err) { toast(err.message, "bad"); renderDock(sel); }
}

async function onClick(e) {
  const hit = (name) => e.target.closest(`[${name}]`);
  let el;
  if ((el = hit("data-accept"))) { acceptSheet([Number(el.dataset.accept)], reload); return; }
  if ((el = hit("data-accept-task"))) { acceptSheet(pendingOf(Number(el.dataset.acceptTask)), reload); return; }
  if (hit("data-accept-all")) { acceptSheet(pendingAll().map((p) => p.id), reload); return; }
  if ((el = hit("data-decline-one"))) { act(`/api/proposals/${el.dataset.declineOne}/decline`, undefined, "Declined"); return; }
  if ((el = hit("data-decline-task"))) { declineMany(pendingOf(Number(el.dataset.declineTask)), reload); return; }
  if (hit("data-decline-all")) { declineMany(pendingAll().map((p) => p.id), reload); return; }
  if ((el = hit("data-revise"))) {
    const id = Number(el.dataset.revise);
    const p = ix.proposals.get(id);
    const th = threadOf(ix.taskOf.get(id));
    if (current() !== th) { location.hash = `r/${th}`; await new Promise((r) => setTimeout(r, 40)); }
    about = p;
    renderDock(th);
    $("prompt").focus();
    return;
  }
  if (hit("data-unchip")) { about = null; renderDock(current()); return; }
  if ((el = hit("data-view-cr"))) { previewCr(el.dataset.viewCr); return; }
  if ((el = hit("data-view-proposal"))) { previewProposal(Number(el.dataset.viewProposal), false); return; }
  if ((el = hit("data-compare"))) { previewProposal(Number(el.dataset.compare), true); return; }
  if ((el = hit("data-view-swipe"))) { openSwipe(ix.swipes.get(Number(el.dataset.viewSwipe))); return; }
  if ((el = hit("data-pf"))) {
    const media = el.closest(".sg-media");
    media.querySelectorAll("[data-pf]").forEach((b) => b.setAttribute("aria-selected", String(b === el)));
    const box = media.querySelector("[data-preview]");
    box.dataset.format = el.dataset.pf;
    box.innerHTML = '<div class="preview-skeleton"><span></span><span></span><span></span><p>Loading Meta\'s preview…</p></div>';
    fillPreview(box);
    return;
  }
  if ((el = hit("data-seed"))) { kind = el.dataset.seed; $("prompt").value = SEEDS[kind]; fitPrompt(); renderDock("new"); $("prompt").focus(); return; }
  if (hit("data-show-cleared")) { showCleared = !showCleared; renderList(current()); return; }
  if ((el = hit("data-next"))) { act(`/api/desk/tasks/${el.dataset.next}/next`, undefined, "Moved to the front of the line"); return; }
  if ((el = hit("data-clear-thread"))) { e.preventDefault(); clearThread(Number(el.dataset.clearThread)); return; }
  if ((el = hit("data-clear-turn"))) { const r = await act(`/api/desk/tasks/${el.dataset.clearTurn}/clear`, {}); offerUndo("Reply removed", r); return; }
  if ((el = hit("data-restore-thread"))) {
    const th = data.board.threads[Number(el.dataset.restoreThread)];
    act("/api/desk/restore", { task_ids: th.turns }, "Put back");
    return;
  }
  if ((el = hit("data-clear-day"))) {
    const threads = el.dataset.clearDay.split(",").map(Number);
    try { const r = await api("/api/desk/clear", { method: "POST", body: { what: "finished", threads } }); selected = threads.includes(selected) ? null : selected; offerUndo(`${r.cleared} ${r.cleared === 1 ? "conversation" : "conversations"} cleared`, r); }
    catch (err) { toast(err.message, "bad"); }
    reload();
    return;
  }
  if ((el = hit("data-stop"))) { const id = Number(el.dataset.stop); if (stopSure === id) doStop(id); else askStop(id); return; }
  if (hit("data-keep")) { clearTimeout(stopTimer); stopSure = null; renderView(); return; }
  if (hit("data-stop-send")) { send({ stopFirst: true }); return; }
  if ((el = hit("data-clear"))) {
    const n = data.board.queue.length;
    const yes = await confirmDialog({ title: "Clear the line?", body: `<p>Cancels ${n === 1 ? "the 1 job" : `all ${n} jobs`} that haven't started. Whatever is running keeps going.</p>`, confirm: `Cancel ${n}`, danger: true });
    if (yes) act("/api/desk/clear", { what: "queue" }, (r) => `${r.cleared} cancelled`);
    return;
  }
  if ((el = hit("data-goto-run"))) { e.preventDefault(); location.hash = `r/${el.dataset.gotoRun}`; }
}

// Says so when something finishes while the page is open.
function announceFinished() {
  const active = new Set(data.tasks.filter((t) => ACTIVE.has(t.status)).map((t) => t.id));
  if (lastActive) {
    const done = data.tasks.filter((t) => lastActive.has(t.id) && !active.has(t.id) && t.status === "done");
    if (done.length) toast(done.length === 1 ? `Claude finished: ${turnTitle(done[0]).slice(0, 70)}` : `Claude finished ${done.length} jobs`);
  }
  lastActive = active;
}

function tick() {
  document.querySelectorAll("[data-since]").forEach((el) => { el.textContent = clock((Date.now() - Number(el.dataset.since)) / 1000); });
}

async function load(force) {
  try {
    data = await api("/api/desk");
    renderMac(data.bridge);
    const sel = $("campaign");
    const keep = sel.value;
    sel.innerHTML = '<option value="">All campaigns</option>' + data.campaigns.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("");
    sel.value = keep || sel.dataset.want || "";
    delete sel.dataset.want;
    announceFinished();
    const json = JSON.stringify([data.tasks, data.ads, data.board, data.bridge.online, data.bridge.can_stop, data.bridge.can_reply]);
    if (force || json !== lastJson) { lastJson = json; renderView(); }
  } catch (err) { toast(err.message, "bad"); }
  clearTimeout(pollTimer);
  const busy = data && data.tasks.some((t) => ACTIVE.has(t.status));
  pollTimer = setTimeout(load, document.hidden ? 60000 : busy ? 3000 : 20000);
}

const me = await boot({ page: "desk", admin: true });
if (me) {
  const q = new URLSearchParams(location.search);
  if (SEEDS[q.get("kind")]) kind = q.get("kind");
  readHash();
  if (q.get("ask") || q.get("kind")) {
    selected = "new";
    if (q.get("ask") && q.get("ask") !== "1") $("prompt").value = q.get("ask");
  }
  if (q.get("campaign")) $("campaign").dataset.want = q.get("campaign");
  const main = document.querySelector(".main");
  main.addEventListener("click", onClick);
  main.addEventListener("toggle", (e) => {
    const d = e.target.closest && e.target.closest("details[data-sec]");
    if (d) openSecs.set(d.dataset.sec, d.open);
  }, true);
  $("ask-form").addEventListener("submit", (e) => { e.preventDefault(); send(); });
  $("prompt").addEventListener("input", () => { fitPrompt(); if (data) renderDockFoot(current(), typeof current() === "number" ? data.board.threads[current()] : null); });
  $("prompt").addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || e.isComposing) return;
    const coarse = window.matchMedia("(pointer: coarse)").matches;
    if (e.metaKey || e.ctrlKey || (!e.shiftKey && !coarse)) { e.preventDefault(); $("ask-form").requestSubmit(); }
  });
  $("search").addEventListener("input", (e) => { query = e.target.value.trim().toLowerCase(); if (data) renderList(current()); });
  $("mac-open").addEventListener("click", () => $("mac-dialog").showModal());
  $("mac-close").addEventListener("click", () => $("mac-dialog").close());
  wireTaskActions(main, reload, null);
  wireSchedules($("view"), async () => { await loadSchedules(); reload(); });
  loadSchedules();
  window.addEventListener("hashchange", route);
  phone.addEventListener("change", route);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
  setInterval(tick, 1000);
  onRefresh(load);
  load();
}
