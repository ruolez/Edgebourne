import { api } from "./api.js";
import { boot, confirmDialog, esc, fieldError, icon, onRefresh, toast } from "./ui.js";
import { ACTIVE, taskCard, wireTaskActions } from "./tasks.js";

const $ = (id) => document.getElementById(id);
const QUICK = ["custom software", "business automation", "QuickBooks integration", "inventory software", "IT consulting Los Angeles", "AI for small business"];
const openReports = new Set();
let timer;
let lastJson = "";

function libraryUrl(q, country, active) {
  const p = new URLSearchParams({ active_status: active ? "active" : "all", ad_type: "all", country, q, search_type: "keyword_unordered", media_type: "all" });
  return `https://www.facebook.com/ads/library/?${p}`;
}

async function load() {
  try {
    const d = await api("/api/desk");
    $("mac-line").textContent = d.bridge.online ? "Your Mac is connected: Claude starts right away." : "Your Mac is offline: this waits until it's on.";
    const tasks = d.tasks.filter((t) => t.kind === "research");
    const json = JSON.stringify(tasks);
    if (json !== lastJson) {
      lastJson = json;
      if (tasks[0]) tasks[0].reports.forEach((r) => openReports.add(r.id));
      $("tasks").innerHTML = tasks.length ? tasks.map((t) => taskCard(t, openReports)).join("")
        : '<section class="panel empty"><h3>No research yet</h3><p>Ask Claude what competitors are running, which angles repeat and what\'s worth testing. Reports land here.</p></section>';
    }
    clearTimeout(timer);
    timer = setTimeout(load, tasks.some((t) => ACTIVE.has(t.status)) ? 4000 : 30000);
  } catch (err) { toast(err.message, "bad"); }
}

// ---------------------------------------------------------------- swipe file + watched Pages

let swipeData = { items: [], watched: [] };
let swipeFilter = "all";
const SF = { all: () => true, long: (s) => s.long_running, claude: (s) => s.source === "claude" };

function swipeCard(s) {
  const tags = Object.entries(s.tags || {}).map(([k, v]) => `<span class="chip" title="${esc(k)}">${esc(v)}</span>`).join("");
  return `<article class="swipe${s.long_running ? " long" : ""}" data-swipe="${s.id}">
    <header><b>${esc(s.page_name)}</b>${s.running_label ? `<span class="pill ${s.long_running ? "ok" : ""}">${esc(s.still_running ? s.running_label : `Ran ${s.days_running} days`)}</span>` : ""}
      ${s.source === "claude" ? '<span class="pill claude">Claude</span>' : ""}</header>
    ${s.media_url ? `<img src="${esc(s.media_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ""}
    ${s.title ? `<p class="swipe-title">${esc(s.title)}</p>` : ""}
    ${s.body ? `<p class="swipe-body">${esc(s.body)}</p>` : ""}
    ${tags ? `<div class="chips">${tags}</div>` : ""}
    <label class="sr-only" for="sn-${s.id}">Notes</label>
    <input class="input swipe-note" id="sn-${s.id}" data-note="${s.id}" value="${esc(s.notes || "")}" placeholder="Why it's worth keeping" autocomplete="off">
    <footer>${s.library_url ? `<a href="${esc(s.library_url)}" target="_blank" rel="noopener noreferrer">Open in Ad Library ${icon("external")}</a>` : "<span></span>"}
      <button type="button" class="link-btn muted" data-remove-swipe="${s.id}">Remove</button></footer>
  </article>`;
}

function renderSwipes() {
  const list = swipeData.items.filter(SF[swipeFilter]);
  $("swipe-count").textContent = `${swipeData.items.length} saved · ${swipeData.items.filter(SF.long).length} running 30+ days`;
  document.querySelectorAll("#swipe-filter [data-sf]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.sf === swipeFilter)));
  $("swipes").innerHTML = list.length ? `<div class="swipe-grid">${list.map(swipeCard).join("")}</div>`
    : swipeData.items.length ? '<p class="muted flush">None match.</p>'
      : '<p class="muted flush">Nothing saved yet. Paste an Ad Library link with Save an ad, or watch a competitor\'s Page and turn on the weekly Competitor check.</p>';
  $("watched").innerHTML = swipeData.watched.length ? swipeData.watched.map((w) => `<li><span><b>${esc(w.name)}</b><small class="muted">${esc([w.search_terms, w.last_checked_at ? `checked ${new Date(w.last_checked_at).toLocaleDateString()}` : "not checked yet"].filter(Boolean).join(" · "))}</small></span>
      <button type="button" class="link-btn muted" data-unwatch="${w.id}">Stop watching</button></li>`).join("")
    : '<li class="muted">No Pages yet.</li>';
}

async function loadSwipes() {
  try { swipeData = await api("/api/swipes"); renderSwipes(); } catch (err) { $("swipes").innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

function wireSwipes() {
  $("swipe-add").addEventListener("click", () => { $("swipe-form").hidden = false; $("sw-link").focus(); });
  $("swipe-cancel").addEventListener("click", () => { $("swipe-form").hidden = true; });
  $("swipe-filter").addEventListener("click", (e) => { const b = e.target.closest("[data-sf]"); if (b) { swipeFilter = b.dataset.sf; renderSwipes(); } });
  $("swipe-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    const body = Object.fromEntries(["link", "page_name", "body", "title", "started_on", "notes"].map((k) => [k, f[k].value]));
    try {
      const r = await api("/api/swipes", { method: "POST", body });
      swipeData.items = r.items; f.reset(); f.hidden = true; renderSwipes();
      toast(r.new ? "Saved to the swipe file" : "Already saved; updated it");
    } catch (err) { toast(err.message, "bad"); }
  });
  $("swipes").addEventListener("change", async (e) => {
    const n = e.target.closest("[data-note]");
    if (!n) return;
    try { swipeData.items = (await api(`/api/swipes/${n.dataset.note}`, { method: "PATCH", body: { notes: n.value } })).items; toast("Note saved"); }
    catch (err) { toast(err.message, "bad"); }
  });
  $("swipes").addEventListener("click", async (e) => {
    const rm = e.target.closest("[data-remove-swipe]");
    if (!rm) return;
    if (!(await confirmDialog({ title: "Remove it from the swipe file?", body: "<p>Only from this list. Nothing changes on Meta.</p>", confirm: "Remove" }))) return;
    try { swipeData.items = (await api(`/api/swipes/${rm.dataset.removeSwipe}`, { method: "DELETE" })).items; renderSwipes(); } catch (err) { toast(err.message, "bad"); }
  });
  $("watch-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    fieldError(f, null);
    try { swipeData = await api("/api/watched", { method: "POST", body: { name: f.name.value, page_id: f.page_id.value, search_terms: f.search_terms.value } }); f.reset(); renderSwipes(); toast("Watching it"); }
    catch (err) { if (err.body && err.body.field) fieldError(f, err.body.field, err.message); else toast(err.message, "bad"); }
  });
  $("watched").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-unwatch]");
    if (!b) return;
    try { swipeData = await api(`/api/watched/${b.dataset.unwatch}`, { method: "DELETE" }); renderSwipes(); } catch (err) { toast(err.message, "bad"); }
  });
}

const me = await boot({ page: "research", admin: true });
if (me) {
  $("quick").innerHTML = QUICK.map((q) => `<button type="button" class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join("");
  $("quick").addEventListener("click", (e) => { const b = e.target.closest("[data-q]"); if (b) { $("q").value = b.dataset.q; $("lib-form").requestSubmit(); } });
  $("lib-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("q").value.trim();
    if (!q) { $("q").focus(); return; }
    window.open(libraryUrl(q, $("country").value, $("active").checked), "_blank", "noopener");
  });
  $("ask-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const prompt = $("prompt").value.trim();
    if (!prompt) { $("prompt").focus(); return; }
    try {
      await api("/api/desk/tasks", { method: "POST", body: { kind: "research", prompt } });
      $("prompt").value = "";
      toast("Sent to Claude");
      lastJson = "";
      load();
    } catch (err) { toast(err.message, "bad"); }
  });
  wireTaskActions($("tasks"), () => { lastJson = ""; load(); }, openReports);
  wireSwipes();
  onRefresh(() => { load(); loadSwipes(); });
  load();
  loadSwipes();
}
