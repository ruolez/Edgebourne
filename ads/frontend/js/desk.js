import { api } from "./api.js";
import { boot, esc, onRefresh, toast, when } from "./ui.js";
import { ACTIVE, wireTaskActions } from "./tasks.js";
import { adsView, index, loadPreviews, runsView, waitingView, workingStrip } from "./board.js";
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
let pollTimer;
let freshKey = null;
let lastJson = "";
const openReports = new Set();
let view = (location.hash.match(/^#(waiting|ads|runs|schedules)/) || [])[1] || null;

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

function setView(next, focusId) {
  view = next;
  history.replaceState(null, "", `${location.pathname}${location.search}#${view}`);
  document.querySelectorAll("#views [data-view]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === view)));
  renderView();
  if (focusId) {
    const el = document.getElementById(focusId);
    if (el) { el.scrollIntoView({ behavior: "smooth", block: "start" }); el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 1600); }
  } else window.scrollTo({ top: 0 });
}

function renderView() {
  const ix = index(data);
  const waiting = data.families.reduce((n, f) => n + f.pending, 0);
  $("tab-waiting").innerHTML = `Waiting for you${waiting ? ` <span class="n claude">${waiting}</span>` : ""}`;
  $("tab-ads").innerHTML = `By ad <span class="n">${data.families.filter((f) => f.root).length}</span>`;
  $("tab-runs").innerHTML = `All runs <span class="n">${data.tasks.length}</span>`;
  const schedOn = scheduleList ? scheduleList.filter((x) => x.enabled).length : 0;
  $("tab-schedules").innerHTML = `Schedules${schedOn ? ` <span class="n">${schedOn} on</span>` : ""}`;
  $("working").innerHTML = workingStrip(data);
  $("view").setAttribute("aria-labelledby", `tab-${view}`);
  if (view === "schedules") { $("view").innerHTML = schedulesView(scheduleList, data.bridge); return; }
  $("view").innerHTML = view === "waiting" ? waitingView(data, ix) : view === "ads" ? adsView(data, ix, openReports) : runsView(data, ix, openReports);
  loadPreviews($("view"));
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
    if (!view) view = data.families.some((f) => f.pending) ? "waiting" : "ads";
    if (!data.tasks.length) openComposer(true);
    document.querySelectorAll("#views [data-view]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === view)));
    const json = JSON.stringify([data.tasks, data.ads, data.families]);
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
  $("views").addEventListener("click", (e) => { const b = e.target.closest("[data-view]"); if (b) setView(b.dataset.view); });
  document.querySelector(".main").addEventListener("click", (e) => {
    const run = e.target.closest("[data-goto-run]");
    if (run) { e.preventDefault(); setView("ads", `run-${run.dataset.gotoRun}`); return; }
    const prop = e.target.closest("[data-goto-proposal]");
    if (prop) { e.preventDefault(); setView("waiting", `p-${prop.dataset.gotoProposal}`); return; }
    if (e.target.closest("[data-ask]")) openComposer(true);
  });
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
      lastJson = "";
      load();
    } catch (err) { toast(err.message, "bad"); } finally { btn.disabled = false; }
  });
  $("prompt").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) $("ask-form").requestSubmit(); });
  wireTaskActions(document.querySelector(".main"), () => { lastJson = ""; load(); }, openReports);
  wireSchedules($("view"), async () => { await loadSchedules(); lastJson = ""; load(); });
  loadSchedules();
  window.addEventListener("hashchange", () => {
    const h = (location.hash.match(/^#(waiting|ads|runs|schedules)/) || [])[1];
    if (h && h !== view && data) setView(h);
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
  onRefresh(load);
  load();
}
