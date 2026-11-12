// Inbox: everything that changed or waits for someone: Meta's approvals and rejections, issues,
// learning limited, new leads, Claude's suggestions, money and tracking alerts. Read/unread per person.
// Needs action (what waits for someone; its new ones drive the badge) and FYI (the rest) are the two boxes;
// a problem fixed since moves to FYI by itself. E only marks read; accepting a suggestion opens the Accept sheet.
import { api, startLoad } from "./api.js";
import { acceptSheet } from "./decide.js";
import { boot, editing, entityLink, esc, icon, onRefresh, setInboxCount, toast, when, errorState } from "./ui.js";
import { closeLayer, leaveLayer, openLayer } from "./urlstate.js";
import { plural } from "./format.js";

// The FYI tab gets a short label on the narrowest phones, so all three tabs fit without scrolling.
const BOXES = [["need", "Needs action"], ["fyi", '<span class="ib-long">For your information</span><span class="ib-short">FYI</span>'], ["all", "All"]];
const KINDS = [["all", "Every kind"], ["status", "Ad status"], ["leads", "Leads"], ["claude", "Claude"], ["money", "Money"], ["system", "Tracking"]];
const ICON = { status: "ads", leads: "leads", claude: "spark", money: "chart", system: "alarm" };
const TONE = { bad: "bad", warn: "warn", ok: "ok", info: "info", lead: "lead", claude: "claude" };
const params = new URLSearchParams(location.search);
// ?box=&kind=&unread=1; the older ?show=unread|all|<kind> links still land in the right place.
const legacy = params.get("show");
let box = BOXES.some(([k]) => k === params.get("box")) ? params.get("box") : legacy ? "all" : "need";
let kind = KINDS.some(([k]) => k === params.get("kind")) ? params.get("kind") : KINDS.some(([k]) => k === legacy) ? legacy : "all";
let unreadOnly = params.get("unread") === "1" || legacy === "unread";
let me = null;
let data = { items: [], counts: {}, kinds: {} };
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
function writeUrl({ clearItem = false } = {}) {
  const u = new URL(location.href);
  u.searchParams.delete("show");
  u.searchParams.set("box", box);
  if (kind === "all") u.searchParams.delete("kind"); else u.searchParams.set("kind", kind);
  if (unreadOnly) u.searchParams.set("unread", "1"); else u.searchParams.delete("unread");
  if (clearItem) u.hash = "";
  history.replaceState(history.state, "", u);
}

const query = () => `box=${box}&filter=${unreadOnly ? "unread" : "all"}&kind=${kind}`;

function renderFilters() {
  const c = data.counts || {};
  // Tabs count what is new, like the badge: reading an item or fixing the problem takes it off.
  const n = { need: c.need_unread, fyi: c.fyi_unread, all: 0 };
  $("ib-box").innerHTML = BOXES.map(([k, label]) =>
    `<button type="button" role="tab" aria-selected="${k === box}" data-box="${k}">${label}${n[k] ? `<span class="n">${n[k]}</span>` : ""}</button>`).join("");
  const kn = data.kinds || {};
  $("ib-filters").innerHTML = KINDS.filter(([k]) => k !== "claude" || me?.role !== "client")
    .map(([k, label]) => `<button type="button" class="view-chip" aria-pressed="${k === kind}" data-f="${k}">${label}${k !== "all" && kn[k] ? `<span class="n">${kn[k]}</span>` : ""}</button>`).join("")
    + `<button type="button" class="view-chip" aria-pressed="${unreadOnly}" data-unread>Unread only</button>`;
  $("ib-sub").textContent = c.need
    ? `${plural(c.need, "thing needs", "things need")} you${c.need_unread ? `, ${c.need_unread} new` : ""}. The rest is for your information.`
    : "Nothing needs you. The rest is for your information.";
  $("ib-all").hidden = !data.items.some((i) => i.unread);
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
    const fyi = data.counts?.fyi_unread;
    $("ib-list").innerHTML = `<li class="empty compact ib-none">${box === "need" && kind === "all"
      ? `Nothing needs you right now.${fyi ? ` <button type="button" class="link-btn" data-goto-box="fyi">${plural(fyi, "new note")} for your information</button>` : ""}`
      : kind !== "all" || unreadOnly ? `Nothing here with these filters. <button type="button" class="link-btn" data-clear-filters>Show every kind</button>` : "Nothing here yet."}</li>`;
    return;
  }
  const today = new Date().toDateString();
  const head = (label) => `<li class="ib-head" role="presentation">${label}</li>`;
  const todays = items.filter((i) => new Date(i.at).toDateString() === today);
  const older = items.filter((i) => new Date(i.at).toDateString() !== today);
  $("ib-list").innerHTML = (todays.length ? head("Today") + todays.map(itemHtml).join("") : "") + (older.length ? head("Earlier") + older.map(itemHtml).join("") : "");
}

function action(i) {
  // A suggestion is accepted through the Accept sheet (Meta read fresh, money never ticked for you), never a bare button.
  if (i.proposal_id && me.role !== "client") {
    // The conversation lives on the Claude page, which only admins can open.
    const talk = i.href && me.role === "admin" ? `<a class="btn" href="${esc(i.href)}">Open the conversation</a>` : "";
    return `<button type="button" class="btn btn-claude" data-accept="${i.proposal_id}">Review and accept</button>${talk}`;
  }
  if (!i.href) return "";
  const label = i.category === "leads" ? "Open the lead" : /[?&#]tab=history/.test(i.href) ? "Open the history" : i.href.startsWith("/ad.html") ? "Open the ad"
    : i.href.startsWith("/settings") ? "Open Settings" : "Open";
  // An event that waits for a person (an outside budget change that broke a money rule) closes with Done.
  const done = (i.actions || []).includes("done") ? `<button type="button" class="btn" data-done="${i.alert_id}">Done</button>` : "";
  return `<a class="btn btn-primary" href="${esc(i.href)}">${label}</a>${done}`;
}

function renderDetail() {
  const i = shownItem();
  if (!i) { $("ib-detail").innerHTML = `<p class="muted ib-pick">Pick an item to see the details.</p>`; return; }
  const s = i.subject;
  $("ib-detail").innerHTML = `<button type="button" class="btn btn-quiet back-link" data-ib-back>${icon("back")} Inbox</button>
    <div class="ib-dh"><span class="ib-ic k-${TONE[i.level] || "info"}">${icon(ICON[i.category] || "alarm")}</span>
      <div><p class="ib-kicker">${esc(when(i.at))} · ${i.need ? "Needs action" : i.resolved ? "Fixed since" : "For your information"}</p><h2>${esc(i.title)}</h2></div></div>
    ${(i.lines || []).map((l) => `<p>${esc(l)}</p>`).join("")}
    ${s ? `<p class="ib-about"><span class="muted">${esc({ campaign: "Campaign", adset: "Ad set", ad: "Ad" }[s.level] || "About")}:</span> ${entityLink(s.level, s.id, s.name)}</p>` : ""}
    <div class="row">${action(i)}${i.unread ? '<button class="btn" type="button" data-read>Mark read</button>' : ""}</div>
    <p class="ib-keys">Keys: J and K move, E marks read. Anything that spends money still opens its confirmation.</p>`;
}

async function markRead(keys) {
  const fresh = data.items.filter((i) => keys.includes(i.key) && i.unread);
  if (!fresh.length) return;
  try {
    await api("/api/inbox/read", { method: "POST", body: { keys: fresh.map((i) => i.key) } });
    const c = data.counts;
    fresh.forEach((i) => {
      i.unread = false;
      c.unread = Math.max(0, (c.unread || 0) - 1);
      if (i.need) c.need_unread = Math.max(0, (c.need_unread || 0) - 1); else c.fyi_unread = Math.max(0, (c.fyi_unread || 0) - 1);
    });
    setInboxCount(c.need_unread);
  } catch (err) { toast(err.message, "bad"); }
}

async function load() {
  const superseded = startLoad("inbox");
  const d = await api(`/api/inbox?${query()}`);
  if (superseded()) return;
  const before = newList ? null : shownItem();
  newList = false;
  data = d;
  if (linked && !data.items.some((i) => i.key === linked) && (box !== "all" || kind !== "all" || unreadOnly)) {  // a read or FYI item named by a link
    box = "all"; kind = "all"; unreadOnly = false; writeUrl(); return load();
  }
  linked = null;
  if (data.items.some((i) => i.key === current)) kept = null;
  else if (before && before.key === current) kept = before;
  else { kept = null; current = covers() ? null : data.items[0]?.key || null; }
  renderFilters(); renderList(); renderDetail();
  $("ib-panel").classList.toggle("showing-detail", Boolean(covers() && current && itemInUrl() === current));
}

// A new box or filter starts a new list: the open item and its #item= go, and the list shows its first item.
function newFilter() {
  linked = null; kept = null; newList = true;
  if (covers()) current = null;
  leaveLayer();
  writeUrl({ clearItem: true });
  $("ib-panel").classList.remove("showing-detail");
  load().catch((err) => toast(err.message, "bad"));
}
$("ib-box").addEventListener("click", (e) => {
  const b = e.target.closest("[data-box]");
  if (b) { box = b.dataset.box; newFilter(); }
});
$("ib-filters").addEventListener("click", (e) => {
  const b = e.target.closest("[data-f], [data-unread]");
  if (!b) return;
  if (b.dataset.f) kind = b.dataset.f; else unreadOnly = !unreadOnly;
  newFilter();
});
$("ib-list").addEventListener("click", (e) => {
  if (e.target.closest("[data-goto-box]")) { box = e.target.closest("[data-goto-box]").dataset.gotoBox; newFilter(); }
  if (e.target.closest("[data-clear-filters]")) { kind = "all"; unreadOnly = false; newFilter(); }
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
  const acc = e.target.closest("[data-accept]");
  if (acc) { acceptSheet([Number(acc.dataset.accept)], () => load().catch((err) => toast(err.message, "bad"))); return; }
  if (e.target.closest("[data-read]")) markRead([current]).then(() => { renderFilters(); renderList(); renderDetail(); });
  const done = e.target.closest("[data-done]");
  if (done) {
    done.disabled = true;
    api(`/api/alerts/${encodeURIComponent(done.dataset.done)}/done`, { method: "POST", body: {} })
      .then(() => markRead([current])).then(() => { toast("Done: it moves to For your information"); return load(); })
      .then(() => setInboxCount(data.counts.need_unread))
      .catch((err) => { toast(err.message, "bad"); done.disabled = false; });
  }
});
$("ib-all").addEventListener("click", async () => {
  try {
    await api("/api/inbox/read", { method: "POST", body: { all: true, kind, box } });
    toast("All marked read");
    await load();
    setInboxCount(data.counts.need_unread);
  } catch (err) { toast(err.message, "bad"); }
});
// E marks the item under the keyboard (or the open one) read. Nothing else: no opening, no accepting.
document.addEventListener("keydown", (e) => {
  if (e.key !== "e" || e.metaKey || e.ctrlKey || e.altKey || editing()) return;
  const key = e.target.closest?.("#ib-list [data-key]")?.dataset.key || current;
  const i = data.items.find((x) => x.key === key);
  if (!i) return;
  e.preventDefault();
  if (!i.unread) return;
  markRead([key]).then(() => { renderFilters(); renderList(); renderDetail(); document.querySelector(`#ib-list [data-key="${CSS.escape(key)}"]`)?.focus({ preventScroll: true }); toast("Marked read"); });
});

me = await boot({ page: "inbox" });
if (me) {
  onRefresh(load);
  load().catch((err) => errorState($("ib-list"), err, load));
}
