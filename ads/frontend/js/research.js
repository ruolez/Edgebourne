// Creative › Research (admins), in four parts: the swipe file (competitor ads worth keeping, the start of a new ad:
// "Make something like this" on one, "Write a brief" on several), search (Meta's Ad Library or Claude), watched Pages
// and past research. The part is in the address (#tab=…); #swipe=<id> opens the swipe file on that ad.
import { api } from "./api.js";
import { boot, confirmDialog, esc, fieldError, icon, onRefresh, toast } from "./ui.js";
import { count } from "./format.js";
import { ACTIVE, taskCard, wireTaskActions } from "./tasks.js";
import { BRIEF_MAX, askForBrief } from "./brief.js";

const $ = (id) => document.getElementById(id);
const QUICK = ["custom software", "business automation", "QuickBooks integration", "inventory software", "IT consulting Los Angeles", "AI for small business"];
const PARTS = ["swipes", "search", "watched", "past"];
const openReports = new Set();
let timer;
let lastJson = "";

function libraryUrl(q, country, active) {
  const p = new URLSearchParams({ active_status: active ? "active" : "all", ad_type: "all", country, q, search_type: "keyword_unordered", media_type: "all" });
  return `https://www.facebook.com/ads/library/?${p}`;
}

// ---------------------------------------------------------------- the four parts

function partFromHash() {
  const h = location.hash;
  if (/^#swipe=/.test(h)) return "swipes";
  const m = h.match(/^#tab=(\w+)/);
  return m && PARTS.includes(m[1]) ? m[1] : "swipes";
}

function showPart(part, { focus = false, remember = true } = {}) {
  document.querySelectorAll("#rs-tabs [data-part]").forEach((t) => t.setAttribute("aria-selected", String(t.dataset.part === part)));
  document.querySelectorAll("[data-part-panel]").forEach((p) => { p.hidden = p.dataset.partPanel !== part; });
  if (remember && partFromHash() !== part) {
    history.replaceState(null, "", part === "swipes" ? location.pathname + location.search : `#tab=${part}`);
  }
  drawTray();
  if (focus) document.querySelector(`#rs-tabs [data-part="${part}"]`)?.focus();
}

function setCount(id, n) {
  const el = $(id);
  el.textContent = n ? count(n) : "";
  el.hidden = !n;
}

async function load() {
  try {
    const d = await api("/api/desk");
    const m = d.bridge.status;
    $("mac-line").textContent = m ? `${m.title}. ${m.detail}` : "";
    const tasks = d.tasks.filter((t) => t.kind === "research");
    setCount("n-past", tasks.length);
    const json = JSON.stringify(tasks);
    if (json !== lastJson) {
      lastJson = json;
      if (tasks[0]) tasks[0].reports.forEach((r) => openReports.add(r.id));
      $("tasks").innerHTML = tasks.length ? tasks.map((t) => taskCard(t, openReports)).join("")
        : '<section class="panel empty"><h3>No research yet</h3><p>Ask Claude what competitors are running, which angles repeat and what\'s worth testing (under Search). Reports land here.</p></section>';
    }
    clearTimeout(timer);
    timer = setTimeout(load, tasks.some((t) => ACTIVE.has(t.status)) ? 4000 : 30000);
  } catch (err) {
    toast(err.message, "bad");
    clearTimeout(timer);
    timer = setTimeout(load, 15000);  // a restart or a blip: try again by itself
  }
}

// ---------------------------------------------------------------- swipe file + watched Pages

let swipeData = { items: [], watched: [] };
let swipeFilter = "all";
const SF = { all: () => true, long: (s) => s.long_running, claude: (s) => s.source === "claude" };
const picked = new Set();  // swipe ids ticked for a brief, kept across the filters

function swipeCard(s) {
  const tags = Object.entries(s.tags || {}).map(([k, v]) => `<span class="chip" title="${esc(k)}">${esc(v)}</span>`).join("");
  const on = picked.has(s.id);
  return `<article class="swipe${s.long_running ? " long" : ""}${on ? " is-picked" : ""}" data-swipe="${s.id}">
    <header><label class="swipe-tick"><input type="checkbox" data-pick-swipe="${s.id}" aria-label="Select the ad from ${esc(s.page_name)}" ${on ? "checked" : ""}></label>
      <b>${esc(s.page_name)}</b>${s.running_label ? `<span class="pill ${s.long_running ? "ok" : ""}">${esc(s.still_running ? s.running_label : `Ran ${s.days_running} days`)}</span>` : ""}
      ${s.source === "claude" ? '<span class="pill claude">Claude</span>' : ""}</header>
    ${s.media_url ? `<img src="${esc(s.media_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ""}
    ${s.title ? `<p class="swipe-title">${esc(s.title)}</p>` : ""}
    ${s.body ? `<p class="swipe-body">${esc(s.body)}</p>` : ""}
    ${tags ? `<div class="chips">${tags}</div>` : ""}
    <label class="sr-only" for="sn-${s.id}">Notes</label>
    <input class="input swipe-note" id="sn-${s.id}" data-note="${s.id}" value="${esc(s.notes || "")}" placeholder="Why it's worth keeping" autocomplete="off">
    <button type="button" class="btn btn-claude-outline btn-small swipe-like" data-like="${s.id}">${icon("spark")}Make something like this</button>
    <footer>${s.library_url ? `<a href="${esc(s.library_url)}" target="_blank" rel="noopener noreferrer">Open in Ad Library ${icon("external")}</a>` : "<span></span>"}
      <button type="button" class="link-btn muted" data-remove-swipe="${s.id}">Remove</button></footer>
  </article>`;
}

function renderSwipes() {
  const list = swipeData.items.filter(SF[swipeFilter]);
  const known = new Set(swipeData.items.map((s) => s.id));
  for (const id of [...picked]) if (!known.has(id)) picked.delete(id);
  $("swipe-count").textContent = `${swipeData.items.length} saved · ${swipeData.items.filter(SF.long).length} running 30+ days`;
  setCount("n-swipes", swipeData.items.length);
  setCount("n-watched", swipeData.watched.length);
  $("swipe-how").hidden = !swipeData.items.length;
  document.querySelectorAll("#swipe-filter [data-sf]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.sf === swipeFilter)));
  $("swipes").innerHTML = list.length ? `<div class="swipe-grid">${list.map(swipeCard).join("")}</div>`
    : swipeData.items.length ? '<p class="muted flush">None match.</p>'
      : '<p class="muted flush">Nothing saved yet. Paste an Ad Library link with Save an ad, or watch a competitor\'s Page and turn on the weekly Competitor check.</p>';
  $("watched").innerHTML = swipeData.watched.length ? swipeData.watched.map((w) => `<li><span><b>${esc(w.name)}</b><small class="muted">${esc([w.search_terms, w.last_checked_at ? `checked ${new Date(w.last_checked_at).toLocaleDateString()}` : "not checked yet"].filter(Boolean).join(" · "))}</small></span>
      <button type="button" class="link-btn muted" data-unwatch="${w.id}">Stop watching</button></li>`).join("")
    : '<li class="muted">No Pages yet.</li>';
  drawTray();
}

// The tray under the swipe file: how many are ticked and Write a brief (BRIEF_MAX at most).
function drawTray() {
  const tray = $("rs-tray");
  const shown = picked.size && !document.querySelector('[data-part-panel="swipes"]').hidden;
  if (!shown) { tray.innerHTML = ""; document.body.classList.remove("has-bulk"); return; }
  const n = picked.size;
  const ok = n <= BRIEF_MAX;
  const why = ok ? "" : `<span class="gal-why" id="rs-why">A brief takes ${BRIEF_MAX} at most</span>`;
  tray.innerHTML = `<div class="bk" role="toolbar" aria-label="${n} selected"><span class="bk-n"><b>${count(n)}</b> selected</span>
    <span class="bk-acts">${why}<button type="button" class="btn btn-claude btn-small" data-tray="brief" ${ok ? "" : 'disabled aria-describedby="rs-why"'}>${icon("spark")}<span>Write a brief</span></button></span>
    <button type="button" class="icon-btn bk-x" data-tray="clear" aria-label="Clear the selection">×</button></div>`;
  document.body.classList.add("has-bulk");
}

async function loadSwipes() {
  try { swipeData = await api("/api/swipes"); renderSwipes(); showLinkedSwipe(); } catch (err) { $("swipes").innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

// #swipe=<id> (a link from the command menu): that saved ad, in view and marked.
function showLinkedSwipe() {
  const m = location.hash.match(/swipe=(\d+)/);
  if (!m || !swipeData.items.some((s) => String(s.id) === m[1])) return;
  showPart("swipes", { remember: false });
  if (swipeFilter !== "all") { swipeFilter = "all"; renderSwipes(); }
  const card = document.querySelector(`#swipes [data-swipe="${m[1]}"]`);
  card.classList.remove("flash");
  void card.offsetWidth;
  card.classList.add("flash");
  card.scrollIntoView({ block: "center" });
}
addEventListener("hashchange", () => { if (/^#swipe=/.test(location.hash)) showLinkedSwipe(); else showPart(partFromHash(), { remember: false }); });

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
    const pick = e.target.closest("[data-pick-swipe]");
    if (pick) {
      const id = Number(pick.dataset.pickSwipe);
      if (pick.checked) picked.add(id); else picked.delete(id);
      pick.closest(".swipe")?.classList.toggle("is-picked", pick.checked);
      drawTray();
      return;
    }
    const n = e.target.closest("[data-note]");
    if (!n) return;
    try { swipeData.items = (await api(`/api/swipes/${n.dataset.note}`, { method: "PATCH", body: { notes: n.value } })).items; toast("Note saved"); }
    catch (err) { toast(err.message, "bad"); }
  });
  $("swipes").addEventListener("click", async (e) => {
    const like = e.target.closest("[data-like]");
    if (like) { await askForBrief([Number(like.dataset.like)], "like"); return; }
    const rm = e.target.closest("[data-remove-swipe]");
    if (!rm) return;
    if (!(await confirmDialog({ title: "Remove it from the swipe file?", body: "<p>Only from this list. Nothing changes on Meta.</p>", confirm: "Remove" }))) return;
    try { swipeData.items = (await api(`/api/swipes/${rm.dataset.removeSwipe}`, { method: "DELETE" })).items; renderSwipes(); } catch (err) { toast(err.message, "bad"); }
  });
  $("rs-tray").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-tray]");
    if (!b) return;
    if (b.dataset.tray === "clear") { picked.clear(); renderSwipes(); return; }
    // In the order they sit on the page, so the brief numbers them as Eugene sees them.
    const order = swipeData.items.map((s) => s.id).filter((id) => picked.has(id));
    await askForBrief(order, "brief");
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && picked.size && !document.querySelector("dialog[open]")) { picked.clear(); renderSwipes(); }
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
  showPart(partFromHash(), { remember: false });
  $("rs-tabs").addEventListener("click", (e) => { const t = e.target.closest("[data-part]"); if (t) showPart(t.dataset.part); });
  // Edge Bourne's own searches; another account starts with none (type one, or ask Claude to watch Pages).
  const quick = (window.ebadsMe && window.ebadsMe.account.id !== 1) ? [] : QUICK;
  $("quick").hidden = !quick.length;
  $("quick").innerHTML = quick.map((q) => `<button type="button" class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join("");
  $("quick").addEventListener("click", (e) => { const b = e.target.closest("[data-q]"); if (b) { $("q").value = b.dataset.q; $("lib-form").requestSubmit(); } });
  $("lib-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("q").value.trim();
    if (!q) { $("q").focus(); return; }
    window.open(libraryUrl(q, $("country").value, $("active").checked), "_blank", "noopener");
  });
  $("ask-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("ask-form").querySelector("button[type=submit]");
    if (btn.disabled) return;  // a second Enter while the first is on its way
    const prompt = $("prompt").value.trim();
    if (!prompt) { $("prompt").focus(); return; }
    btn.disabled = true;
    try {
      await api("/api/desk/tasks", { method: "POST", body: { kind: "research", prompt } });
      $("prompt").value = "";
      toast("Sent to Claude. Its report will show in Past research");
      lastJson = "";
      load();
    } catch (err) { toast(err.message, "bad"); }
    finally { btn.disabled = false; }
  });
  wireTaskActions($("tasks"), () => { lastJson = ""; load(); }, openReports);
  wireSwipes();
  onRefresh(() => { load(); loadSwipes(); });
  load();
  loadSwipes();
}
