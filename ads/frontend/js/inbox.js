// Inbox: everything that changed or waits for someone: Meta's approvals and rejections, issues,
// learning limited, new leads, Claude's proposals, money and tracking alerts. Read/unread per person.
import { api } from "./api.js";
import { boot, esc, icon, onRefresh, toast, when, errorState } from "./ui.js";

const FILTERS = [["unread", "Unread"], ["all", "All"], ["status", "Ad status"], ["leads", "Leads"], ["claude", "Claude"], ["money", "Money"], ["system", "Tracking"]];
const ICON = { status: "ads", leads: "leads", claude: "spark", money: "chart", system: "alarm" };
const TONE = { bad: "bad", warn: "warn", ok: "ok", info: "info", lead: "lead", claude: "claude" };
const params = new URLSearchParams(location.search);
let filter = FILTERS.some(([k]) => k === params.get("show")) ? params.get("show") : "unread";
let data = { items: [], counts: {} };
let current = null;
const $ = (id) => document.getElementById(id);

function query() {
  if (filter === "unread" || filter === "all") return `filter=${filter}`;
  return `filter=all&kind=${filter}`;
}

function renderFilters() {
  const c = data.counts || {};
  $("ib-filters").innerHTML = FILTERS.map(([k, label]) => {
    const n = k === "unread" ? c.unread : k === "all" ? 0 : c[k];
    return `<button type="button" role="tab" class="view-chip" aria-selected="${k === filter}" data-f="${k}">${label}${n ? `<span>${n}</span>` : ""}</button>`;
  }).join("");
  $("ib-sub").textContent = c.unread ? `${c.unread} unread · approvals, rejections, leads, Claude and alerts in one place` : "All caught up";
  $("ib-all").hidden = !c.unread;
}

function itemHtml(i) {
  return `<li class="ib-item ${i.unread ? "unread" : ""} k-${TONE[i.level] || "info"}" data-key="${esc(i.key)}" ${current === i.key ? 'aria-current="true"' : ""} tabindex="0">
    <span class="ib-ic">${icon(ICON[i.category] || "alarm")}</span>
    <span class="ib-b"><b>${esc(i.title)}</b><small>${esc((i.lines || [])[0] || "")}</small></span>
    <span class="ib-t tnum">${esc(when(i.at))}</span></li>`;
}

function renderList() {
  const items = data.items;
  if (!items.length) {
    $("ib-list").innerHTML = `<li class="ib-empty">${filter === "unread" ? "Nothing new. Meta's approvals and rejections, new leads and Claude's ideas show up here." : "Nothing here yet."}</li>`;
    return;
  }
  const today = new Date().toDateString();
  const head = (label) => `<li class="ib-head" role="presentation">${label}</li>`;
  const todays = items.filter((i) => new Date(i.at).toDateString() === today);
  const older = items.filter((i) => new Date(i.at).toDateString() !== today);
  $("ib-list").innerHTML = (todays.length ? head("Today") + todays.map(itemHtml).join("") : "") + (older.length ? head("Earlier") + older.map(itemHtml).join("") : "");
}

function action(i) {
  if (!i.href) return "";
  const label = i.category === "leads" ? "Open the lead" : i.category === "claude" ? "Review in Claude" : i.href.startsWith("/ad.html") ? "Open the ad"
    : i.href.startsWith("/settings") ? "Open Settings" : "Open";
  return `<a class="btn btn-primary" href="${esc(i.href)}">${label}</a>`;
}

function renderDetail() {
  const i = data.items.find((x) => x.key === current);
  if (!i) { $("ib-detail").innerHTML = `<p class="muted ib-pick">Pick an item to see the details.</p>`; return; }
  $("ib-detail").innerHTML = `<div class="ib-dh"><span class="ib-ic k-${TONE[i.level] || "info"}">${icon(ICON[i.category] || "alarm")}</span>
      <div><p class="ib-kicker">${esc(when(i.at))}${i.resolved ? " · fixed since" : ""}</p><h2>${esc(i.title)}</h2></div></div>
    ${(i.lines || []).map((l) => `<p>${esc(l)}</p>`).join("")}
    <div class="row">${action(i)}${i.unread ? '<button class="btn" type="button" data-read>Mark read</button>' : ""}</div>`;
}

async function markRead(keys) {
  if (!keys.length) return;
  try {
    await api("/api/inbox/read", { method: "POST", body: { keys } });
    data.items.forEach((i) => { if (keys.includes(i.key)) i.unread = false; });
    data.counts.unread = Math.max(0, (data.counts.unread || 0) - keys.length);
    document.querySelectorAll("[data-inbox-count]").forEach((el) => { el.hidden = !data.counts.unread; el.textContent = data.counts.unread || ""; });
  } catch (err) { toast(err.message, "bad"); }
}

async function load() {
  data = await api(`/api/inbox?${query()}`);
  if (!data.items.some((i) => i.key === current)) current = matchMedia("(max-width: 960px)").matches ? null : data.items[0]?.key || null;
  renderFilters(); renderList(); renderDetail();
}

$("ib-filters").addEventListener("click", (e) => {
  const b = e.target.closest("[data-f]");
  if (!b) return;
  filter = b.dataset.f;
  const u = new URL(location.href); u.searchParams.set("show", filter); history.replaceState(null, "", u);
  load().catch((err) => toast(err.message, "bad"));
});
function pick(li) {
  current = li.dataset.key;
  const i = data.items.find((x) => x.key === current);
  if (matchMedia("(max-width: 960px)").matches && i?.href) {
    markRead(i.unread ? [i.key] : []).finally(() => { location.href = i.href; });
    return;
  }
  if (i?.unread) markRead([i.key]).then(() => { renderFilters(); renderList(); renderDetail(); });
  else { renderList(); renderDetail(); }
}
$("ib-list").addEventListener("click", (e) => { const li = e.target.closest("[data-key]"); if (li) pick(li); });
$("ib-list").addEventListener("keydown", (e) => {
  const li = e.target.closest("[data-key]");
  if (!li) return;
  if (e.key === "Enter") pick(li);
  if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); li.nextElementSibling?.closest("[data-key]")?.focus() || li.parentElement.querySelectorAll("[data-key]")[[...li.parentElement.querySelectorAll("[data-key]")].indexOf(li) + 1]?.focus(); }
  if (e.key === "ArrowUp" || e.key === "k") { e.preventDefault(); const all = [...li.parentElement.querySelectorAll("[data-key]")]; all[all.indexOf(li) - 1]?.focus(); }
});
$("ib-detail").addEventListener("click", (e) => {
  if (e.target.closest("[data-read]")) markRead([current]).then(() => { renderFilters(); renderList(); renderDetail(); });
});
$("ib-all").addEventListener("click", async () => {
  try {
    await api("/api/inbox/read", { method: "POST", body: { all: true, kind: ["unread", "all"].includes(filter) ? "all" : filter } });
    toast("All marked read");
    await load();
    document.querySelectorAll("[data-inbox-count]").forEach((el) => { el.hidden = !data.counts.unread; el.textContent = data.counts.unread || ""; });
  } catch (err) { toast(err.message, "bad"); }
});

const me = await boot({ page: "inbox" });
if (me) {
  onRefresh(load);
  load().catch((err) => errorState($("ib-list"), err, load));
}
