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
  if (me.must_change_password && page !== "account") {
    location.href = "/account.html?first=1";
    return null;
  }
  if (admin && me.role !== "admin") { location.href = "/leads.html"; return null; }
  const links = [
    { id: "leads", href: "/leads.html", label: "Leads", icon: "leads" },
    { id: "performance", href: "/performance.html", label: "Performance", icon: "chart" },
    ...(me.role === "admin" ? [
      { id: "desk", href: "/desk.html", label: "Desk", icon: "spark" },
      { id: "team", href: "/team.html", label: "Team", icon: "team" },
      { id: "settings", href: "/settings.html", label: "Settings", icon: "settings" },
    ] : []),
  ];
  const rail = document.querySelector(".rail");
  const initials = me.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  rail.innerHTML = `
    <a class="brand" href="/leads.html"><img src="/img/favicon.svg" alt=""><span>Edge Bourne Ads</span></a>
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
