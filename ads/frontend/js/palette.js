// Command menu: jump to any page, tab, Settings section or saved view, run a common action, or find a
// campaign, ad set, ad, lead, lead form, test or saved competitor ad. Opened with ⌘K / Ctrl+K, "/" or the
// search field in the sidebar. Arrow keys, Enter, Esc. Words people use for a page ("Home", "Results",
// "Performance"…) find it too.
import { api } from "./api.js";
import { esc, icon } from "./ui.js";

let dlg = null;
let items = [];
let sel = 0;
let timer = null;
let seq = 0;
let views = null;

const TYPE_ICON = { page: "table", tab: "table", setting: "settings", view: "grid", campaign: "ads", adset: "ads", ad: "image",
  lead: "leads", form: "leads", test: "tests", swipe: "research", action: "plus" };

// who: "all" everyone signed in · "staff" not a client · "admin" · "owner" (whole-console settings) · "report" admins and clients.
const P = (title, href, who, icon_, keys = "", sub = "Go to") => ({ type: "page", title, href, who, icon: icon_, sub, keys });
const PAGES = [
  P("Today", "/home.html", "all", "sun", "home start dashboard overview front page"),
  P("Inbox", "/inbox.html", "all", "inbox", "notifications alerts approvals rejections messages feed"),
  P("Leads", "/leads.html", "all", "leads", "contacts people prospects calls customers"),
  P("Ads", "/ads.html", "all", "ads", "manager creatives ad list"),
  P("Ad sets", "/ads.html?level=adset", "all", "ads", "adsets audiences", "Ads"),
  P("Campaigns", "/ads.html?level=campaign", "all", "ads", "budgets", "Ads"),
  P("Lead forms", "/forms.html", "admin", "leads", "instant forms questions", "Ads"),
  P("Gallery", "/gallery.html", "all", "image", "creative creatives pictures videos visuals thumbnails what works best ads copies", "Creative"),
  P("Results", "/performance.html", "all", "chart", "insights performance numbers stats statistics charts spend cost per lead", "Insights"),
  P("Compare ads", "/compare.html", "all", "compare", "side by side versus", "Insights"),
  P("Tests", "/experiments.html", "admin", "tests", "experiments a/b split test", "Insights"),
  P("Reports", "/report.html", "report", "table", "client report share pdf print", "Insights"),
  P("Claude", "/desk.html", "admin", "spark", "desk ai assistant requests conversations"),
  P("Research", "/research.html", "admin", "research", "swipe file competitors ad library inspiration", "Creative"),
  P("Settings", "/settings.html", "admin", "settings", "preferences configuration setup options"),
  P("Team", "/team.html", "admin", "team", "users people members invite logins", "Settings"),
  P("Your account", "/account.html", "all", "user", "profile password notifications push phone sign in"),
];
const T = (title, href, who, icon_, keys = "") => ({ type: "tab", title, href, who, icon: icon_, sub: "Tab", keys });
const TABS = [
  T("Claude: Conversations", "/desk.html#list", "admin", "spark", "requests runs history"),
  T("Claude: Suggestions waiting", "/desk.html#decide", "admin", "spark", "decisions accept approve review proposals"),
  T("Claude: By ad", "/desk.html#ads", "admin", "spark", "per ad"),
  T("Claude: Schedules", "/desk.html#schedules", "admin", "clock", "scheduled recurring repeat"),
  T("Gallery: Just launched", "/gallery.html?view=launched", "all", "image", "new recent started"),
  T("Gallery: Tired", "/gallery.html?view=tired", "all", "image", "fatigue worn out seen too often"),
  T("Results: By idea", "/performance.html#ideas-panel", "all", "chart", "concepts tags hooks angles"),
  T("Inbox: Needs action", "/inbox.html?box=need", "all", "inbox", "needs you to do waiting triage"),
  T("Inbox: For your information", "/inbox.html?box=fyi", "all", "inbox", "fyi notes approved changed outside"),
  T("Inbox: Unread", "/inbox.html?box=all&unread=1", "all", "inbox", "new"),
  T("Inbox: Ad status", "/inbox.html?box=all&kind=status", "all", "inbox", "approved rejected review"),
  T("Inbox: Leads", "/inbox.html?box=all&kind=leads", "all", "inbox", ""),
  T("Inbox: Claude", "/inbox.html?box=all&kind=claude", "staff", "inbox", "suggestions"),
  T("Inbox: Money", "/inbox.html?box=all&kind=money", "all", "inbox", "spending limit budget"),
  T("Inbox: Tracking", "/inbox.html?box=all&kind=system", "all", "inbox", "pixel dataset"),
  T("Ads delivering", "/ads.html?view=delivering", "all", "ads", "running live active on"),
  T("Ads in review", "/ads.html?view=review", "all", "clock", "pending approval"),
  T("Ads that need attention", "/ads.html?view=attention", "all", "power", "needs attention problems rejected issues"),
  T("Ads learning", "/ads.html?view=learning", "all", "ads", "learning phase limited"),
  T("Ads turned off", "/ads.html?view=off", "all", "power", "paused off stopped"),
  T("Test ads", "/ads.html?view=tests", "all", "tests", "qa copies"),
];
const S = (title, hash, keys = "", who = "admin") => ({ type: "setting", title: `Settings: ${title}`, href: `/settings.html#${hash}`, who, sub: "Settings", keys });
const SETTINGS = [
  S("Meta connection", "meta", "token system user page id ad account sync connect"),
  S("Targets", "targets", "cost per lead target highest daily budget ceiling goal"),
  S("Alerts", "alerts", "rules warnings notifications"),
  S("Clients and reports", "reports-panel", "client logins report email"),
  S("Lead replies", "replies", "automatic reply templates email answer"),
  S("Tracking health", "tracking", "pixel dataset conversions api capi events"),
  S("Lead stages to Meta", "crm", "crm conversion leads quality"),
  S("Meta A/B tests", "ab", "split tests"),
  S("Activity", "activity-panel", "log history who changed"),
  S("Meta app", "meta-app", "app secret webhooks instant status updates", "owner"),
  S("Automatic refresh", "auto", "interval updates every", "owner"),
  S("Telegram", "telegram", "bot messages", "owner"),
  S("Email", "email", "smtp mail mailbox", "owner"),
  S("Accounts", "accounts-panel", "businesses clients add an account", "owner"),
];
const A = (title, extra, who, icon_, keys = "", sub = "Do") => ({ type: "action", title, who, icon: icon_, sub, keys, ...extra });
const ACTIONS = [
  A("New ad", { href: "/new-ad.html" }, "admin", "plus", "create make", "Create"),
  A("New ad set", { href: "/new-adset.html" }, "admin", "plus", "create make audience", "Create"),
  A("New campaign", { href: "/new-campaign.html" }, "admin", "plus", "create make", "Create"),
  A("New lead form", { href: "/forms.html" }, "admin", "plus", "create make instant form", "Create"),
  A("Ask Claude", { href: "/desk.html?ask=1" }, "admin", "spark", "question request help ai", "Claude"),
  A("Refresh from Meta", { run: "refresh" }, "staff", "refresh", "update sync reload latest"),
  A("Switch theme", { run: "theme" }, "all", "moon", "dark mode light mode appearance colours colors"),
  A("Keyboard shortcuts", { run: "shortcuts" }, "all", "grid", "keys hotkeys help ?"),
  A("Sign out", { run: "signout" }, "all", "logout", "log out logout"),
];
const VIEW_PAGE = { ads: ["/ads.html", "Ads"], leads: ["/leads.html", "Leads"], insights: ["/performance.html", "Results"], inbox: ["/inbox.html", "Inbox"] };

function allowed(who, me) {
  const role = me && me.role;
  return who === "all" || (who === "staff" && role !== "client") || (who === "admin" && role === "admin")
    || (who === "owner" && role === "admin" && me.owner) || (who === "report" && (role === "admin" || role === "client"));
}

// This page's own tabs (an ad's Overview · Polish · Audience…, the Inbox filters): a click away.
function pageTabs() {
  const name = (document.querySelector(".main h1")?.textContent || "").trim().slice(0, 40) || "This page";
  return [...document.querySelectorAll('.main [role="tablist"] [role="tab"]')].filter((t) => !t.disabled && t.offsetParent !== null)
    .map((t) => {
      const c = t.cloneNode(true);
      c.querySelectorAll(".n, .count").forEach((x) => x.remove());
      return { type: "tab", title: `${name}: ${c.textContent.trim()}`, sub: "This page", icon: "table", keys: "", tabEl: t };
    }).filter((t) => !/:\s*$/.test(t.title));
}

function catalogue(me) {
  const savedViews = (views || []).map((v) => {
    const [path, label] = VIEW_PAGE[v.page] || VIEW_PAGE.ads;
    return { type: "view", title: v.name, href: `${path}${v.query ? `?${v.query}` : ""}`, sub: `Saved view · ${label}`, keys: "view saved" };
  });
  return [...PAGES, ...ACTIONS, ...pageTabs(), ...TABS, ...SETTINGS].filter((i) => !i.who || allowed(i.who, me)).concat(savedViews);
}

// How well a thing matches what was typed: its name first, then the words people use for it, then where it lives.
const words = (s) => s.toLowerCase().split(/[^a-z0-9/?]+/).filter(Boolean);
function scoreText(text, q) {
  const t = text.toLowerCase();
  if (t === q) return 100;
  if (t.startsWith(q)) return 80;
  if (t.split(/[\s:·/-]+/).some((w) => w.startsWith(q))) return 60;
  return t.includes(q) ? 40 : 0;
}
export function score(item, raw) {
  const q = raw.trim().toLowerCase();
  if (!q) return 1;
  const title = scoreText(item.title, q);
  const keys = item.keys ? scoreText(item.keys, q) - 15 : 0;
  const best = Math.max(title, keys, item.sub ? scoreText(item.sub, q) - 30 : 0);
  if (best > 0) return best;
  // Several words: each one found somewhere ("ads review", "settings email").
  const hay = `${item.title} ${item.keys || ""} ${item.sub || ""}`.toLowerCase();
  return words(q).length > 1 && words(q).every((w) => hay.includes(w)) ? 20 : 0;
}
function match(list, q) {
  return list.map((i, n) => ({ i, n, s: score(i, q) })).filter((x) => x.s > 0).sort((a, b) => b.s - a.s || a.n - b.n).map((x) => x.i);
}

function render(groups) {
  const ul = dlg.querySelector(".pal-list");
  items = groups.flatMap(([, list]) => list);
  sel = Math.min(sel, Math.max(items.length - 1, 0));
  if (!items.length) { ul.innerHTML = `<li class="empty compact">Nothing found. Try a campaign, ad, lead or page name.</li>`; return; }
  let n = 0;
  ul.innerHTML = groups.filter(([, list]) => list.length).map(([label, list]) => `<li class="pal-group" role="presentation">${esc(label)}</li>`
    + list.map((i) => `<li class="pal-item" role="option" id="pal-${n}" data-i="${n}" data-type="${esc(i.type)}" aria-selected="${n++ === sel}">${icon(i.icon || TYPE_ICON[i.type])}<span class="pal-t">${esc(i.title)}</span><small>${esc(i.sub || "")}</small></li>`).join("")).join("");
  dlg.querySelector("input").setAttribute("aria-activedescendant", `pal-${sel}`);
  ul.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
}

const QUICK = ["Today", "Inbox", "Leads", "Ads", "Gallery", "Results", "Compare ads", "Tests", "Reports", "Claude", "Research", "Settings",
  "New ad", "Ask Claude", "Ads that need attention", "Keyboard shortcuts"];

async function update(ctx) {
  const q = dlg.querySelector("input").value.trim();
  const all = catalogue(ctx.me);
  let local;
  if (q) local = match(all, q).slice(0, 10);
  else local = QUICK.map((t) => all.find((i) => i.title === t)).filter(Boolean).concat(all.filter((i) => i.type === "view").slice(0, 5));
  const best = q && local.length ? score(local[0], q) : 0;
  const groups = [[q ? "Pages and actions" : "Jump to", local]];
  render(groups);
  clearTimeout(timer);
  if (q.length < 2) return;
  const mine = ++seq;
  timer = setTimeout(async () => {
    try {
      const r = await api(`/api/search?q=${encodeURIComponent(q)}`);
      if (mine !== seq) return;
      // Whichever matches what was typed better comes first: a page or action, or things found by name.
      const found = ["Found", r.items];
      const foundBest = r.items.length ? Math.max(...r.items.map((i) => score(i, q))) : 0;
      render(best > 0 && best >= foundBest ? [...groups, found] : [found, ...groups]);
    } catch (e) { /* local results stay */ }
  }, 160);
}

function go(i, ctx) {
  const item = items[i];
  if (!item) return;
  dlg.close();
  if (item.tabEl) { item.tabEl.click(); item.tabEl.focus(); return; }
  if (item.run) { ctx.actions[item.run]?.(); return; }
  location.href = item.href;
}

export function open(ctx) {
  if (!dlg) {
    dlg = document.createElement("dialog");
    dlg.className = "palette";
    dlg.setAttribute("aria-label", "Search or jump to");
    dlg.innerHTML = `<div class="pal-box"><label class="pal-in">${icon("search")}<input type="text" role="combobox" aria-expanded="true" aria-controls="pal-list"
        placeholder="Search campaigns, ads, leads, or type a page…" autocomplete="off" spellcheck="false"></label>
      <ul class="pal-list" id="pal-list" role="listbox"></ul>
      <div class="pal-foot"><span><kbd>↑</kbd> <kbd>↓</kbd> move</span><span><kbd>Enter</kbd> open</span><span><kbd>Esc</kbd> close</span></div></div>`;
    document.body.append(dlg);
    const input = dlg.querySelector("input");
    input.addEventListener("input", () => { sel = 0; update(ctx); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(sel + 1, items.length - 1); refresh(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(sel - 1, 0); refresh(); }
      else if (e.key === "Enter") { e.preventDefault(); go(sel, ctx); }
    });
    dlg.querySelector(".pal-list").addEventListener("click", (e) => { const li = e.target.closest("[data-i]"); if (li) go(Number(li.dataset.i), ctx); });
    dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  }
  const refresh = () => {
    dlg.querySelectorAll(".pal-item").forEach((li) => li.setAttribute("aria-selected", String(Number(li.dataset.i) === sel)));
    dlg.querySelector("input").setAttribute("aria-activedescendant", `pal-${sel}`);
    dlg.querySelector('.pal-item[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  };
  const input = dlg.querySelector("input");
  input.value = ctx.query || "";
  sel = 0;
  update(ctx);
  if (!dlg.open) dlg.showModal();
  input.focus();
  // Saved views come once per page; the menu redraws when they arrive.
  if (views === null) {
    views = [];
    api("/api/views").then((r) => { views = r.views || []; if (dlg.open) update(ctx); }).catch(() => {});
  }
}
