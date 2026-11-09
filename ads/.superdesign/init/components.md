# Shared UI components (vanilla JS template strings + CSS classes, no framework)

Framework: none. Static HTML pages + ES module JS rendering HTML strings into containers. CSS: one file, frontend/css/app.css (tokens + classes). Strict CSP: no inline style attributes (widths set from JS via data-w).

## `frontend/js/ui.js`
```js
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
  play: '<path d="M8 5.5v13l10.5-6.5z" fill="currentColor"/>',
  plus: '<path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  copy: '<rect x="8.5" y="8.5" width="11" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M15.5 5.5V5a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 5v8A1.5 1.5 0 0 0 6 14.5h.5" fill="none" stroke="currentColor" stroke-width="1.8"/>',
  external: '<path d="M14 4.5h5.5V10M19.5 4.5L11 13M17 14v4.5a1 1 0 0 1-1 1H5.5a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1H10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  upload: '<path d="M12 15.5V4.5M7.5 9L12 4.5 16.5 9M4.5 15v3.5a1 1 0 0 0 1 1h13a1 1 0 0 0 1-1V15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  image: '<rect x="3.5" y="4.5" width="17" height="15" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="9" cy="10" r="1.8" fill="currentColor"/><path d="M4 17l5-4.5 4 3.5 3-2.5 4.5 3.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
  table: '<path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  grid: '<rect x="4" y="4" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="13" y="4" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="4" y="13" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/><rect x="13" y="13" width="7" height="7" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.8"/>',
  back: '<path d="M14.5 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
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
export async function boot({ page, admin = false }) {
  let me;
  try { me = await api("/api/auth/me"); } catch (e) { return null; }
  if (!me) { location.href = "/login.html"; return null; }
  if (me.must_change_password && page !== "account") {
    location.href = "/account.html?first=1";
    return null;
  }
  if (admin && me.role !== "admin") { location.href = "/home.html"; return null; }
  const links = [
    { id: "home", href: "/home.html", label: "Home", icon: "home" },
    { id: "leads", href: "/leads.html", label: "Leads", icon: "leads" },
    { id: "ads", href: "/ads.html", label: "Ads", icon: "ads" },
    { id: "performance", href: "/performance.html", label: "Performance", icon: "chart" },
    ...(me.role === "admin" ? [
      { id: "desk", href: "/desk.html", label: "Desk", icon: "spark" },
      { id: "research", href: "/research.html", label: "Research", icon: "research" },
      { id: "team", href: "/team.html", label: "Team", icon: "team" },
      { id: "settings", href: "/settings.html", label: "Settings", icon: "settings" },
    ] : []),
  ];
  const rail = document.querySelector(".rail");
  const initials = me.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  rail.innerHTML = `
    <a class="brand" href="/home.html"><img src="/img/favicon.svg" alt=""><span>Edge Bourne Ads</span></a>
    <nav class="nav" aria-label="Main">
      ${links.map((l) => `<a href="${l.href}" ${l.id === page ? 'aria-current="page"' : ""}>${icon(l.icon)}<span class="label">${l.label}</span>${l.id === "leads" ? '<span class="count" id="nav-new" hidden></span>' : ""}</a>`).join("")}
    </nav>
    <div class="rail-foot">
      <a class="me" href="/account.html" ${page === "account" ? 'aria-current="page"' : ""}>
        <span class="avatar" aria-hidden="true">${esc(initials)}</span>
        <span class="who"><b>${esc(me.name)}</b><small>${me.role === "admin" ? "Admin" : "Team member"}</small></span>
      </a>
      <div class="rail-actions">
        <button type="button" id="theme-btn">${themeLabel(currentTheme())}</button>
        <button type="button" id="signout-btn">Sign out</button>
      </div>
    </div>`;
  document.getElementById("theme-btn").addEventListener("click", (e) => {
    const next = THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length];
    applyTheme(next);
    e.currentTarget.textContent = themeLabel(next);
  });
  document.getElementById("signout-btn").addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST" });
    location.href = "/login.html";
  });
  return me;
}

export function setNewCount(n) {
  const el = document.getElementById("nav-new");
  if (!el) return;
  el.hidden = !n;
  el.textContent = n;
  el.setAttribute("aria-label", `${n} new`);
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
```

## `frontend/js/format.js`
```js
// Number and date formatting shared by every page.
export const money = (cents, { exact = false } = {}) => {
  const v = (cents || 0) / 100;
  const digits = exact || Math.abs(v) < 100 ? 2 : 0;
  return v.toLocaleString(undefined, { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits });
};
export const count = (n) => Number(n || 0).toLocaleString();
export const per = (cents, n) => (n ? money(cents / n, { exact: true }) : "—");
export const pct = (a, b) => (b ? `${((a / b) * 100).toFixed(2)}%` : "—");
export const dayLabel = (iso) => new Date(iso + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" });
export const plural = (n, word, many = word + "s") => `${count(n)} ${n === 1 ? word : many}`;

export const CTA_LABELS = {
  BOOK_TRAVEL: "Book now", SIGN_UP: "Sign up", LEARN_MORE: "Learn more", GET_QUOTE: "Get quote",
  APPLY_NOW: "Apply now", SUBSCRIBE: "Subscribe", DOWNLOAD: "Download", CONTACT_US: "Contact us",
};

// Meta's effective_status → [pill class, words people use].
export const STATUS = {
  ACTIVE: ["ok", "On"], PAUSED: ["", "Off"], CAMPAIGN_PAUSED: ["", "Off (campaign is off)"],
  ADSET_PAUSED: ["", "Off (ad set is off)"], IN_PROCESS: ["warn", "In review"], PENDING_REVIEW: ["warn", "In review"],
  DISAPPROVED: ["bad", "Rejected"], WITH_ISSUES: ["bad", "Has issues"], ARCHIVED: ["", "Archived"],
  PENDING_BILLING_INFO: ["bad", "Needs billing"], DELETED: ["", "Deleted"],
};
export const statusOf = (s) => STATUS[s] || ["", (s || "Unknown").replace(/_/g, " ").toLowerCase()];
```

## `frontend/js/charts.js`
```js
// Column charts (one measure per chart, rounded data-ends, tooltips). Colors come
// from CSS variables validated with the dataviz palette checker.
import { esc } from "./ui.js";
import { dayLabel } from "./format.js";

// Clean tick steps (1, 2, 2.5, 5 × 10^n) so the axis reads in round numbers.
export function niceMax(max, ticks = 4, integer = false) {
  if (max <= 0) return { top: ticks, step: 1 };
  const raw = max / ticks;
  const mag = 10 ** Math.floor(Math.log10(raw));
  let step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
  if (integer) step = Math.max(1, Math.ceil(step));
  return { top: step * Math.ceil(max / step), step };
}

export function columnChart({ el, series, key, color, format, axisFormat, title, integer = false, height = 220 }) {
  const W = 560, H = height, L = 52, R = 8, T = 10, B = 26;
  const values = series.map((d) => d[key]);
  const { top, step } = niceMax(Math.max(...values, 0), 4, integer);
  const plotW = W - L - R, plotH = H - T - B;
  const band = plotW / series.length;
  const bw = Math.min(24, Math.max(3, band - 2));
  const y = (v) => T + plotH - (v / top) * plotH;
  let grid = "", ticks = "";
  for (let v = 0; v <= top + 1e-9; v += step) {
    grid += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`;
    ticks += `<text class="tick" x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${axisFormat(v)}</text>`;
  }
  const every = Math.ceil(series.length / 6);
  const cols = series.map((d, i) => {
    const x = L + i * band + (band - bw) / 2;
    const h = (d[key] / top) * plotH;
    const r = Math.min(4, h);
    const path = h <= 0 ? "" : `M${x},${T + plotH} V${T + plotH - h + r} Q${x},${T + plotH - h} ${x + r},${T + plotH - h} H${x + bw - r} Q${x + bw},${T + plotH - h} ${x + bw},${T + plotH - h + r} V${T + plotH} Z`;
    const label = i % every === 0 || i === series.length - 1 ? `<text class="tick" x="${L + i * band + band / 2}" y="${H - 6}" text-anchor="middle">${dayLabel(d.day)}</text>` : "";
    return `<rect class="hit" data-i="${i}" x="${L + i * band}" y="${T}" width="${band}" height="${plotH}"/><path class="col" d="${path}" fill="${color}"/>${label}`;
  }).join("");
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}"><g class="grid">${grid}</g>${ticks}${cols}</svg><div class="tip" hidden></div>`;
  el.querySelector("svg").style.height = `${H}px`;
  const tip = el.querySelector(".tip");
  const svg = el.querySelector("svg");
  el.querySelectorAll(".hit").forEach((hit) => {
    hit.addEventListener("mouseenter", () => {
      const i = Number(hit.dataset.i);
      const d = series[i];
      const scale = svg.getBoundingClientRect().width / W;
      tip.innerHTML = `${format(d[key])}<small>${dayLabel(d.day)}</small>`;
      tip.style.left = `${(L + i * band + band / 2) * scale}px`;
      tip.style.top = `${y(d[key]) * scale}px`;
      tip.hidden = false;
    });
    hit.addEventListener("mouseleave", () => { tip.hidden = true; });
  });
}

// Horizontal bars for a breakdown: one measure, sorted, labels left, values right.
export function barList(el, items, { key, format, max = null, extra = null }) {
  const top = max ?? Math.max(...items.map((i) => i[key]), 0);
  el.innerHTML = items.length ? `<ul class="bars">${items.map((i) => `
    <li><span class="bar-label">${esc(i.label)}</span>
      <span class="bar-track"><i data-w="${top ? (i[key] / top) * 100 : 0}"></i></span>
      <span class="bar-value">${esc(format(i[key]))}</span>${extra ? `<span class="bar-extra">${extra(i)}</span>` : ""}</li>`).join("")}</ul>`
    : '<p class="muted flush">No data for this period.</p>';
  el.querySelectorAll(".bar-track i[data-w]").forEach((b) => { b.style.width = `${b.dataset.w}%`; });
}
```

## `frontend/js/controls.js`
```js
// On/off switches and budget changes, with a confirmation that names the change.
import { api } from "./api.js";
import { confirmDialog, toast } from "./ui.js";
import { money } from "./format.js";

const WHAT = { campaign: "campaign", adset: "ad set", ad: "ad" };

export async function toggleEntity(btn, after) {
  const [level, id] = btn.dataset.toggle.split(":");
  const turnOn = btn.getAttribute("aria-checked") !== "true";
  const name = btn.dataset.name;
  const ok = await confirmDialog({
    title: `${turnOn ? "Turn on" : "Turn off"} “${name}”?`,
    body: turnOn
      ? `<p>The ${WHAT[level]} starts delivering again and spends from its budget.${level !== "ad" ? " Ads inside it that are on start too." : ""}</p>`
      : `<p>The ${WHAT[level]} stops showing within a few minutes${level !== "ad" ? ", and every ad inside it stops with it" : ""}. Nothing is deleted; you can turn it back on any time.</p>`,
    confirm: turnOn ? "Turn on" : "Turn off", danger: !turnOn,
  });
  if (!ok) return;
  btn.disabled = true;
  try {
    await api(`/api/ads/${level}/${id}/status`, { method: "POST", body: { status: turnOn ? "ACTIVE" : "PAUSED" } });
    toast(`${name} is ${turnOn ? "on" : "off"}`);
    after();
  } catch (err) { toast(err.message, "bad"); btn.disabled = false; }
}

export async function editBudget({ level, id, name, current }, after) {
  const now = current / 100;
  const value = await confirmDialog({
    title: `Daily budget for “${name}”`,
    body: `<p>Now <b>${money(current, { exact: true })} a day</b>. Meta may spend up to 75% more on a busy day and evens it out over the week.</p>`,
    confirm: "Change budget",
    field: {
      label: "New daily budget", prefix: "$", suffix: "/day", inputmode: "decimal", value: now.toFixed(2),
      validate: (v) => {
        const n = Number(String(v).replace(/[$,\s]/g, ""));
        if (!Number.isFinite(n) || n < 1) return "Enter at least $1";
        if (Math.round(n * 100) === current) return "That's the current budget";
        return null;
      },
      hint: (v) => {
        const n = Number(String(v).replace(/[$,\s]/g, ""));
        if (!Number.isFinite(n) || n <= 0) return "";
        const change = (n * 100 - current) / current;
        const words = `${change > 0 ? "+" : ""}${Math.round(change * 100)}% · about ${money(n * 100 * 30)} a month`;
        return change > 0.2 ? `${words}. <b>Bigger than +20%:</b> Meta may restart learning and results can wobble for a few days.` : words;
      },
    },
  });
  if (value === false) return;
  const cents = Math.round(Number(String(value).replace(/[$,\s]/g, "")) * 100);
  try {
    await api(`/api/ads/${level}/${id}/budget`, { method: "POST", body: { daily_budget_cents: cents } });
    toast(`Budget is now ${money(cents, { exact: true })}/day`);
    after();
  } catch (err) { toast(err.message, "bad"); }
}

```

## `frontend/js/tasks.js`
```js
// Desk tasks and Claude's proposals, rendered the same way on Desk, Research and ad pages.
import { api } from "./api.js";
import { confirmDialog, esc, toast, when } from "./ui.js";
import { renderMarkdown } from "./markdown.js";

export const KIND_LABELS = { question: "Question", review: "Review results", research: "Research competitors", creative: "New ad ideas", polish: "Polish", render: "New version" };
const STATUS = {
  queued: ["warn", "Waiting for your Mac"], claimed: ["claude", "Claude picked it up"], running: ["claude", "Claude is working"],
  done: ["ok", "Done"], failed: ["bad", "Didn't finish"], cancelled: ["", "Cancelled"],
};
export const ACTIVE = new Set(["queued", "claimed", "running"]);
const DECIDED = {
  applied: ["ok", "Approved and applied"], approved: ["ok", "Approved"], declined: ["", "Declined"],
  failed: ["bad", "Approved, but Meta refused"], expired: ["", "Expired"],
};

const SCORE_WORDS = { 5: "Ready", 4: "Small polish", 3: "Worth fixing", 2: "Hurting results", 1: "Blocking" };
export const scoreClass = (n) => (n >= 5 ? "s5" : n >= 4 ? "s4" : n >= 3 ? "s3" : "s2");

export function scorecardHtml(card) {
  if (!card || !card.passes) return "";
  const rows = card.passes.map((p) => `
    <details class="score-row ${scoreClass(p.score)}">
      <summary>
        <span class="score-name">${esc(p.label)}</span>
        <span class="score-bar" aria-hidden="true">${[1, 2, 3, 4, 5].map((i) => `<i class="${i <= (p.score || 0) ? "on" : ""}"></i>`).join("")}</span>
        <span class="score-num">${p.score ? `${p.score}/5` : "—"}</span>
        <span class="score-verdict">${esc(p.verdict || SCORE_WORDS[p.score] || "")}</span>
      </summary>
      <div class="score-detail">
        ${p.findings.length ? `<b>What Claude saw</b><ul>${p.findings.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}
        ${p.fixes.length ? `<b>Fixes</b><ul class="fixes">${p.fixes.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}
      </div>
    </details>`).join("");
  return `<section class="scorecard">
    <header><span class="overall ${scoreClass(card.overall)}"><b>${card.overall ?? "—"}</b><small>/5</small></span>
      <div><b>Polish score</b><p>${esc(card.headline || "")}</p></div></header>
    <div class="score-rows">${rows}</div>
  </section>`;
}

function creativeProposal(p) {
  const pl = p.payload || {};
  const decided = DECIDED[p.status];
  const foot = p.status === "pending"
    ? `<div class="row"><button class="btn btn-claude btn-small" type="button" data-approve="${p.id}">Create this ad (off)</button>
       <a class="btn btn-small" href="/new-ad.html?proposal=${p.id}">Edit first</a><button class="btn btn-small" type="button" data-decline="${p.id}">Decline</button></div>`
    : `<p class="flush"><span class="pill ${decided ? decided[0] : ""}">${esc(decided ? decided[1] : p.status)}</span></p>`;
  return `<article class="proposal variant" data-proposal="${p.id}" data-title="${esc(p.title)}" data-change="${esc(`New ad “${pl.name || ""}”, switched off, ${pl.media && pl.media.kind !== "same" ? "with new media" : "same image or video"}`)}">
    <header><span class="tag">new ad</span><b>${esc(p.title)}</b></header>
    <div class="variant-copy">
      <p class="v-headline">${esc(pl.title || "")}</p>
      <p class="v-body">${esc(pl.body || "")}</p>
      <p class="muted small flush">${pl.media && pl.media.kind !== "same" ? `New ${esc(pl.media.kind)} from Claude` : "Same image or video"}${pl.name ? ` · named “${esc(pl.name)}”` : ""}</p>
    </div>
    ${p.rationale ? `<p class="muted small flush">${esc(p.rationale)}</p>` : ""}
    ${foot}
  </article>`;
}

export function proposalCard(p, task = null) {
  if (p.kind === "creative" && p.payload) return creativeProposal(p);
  const adId = task && task.options && task.options.ad_id;
  if (p.status === "pending" && adId && /^make a new version/i.test(p.title || "")) {
    return `<article class="proposal" data-proposal="${p.id}" data-title="${esc(p.title)}">
      <header><span class="tag">new version</span><b>${esc(p.title)}</b></header>
      ${p.rationale ? `<p class="muted small">${esc(p.rationale)}</p>` : ""}
      <div class="row"><button class="btn btn-claude btn-small" type="button" data-render-ad="${esc(adId)}" data-render-task="${task.id}" data-render-note="${esc(p.rationale || p.title)}">Make it now</button>
        <button class="btn btn-small" type="button" data-decline="${p.id}">Not now</button></div>
    </article>`;
  }
  const change = p.field || p.current_value || p.proposed_value
    ? `<div><dt>Change</dt><dd>${esc(p.field || "")}${p.field ? ": " : ""}${esc(p.current_value || "—")} → <b>${esc(p.proposed_value || "—")}</b></dd></div>` : "";
  const row = (label, v) => (v ? `<div><dt>${label}</dt><dd>${esc(v)}</dd></div>` : "");
  const decided = DECIDED[p.status];
  const foot = p.status === "pending"
    ? `<div class="row"><button class="btn btn-claude btn-small" type="button" data-approve="${p.id}">Approve</button><button class="btn btn-small" type="button" data-decline="${p.id}">Decline</button></div>`
    : `<p class="flush"><span class="pill ${decided ? decided[0] : ""}">${esc(decided ? decided[1] : p.status)}</span>${p.decided_at ? ` <span class="muted small">${esc(when(p.decided_at))}</span>` : ""}</p>`;
  return `<article class="proposal" data-proposal="${p.id}" data-title="${esc(p.title)}" data-change="${esc([p.entity_name, p.field && `${p.field}: ${p.current_value || "—"} → ${p.proposed_value || "—"}`].filter(Boolean).join(" · "))}">
    <header><span class="tag">${esc(p.kind)}</span><b>${esc(p.title)}</b></header>
    <dl class="facts">
      ${row("On", [p.entity_type, p.entity_name].filter(Boolean).join(" · "))}
      ${change}${row("Why", p.rationale)}${row("Expected", p.expected)}${row("Undo", p.rollback)}
    </dl>
    ${foot}
  </article>`;
}

export function taskCard(t, openReports = new Set()) {
  const [cls, label] = STATUS[t.status] || ["", t.status];
  const meta = [KIND_LABELS[t.kind] || t.kind, t.campaign_name, when(t.created_at), t.created_by_name].filter(Boolean).map(esc).join(" · ");
  const working = ACTIVE.has(t.status) && t.status !== "queued" && t.progress ? `<p class="progress"><span class="dot" aria-hidden="true"></span>${esc(t.progress)}</p>` : "";
  const reports = t.reports.map((r) => `
    <details class="report" data-report="${r.id}" ${openReports.has(r.id) ? "open" : ""}>
      <summary>${esc(r.title)}</summary>
      <div class="md">${renderMarkdown(r.body)}</div>
    </details>`).join("");
  const proposals = t.proposals.length ? `
    <div class="proposals stack tight">
      <p class="muted small flush">Claude's proposals. Approving an on/off or budget change applies it on Meta right away; other kinds are recorded for the next step.</p>
      ${t.proposals.map((p) => proposalCard(p, t)).join("")}
    </div>` : "";
  const actions = [
    t.status === "queued" ? `<button class="btn btn-small" type="button" data-cancel="${t.id}">Cancel</button>` : "",
    ["failed", "cancelled", "done"].includes(t.status) ? `<button class="btn btn-small" type="button" data-again="${t.id}">Ask again</button>` : "",
  ].join("");
  return `<article class="panel task ${t.status}">
    <div class="panel-body stack tight">
      <header class="task-head"><span class="pill ${cls}">${esc(label)}</span><span class="muted small">${meta}</span><span class="spacer"></span>${actions}</header>
      <p class="prompt">${esc(t.prompt)}</p>
      ${working}
      ${t.summary ? `<p class="summary">${esc(t.summary)}</p>` : ""}
      ${scorecardHtml(t.scorecard)}
      ${t.error ? `<p class="note bad flush">${esc(t.error)}</p>` : ""}
      ${reports}${proposals}
    </div>
  </article>`;
}

// Click handling for task lists and proposal cards; onChange reloads the page data.
export function wireTaskActions(root, onChange, openReports) {
  root.addEventListener("click", async (e) => {
    const cancel = e.target.closest("[data-cancel]");
    const again = e.target.closest("[data-again]");
    const approve = e.target.closest("[data-approve]");
    const render = e.target.closest("[data-render-ad]");
    if (render) {
      const card = render.closest("[data-proposal]");
      const yes = await confirmDialog({
        title: "Make the new version now?",
        body: "<p>Claude rebuilds the creative on your Mac with these fixes (10–40 minutes), uploads it to your media library and sends it back as a new ad for you to approve. Nothing changes on the live ad.</p>",
        confirm: "Make it", claude: true,
      });
      if (!yes) return;
      try {
        await api(`/api/ads/ad/${encodeURIComponent(render.dataset.renderAd)}/render`, { method: "POST",
          body: { from_task: Number(render.dataset.renderTask), direction: render.dataset.renderNote } });
        await api(`/api/proposals/${card.dataset.proposal}/approve`, { method: "POST" });
        toast("Sent to Claude. The new version shows up under Runs.");
        onChange();
      } catch (err) { toast(err.message, "bad"); }
      return;
    }
    const decline = e.target.closest("[data-decline]");
    try {
      if (cancel) { await api(`/api/desk/tasks/${cancel.dataset.cancel}/cancel`, { method: "POST" }); toast("Cancelled"); onChange(); }
      if (again) { await api(`/api/desk/tasks/${again.dataset.again}/again`, { method: "POST" }); toast("Asked again"); onChange(); }
      if (approve || decline) {
        const card = (approve || decline).closest("[data-proposal]");
        const id = card.dataset.proposal;
        const yes = await confirmDialog(approve ? {
          title: `Approve “${card.dataset.title}”?`,
          body: `<p>${esc(card.dataset.change || "")}</p><p class="muted">On/off, budget and new-ad proposals are applied on Meta as soon as you approve (new ads are created switched off). Anything else is recorded as approved.</p>`,
          confirm: "Approve", claude: true,
        } : { title: `Decline “${card.dataset.title}”?`, body: "<p>Nothing changes on Meta.</p>", confirm: "Decline" });
        if (!yes) return;
        const r = await api(`/api/proposals/${id}/${approve ? "approve" : "decline"}`, { method: "POST" });
        if (r.ad_id) { toast("Ad created (off). Opening it…"); location.href = `/ad.html?id=${encodeURIComponent(r.ad_id)}&created=1`; return; }
        toast(r.status === "applied" ? "Approved and applied on Meta" : r.status === "approved" ? (r.note || "Approved") : "Declined");
        onChange();
      }
    } catch (err) { toast(err.message, "bad"); onChange(); }
  });
  if (openReports) {
    root.addEventListener("toggle", (e) => {
      const d = e.target.closest("details[data-report]");
      if (!d) return;
      const id = Number(d.dataset.report);
      if (d.open) openReports.add(id); else openReports.delete(id);
    }, true);
  }
}
```

