// Shared UI: app frame, icons, toasts, formatting.
import { api } from "./api.js";
import { setCurrency, currencySymbol, money, moneyWhole, explain } from "./format.js";

const ICONS = {
  close: '<path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  leads: '<path d="M4 5h16v11H8l-4 4z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
  team: '<circle cx="9" cy="8" r="3.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M3 19c.8-3.2 3.2-5 6-5s5.2 1.8 6 5M16 5.5a3 3 0 0 1 0 5.6M18 14.5c1.6.6 2.6 2.1 3 4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  settings: '<circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 2.8v2.6M12 18.6v2.6M2.8 12h2.6M18.6 12h2.6M5.5 5.5l1.8 1.8M16.7 16.7l1.8 1.8M5.5 18.5l1.8-1.8M16.7 7.3l1.8-1.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  phone: '<path d="M6.6 3.5h3l1.5 4-2 1.3a11 11 0 0 0 6.1 6.1l1.3-2 4 1.5v3c0 1-.8 1.8-1.8 1.8C10.5 19.2 4.8 13.5 4.8 5.3c0-1 .8-1.8 1.8-1.8z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
  mail: '<rect x="3.5" y="5.5" width="17" height="13" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M4 7l8 6 8-6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
  search: '<circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M16 16l4.5 4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M21 20H3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  spark: '<path d="M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9-1.9 5.1-1.9-5.1-5.1-1.9 5.1-1.9z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M18.5 15.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" fill="currentColor"/>',
  home: '<path d="M4 11l8-6.5 8 6.5V20h-5.5v-5h-5v5H4z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
  ads: '<rect x="3.5" y="4.5" width="7" height="8.5" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="13.5" y="4.5" width="7" height="8.5" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M3.5 17h7M3.5 20h4.5M13.5 17h7M13.5 20h4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  research: '<circle cx="10.5" cy="10.5" r="6" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M15 15l5 5M8 10.5h5M10.5 8v5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  tests: '<path d="M9 3.5h6M10 3.5v5.2L4.8 18.3A1.5 1.5 0 0 0 6.1 20.5h11.8a1.5 1.5 0 0 0 1.3-2.2L14 8.7V3.5M7.5 14.5h9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  play: '<path d="M8 5.5v13l10.5-6.5z" fill="currentColor"/>',
  plus: '<path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  copy: '<rect x="8.5" y="8.5" width="11" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M15.5 5.5V5a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 5v8A1.5 1.5 0 0 0 6 14.5h.5" fill="none" stroke="currentColor" stroke-width="1.8"/>',
  external: '<path d="M14 4.5h5.5V10M19.5 4.5L11 13M17 14v4.5a1 1 0 0 1-1 1H5.5a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1H10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  upload: '<path d="M12 15.5V4.5M7.5 9L12 4.5 16.5 9M4.5 15v3.5a1 1 0 0 0 1 1h13a1 1 0 0 0 1-1V15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  image: '<rect x="3.5" y="4.5" width="17" height="15" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="9" cy="10" r="1.8" fill="currentColor"/><path d="M4 17l5-4.5 4 3.5 3-2.5 4.5 3.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
  table: '<path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  grid: '<rect x="4" y="4" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="13" y="4" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="4" y="13" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="13" y="13" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/>',
  back: '<path d="M14.5 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  sun: '<circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  refresh: '<path d="M20 11.5A8 8 0 0 0 6.2 6.3L4 8.5M4 4.5v4h4M4 12.5a8 8 0 0 0 13.8 5.2L20 15.5M20 19.5v-4h-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  clock: '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 7.5V12l3 2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  alarm: '<circle cx="12" cy="13" r="7.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 9.5V13l2.5 1.5M4 5l3-2.5M20 5l-3-2.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  missed: '<path d="M6.6 3.5h3l1.5 4-2 1.3a11 11 0 0 0 6.1 6.1l1.3-2 4 1.5v3c0 1-.8 1.8-1.8 1.8C10.5 19.2 4.8 13.5 4.8 5.3c0-1 .8-1.8 1.8-1.8z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M15 3.5l5 5M20 3.5l-5 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  power: '<path d="M12 3.5v8M7.3 6.6a7 7 0 1 0 9.4 0" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  made: '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 8v8M8 12h8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  moon: '<path d="M19.5 14.5A8 8 0 0 1 9.5 4.5a8 8 0 1 0 10 10z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
  logout: '<path d="M14 4.5h4.5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H14M10 16l4-4-4-4M14 12H4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  inbox: '<path d="M3.5 13.5h5l1.5 2.5h4l1.5-2.5h5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M6.2 5.5h11.6l2.7 8V18a1.5 1.5 0 0 1-1.5 1.5h-14A1.5 1.5 0 0 1 3.5 18v-4.5z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
  compare: '<rect x="3.5" y="4.5" width="7" height="15" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="13.5" y="4.5" width="7" height="15" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/>',
  user: '<circle cx="12" cy="8.5" r="3.8" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M4.5 20c1-3.6 4-5.5 7.5-5.5s6.5 1.9 7.5 5.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
};
// The service worker makes the console installable and shows push notifications.
if ("serviceWorker" in navigator && location.protocol !== "file:") {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
let installPrompt = null;
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); installPrompt = e; document.dispatchEvent(new Event("ebads:installable")); });
export const canInstall = () => !!installPrompt;
export async function promptInstall() {
  if (!installPrompt) return false;
  installPrompt.prompt();
  const { outcome } = await installPrompt.userChoice;
  installPrompt = null;
  return outcome === "accepted";
}

export const icon = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ""}</svg>`;

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Toasts sit in the top layer (a manual popover, shown again on every message), so one raised while a
// dialog is open shows above the dialog instead of behind its backdrop.
let toastTimer;
const topLayer = (el, on) => {
  if (!el.popover) return;
  try {
    if (el.matches(":popover-open")) el.hidePopover();
    if (on) el.showPopover();
  } catch (e) { /* not connected yet */ }
};
export function toast(message, kind = "") {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    el.setAttribute("role", kind === "bad" ? "alert" : "status");
    if ("showPopover" in el) el.popover = "manual";
    document.body.appendChild(el);
  }
  // An open modal dialog makes everything outside it inert, so screen readers would never hear the toast:
  // it lives inside that dialog while one is open, and goes back to the page when the dialog closes.
  const modals = [...document.querySelectorAll("dialog[open]")].filter((d) => { try { return d.matches(":modal"); } catch (e) { return true; } });
  const host = modals[modals.length - 1] || document.body;
  if (el.parentNode !== host) {
    topLayer(el, false);
    host.appendChild(el);
    if (host !== document.body) {
      host.addEventListener("close", () => {
        if (el.parentNode !== host) return;
        document.body.appendChild(el);
        if (!el.hidden) topLayer(el, true);
      }, { once: true });
    }
  }
  el.textContent = message;
  el.className = "toast " + kind;
  el.setAttribute("role", kind === "bad" ? "alert" : "status");
  el.hidden = false;
  topLayer(el, true);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; topLayer(el, false); }, kind === "bad" ? 6000 : 3000);
}

// Tablists: arrow keys (Home / End) move between the tabs and open the one reached; only the chosen tab
// sits in the Tab order. A tablist with data-tabpanel="<id>" names the panel its tabs show.
const tabsOf = (list) => [...list.querySelectorAll('[role="tab"]')].filter((t) => t.closest('[role="tablist"]') === list && !t.disabled && !t.hidden);
let tabSeq = 0;
export function syncTabs(root = document) {
  root.querySelectorAll('[role="tablist"]').forEach((list) => {
    const tabs = tabsOf(list);
    const chosen = tabs.find((t) => t.getAttribute("aria-selected") === "true") || tabs[0];
    const panel = list.dataset.tabpanel && document.getElementById(list.dataset.tabpanel);
    tabs.forEach((t) => {
      if (!t.hasAttribute("aria-selected")) t.setAttribute("aria-selected", "false");  // once: setting it again would wake the observer
      const want = t === chosen ? 0 : -1;
      if (t.tabIndex !== want) t.tabIndex = want;
      if (panel) { if (!t.id) t.id = `tab-${++tabSeq}`; t.setAttribute("aria-controls", panel.id); }
    });
    if (panel && chosen) { panel.setAttribute("role", "tabpanel"); panel.setAttribute("aria-labelledby", chosen.id); }
  });
}
document.addEventListener("keydown", (e) => {
  const tab = e.target.closest && e.target.closest('[role="tab"]');
  const list = tab && tab.closest('[role="tablist"]');
  if (!list || e.metaKey || e.ctrlKey || e.altKey) return;
  const tabs = tabsOf(list);
  const i = tabs.indexOf(tab);
  const to = { ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
  if (to === undefined || i < 0) return;
  e.preventDefault();
  const next = tabs[(to + tabs.length) % tabs.length];
  next.focus();
  if (next.getAttribute("aria-selected") === "true") return;
  // Some pages draw their tabs again on a switch (now, or once the data is in): focus follows to the new copy.
  const key = [...next.attributes].filter((a) => a.name.startsWith("data-")).map((a) => `[${a.name}="${CSS.escape(a.value)}"]`).join("");
  next.click();
  const follow = (tries) => {
    const again = !next.isConnected && key && document.querySelector(`[role="tab"]${key}`);
    if (again) { if (!document.activeElement || document.activeElement === document.body) again.focus(); return; }
    if (tries) setTimeout(() => follow(tries - 1), 150);
  };
  follow(12);
});
let tabsQueued = false;
new MutationObserver(() => {
  if (tabsQueued) return;
  tabsQueued = true;
  queueMicrotask(() => { tabsQueued = false; syncTabs(); });
}).observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ["aria-selected"] });

// ---------- time ----------
export function waited(iso, now = Date.now()) {
  const mins = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60000));
  if (mins < 60) return { text: `${mins}m`, mins };
  if (mins < 48 * 60) {
    const m = mins % 60;
    return { text: m ? `${Math.floor(mins / 60)}h ${m}m` : `${Math.floor(mins / 60)}h`, mins };
  }
  return { text: `${Math.floor(mins / 1440)}d`, mins };
}
export function shortWait(iso, now = Date.now()) {
  const mins = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins}m`;
  if (mins < 48 * 60) return `${Math.floor(mins / 60)}h`;
  return `${Math.floor(mins / 1440)}d`;
}
export function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
export function phoneDisplay(p) {
  if (!p) return "";
  const d = p.replace(/\D/g, "");
  if (d.length === 11 && d[0] === "1") return `(${d.slice(1, 4)}) ${d.slice(4, 7)}-${d.slice(7)}`;
  if (d.length === 10) return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`;
  return p;
}

// ---------- theme ----------
const THEMES = ["system", "light", "dark"];
export function currentTheme() {
  try { return localStorage.getItem("ebads-theme") || "system"; } catch (e) { return "system"; }
}
const themeLabel = (t) => ({ system: "Theme: auto", light: "Theme: light", dark: "Theme: dark" }[t]);
export function applyTheme(t) {
  if (t === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem("ebads-theme", t); } catch (e) {}
  document.querySelectorAll("[data-theme-btn]").forEach((b) => { (b.querySelector("span") || b).textContent = themeLabel(t); });
}

// ---------- frame ----------
// Desktop: light sidebar. Phone: top bar + bottom tab bar + "More" sheet.
// Every page gets the Refresh control; a page hands its reload to onRefresh(fn).
// opts.auto, when given, runs instead of fn for the frame's own catch-up with the server's pulls.
let refreshHandler = null;
let autoHandler = null;
let updatedAt = null;
let shownAt = null; // the updated_at the page's data was last loaded at
let autoMinutes = null;
let clockSkew = 0;
export function onRefresh(fn, opts = {}) { refreshHandler = fn; autoHandler = opts.auto || null; }

export function ago(ts, now = Date.now() / 1000) {
  if (!ts) return "not yet";
  const s = Math.max(0, Math.round(now - ts));
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  return `${Math.round(h / 24)} d ago`;
}

function paintUpdated() {
  const text = updatedAt ? `Updated ${ago(updatedAt, Date.now() / 1000 + clockSkew)}` : "Not refreshed yet";
  document.querySelectorAll("[data-updated]").forEach((el) => { el.textContent = text; });
  const auto = autoMinutes ? ` Updates by itself every ${autoMinutes === 60 ? "hour" : `${autoMinutes} min`}.` : "";
  document.querySelectorAll("[data-refresh]").forEach((b) => {
    b.setAttribute("aria-label", `Refresh. ${text}.${auto}`);
    b.title = `Get the latest from Meta.${auto}`;
  });
}

// Typing, a dialog or an open menu: reloading now would throw the person's work away.
export function editing() {
  const a = document.activeElement;
  return Boolean((a && a.matches("input, textarea, select, [contenteditable]")) || document.querySelector("dialog[open]"));
}

// The server pulls from Meta by itself; when it has newer data, this page reloads its own.
async function catchUp() {
  if (document.hidden) return;
  await frameStatus();
  if (!updatedAt || (shownAt && updatedAt <= shownAt) || editing()) return;
  const first = shownAt === null;
  shownAt = updatedAt;
  const reload = autoHandler || refreshHandler;
  if (first || !reload) return;
  try { await reload(); } catch (e) { /* the next manual refresh shows the error */ }
}

async function doRefresh() {
  const buttons = document.querySelectorAll("[data-refresh]");
  buttons.forEach((b) => { b.disabled = true; b.classList.add("busy"); });
  try {
    const r = await api("/api/refresh", { method: "POST" });
    updatedAt = r.updated_at;
    clockSkew = r.server_now ? r.server_now - Date.now() / 1000 : 0;
    if (r.ran) toast(r.new_leads ? `Up to date. ${r.new_leads} new lead${r.new_leads === 1 ? "" : "s"} found.` : "Up to date with Meta");
    else if (r.busy) toast("Already refreshing, one moment");
    if (refreshHandler) await refreshHandler();
    shownAt = updatedAt;
    frameStatus();
  } catch (err) {
    toast(err.message, "bad");
  } finally {
    buttons.forEach((b) => { b.disabled = false; b.classList.remove("busy"); });
    paintUpdated();
  }
}

async function frameStatus() {
  try {
    const st = await api("/api/refresh");
    updatedAt = st.updated_at;
    autoMinutes = st.auto_minutes || null;
    clockSkew = st.server_now ? st.server_now - Date.now() / 1000 : 0;
    setNewCount(st.new_leads || 0);
    document.querySelectorAll("[data-claude-count]").forEach((el) => { el.hidden = !st.proposals; el.textContent = st.proposals || ""; });
    document.querySelectorAll("[data-inbox-count]").forEach((el) => { el.hidden = !st.inbox_unread; el.textContent = st.inbox_unread > 99 ? "99+" : st.inbox_unread || ""; });
    const cap = st.cap;
    const card = document.getElementById("cap-card");
    if (card && cap && cap.limit_cents) {
      const used = Math.min(cap.spent_cents / cap.limit_cents, 1);
      const $$ = (c) => (c % 100 ? money(c, { exact: true }) : moneyWhole(c));
      card.hidden = false;
      card.innerHTML = `<span class="cap-top"><span>Spending limit</span><b>${$$(cap.spent_cents)} / ${$$(cap.limit_cents)}</b></span>
        <span class="bar ${used >= 1 ? "bad" : used >= 0.8 ? "warn" : ""}"><i data-w="${(used * 100).toFixed(1)}"></i></span>
        <small>${cap.remaining_cents <= 0 ? "Reached: every ad is paused" : `${$$(cap.remaining_cents)} left before ads pause`}</small>`;
      card.querySelectorAll("[data-w]").forEach((i) => { i.style.width = `${i.dataset.w}%`; });
    }
  } catch (e) { /* the frame works without it */ }
  paintUpdated();
}

function refreshButton() {
  return `<button type="button" class="refresh" data-refresh title="Get the latest from Meta">${icon("refresh")}<span class="r-text"><b>Refresh</b> <small data-updated>…</small></span></button>`;
}

// Agency mode: which ad account the console shows. Admins switch; others see their own.
function accountSwitch(me, where) {
  const list = me.accounts || [];
  if (!me.owner || list.length < 1) {
    return list.length > 1 || me.role === "client" ? `<p class="acct-name acct-${where}">${esc(me.account.name)}</p>` : "";
  }
  if (list.length === 1) {
    return `<div class="acct acct-${where}"><span class="acct-only">${esc(me.account.name)}</span>
      <button type="button" class="link-btn small" data-acct-add>+ Add an account</button></div>`;
  }
  return `<div class="acct acct-${where}"><label class="sr-only" for="acct-${where}">Ad account</label>
    <select class="input acct-select" id="acct-${where}" data-acct>${list.map((a) => `<option value="${a.id}" ${a.id === me.account.id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}
      <option value="new">+ Add an account…</option></select></div>`;
}

async function addAccount() {
  const name = await confirmDialog({ title: "Add an ad account", confirm: "Add",
    body: "<p>A business whose Meta ads this console will run (for example a client). Its ads, leads, results and Claude's work stay separate from the others.</p>",
    field: { label: "Business name", value: "", validate: (v) => (v.trim() ? null : "Give it a name") } });
  if (!name) return false;
  await api("/api/accounts", { method: "POST", body: { name: name.trim() } });
  location.href = "/settings.html#meta-form";
  return true;
}

// Listening on the document from the start: the switcher is drawn before boot() finishes, and a
// quick change must not slip through before a per-element listener would be attached.
document.addEventListener("change", async (e) => {
  const sel = e.target.closest("[data-acct]");
  if (!sel) return;
  try {
    if (sel.value === "new") { if (!(await addAccount())) sel.value = sel.querySelector("[selected]")?.value || sel.options[0].value; return; }
    await api("/api/accounts/switch", { method: "POST", body: { id: Number(sel.value) } });
    location.reload();
  } catch (err) { toast(err.message, "bad"); }
});
document.addEventListener("click", (e) => {
  if (e.target.closest("[data-acct-add]")) addAccount().catch((err) => toast(err.message, "bad"));
});

// The frame's map: every page belongs to one section of the sidebar; some sections have sub-pages
// shown as tabs under the breadcrumb line.
const PAGE_SECTION = {
  home: "today", inbox: "inbox", leads: "leads",
  ads: "ads", ad: "ads", "new-ad": "ads", "new-adset": "ads", "new-campaign": "ads", forms: "ads", campaign: "ads", adset: "ads",
  performance: "insights", compare: "insights", experiments: "insights", report: "insights",
  desk: "claude", research: "claude", settings: "settings", team: "settings", account: "account",
};
const PAGE_TITLE = {
  home: "Today", inbox: "Inbox", leads: "Leads", ads: "Ads", ad: "Ad", "new-ad": "New ad", "new-adset": "New ad set",
  "new-campaign": "New campaign", forms: "Lead forms", campaign: "Campaign", adset: "Ad set", performance: "Results",
  compare: "Compare", experiments: "Tests", report: "Reports", desk: "Claude", research: "Research", settings: "Settings",
  team: "Team", account: "Your account",
};
const SECTIONS = {
  today: { href: "/home.html", label: "Today", icon: "sun" },
  inbox: { href: "/inbox.html", label: "Inbox", icon: "inbox", badge: "inbox" },
  leads: { href: "/leads.html", label: "Leads", icon: "leads", badge: "leads" },
  ads: { href: "/ads.html", label: "Ads", icon: "ads" },
  insights: { href: "/performance.html", label: "Insights", icon: "chart" },
  claude: { href: "/desk.html", label: "Claude", icon: "spark", badge: "claude", admin: true },
  settings: { href: "/settings.html", label: "Settings", icon: "settings", admin: true },
  account: { href: "/account.html", label: "Your account", icon: "user" },
};
// Section tabs: [page, label, who] (who: "admin" = admins only, "all" = everyone signed in).
const SUBNAV = {
  ads: [["ads", "Ads", "all"], ["forms", "Lead forms", "admin"]],
  insights: [["performance", "Results", "all"], ["compare", "Compare", "all"], ["experiments", "Tests", "admin"], ["report", "Reports", "report"]],
  claude: [["desk", "Claude", "admin"], ["research", "Research", "admin"]],
  settings: [["settings", "Settings", "admin"], ["team", "Team", "admin"]],
};
const PAGE_HREF = { ads: "/ads.html", forms: "/forms.html", performance: "/performance.html", compare: "/compare.html",
  experiments: "/experiments.html", report: "/report.html", desk: "/desk.html", research: "/research.html",
  settings: "/settings.html", team: "/team.html" };

let frame = { page: null, section: null };

// Breadcrumbs: [{label, href}], the last one is the page itself. Pages that load names later call this.
export function setCrumbs(items) {
  const nav = document.querySelector(".crumbs");
  if (nav) {
    nav.innerHTML = items.map((c, i) => i === items.length - 1
      ? `<span aria-current="page">${esc(c.label)}</span>`
      : `<a href="${esc(c.href)}">${esc(c.label)}</a><span class="sep" aria-hidden="true">/</span>`).join("");
  }
  const up = document.querySelector(".topbar .crumb-up");
  const parent = items.length > 1 ? items[items.length - 2] : null;
  const root = !frame.page || Object.values(SUBNAV).some((tabs) => tabs.some(([p]) => p === frame.page)) || ["home", "inbox", "leads", "account"].includes(frame.page);
  if (up) { up.hidden = !parent || root; if (parent) up.href = parent.href; }
  const title = document.querySelector(".topbar .brand span");
  if (title && items.length) title.firstChild.textContent = items[items.length - 1].label;
}

// The one empty state: a title, a plain sentence (HTML) and at most one or two actions (HTML).
// `tag` li for lists; `panel: false` when it sits inside a panel already; `variant` "center" or "compact".
export function emptyState({ title, body = "", actions = "", tag = "section", panel = true, role = "", variant = "" }) {
  const cls = `${panel && tag !== "li" ? "panel " : ""}empty${variant ? ` ${variant}` : ""}`;
  return `<${tag} class="${cls}"${role ? ` role="${role}"` : ""}>${title ? `<h3>${esc(title)}</h3>` : ""}${body ? `<p>${body}</p>` : ""}${actions ? `<div class="row">${actions}</div>` : ""}</${tag}>`;
}

// The one loading placeholder: shimmering bars and a line saying what is coming.
// `preview` draws the tall bar of an ad preview.
export const skeleton = (text = "Loading…", { preview = false } = {}) =>
  `<div class="skeleton${preview ? " preview" : ""}" role="status"><span></span><span></span><span></span><p>${esc(text)}</p></div>`;

// A page whose data didn't arrive: says what happened and offers another try, instead of staying blank.
export function errorState(el, err, retry, back) {
  const missing = err && err.status === 404;
  const actions = `${retry && !missing ? '<button type="button" class="btn" data-retry>Try again</button>' : ""}${back ? `<a class="btn btn-quiet" href="${esc(back.href)}">${esc(back.label)}</a>` : ""}`;
  el.innerHTML = emptyState({ title: missing ? "Not found" : "This didn't load", body: esc((err && err.message) || "Something went wrong."),
    actions, tag: el.tagName === "UL" ? "li" : "section", role: "alert" });
  el.querySelector("[data-retry]")?.addEventListener("click", () => retry());
}

// First load fails: the error state. Data already on screen stays, with a toast.
export function showLoadError(el, err, retry) {
  if (el.querySelector("section, .panel, table, li, .card")) toast(err.message, "bad");
  else errorState(el, err, retry);
}

// Half-typed forms: warn before the page goes away. Tracked per form: a page calls markSaved(form) once
// that form's work is safe (markSaved() for all of them); a form taken off the page no longer counts.
const unsaved = new Set();
export const markSaved = (form) => { if (form) unsaved.delete(form); else unsaved.clear(); };
export function guardLeaving() {
  document.addEventListener("input", (e) => {
    const form = e.target.closest("form");
    if (e.target.matches('input:not([type=checkbox]):not([type=radio]):not([type=search]), textarea') && form && !e.target.closest("dialog")) unsaved.add(form);
  });
  window.addEventListener("beforeunload", (e) => { if ([...unsaved].some((f) => f.isConnected)) { e.preventDefault(); e.returnValue = ""; } });
}

export async function boot({ page, admin = false }) {
  let me;
  try { me = await api("/api/auth/me"); } catch (e) {
    if (e.status !== 401) errorState(document.querySelector("main") || document.body, e, () => location.reload());
    return null;
  }
  if (!me) { location.href = "/login.html"; return null; }
  if (me.must_change_password && page !== "account") {
    location.href = "/account.html?first=1";
    return null;
  }
  // A link from an alert names its account (?acct=): open it there, not in whichever one was last chosen.
  const params = new URLSearchParams(location.search);
  const wanted = Number(params.get("acct"));
  if (wanted) {
    params.delete("acct");
    const clean = location.pathname + (params.toString() ? `?${params}` : "") + location.hash;
    if (me.owner && wanted !== me.account.id && (me.accounts || []).some((a) => a.id === wanted)) {
      try { await api("/api/accounts/switch", { method: "POST", body: { id: wanted } }); location.replace(clean); return null; }
      catch (e) { /* stay where we are */ }
    }
    history.replaceState(null, "", clean);
  }
  if (admin && me.role !== "admin") { location.href = "/home.html"; return null; }
  if (me.role === "client") document.documentElement.classList.add("read-only");
  if (me.role === "client" && me.account.clients_update_leads) document.documentElement.classList.add("client-leads");
  setCurrency(me.account.currency);
  // Meta's own terms carry their plain explanation from format.js (one wording everywhere).
  document.querySelectorAll("[data-explain]").forEach((el) => { el.textContent = explain(el.dataset.explain); });
  document.querySelectorAll(".money-input").forEach((el) => { if (el.firstChild && el.firstChild.nodeType === 3) el.firstChild.textContent = currencySymbol(); });
  window.ebadsMe = me;
  const isAdmin = me.role === "admin";
  const section = PAGE_SECTION[page] || page;
  frame = { page, section };
  const roleLabel = me.owner ? "Admin" : isAdmin ? `Admin · ${me.account.name}` : me.role === "client" ? "Client" : "Team member";
  const showAcct = (me.accounts || []).length > 1 || !me.owner;
  const allowed = (key) => !SECTIONS[key].admin || isAdmin;
  const groups = [["Work", ["today", "inbox", "leads"]], ["Run", ["ads", "insights", "claude"]]]
    .map(([label, keys]) => [label, keys.filter(allowed)]);
  const badge = (b) => b === "leads" ? '<span class="count bad" data-new-count hidden></span>'
    : b === "claude" ? '<span class="count claude" data-claude-count hidden></span>'
    : b === "inbox" ? '<span class="count" data-inbox-count hidden></span>' : "";
  const cur = (key) => key === section ? 'aria-current="page"' : "";
  const link = (key) => { const l = SECTIONS[key]; return `<a href="${l.href}" ${cur(key)}>${icon(l.icon)}<span class="label">${l.label}</span>${badge(l.badge)}</a>`; };
  const initials = me.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  const mac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

  const rail = document.querySelector(".rail");
  rail.innerHTML = `
    <a class="brand" href="/home.html"><img src="/img/favicon.svg" alt=""><span>Edge Bourne Ads</span></a>
    ${accountSwitch(me, "rail")}
    <button type="button" class="jump" data-palette>${icon("search")}<span>Search or jump to…</span><kbd>${mac ? "⌘" : "Ctrl "}K</kbd></button>
    <nav class="nav" aria-label="Main">
      ${groups.map(([label, keys]) => `<div class="nav-group"><span class="nav-label">${label}</span>${keys.map(link).join("")}</div>`).join("")}
    </nav>
    <div class="rail-foot">
      ${isAdmin ? `<a class="setlink" href="/settings.html" ${cur("settings")}>${icon("settings")}<span>Settings</span></a>` : ""}
      ${isAdmin ? '<a class="cap-card" id="cap-card" href="/performance.html" hidden></a>' : ""}
      <a class="me" href="/account.html" ${cur("account")}>
        <span class="avatar" aria-hidden="true">${esc(initials)}</span>
        <span class="who"><b>${esc(me.name)}</b><small>${esc(roleLabel)}</small></span>
      </a>
      <div class="rail-actions">
        <button type="button" data-theme-btn>${themeLabel(currentTheme())}</button>
        <button type="button" data-signout>Sign out</button>
      </div>
    </div>`;

  const main = document.querySelector(".main");
  // Skip link: the first stop for the keyboard, past the sidebar to the page. It focuses the page without
  // touching the hash, which several pages use for their own state (#tab=, #lead=, #r/…).
  if (!main.id) main.id = "main";
  const skip = document.createElement("a");
  skip.className = "skip-link";
  skip.href = `#${main.id}`;
  skip.textContent = "Skip to the page";
  skip.addEventListener("click", (e) => {
    e.preventDefault();
    main.tabIndex = -1;  // only while it holds focus: a click on empty space shouldn't focus the page
    main.addEventListener("blur", () => main.removeAttribute("tabindex"), { once: true });
    main.focus({ preventScroll: true });
    main.scrollIntoView({ block: "start" });
  });
  document.body.prepend(skip);
  const line = document.createElement("div");
  line.className = "topline";
  line.innerHTML = `<nav class="crumbs" aria-label="Breadcrumb"></nav><span class="grow"></span>${refreshButton()}`;
  main.prepend(line);
  const canSee = (who) => who === "all" || isAdmin || (who === "report" && me.role === "client");
  const tabsFor = (SUBNAV[section] || []).filter(([, , who]) => canSee(who));
  if (tabsFor.length > 1 && tabsFor.some(([p]) => p === page)) {
    const sub = document.createElement("nav");
    sub.className = "subnav";
    sub.setAttribute("aria-label", SECTIONS[section].label);
    sub.innerHTML = tabsFor.map(([p, label]) => `<a href="${PAGE_HREF[p]}" ${p === page ? 'aria-current="page"' : ""}>${label}</a>`).join("");
    line.after(sub);
  }

  const app = document.querySelector(".app");
  const top = document.createElement("header");
  top.className = "topbar";
  top.innerHTML = `<a class="crumb-up" href="${SECTIONS[section]?.href || "/home.html"}" aria-label="Back" hidden>${icon("back")}</a>
    <a class="brand" href="/home.html"><img src="/img/favicon.svg" alt="Edge Bourne"><span>${esc(PAGE_TITLE[page] || "Edge Bourne Ads")}${showAcct ? `<small class="top-acct">${esc(me.account.name)}</small>` : ""}</span></a>
    <button type="button" class="icon-btn" data-palette aria-label="Search">${icon("search")}</button>
    <button type="button" class="icon-btn" data-refresh aria-label="Refresh">${icon("refresh")}</button>
    <a class="icon-btn" href="/account.html" aria-label="Your account"><span class="avatar">${esc(initials)}</span></a>`;
  app.prepend(top);
  if (isAdmin) startClaudeNow(top);
  const sectionCrumb = SECTIONS[section] ? { label: SECTIONS[section].label, href: SECTIONS[section].href } : null;
  const own = PAGE_TITLE[page];
  setCrumbs(sectionCrumb && own && own !== sectionCrumb.label ? [sectionCrumb, { label: own, href: location.pathname }] : [sectionCrumb || { label: own || "", href: location.pathname }]);

  const tabKeys = ["today", "leads", "ads", "inbox"];
  const moreKeys = ["insights", "claude", "settings"].filter(allowed);
  const inMore = !tabKeys.includes(section);
  const tabs = document.createElement("nav");
  tabs.className = "tabbar";
  tabs.setAttribute("aria-label", "Main");
  tabs.innerHTML = `${tabKeys.map((k) => { const l = SECTIONS[k]; return `<a href="${l.href}" ${cur(k)}>${icon(l.icon)}<span>${l.label}</span>${badge(l.badge)}</a>`; }).join("")}
    <button type="button" data-more ${inMore ? 'aria-current="page"' : ""}>${icon("menu")}<span>More</span></button>`;
  app.append(tabs);

  const sheet = document.createElement("dialog");
  sheet.className = "sheet";
  sheet.setAttribute("aria-label", "More");
  sheet.innerHTML = `<div class="grab"></div>${accountSwitch(me, "sheet")}<nav>
      ${moreKeys.map((k) => { const l = SECTIONS[k]; return `<a href="${l.href}" ${cur(k)}>${icon(l.icon)}${l.label}${badge(l.badge)}</a>`; }).join("")}
      ${(SUBNAV.insights).filter(([p, , who]) => p !== "performance" && canSee(who)).map(([p, label]) => `<a href="${PAGE_HREF[p]}" ${p === page ? 'aria-current="page"' : ""}>${icon(p === "compare" ? "compare" : p === "experiments" ? "tests" : "table")}${label}</a>`).join("")}
      <a href="/account.html" ${cur("account")}>${icon("user")}Your account</a>
      <div class="sep"></div>
      <button type="button" class="item" data-theme-btn>${icon("moon")}<span>${themeLabel(currentTheme())}</span></button>
      <button type="button" class="item" data-signout>${icon("logout")}Sign out</button>
    </nav>`;
  document.body.append(sheet);
  tabs.querySelector("[data-more]").addEventListener("click", () => sheet.showModal());
  sheet.addEventListener("click", (e) => { if (e.target === sheet) sheet.close(); });

  document.querySelectorAll("[data-refresh]").forEach((b) => b.addEventListener("click", doRefresh));
  document.querySelectorAll("[data-palette]").forEach((b) => b.addEventListener("click", () => openPalette()));
  document.querySelectorAll("[data-theme-btn]").forEach((b) => b.addEventListener("click", () => {
    applyTheme(THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length]);
  }));
  document.querySelectorAll("[data-signout]").forEach((b) => b.addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST" });
    location.href = "/login.html";
  }));
  shortcuts(isAdmin);

  banners(me);
  catchUp();
  setInterval(paintUpdated, 30000);
  setInterval(catchUp, 60000);
  document.addEventListener("visibilitychange", catchUp);
  return me;
}

// ⌘K / Ctrl+K or "/" opens the palette; "g" then a letter jumps to a section.
const JUMPS = { t: "/home.html", i: "/inbox.html", l: "/leads.html", a: "/ads.html", n: "/performance.html", c: "/desk.html", s: "/settings.html" };
function typing(el) { return el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)); }
function shortcuts(isAdmin) {
  let g = 0;
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); return; }
    if (typing(e.target) || e.metaKey || e.ctrlKey || e.altKey || document.querySelector("dialog[open]")) return;
    if (e.key === "/") { e.preventDefault(); openPalette(); return; }
    if (e.key === "g") { g = Date.now(); return; }
    if (g && Date.now() - g < 1200 && JUMPS[e.key]) {
      if (!isAdmin && (e.key === "c" || e.key === "s")) return;
      e.preventDefault(); location.href = JUMPS[e.key];
    }
    g = 0;
  });
}

let paletteMod = null;
export async function openPalette(query = "") {
  paletteMod = paletteMod || await import("./palette.js");
  paletteMod.open({ query, me: window.ebadsMe, pages: { SECTIONS, PAGE_HREF, PAGE_TITLE } });
}

// Things an admin must know on every page: the background worker stopped, or Meta refused the token.
function banners(me) {
  const items = [];
  if (me.worker_stale) items.push(`<b>The console's background work has stopped</b> (new leads, alerts and automatic refresh wait). Run Update on the server, or ask for help.`);
  if (me.meta_token_error) items.push(`<b>Meta stopped accepting the access token</b> on ${esc(me.meta_token_error.slice(0, 10))}. Paste a new System User token in <a href="/settings.html#meta-form">Settings → Meta</a>.`);
  if (me.bridge_outdated) items.push(`<b>The Mac helper is out of date</b> (version ${esc(me.bridge_outdated)}). Re-run <code>ads/bridge/install.sh</code> on the Mac so Claude works on the right account.`);
  if (me.claude_sign_in_failed) items.push(`<b>Claude can't sign in on your Mac</b> (its sign-in expired), so Claude can't work on anything. On the Mac run <code>claude setup-token</code> and store it again with <code>ads/bridge/install.sh</code>.`);
  if (!items.length) return;
  const box = document.createElement("div");
  box.className = "sys-banners";
  box.setAttribute("role", "alert");
  box.innerHTML = items.map((t) => `<p class="note bad">${t}</p>`).join("");
  const main = document.querySelector("main") || document.querySelector(".app");
  main.prepend(box);
}

// What Claude is doing, on every page: a line in the sidebar, and a bar under the phone's top bar
// while there is anything going on.
let paintClaudeNow = null;
export const refreshClaudeNow = () => { if (paintClaudeNow) paintClaudeNow(); };

function startClaudeNow(top) {
  const card = document.createElement("a");
  card.className = "claude-now";
  document.querySelector(".rail-foot")?.prepend(card);
  const bar = document.createElement("a");
  bar.className = "claude-now-bar";
  bar.hidden = true;
  top.after(bar);
  let since = null;
  const tick = () => {
    if (!since) return;
    const s = Math.max(0, Math.floor((Date.now() - since) / 1000));
    document.querySelectorAll("[data-now-clock]").forEach((el) => { el.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; });
  };
  paintClaudeNow = async () => {
    let n;
    try { n = await (await fetch("/api/desk/now", { credentials: "same-origin" })).json(); } catch (e) { return; }
    if (!n || n.error) return;
    const w = n.working;
    since = w ? new Date(w.since).getTime() : null;
    const state = w ? "working" : n.queued ? "waiting" : "idle";
    const title = w ? 'Claude working <time data-now-clock></time>' : n.queued || !n.online ? (n.online ? "Claude is starting the next one" : "Your Mac is offline") : "Claude is idle";
    const detail = w ? esc(w.progress || w.title) : n.queued ? esc(n.next[0]?.title || "") : n.online ? "Nothing in line" : "Anything you ask waits until it’s back";
    const line = n.queued ? `<em>${n.queued} in line</em>` : "";
    const href = w ? `/desk.html#r/${w.thread}` : "/desk.html#list";
    [card, bar].forEach((el) => {
      el.href = href;
      el.dataset.state = state;
      el.innerHTML = `<span class="claude-now-dot" aria-hidden="true"></span><span class="claude-now-text"><b>${title}</b><small>${detail}</small></span>${line}`;
    });
    bar.hidden = state === "idle";
    tick();
  };
  paintClaudeNow();
  setInterval(() => { if (!document.hidden) paintClaudeNow(); }, 10000);
  setInterval(tick, 1000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) paintClaudeNow(); });
}

export function setNewCount(n) {
  document.querySelectorAll("[data-new-count]").forEach((el) => {
    el.hidden = !n;
    el.textContent = n;
    el.setAttribute("aria-label", `${n} new`);
  });
}

// A field's own error: marked invalid for screen readers and tied to its message (aria-describedby keeps
// the field's hint too). fieldError(form) clears every error in the form.
let errSeq = 0;
export function fieldError(form, name, message) {
  form.querySelectorAll(".field.error").forEach((f) => f.classList.remove("error"));
  form.querySelectorAll('[aria-invalid="true"]').forEach((el) => {
    el.removeAttribute("aria-invalid");
    const rest = (el.getAttribute("aria-describedby") || "").split(" ").filter((id) => id && !id.startsWith("ferr-")).join(" ");
    if (rest) el.setAttribute("aria-describedby", rest); else el.removeAttribute("aria-describedby");
  });
  form.querySelectorAll(".field .err").forEach((e) => e.remove());
  if (!name) return;
  const input = form.querySelector(`[name="${name}"]`);
  const field = input && input.closest(".field");
  if (!field) return;
  field.classList.add("error");
  const err = document.createElement("div");
  err.className = "err";
  err.id = `ferr-${++errSeq}`;
  err.textContent = message;
  field.appendChild(err);
  input.setAttribute("aria-invalid", "true");
  input.setAttribute("aria-describedby", [input.getAttribute("aria-describedby"), err.id].filter(Boolean).join(" "));
  input.focus();
}

// ---------- confirm dialog ----------
// confirmDialog({ title, body (HTML), confirm, danger, field }) → Promise<false | true | field value>.
// `field` = { label, value, prefix, suffix, inputmode, validate(v) → error|null, hint(v) → html } adds one input.
// `cancel: false` makes it a notice with one button (nothing to decide, e.g. a password shown once).
export function confirmDialog({ title, body = "", confirm = "Confirm", danger = false, claude = false, field = null, cancel = "Cancel" }) {
  return new Promise((resolve) => {
    const dlg = document.createElement("dialog");
    dlg.className = "confirm";
    dlg.innerHTML = `<form method="dialog" novalidate>
      <h2>${esc(title)}</h2>
      ${body ? `<div class="confirm-body">${body}</div>` : ""}
      ${field ? `<div class="field"><label for="cd-input">${esc(field.label)}</label>
        <div class="affix">${field.prefix ? `<span>${esc(field.prefix)}</span>` : ""}<input class="input" id="cd-input" inputmode="${field.inputmode || "text"}" value="${esc(field.value ?? "")}" autocomplete="off" aria-describedby="cd-hint">${field.suffix ? `<span>${esc(field.suffix)}</span>` : ""}</div>
        <span class="hint" id="cd-hint" aria-live="polite"></span><span class="err" id="cd-err" role="alert" hidden></span></div>` : ""}
      <div class="row end">${cancel ? `<button class="btn" type="button" value="cancel" id="cd-cancel">${esc(cancel)}</button>` : ""}
        <button class="btn ${danger ? "btn-danger" : claude ? "btn-claude" : "btn-primary"}" type="submit" id="cd-ok">${esc(confirm)}</button></div>
    </form>`;
    document.body.appendChild(dlg);
    const input = dlg.querySelector("#cd-input");
    const hint = dlg.querySelector("#cd-hint");
    const err = dlg.querySelector("#cd-err");
    const refresh = () => { if (field && field.hint) hint.innerHTML = field.hint(input.value); };
    const invalid = (on) => {
      if (on) { input.setAttribute("aria-invalid", "true"); input.setAttribute("aria-describedby", "cd-hint cd-err"); }
      else { input.removeAttribute("aria-invalid"); input.setAttribute("aria-describedby", "cd-hint"); }
    };
    if (input) { input.addEventListener("input", () => { err.hidden = true; invalid(false); refresh(); }); refresh(); }
    let result = false;
    dlg.querySelector("#cd-cancel")?.addEventListener("click", () => dlg.close());
    dlg.querySelector("form").addEventListener("submit", (e) => {
      if (field) {
        const problem = field.validate ? field.validate(input.value) : null;
        if (problem) { e.preventDefault(); err.textContent = problem; err.hidden = false; invalid(true); input.focus(); return; }
        result = input.value;
      } else result = true;
    });
    dlg.addEventListener("close", () => { dlg.remove(); resolve(result); });
    dlg.showModal();
    // Safe default: a stray Enter or Space never confirms. With a field, focus is on it (typing is deliberate);
    // otherwise on Cancel, never on the button that acts.
    (input || dlg.querySelector("#cd-cancel") || dlg.querySelector("#cd-ok")).focus();
    if (input) input.select();
  });
}

// An on/off switch. data-* attributes say what it controls.
export const switchHtml = (on, attrs, label) =>
  `<button type="button" class="switch" role="switch" aria-checked="${on ? "true" : "false"}" aria-label="${esc(label)}" ${attrs}><span></span></button>`;

// Meta's previews take a few seconds and the iframe is blank white until then: keep the
// skeleton up until the frame has loaded, and offer a new tab if Meta is slow.
export const previewSkeleton = () => skeleton("Loading Meta's preview…", { preview: true });

export function showPreviewFrame(box, p, { title, width, height }) {
  const frame = document.createElement("iframe");
  frame.title = title;
  frame.referrerPolicy = "no-referrer";
  frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-popups");
  if (width) frame.style.width = `${width}px`;
  frame.style.height = `${height}px`;
  frame.className = "preview-loading";
  const slow = setTimeout(() => {
    const note = box.querySelector(".skeleton p");
    if (note) note.innerHTML = `Meta is slow to answer. <a href="${p.src}" target="_blank" rel="noopener noreferrer">Open the preview in a new tab</a>`;
  }, 12000);
  frame.addEventListener("load", () => {
    clearTimeout(slow);
    frame.classList.remove("preview-loading");
    box.querySelector(".skeleton")?.remove();
  }, { once: true });
  box.innerHTML = previewSkeleton();
  box.append(frame);
  frame.src = p.src;
  return frame;
}
