// Shared UI: app frame, icons, toasts, formatting.
import { api } from "./api.js";

const ICONS = {
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
  user: '<circle cx="12" cy="8.5" r="3.8" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M4.5 20c1-3.6 4-5.5 7.5-5.5s6.5 1.9 7.5 5.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
};
export const icon = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ""}</svg>`;

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let toastTimer;
export function toast(message, kind = "") {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    el.setAttribute("role", "status");
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.className = "toast " + kind;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), kind === "bad" ? 6000 : 3000);
}

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
export function applyTheme(t) {
  if (t === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
  try { localStorage.setItem("ebads-theme", t); } catch (e) {}
}
const themeLabel = (t) => ({ system: "Theme: auto", light: "Theme: light", dark: "Theme: dark" }[t]);

// ---------- frame ----------
// Desktop: light sidebar. Phone: top bar + bottom tab bar + "More" sheet.
// Every page gets the Refresh control; a page hands its reload to onRefresh(fn).
let refreshHandler = null;
let updatedAt = null;
let shownAt = null; // the updated_at the page's data was last loaded at
let autoMinutes = null;
let clockSkew = 0;
export function onRefresh(fn) { refreshHandler = fn; }

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
function editing() {
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
  if (first || !refreshHandler) return;
  try { await refreshHandler(); } catch (e) { /* the next manual refresh shows the error */ }
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
    if (refreshHandler) await refreshHandler(); else location.reload();
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
    const cap = st.cap;
    const card = document.getElementById("cap-card");
    if (card && cap && cap.limit_cents) {
      const used = Math.min(cap.spent_cents / cap.limit_cents, 1);
      const $$ = (c) => { const d = c % 100 ? 2 : 0; return `$${(c / 100).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })}`; };
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
  return `<button type="button" class="refresh" data-refresh title="Get the latest from Meta">${icon("refresh")}<span class="r-text"><b>Refresh</b><small data-updated>…</small></span></button>`;
}

export async function boot({ page, admin = false }) {
  let me;
  try { me = await api("/api/auth/me"); } catch (e) { return null; }
  if (!me) { location.href = "/login.html"; return null; }
  if (me.must_change_password && page !== "account") {
    location.href = "/account.html?first=1";
    return null;
  }
  if (admin && me.role !== "admin") { location.href = "/home.html"; return null; }
  const isAdmin = me.role === "admin";
  const main = [
    { id: "home", href: "/home.html", label: "Today", icon: "sun" },
    { id: "leads", href: "/leads.html", label: "Leads", icon: "leads", badge: "leads" },
    { id: "ads", href: "/ads.html", label: "Ads", icon: "ads" },
    { id: "performance", href: "/performance.html", label: "Results", icon: "chart" },
  ];
  const extra = isAdmin ? [
    { id: "experiments", href: "/experiments.html", label: "Tests", icon: "tests" },
    { id: "desk", href: "/desk.html", label: "Claude", icon: "spark", badge: "claude" },
    { id: "research", href: "/research.html", label: "Research", icon: "research" },
  ] : [];
  const admin2 = isAdmin ? [
    { id: "team", href: "/team.html", label: "Team", icon: "team" },
    { id: "settings", href: "/settings.html", label: "Settings", icon: "settings" },
  ] : [];
  const badge = (b) => b === "leads" ? '<span class="count" data-new-count hidden></span>'
    : b === "claude" ? '<span class="count claude" data-claude-count hidden></span>' : "";
  const link = (l) => `<a href="${l.href}" ${l.id === page ? 'aria-current="page"' : ""}>${icon(l.icon)}<span class="label">${l.label}</span>${badge(l.badge)}</a>`;
  const initials = me.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();

  const rail = document.querySelector(".rail");
  rail.innerHTML = `
    <a class="brand" href="/home.html"><img src="/img/favicon.svg" alt=""><span>Edge Bourne Ads</span></a>
    <nav class="nav" aria-label="Main">
      ${[...main, ...extra].map(link).join("")}
      ${admin2.length ? `<div class="sep" role="separator"></div>${admin2.map(link).join("")}` : ""}
    </nav>
    <div class="rail-foot">
      ${isAdmin ? '<a class="cap-card" id="cap-card" href="/performance.html" hidden></a>' : ""}
      <a class="me" href="/account.html" ${page === "account" ? 'aria-current="page"' : ""}>
        <span class="avatar" aria-hidden="true">${esc(initials)}</span>
        <span class="who"><b>${esc(me.name)}</b><small>${isAdmin ? "Admin" : "Team member"}</small></span>
      </a>
      <div class="rail-actions">
        <button type="button" data-theme-btn>${themeLabel(currentTheme())}</button>
        <button type="button" data-signout>Sign out</button>
      </div>
    </div>`;

  const app = document.querySelector(".app");
  const titles = { home: "Today", leads: "Leads", ads: "Ads", ad: "Ad", "new-ad": "New ad", performance: "Results", experiments: "Tests", desk: "Claude", research: "Research", team: "Team", settings: "Settings", account: "Your account" };
  const top = document.createElement("header");
  top.className = "topbar";
  top.innerHTML = `<a class="brand" href="/home.html"><img src="/img/favicon.svg" alt="Edge Bourne"><span>${esc(titles[page] || "Edge Bourne Ads")}</span></a>
    <button type="button" class="icon-btn" data-refresh>${icon("refresh")}</button>
    <a class="icon-btn" href="/account.html" aria-label="Your account"><span class="avatar">${esc(initials)}</span></a>`;
  app.prepend(top);

  const inMore = [...extra, ...admin2].some((l) => l.id === page) || page === "account";
  const tabs = document.createElement("nav");
  tabs.className = "tabbar";
  tabs.setAttribute("aria-label", "Main");
  tabs.innerHTML = `${main.map((l) => `<a href="${l.href}" ${l.id === page || (l.id === "ads" && (page === "ad" || page === "new-ad")) ? 'aria-current="page"' : ""}>${icon(l.icon)}<span>${l.label}</span>${l.badge === "leads" ? '<span class="count" data-new-count hidden></span>' : ""}</a>`).join("")}
    <button type="button" data-more ${inMore ? 'aria-current="page"' : ""}>${icon("menu")}<span>More</span></button>`;
  app.append(tabs);

  const sheet = document.createElement("dialog");
  sheet.className = "sheet";
  sheet.setAttribute("aria-label", "More");
  sheet.innerHTML = `<div class="grab"></div><nav>
      ${[...extra, ...admin2].map((l) => `<a href="${l.href}" ${l.id === page ? 'aria-current="page"' : ""}>${icon(l.icon)}${l.label}${badge(l.badge)}</a>`).join("")}
      <a href="/account.html" ${page === "account" ? 'aria-current="page"' : ""}>${icon("user")}Your account</a>
      <div class="sep"></div>
      <button type="button" class="item" data-theme-btn>${icon("moon")}<span>${themeLabel(currentTheme())}</span></button>
      <button type="button" class="item" data-signout>${icon("logout")}Sign out</button>
    </nav>`;
  document.body.append(sheet);
  tabs.querySelector("[data-more]").addEventListener("click", () => sheet.showModal());
  sheet.addEventListener("click", (e) => { if (e.target === sheet) sheet.close(); });

  // Refresh: in the page header on desktop, in the top bar on phones.
  const head = document.querySelector(".page-head");
  if (head && !head.querySelector(".refresh")) {
    const spacer = head.querySelector(".spacer");
    const tmp = document.createElement("div");
    tmp.innerHTML = refreshButton();
    if (spacer) spacer.after(tmp.firstElementChild);
    else { const sp = document.createElement("span"); sp.className = "spacer"; head.append(sp, tmp.firstElementChild); }
  }
  document.querySelectorAll("[data-refresh]").forEach((b) => b.addEventListener("click", doRefresh));

  document.querySelectorAll("[data-theme-btn]").forEach((b) => b.addEventListener("click", () => {
    const next = THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length];
    applyTheme(next);
    document.querySelectorAll("[data-theme-btn]").forEach((x) => {
      const span = x.querySelector("span");
      (span || x).textContent = themeLabel(next);
    });
  }));
  document.querySelectorAll("[data-signout]").forEach((b) => b.addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST" });
    location.href = "/login.html";
  }));

  catchUp();
  setInterval(paintUpdated, 30000);
  setInterval(catchUp, 60000);
  document.addEventListener("visibilitychange", catchUp);
  return me;
}

export function setNewCount(n) {
  document.querySelectorAll("[data-new-count]").forEach((el) => {
    el.hidden = !n;
    el.textContent = n;
    el.setAttribute("aria-label", `${n} new`);
  });
}

export function fieldError(form, name, message) {
  form.querySelectorAll(".field.error").forEach((f) => f.classList.remove("error"));
  form.querySelectorAll(".field .err").forEach((e) => e.remove());
  if (!name) return;
  const input = form.querySelector(`[name="${name}"]`);
  const field = input && input.closest(".field");
  if (!field) return;
  field.classList.add("error");
  const err = document.createElement("div");
  err.className = "err";
  err.textContent = message;
  field.appendChild(err);
  input.focus();
}

// ---------- confirm dialog ----------
// confirmDialog({ title, body (HTML), confirm, danger, field }) → Promise<false | true | field value>.
// `field` = { label, value, prefix, suffix, inputmode, validate(v) → error|null, hint(v) → html } adds one input.
export function confirmDialog({ title, body = "", confirm = "Confirm", danger = false, claude = false, field = null }) {
  return new Promise((resolve) => {
    const dlg = document.createElement("dialog");
    dlg.className = "confirm";
    dlg.innerHTML = `<form method="dialog" novalidate>
      <h2>${esc(title)}</h2>
      ${body ? `<div class="confirm-body">${body}</div>` : ""}
      ${field ? `<div class="field"><label for="cd-input">${esc(field.label)}</label>
        <div class="affix">${field.prefix ? `<span>${esc(field.prefix)}</span>` : ""}<input class="input" id="cd-input" inputmode="${field.inputmode || "text"}" value="${esc(field.value ?? "")}" autocomplete="off">${field.suffix ? `<span>${esc(field.suffix)}</span>` : ""}</div>
        <span class="hint" id="cd-hint"></span><span class="err" id="cd-err" hidden></span></div>` : ""}
      <div class="row end"><button class="btn" type="button" value="cancel" id="cd-cancel">Cancel</button>
        <button class="btn ${danger ? "btn-danger" : claude ? "btn-claude" : "btn-primary"}" type="submit" id="cd-ok">${esc(confirm)}</button></div>
    </form>`;
    document.body.appendChild(dlg);
    const input = dlg.querySelector("#cd-input");
    const hint = dlg.querySelector("#cd-hint");
    const err = dlg.querySelector("#cd-err");
    const refresh = () => { if (field && field.hint) hint.innerHTML = field.hint(input.value); };
    if (input) { input.addEventListener("input", () => { err.hidden = true; refresh(); }); refresh(); }
    let result = false;
    dlg.querySelector("#cd-cancel").addEventListener("click", () => dlg.close());
    dlg.querySelector("form").addEventListener("submit", (e) => {
      if (field) {
        const problem = field.validate ? field.validate(input.value) : null;
        if (problem) { e.preventDefault(); err.textContent = problem; err.hidden = false; input.focus(); return; }
        result = input.value;
      } else result = true;
    });
    dlg.addEventListener("close", () => { dlg.remove(); resolve(result); });
    dlg.showModal();
    (input || dlg.querySelector("#cd-ok")).focus();
    if (input) input.select();
  });
}

// An on/off switch. data-* attributes say what it controls.
export const switchHtml = (on, attrs, label) =>
  `<button type="button" class="switch" role="switch" aria-checked="${on ? "true" : "false"}" aria-label="${esc(label)}" ${attrs}><span></span></button>`;

// Meta's previews take a few seconds and the iframe is blank white until then: keep the
// skeleton up until the frame has loaded, and offer a new tab if Meta is slow.
const SKELETON = (text) => `<div class="preview-skeleton" role="status"><span></span><span></span><span></span><p>${text}</p></div>`;
export const previewSkeleton = () => SKELETON("Loading Meta's preview…");

export function showPreviewFrame(box, p, { title, width, height }) {
  const frame = document.createElement("iframe");
  frame.title = title;
  frame.referrerPolicy = "no-referrer";
  frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-popups");
  if (width) frame.style.width = `${width}px`;
  frame.style.height = `${height}px`;
  frame.className = "preview-loading";
  const slow = setTimeout(() => {
    const note = box.querySelector(".preview-skeleton p");
    if (note) note.innerHTML = `Meta is slow to answer. <a href="${p.src}" target="_blank" rel="noopener noreferrer">Open the preview in a new tab</a>`;
  }, 12000);
  frame.addEventListener("load", () => {
    clearTimeout(slow);
    frame.classList.remove("preview-loading");
    box.querySelector(".preview-skeleton")?.remove();
  }, { once: true });
  box.innerHTML = previewSkeleton();
  box.append(frame);
  frame.src = p.src;
  return frame;
}
