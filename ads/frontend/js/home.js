import { api } from "./api.js";
import { boot, esc, icon, shortWait, toast, when } from "./ui.js";
import { count, money, per, plural } from "./format.js";
import { KIND_LABELS } from "./tasks.js";

const $ = (id) => document.getElementById(id);
let me;

const greeting = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"; };
const vs = (now, before, fmt) => (before == null ? "" : now === before ? "same as the day before" : `${now > before ? "up" : "down"} from ${fmt(before)}`);

function render(d) {
  const attention = d.attention.length
    ? `<ul class="attention">${d.attention.map((a) => `<li class="${a.level}"><span>${esc(a.text)}</span>${a.href ? `<a class="btn btn-small" href="${esc(a.href)}">${esc(a.action || "Open")}</a>` : ""}</li>`).join("")}</ul>`
    : `<p class="all-clear">${icon("spark")}<span>Nothing needs you right now.</span></p>`;

  const y = d.yesterday;
  const running = d.ads.ACTIVE || 0;
  const off = (d.ads.PAUSED || 0) + (d.ads.CAMPAIGN_PAUSED || 0) + (d.ads.ADSET_PAUSED || 0);
  const review = (d.ads.IN_PROCESS || 0) + (d.ads.PENDING_REVIEW || 0);
  const stopped = (d.ads.DISAPPROVED || 0) + (d.ads.WITH_ISSUES || 0);
  const figures = `<section class="panel figures home-figs" aria-label="At a glance">
    <div class="figure hero"><span class="label">Spent today so far</span><span class="value">${money(d.today.spend_cents, { exact: true })}</span>
      <span class="sub">${plural(d.today.leads, "lead")} so far${d.today.as_of ? ` · as of ${new Date(d.today.as_of * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}` : ""}. Meta reports late, so today keeps filling in.</span></div>
    <div class="figure"><span class="label">Yesterday</span><span class="value">${y ? money(y.spend_cents) : "—"}</span><span class="sub">${y ? `${plural(y.leads, "lead")} · ${vs(y.leads, y.prev_leads, count)}` : ""}</span></div>
    <div class="figure"><span class="label">Last 7 days</span><span class="value">${per(d.week.spend_cents, d.week.leads)}</span><span class="sub">per lead · ${plural(d.week.leads, "lead")} from ${money(d.week.spend_cents)}</span></div>
    <div class="figure"><span class="label">Ads</span><span class="value">${count(running)} on</span><span class="sub">${[off && `${off} off`, review && `${review} in review`, stopped && `${stopped} stopped by Meta`].filter(Boolean).join(" · ") || "&nbsp;"}</span></div>
  </section>`;

  const leads = d.leads.length
    ? `<ul class="lead-mini">${d.leads.map((l) => `<li><a href="/leads.html#lead=${l.id}"><b>${esc(l.full_name || "Unnamed")}</b><span>${esc(l.business_type || l.ad_name || "")}</span></a><span class="pill ${l.status}">${esc(l.status)}</span><small>${esc(shortWait(l.created_time))} ago${l.is_test ? " · test" : ""}</small></li>`).join("")}</ul>`
    : '<p class="muted flush">No leads yet. They appear here the moment Meta sends them.</p>';

  const LEVEL = { campaign: "campaign", adset: "ad set", ad: "ad" };
  const changes = d.changes.length
    ? `<ul class="changes">${d.changes.map((c) => {
        const what = c.action === "status" ? `${c.new_value === "ACTIVE" ? "Turned on" : "Turned off"} ${LEVEL[c.level]} “${c.entity_name}”`
          : c.action === "budget" ? `Budget of “${c.entity_name}”: ${money(Number(c.old_value), { exact: true })} → ${money(Number(c.new_value), { exact: true })}/day`
          : c.action === "duplicate" ? `Duplicated “${c.old_value}”` : `Created “${c.new_value}”`;
        return `<li><span>${esc(what)}${c.ok ? "" : ' <b class="bad-text">(Meta refused)</b>'}</span><small>${esc(when(c.created_at))}${c.user_name ? ` · ${esc(c.user_name)}` : ""}</small></li>`;
      }).join("")}</ul>`
    : '<p class="muted flush">No changes made from the dashboard yet.</p>';

  let claude = "";
  if (d.desk) {
    const mac = d.bridge.online ? '<span class="mac-status on">Mac connected</span>' : d.bridge.has_key ? '<span class="mac-status off">Mac offline</span>' : '<span class="mac-status off">Mac not set up</span>';
    claude = `<section class="panel claude-panel">
      <div class="panel-head"><h2>Claude</h2>${mac}<span class="spacer"></span><a class="btn btn-claude btn-small" href="/desk.html">${icon("spark")}<span>Ask Claude</span></a></div>
      <div class="panel-body">${d.desk.length ? `<ul class="desk-mini">${d.desk.map((t) => `<li><a href="/desk.html"><small>${esc(KIND_LABELS[t.kind] || t.kind)} · ${esc(t.status === "done" ? when(t.finished_at) : t.status)}</small><b>${esc(t.prompt)}</b>${t.summary ? `<span>${esc(t.summary)}</span>` : ""}</a></li>`).join("")}</ul>` : '<p class="muted flush">Ask a question, request a review or new ad ideas from the Desk.</p>'}</div>
    </section>`;
  }

  $("home").innerHTML = `
    <section class="panel"><div class="panel-head"><h2>Needs attention</h2></div><div class="panel-body">${attention}</div></section>
    ${figures}
    <div class="home-grid">
      <section class="panel"><div class="panel-head"><h2>Newest leads</h2><span class="spacer"></span><a class="small" href="/leads.html">All leads</a></div><div class="panel-body">${leads}</div></section>
      ${claude}
      <section class="panel"><div class="panel-head"><h2>Recent changes</h2><span class="spacer"></span><a class="small" href="/ads.html">Ads</a></div><div class="panel-body">${changes}</div></section>
    </div>`;
}

async function load() {
  try { render(await api("/api/home")); } catch (err) { toast(err.message, "bad"); }
}

me = await boot({ page: "home" });
if (me) {
  $("hello").textContent = `${greeting()}, ${me.name.split(" ")[0]}`;
  $("today-date").textContent = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
  load();
  setInterval(() => { if (!document.hidden) load(); }, 60000);
}
