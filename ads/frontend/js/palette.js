// Command palette: jump to any page, campaign, ad set, ad or lead, or run a common action.
// Opened with ⌘K / Ctrl+K, "/" or the search field in the sidebar. Arrow keys, Enter, Esc.
import { api } from "./api.js";
import { esc, icon } from "./ui.js";

let dlg = null;
let items = [];
let sel = 0;
let timer = null;
let seq = 0;

const TYPE_ICON = { page: "table", campaign: "ads", adset: "ads", ad: "image", lead: "leads", action: "plus" };

function baseItems(me, pages) {
  const admin = me && me.role === "admin";
  const { SECTIONS, PAGE_HREF } = pages;
  const out = [];
  for (const [key, s] of Object.entries(SECTIONS)) {
    if (s.admin && !admin) continue;
    out.push({ type: "page", title: s.label, sub: "Go to", href: s.href, icon: s.icon });
  }
  const sub = [["report", "Reports"], ["forms", "Lead forms", true], ["experiments", "Tests", true],
    ["research", "Research", true], ["team", "Team", true]];
  for (const [p, label, adm] of sub) if (!adm || admin) out.push({ type: "page", title: label, sub: "Go to", href: PAGE_HREF[p] });
  if (admin) {
    out.push({ type: "action", title: "New ad", sub: "Create", href: "/new-ad.html", icon: "plus" });
    out.push({ type: "action", title: "New ad set", sub: "Create", href: "/new-adset.html", icon: "plus" });
    out.push({ type: "action", title: "New campaign", sub: "Create", href: "/new-campaign.html", icon: "plus" });
    out.push({ type: "action", title: "Ask Claude", sub: "Claude", href: "/desk.html?ask=1", icon: "spark" });
  }
  out.push({ type: "action", title: "Ads in review", sub: "View", href: "/ads.html?view=review", icon: "clock" });
  out.push({ type: "action", title: "Ads that need attention", sub: "View", href: "/ads.html?view=attention", icon: "power" });
  return out;
}

function match(list, q) {
  if (!q) return list;
  const t = q.toLowerCase();
  return list.filter((i) => i.title.toLowerCase().includes(t) || (i.sub || "").toLowerCase().includes(t));
}

function render(groups) {
  const ul = dlg.querySelector(".pal-list");
  items = groups.flatMap(([, list]) => list);
  sel = Math.min(sel, Math.max(items.length - 1, 0));
  if (!items.length) { ul.innerHTML = `<li class="pal-empty">Nothing found. Try a campaign, ad or lead name.</li>`; return; }
  let n = 0;
  ul.innerHTML = groups.filter(([, list]) => list.length).map(([label, list]) => `<li class="pal-group" role="presentation">${esc(label)}</li>`
    + list.map((i) => `<li class="pal-item" role="option" id="pal-${n}" data-i="${n}" aria-selected="${n++ === sel}">${icon(i.icon || TYPE_ICON[i.type])}<span class="pal-t">${esc(i.title)}</span><small>${esc(i.sub || "")}</small></li>`).join("")).join("");
  dlg.querySelector("input").setAttribute("aria-activedescendant", `pal-${sel}`);
  ul.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
}

async function update(ctx) {
  const q = dlg.querySelector("input").value.trim();
  const local = match(baseItems(ctx.me, ctx.pages), q);
  const groups = [[q ? "Pages and actions" : "Jump to", local.slice(0, q ? 8 : 14)]];
  render(groups);
  clearTimeout(timer);
  if (q.length < 2) return;
  const mine = ++seq;
  timer = setTimeout(async () => {
    try {
      const r = await api(`/api/search?q=${encodeURIComponent(q)}`);
      if (mine !== seq) return;
      render([["Found", r.items], ...groups]);
    } catch (e) { /* local results stay */ }
  }, 160);
}

function go(i) {
  const item = items[i];
  if (!item) return;
  dlg.close();
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
      else if (e.key === "Enter") { e.preventDefault(); go(sel); }
    });
    dlg.querySelector(".pal-list").addEventListener("click", (e) => { const li = e.target.closest("[data-i]"); if (li) go(Number(li.dataset.i)); });
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
}
