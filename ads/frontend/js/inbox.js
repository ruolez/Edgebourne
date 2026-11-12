// Inbox: everything that changed or waits for someone: Meta's approvals and rejections, issues,
// learning limited, new leads, Claude's suggestions, money and tracking alerts. Read/unread per person.
import { api, startLoad } from "./api.js";
import { boot, entityLink, esc, icon, onRefresh, toast, when, errorState } from "./ui.js";
import { closeLayer, leaveLayer, openLayer } from "./urlstate.js";

const FILTERS = [["unread", "Unread"], ["all", "All"], ["status", "Ad status"], ["leads", "Leads"], ["claude", "Claude"], ["money", "Money"], ["system", "Tracking"]];
const ICON = { status: "ads", leads: "leads", claude: "spark", money: "chart", system: "alarm" };
const TONE = { bad: "bad", warn: "warn", ok: "ok", info: "info", lead: "lead", claude: "claude" };
const params = new URLSearchParams(location.search);
let filter = FILTERS.some(([k]) => k === params.get("show")) ? params.get("show") : "unread";
let data = { items: [], counts: {} };
const $ = (id) => document.getElementById(id);
// The open item is in the URL (#item=<key>). On a phone it covers the list, so opening it is a step Back undoes.
const itemInUrl = () => { const m = location.hash.match(/item=([^&]+)/); return m ? decodeURIComponent(m[1]) : null; };
const covers = () => matchMedia("(max-width: 960px)").matches;
const listUrl = () => location.pathname + location.search;
let current = itemInUrl();
// An item named by the link this page was opened with: honoured on the first load only, so later refreshes
// and the filters the person picks are never overruled by it.
let linked = current;
// The open item after it left the list (read in Unread, say): it stays on screen until another is picked.
let kept = null;
let listScroll = 0;
let newList = false;  // the person picked another filter: nothing from the old list stays open
const shownItem = () => data.items.find((x) => x.key === current) || (kept && kept.key === current ? kept : null);
function setShow(f) {
  const u = new URL(location.href); u.searchParams.set("show", f); history.replaceState(history.state, "", u);
}

function query() {
  if (filter === "unread" || filter === "all") return `filter=${filter}`;
  return `filter=all&kind=${filter}`;
}

function renderFilters() {
  const c = data.counts || {};
  $("ib-filters").innerHTML = FILTERS.map(([k, label]) => {
    const n = k === "unread" ? c.unread : k === "all" ? 0 : c[k];
    return `<button type="button" role="tab" aria-selected="${k === filter}" data-f="${k}">${label}${n ? `<span class="n">${n}</span>` : ""}</button>`;
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
    $("ib-list").innerHTML = `<li class="empty compact ib-none">${filter === "unread" ? "Nothing new. Meta's approvals and rejections, new leads and Claude's suggestions show up here." : "Nothing here yet."}</li>`;
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
  const i = shownItem();
  if (!i) { $("ib-detail").innerHTML = `<p class="muted ib-pick">Pick an item to see the details.</p>`; return; }
  const s = i.subject;
  $("ib-detail").innerHTML = `<button type="button" class="btn btn-quiet back-link" data-ib-back>${icon("back")} Inbox</button>
    <div class="ib-dh"><span class="ib-ic k-${TONE[i.level] || "info"}">${icon(ICON[i.category] || "alarm")}</span>
      <div><p class="ib-kicker">${esc(when(i.at))}${i.resolved ? " · fixed since" : ""}</p><h2>${esc(i.title)}</h2></div></div>
    ${(i.lines || []).map((l) => `<p>${esc(l)}</p>`).join("")}
    ${s ? `<p class="ib-about"><span class="muted">${esc({ campaign: "Campaign", adset: "Ad set", ad: "Ad" }[s.level] || "About")}:</span> ${entityLink(s.level, s.id, s.name)}</p>` : ""}
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
  const superseded = startLoad("inbox");
  const d = await api(`/api/inbox?${query()}`);
  if (superseded()) return;
  const before = newList ? null : shownItem();
  newList = false;
  data = d;
  if (linked && !data.items.some((i) => i.key === linked) && filter !== "all") { filter = "all"; setShow("all"); return load(); }  // a read item named by a link
  linked = null;
  if (data.items.some((i) => i.key === current)) kept = null;
  else if (before && before.key === current) kept = before;
  else { kept = null; current = covers() ? null : data.items[0]?.key || null; }
  renderFilters(); renderList(); renderDetail();
  $("ib-panel").classList.toggle("showing-detail", Boolean(covers() && current && itemInUrl() === current));
}

$("ib-filters").addEventListener("click", (e) => {
  const b = e.target.closest("[data-f]");
  if (!b) return;
  filter = b.dataset.f;
  // A new filter starts a new list: the open item and its #item= go, and the list shows its first item.
  linked = null; kept = null; newList = true;
  if (covers()) current = null;
  leaveLayer();
  const u = new URL(location.href); u.searchParams.set("show", filter); u.hash = ""; history.replaceState(history.state, "", u);
  $("ib-panel").classList.remove("showing-detail");
  load().catch((err) => toast(err.message, "bad"));
});
function pick(li) {
  current = li.dataset.key;
  const i = data.items.find((x) => x.key === current);
  const href = `${listUrl()}#item=${encodeURIComponent(current)}`;
  kept = null;
  if (covers()) {
    if (!$("ib-panel").classList.contains("showing-detail")) listScroll = window.scrollY;
    openLayer(href); $("ib-panel").classList.add("showing-detail"); window.scrollTo(0, 0);
  } else history.replaceState(history.state, "", href);
  const focusBack = () => { if (covers()) $("ib-detail").querySelector("[data-ib-back]")?.focus({ preventScroll: true }); };
  if (i?.unread) markRead([i.key]).then(() => { renderFilters(); renderList(); renderDetail(); focusBack(); });
  else { renderList(); renderDetail(); focusBack(); }
}
// The list comes back where it was, with focus on the item that was open.
function showList() {
  const wasOpen = $("ib-panel").classList.contains("showing-detail");
  $("ib-panel").classList.remove("showing-detail");
  if (!wasOpen) return;
  window.scrollTo(0, listScroll);
  const li = [...document.querySelectorAll("#ib-list [data-key]")].find((x) => x.dataset.key === current);
  li?.focus({ preventScroll: true });
}
// Back (or ← Inbox) shows the list again; Forward or a link opens the item it names.
function followUrl() {
  const key = itemInUrl();
  if (key && (data.items.some((i) => i.key === key) || kept?.key === key)) { current = key; renderList(); renderDetail(); }
  if (covers() && key && key === current) $("ib-panel").classList.add("showing-detail");
  else showList();
}
addEventListener("popstate", followUrl);
addEventListener("hashchange", followUrl);
$("ib-list").addEventListener("click", (e) => { const li = e.target.closest("[data-key]"); if (li) pick(li); });
$("ib-list").addEventListener("keydown", (e) => {
  const li = e.target.closest("[data-key]");
  if (!li) return;
  if (e.key === "Enter") pick(li);
  if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); li.nextElementSibling?.closest("[data-key]")?.focus() || li.parentElement.querySelectorAll("[data-key]")[[...li.parentElement.querySelectorAll("[data-key]")].indexOf(li) + 1]?.focus(); }
  if (e.key === "ArrowUp" || e.key === "k") { e.preventDefault(); const all = [...li.parentElement.querySelectorAll("[data-key]")]; all[all.indexOf(li) - 1]?.focus(); }
});
$("ib-detail").addEventListener("click", (e) => {
  if (e.target.closest("[data-ib-back]")) { showList(); closeLayer(listUrl()); return; }
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
