import { api } from "./api.js";
import { boot, confirmDialog, esc, onRefresh, toast } from "./ui.js";
import { ACTIVE, wireTaskActions } from "./tasks.js";
import { adsView, index, loadPreviews } from "./board.js";
import { decideHtml, emptyDetail, requestHtml, requestTitle, traysHtml } from "./requests.js";
import { acceptSheet, declineMany } from "./decide.js";
import { schedulesView, wireSchedules } from "./schedules.js";

let scheduleList = null;
async function loadSchedules() {
  try { scheduleList = (await api("/api/desk/schedules")).schedules; } catch (e) { /* the tab says Loading */ }
  if (view === "schedules") { $("view").innerHTML = schedulesView(scheduleList, data && data.bridge); }
}

const $ = (id) => document.getElementById(id);
const KINDS = {
  question: { label: "Question", placeholder: "Ask anything about your ads, e.g. Why did N3 cost more per lead than N1 this week?" },
  review: { label: "Review results", placeholder: "What should Claude look at? e.g. Review the last 7 days against a $40 target cost per lead and tell me what to change." },
  research: { label: "Research competitors", placeholder: "Who or what to research? e.g. What are IT consultants and software agencies in Southern California running on Facebook right now?" },
  creative: { label: "New ad ideas", placeholder: "What should the new ads do? e.g. Three new concepts for restaurant owners, same free intro call offer." },
};
let kind = "question";
let data = null;
let ix = null;
let pollTimer;
let freshKey = null;
let lastJson = "";
let lastDetail = "";
let lastActive = null;
let view = "requests";
let selected = null;      // "decide", a request id, or null for the phone's list / the default
let focusProposal = null;
let showCleared = false;
const openReports = new Set();
const openRows = new Map();
const picked = new Set();
const phone = window.matchMedia("(max-width: 900px)");

const ago = (secs) => {
  if (secs == null) return "never";
  const s = Math.max(0, Math.round(Date.now() / 1000 - secs));
  if (s < 10) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
};

function setKind(k) {
  kind = k;
  document.querySelectorAll("#kinds button").forEach((b) => {
    const on = b.dataset.kind === k;
    b.setAttribute("aria-checked", String(on));
    b.setAttribute("aria-pressed", String(on));
  });
  $("prompt").placeholder = KINDS[k].placeholder;
}

function renderMac(bridge) {
  const s = $("mac-status");
  if (!bridge.has_key) { s.className = "mac-status off"; s.textContent = "Mac not connected"; }
  else if (bridge.online) { s.className = "mac-status on"; s.textContent = `Mac connected · checked ${ago(bridge.last_seen)}`; }
  else { s.className = "mac-status off"; s.textContent = bridge.last_seen ? `Mac offline · last seen ${ago(bridge.last_seen)}` : "Mac not set up yet"; }

  $("ask-hint").textContent = bridge.online
    ? "Claude reads your ads, results and lead stages. It never spends money or changes ads from here: anything like that comes back as a proposal for you."
    : "Your Mac is offline, so this waits in the queue until it's on. You can also run /ads-desk in Claude Code to pick it up. Claude never spends money or changes ads from here.";

  $("mac-summary").textContent = bridge.online ? `· ${bridge.host || "connected"}` : bridge.has_key ? "· offline" : "· not set up";
  if (!bridge.has_key || !bridge.last_seen) $("mac-panel").open = true;
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
  focusProposal = null;
  if (h === "ads" || h === "schedules") { view = h; return; }
  view = "requests";
  const run = h.match(/^r\/(\d+)/);
  const prop = h.match(/^p\/(\d+)/);
  if (run) selected = Number(run[1]);
  else if (prop) { focusProposal = Number(prop[1]); selected = "decide"; }
  else selected = h === "decide" || h === "waiting" ? "decide" : null;
}

function showRun(id) {
  location.hash = "ads";
  setTimeout(() => {
    const el = document.getElementById(`run-${id}`);
    if (el) { el.scrollIntoView({ behavior: "smooth", block: "start" }); el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 1600); }
  }, 60);
}

const pendingAll = () => data.tasks.flatMap((t) => t.proposals.filter((p) => p.status === "pending"));
const pendingOf = (taskId) => ix.tasks.get(taskId).proposals.filter((p) => p.status === "pending").map((p) => p.id);

// What the right side shows: the choice in the address, else what most needs looking at.
// A phone with no choice shows only the list.
function current() {
  if (selected != null || phone.matches) return selected;
  const b = data.board;
  return pendingAll().length ? "decide" : b.working[0] ?? b.next[0] ?? b.finished[0] ?? null;
}

function detailKey(sel) {
  const slim = (t) => [t.status, t.progress, t.summary, t.error, t.archived_at, t.proposals.map((p) => [p.id, p.status, p.state]), t.reports.map((r) => r.id), data.board.next.indexOf(t.id)];
  if (sel === "decide") return JSON.stringify(["decide", data.tasks.filter((t) => t.proposals.some((p) => p.status === "pending")).map((t) => [t.id, slim(t)])]);
  const t = ix.tasks.get(sel);
  return JSON.stringify([sel, t ? slim(t) : null, data.bridge.online, data.bridge.can_stop]);
}

function markSeen(t) {
  if (!data.board.fresh.includes(t.id)) return;
  data.board.fresh = data.board.fresh.filter((id) => id !== t.id);
  t.seen_at = new Date().toISOString();
  api(`/api/desk/tasks/${t.id}/seen`, { method: "POST" }).catch(() => {});
}

function syncPicks() {
  const live = new Set(pendingAll().map((p) => p.id));
  [...picked].forEach((id) => { if (!live.has(id)) picked.delete(id); });
  document.querySelectorAll("[data-pick]").forEach((c) => { c.checked = picked.has(Number(c.dataset.pick)); c.closest(".sg").classList.toggle("picked", c.checked); });
  const set = (box, ids) => { const n = ids.filter((id) => picked.has(id)).length; box.checked = !!ids.length && n === ids.length; box.indeterminate = n > 0 && n < ids.length; };
  document.querySelectorAll("[data-pick-task]").forEach((c) => set(c, pendingOf(Number(c.dataset.pickTask))));
  document.querySelectorAll("[data-pick-all]").forEach((c) => set(c, [...live]));
  const bar = $("pick-bar");
  bar.hidden = !picked.size;
  document.body.classList.toggle("has-bulk", picked.size > 0);
  bar.innerHTML = picked.size ? `<div class="bk" role="toolbar" aria-label="${picked.size} selected"><span class="bk-n"><b>${picked.size}</b> selected</span>
    <button type="button" class="btn btn-small btn-claude" data-accept-picked>Accept ${picked.size}</button>
    <button type="button" class="btn btn-small btn-quiet" data-decline-picked>Decline ${picked.size}</button>
    <button type="button" class="icon-btn bk-x" data-clear-picks aria-label="Clear the selection">×</button></div>` : "";
}

function renderDetail(sel) {
  const key = detailKey(sel);
  if (key === lastDetail) return;
  lastDetail = key;
  const ctx = { openRows, picked, openReports };
  const t = typeof sel === "number" ? ix.tasks.get(sel) : null;
  $("detail").innerHTML = sel === "decide" ? decideHtml(data, ix, ctx) : t ? requestHtml(t, data, ix, ctx) : emptyDetail();
  loadPreviews($("detail"));
  if (t) markSeen(t);
}

function renderTabs() {
  const waiting = pendingAll().length;
  $("tab-requests").innerHTML = `Requests${waiting ? ` <span class="n claude">${waiting}</span>` : ""}`;
  $("tab-ads").innerHTML = `By ad <span class="n">${data.families.filter((f) => f.root).length}</span>`;
  const schedOn = scheduleList ? scheduleList.filter((x) => x.enabled).length : 0;
  $("tab-schedules").innerHTML = `Schedules${schedOn ? ` <span class="n">${schedOn} on</span>` : ""}`;
  document.querySelectorAll("#views [data-view]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === view)));
}

function renderView() {
  ix = index(data);
  renderTabs();
  $("work").hidden = view !== "requests";
  $("view").hidden = view === "requests";
  if (view === "requests") {
    const sel = current();
    renderDetail(sel);
    $("trays").innerHTML = traysHtml(data, ix, sel, showCleared);
    $("work").dataset.mode = sel == null ? "list" : "detail";
    syncPicks();
    if (focusProposal) {
      const p = ix.proposals.get(focusProposal);
      const id = focusProposal;
      focusProposal = null;
      if (!p || p.status !== "pending") { if (p) location.hash = `r/${ix.taskOf.get(id).id}`; return; }
      revealRow(id);
    }
    return;
  }
  document.body.classList.remove("has-bulk");
  $("pick-bar").hidden = true;
  if (view === "schedules") { $("view").innerHTML = schedulesView(scheduleList, data.bridge); return; }
  $("view").innerHTML = adsView(data, ix, openReports);
  loadPreviews($("view"));
}

function setRowOpen(id, open) {
  openRows.set(id, open);
  const body = document.getElementById(`sg-body-${id}`);
  if (!body) return;
  body.hidden = !open;
  document.querySelector(`[data-toggle="${id}"]`).setAttribute("aria-expanded", String(open));
}

function revealRow(id) {
  setRowOpen(id, true);
  const el = document.getElementById(`p-${id}`);
  if (el) { el.scrollIntoView({ behavior: "smooth", block: "center" }); el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 1600); }
}

function route() {
  readHash();
  lastDetail = "";
  if (data) renderView();
  if (phone.matches) window.scrollTo({ top: 0 });
}

const reload = () => { lastJson = ""; lastDetail = ""; load(); };

async function act(path, body, message) {
  try { const r = await api(path, { method: "POST", body }); if (message) toast(typeof message === "function" ? message(r) : message); reload(); }
  catch (err) { toast(err.message, "bad"); reload(); }
}

async function onBoardClick(e) {
  const hit = (name) => e.target.closest(`[${name}]`);
  let el;
  if ((el = hit("data-toggle"))) { const id = Number(el.dataset.toggle); setRowOpen(id, el.getAttribute("aria-expanded") !== "true"); return; }
  if ((el = hit("data-accept"))) { acceptSheet([Number(el.dataset.accept)], reload); return; }
  if ((el = hit("data-accept-task"))) { acceptSheet(pendingOf(Number(el.dataset.acceptTask)), reload); return; }
  if (hit("data-accept-all")) { acceptSheet(pendingAll().map((p) => p.id), reload); return; }
  if (hit("data-accept-picked")) { acceptSheet([...picked], reload); return; }
  if ((el = hit("data-decline-task"))) { declineMany(pendingOf(Number(el.dataset.declineTask)), reload); return; }
  if (hit("data-decline-all")) { declineMany(pendingAll().map((p) => p.id), reload); return; }
  if (hit("data-decline-picked")) { declineMany([...picked], reload); return; }
  if (hit("data-clear-picks")) { picked.clear(); syncPicks(); return; }
  if (hit("data-show-cleared")) { showCleared = !showCleared; $("trays").innerHTML = traysHtml(data, ix, current(), showCleared); return; }
  if ((el = hit("data-next"))) { act(`/api/desk/tasks/${el.dataset.next}/next`, undefined, "Moved to the front of the line"); return; }
  if ((el = hit("data-clear-task"))) { act(`/api/desk/tasks/${el.dataset.clearTask}/clear`, {}, "Cleared. It's under Cleared if you need it."); return; }
  if ((el = hit("data-restore"))) { act(`/api/desk/tasks/${el.dataset.restore}/clear`, { restore: true }, "Put back"); return; }
  if ((el = hit("data-stop"))) {
    const id = el.dataset.stop;
    const yes = await confirmDialog({ title: "Stop this run?", body: `<p>${esc(requestTitle(ix.tasks.get(Number(id))))}</p><p class="muted">Your Mac ends it within about 15 seconds. Nothing has been changed on your ads, and you can ask again.</p>`, confirm: "Stop it", danger: true });
    if (yes) act(`/api/desk/tasks/${id}/stop`, undefined, "Stopped");
    return;
  }
  if ((el = hit("data-clear"))) {
    if (el.dataset.clear === "queue") {
      const n = data.board.next.length;
      const yes = await confirmDialog({ title: `Clear the queue?`, body: `<p>Cancels ${n === 1 ? "the 1 request" : `all ${n} requests`} that haven't started. Whatever is running keeps going. You can ask again from Cleared.</p>`, confirm: `Cancel ${n}`, danger: true });
      if (yes) act("/api/desk/clear", { what: "queue" }, (r) => `${r.cleared} cancelled`);
    } else act("/api/desk/clear", { what: "finished" }, (r) => `${r.cleared} cleared. They're under Cleared if you need them.`);
    return;
  }
  if ((el = hit("data-goto-run"))) { e.preventDefault(); showRun(el.dataset.gotoRun); return; }
  if (hit("data-ask")) openComposer(true);
}

function onBoardChange(e) {
  const one = e.target.closest("[data-pick]");
  const task = e.target.closest("[data-pick-task]");
  const all = e.target.closest("[data-pick-all]");
  if (!one && !task && !all) return;
  const ids = one ? [Number(one.dataset.pick)] : task ? pendingOf(Number(task.dataset.pickTask)) : pendingAll().map((p) => p.id);
  ids.forEach((id) => (e.target.checked ? picked.add(id) : picked.delete(id)));
  syncPicks();
}

// Says so when something finishes while the page is open.
function announceFinished() {
  const active = new Set(data.tasks.filter((t) => ACTIVE.has(t.status)).map((t) => t.id));
  if (lastActive) {
    const done = data.tasks.filter((t) => lastActive.has(t.id) && !active.has(t.id) && t.status === "done");
    if (done.length) toast(done.length === 1 ? `Claude finished: ${requestTitle(done[0]).slice(0, 70)}` : `Claude finished ${done.length} requests`);
  }
  lastActive = active;
}

function openComposer(open) {
  $("composer").hidden = !open;
  $("ask-open").setAttribute("aria-expanded", String(open));
  if (open) { $("composer").scrollIntoView({ block: "nearest" }); $("prompt").focus(); }
}

async function load() {
  try {
    data = await api("/api/desk");
    renderMac(data.bridge);
    const sel = $("campaign");
    const keep = sel.value;
    sel.innerHTML = '<option value="">All campaigns</option>' + data.campaigns.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("");
    sel.value = keep || sel.dataset.want || "";
    delete sel.dataset.want;
    if (!data.tasks.length) openComposer(true);
    announceFinished();
    const json = JSON.stringify([data.tasks, data.ads, data.families, data.board, data.bridge.online, data.bridge.can_stop]);
    if (json !== lastJson) { lastJson = json; renderView(); }
  } catch (err) { toast(err.message, "bad"); }
  clearTimeout(pollTimer);
  const busy = data && data.tasks.some((t) => ACTIVE.has(t.status));
  pollTimer = setTimeout(load, document.hidden ? 60000 : busy ? 4000 : 20000);
}

const me = await boot({ page: "desk", admin: true });
if (me) {
  const q = new URLSearchParams(location.search);
  setKind(KINDS[q.get("kind")] ? q.get("kind") : "question");
  if (q.get("ask") || q.get("kind")) { openComposer(true); if (q.get("ask")) $("prompt").value = q.get("ask"); }
  $("ask-open").addEventListener("click", () => openComposer($("composer").hidden));
  $("ask-close").addEventListener("click", () => openComposer(false));
  $("views").addEventListener("click", (e) => {
    const b = e.target.closest("[data-view]");
    if (b) location.hash = b.dataset.view;
  });
  const main = document.querySelector(".main");
  main.addEventListener("click", onBoardClick);
  main.addEventListener("change", onBoardChange);
  if (q.get("campaign")) $("campaign").dataset.want = q.get("campaign");
  $("kinds").addEventListener("click", (e) => { const b = e.target.closest("button[data-kind]"); if (b) setKind(b.dataset.kind); });
  $("ask-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const prompt = $("prompt").value.trim();
    if (!prompt) { $("prompt").focus(); toast("Write what you'd like Claude to do", "bad"); return; }
    const btn = e.submitter || e.target.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      await api("/api/desk/tasks", { method: "POST", body: { kind, prompt, campaign_id: $("campaign").value } });
      $("prompt").value = "";
      openComposer(false);
      toast(data && data.bridge.online ? "Sent. Your Mac picks it up in a moment." : "Queued. It runs when your Mac is on.");
      reload();
    } catch (err) { toast(err.message, "bad"); } finally { btn.disabled = false; }
  });
  $("prompt").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) $("ask-form").requestSubmit(); });
  wireTaskActions(main, reload, openReports);
  wireSchedules($("view"), async () => { await loadSchedules(); reload(); });
  loadSchedules();
  readHash();
  window.addEventListener("hashchange", route);
  phone.addEventListener("change", route);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
  onRefresh(load);
  load();
}
