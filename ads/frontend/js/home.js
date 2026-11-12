import { api } from "./api.js";
import { acceptSheet } from "./decide.js";
import { boot, confirmDialog, entityLink, esc, icon, leadClock, onRefresh, toast, when, editing, showLoadError, withFrom } from "./ui.js";
import { money, per, plural } from "./format.js";
import { alertButtons, moreButton, runChip, wireAlerts } from "./alertmenu.js";

const $ = (id) => document.getElementById(id);
let me;

const greeting = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"; };
const shortAd = (name) => (name || "").split(/\s+-\s+|\s+/)[0];

// Today is one ranked queue (the server's today.rank): the Inbox's Needs action, never its FYI, with the
// leads to call first. Groups keep the server's order; each thing shows once.
const GROUPS = {
  call: ["Call first", "the first hour matters most, then the longest wait"],
  problems: ["Fix", ""],
  follow: ["Follow up", ""],
  decide: ["Decide", "nothing changes until you accept"],
  money: ["Money", ""],
  system: ["Keep it running", ""],
  later: ["Later today", ""],
};
const ICON = { status: "ads", leads: "leads", claude: "spark", money: "chart", system: "alarm" };
const TONE = { bad: "bad", warn: "warn", ok: "ok", info: "info", claude: "claude" };

function actionLabel(r) {
  if (r.action) return r.action;
  const h = r.href || "";
  return h.startsWith("/ad.html") ? "Open the ad" : h.startsWith("/adset.html") ? "Open the ad set" : h.startsWith("/campaign.html") ? "Open the campaign"
    : h.startsWith("/settings") ? "Open Settings" : "Open";
}

function leadRow(r) {
  const l = r.lead;
  const from = l.ad_name ? ` · from ${entityLink("ad", l.ad_id, shortAd(l.ad_name))}` : "";
  return `<li class="tq-row tq-lead" data-key="${esc(r.key)}">
    ${leadClock({ urgency: r.level, created_time: l.created_time })}
    <div class="tq-b"><a class="tq-name" href="${esc(r.href)}"><b>${esc(r.title)}</b></a><p>${esc(r.line || "No business given")}${from}</p></div>
    <div class="tq-acts">${l.phone ? `<a class="btn btn-call" href="tel:${esc(l.phone)}">${icon("phone")}Call</a>` : `<a class="btn" href="${esc(r.href)}">Open</a>`}
      ${l.email ? `<a class="btn tq-mail" href="mailto:${esc(l.email)}" aria-label="Email ${esc(r.title)}">${icon("mail")}</a>` : ""}</div>
  </li>`;
}

function itemRow(r) {
  const s = r.subject;
  // The thing it is about links to its page, named once (a suggestion's line is that name already).
  const link = s && !(r.title || "").includes(s.name) ? entityLink(s.level, s.id, s.name) : "";
  const text = r.line && !(s && r.line === s.name) ? esc(r.line) : "";
  const line = text || link ? `<p${text ? "" : ' class="tq-about"'}>${[text, link].filter(Boolean).join(" · ")}</p>` : "";
  let acts;
  if (r.proposal_id) {
    acts = `<button type="button" class="btn btn-claude" data-accept="${r.proposal_id}">Review</button>`
      + (me.role === "admin" ? `<a class="btn btn-quiet" href="${esc(r.href)}">Conversation</a>` : "");
  } else {
    acts = r.href ? `<a class="btn" href="${esc(r.href)}">${esc(actionLabel(r))}</a>` : "";
    // Admins: Diagnose with Claude and Got it… beside it on a computer, in one ⋯ on a phone (rows keep one button).
    const more = alertButtons(r);
    if (more) acts += `<span class="al-inline">${more}</span>${moreButton(r)}`;
  }
  return `<li class="tq-row" data-key="${esc(r.key)}"><span class="tq-ic k-${TONE[r.level] || "info"}">${icon(ICON[r.category] || "alarm")}</span>
    <div class="tq-b"><b>${esc(r.title)}</b>${line}</div><div class="tq-acts">${acts}</div></li>`;
}

function queueHtml(d) {
  const q = d.queue;
  if (!q.length) return `<p class="tq-clear">${icon("spark")}<span>Nothing needs you right now.</span></p>`;
  const groups = [...new Set(q.map((r) => r.group))];
  return groups.map((g) => {
    const rows = q.filter((r) => r.group === g);
    const [title, hint] = GROUPS[g] || ["Other", ""];
    const ids = rows.filter((r) => r.proposal_id).map((r) => r.proposal_id);
    const all = g === "decide" && ids.length > 1 ? `<button type="button" class="link-btn" data-accept-all="${ids.join(",")}">Review all ${ids.length}</button>` : "";
    const more = g === "call" && d.waiting_calls > rows.length
      ? `<li class="tq-more"><a href="/leads.html">${plural(d.waiting_calls - rows.length, "more lead")} waiting for a first call</a></li>` : "";
    return `<section class="tq-group" aria-labelledby="tq-${g}"><h2 class="tq-h" id="tq-${g}">${title}${hint ? ` <small>${hint}</small>` : ""}<span class="spacer"></span>${all}</h2>
      <ul>${rows.map((r) => (r.group === "call" ? leadRow(r) : itemRow(r))).join("")}${more}</ul></section>`;
  }).join("");
}

function lede(d) {
  const n = (g) => d.queue.filter((r) => r.group === g).length;
  const parts = [];
  if (d.waiting_calls) parts.push(`${plural(d.waiting_calls, "person", "people")} to call`);
  if (n("problems")) parts.push(`${plural(n("problems"), "problem")} to fix`);
  if (n("decide")) parts.push(`${plural(n("decide"), "thing")} to decide`);
  const first = parts.length ? parts.slice(0, -1).join(", ") + (parts.length > 1 ? " and " : "") + parts[parts.length - 1] + "." : "Nothing needs you right now.";
  const on = d.ads?.ACTIVE || 0;
  return `${first.charAt(0).toUpperCase()}${first.slice(1)} ${on ? `${plural(on, "ad")} delivering.` : "No ads are delivering."}`;
}

function render(d) {
  $("today-lede").textContent = lede(d);
  const fyi = d.fyi_unread ? `${plural(d.fyi_unread, "new note")} for your information, like approvals and changes made in Ads Manager.` : "Approvals, changes made in Ads Manager and other notes for your information stay in the Inbox.";
  const queueCard = `<section class="panel tq" aria-label="What needs you, most urgent first">${queueHtml(d)}
    ${d.snoozed ? `<p class="tq-foot al-snoozed-line">${plural(d.snoozed, "snoozed alert")}. <a href="/inbox.html?box=fyi">See them</a></p>` : ""}
    <p class="tq-foot">${fyi} <a href="/inbox.html?box=fyi">Open the Inbox</a></p></section>`;

  const budget = d.daily_budget_cents;
  const spentPct = budget ? Math.min(d.today.spend_cents / budget, 1) * 100 : 0;
  const y = d.yesterday;
  const asOf = d.today.as_of ? `as of ${new Date(d.today.as_of * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}` : "";
  const moneyCard = `<section class="panel td-sec" aria-labelledby="h-money">
    <div class="td-sec-h"><h2 id="h-money">Money</h2><small>${asOf}</small></div>
    <p class="td-big"><b>${money(d.today.spend_cents, { exact: true })}</b><span>spent today${budget ? ` of ${money(budget)} a day` : ""}</span></p>
    ${budget ? `<div class="bar ink"><i data-w="${spentPct.toFixed(1)}"></i></div>` : ""}
    <p class="td-note">${plural(d.today.leads, "lead")} so far. Today keeps filling in; Meta reports late.</p>
    <dl class="td-stats">
      <div><dt>Yesterday</dt><dd>${y ? `${money(y.spend_cents, { exact: true })} · ${plural(y.leads, "lead")}` : "no data yet"}</dd></div>
      <div><dt>Leads, last 7 days</dt><dd>${d.week.leads ?? 0}</dd></div>
      <div><dt>Cost per lead</dt><dd>${per(d.week.spend_cents, d.week.leads)}</dd></div>
    </dl>
    <a class="btn" href="/performance.html">See all results</a>
  </section>`;

  const st = d.stages || {};
  const leadsCard = `<section class="panel td-sec" aria-labelledby="h-week">
    <div class="td-sec-h"><h2 id="h-week">Leads this week</h2><a class="more" href="/leads.html">All leads</a></div>
    <dl class="td-stats"><div><dt>Contacted</dt><dd>${st.contacted || 0}</dd></div><div><dt>Qualified</dt><dd>${st.qualified || 0}</dd></div><div><dt>Won</dt><dd>${st.won || 0}</dd></div></dl>
    <p class="td-note">Call within 5 minutes: far more of them book.</p>
  </section>`;

  const strip = d.ad_strip || [];
  const best = strip.reduce((b, a) => (a.leads > (b ? b.leads : 0) ? a : b), null);
  const inReview = (d.ads?.IN_PROCESS || 0) + (d.ads?.PENDING_REVIEW || 0);
  const adsCard = `<section class="panel td-sec" aria-labelledby="h-ads">
    <div class="td-sec-h"><h2 id="h-ads">Ads</h2><span class="on-count">${d.ads?.ACTIVE || 0} on</span>${inReview ? `<span class="pill warn">${inReview} in review</span>` : ""}<a class="more" href="/ads.html">Manage</a></div>
    ${strip.length ? `<ul class="td-onair">${strip.slice(0, 5).map((a) => `<li><a href="/ad.html?id=${esc(a.id)}" aria-label="${esc(a.name)}: ${plural(a.leads, "lead")}, ${money(a.spend_cents, { exact: true })}">
        <span class="t ${a.status === "ACTIVE" ? "" : "off"} ${best && best.id === a.id ? "best" : ""}">${a.thumbnail_url ? `<img src="${esc(a.thumbnail_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ""}<span>${esc(shortAd(a.name))}</span></span>
        <b>${plural(a.leads, "lead")}</b><small>${money(a.spend_cents, { exact: true })}</small></a></li>`).join("")}</ul>
      <p class="td-note">Last 7 complete days. Judge an ad after it has spent about twice your target cost per lead.</p>`
      : '<p class="td-note">No ads synced yet.</p>'}
  </section>`;

  let claudeCard = "";
  if (d.desk) {
    const m = d.bridge.status || { state: "", title: "", detail: "" };
    const mac = `<span class="mac-dot ${["offline", "not_set_up", "sign_in"].includes(m.state) ? "" : "on"}" title="${esc(m.detail)}">${esc(m.title)}</span>`;
    const lastDone = d.desk.find((t) => t.status === "done" && t.summary);
    const pend = d.pending_proposals || 0;
    claudeCard = `<section class="panel td-sec td-claude" aria-labelledby="h-claude">
      <div class="td-sec-h">${icon("spark")}<h2 id="h-claude">Claude</h2>${mac}</div>
      <p class="td-note">${lastDone ? esc(lastDone.summary) : "Ask for a review, a polish audit or new ad ideas."}</p>
      <a class="btn btn-claude-outline" href="/desk.html">${pend ? `Open ${plural(pend, "suggestion")}` : "Ask Claude"}</a>
    </section>`;
  }

  const LEVEL = { campaign: "campaign", adset: "ad set", ad: "ad", study: "A/B test", form: "lead form", account: "account" };
  const changes = d.changes.length
    ? `<ul class="chg-list">${d.changes.slice(0, 6).map((c) => {
        const [cls, ic, what] = changeWords(c, LEVEL);
        return `<li class="ic ${cls}">${icon(ic)}<span>${what}${c.ok ? "" : ' <b class="bad-text">(Meta refused)</b>'}<small>${esc(when(c.created_at))}${c.user_name ? `, ${esc(c.user_name)}` : ""}</small></span></li>`;
      }).join("")}</ul>`
    : '<p class="td-note">No changes made from the dashboard yet.</p>';
  const changesCard = `<details class="panel td-sec today-changes"><summary>Changes made from the console</summary>${changes}</details>`;

  const adviceCard = d.bridge ? `<section class="panel advice-card" aria-labelledby="h-advice" id="advice"><div class="card-head"><h2 id="h-advice">Meta's advice</h2></div><p class="muted flush">Reading from Meta…</p></section>` : "";
  const keepAdvice = $("advice");  // a refresh keeps what Meta said instead of reading it again
  const changesOpen = $("home").querySelector(".today-changes")?.open;
  $("home").innerHTML = `<div class="td-layout"><div class="td-main">${queueCard}${adviceCard}</div>
    <aside class="td-side" aria-label="The day at a glance">${moneyCard}${leadsCard}${adsCard}${claudeCard}${changesCard}</aside></div>`;
  if (adviceCard) {
    if (keepAdvice && keepAdvice.dataset.loaded) $("advice").replaceWith(keepAdvice);
    else loadAdvice();
  }
  if (changesOpen) $("home").querySelector(".today-changes").open = true;
  $("home").querySelectorAll("[data-w]").forEach((i) => { i.style.width = `${i.dataset.w}%`; });
}

// Today → Changes: each kind of change in its own words (audit A21).
function changeWords(c, LEVEL) {
  // The thing changed links to its page (a deleted ad has none left).
  const name = c.action !== "delete" && ["campaign", "adset", "ad", "form"].includes(c.level) ? entityLink(c.level, c.entity_id, c.entity_name || "") : esc(c.entity_name || "");
  const lvl = LEVEL[c.level] || c.level || "";
  const short = (v) => esc(String(v || "").slice(0, 80));
  switch (c.action) {
    case "status": return [c.new_value === "ACTIVE" ? "on" : "", "power", `<b>${c.new_value === "ACTIVE" ? "Turned on" : "Turned off"}</b> ${lvl} “${name}”`];
    case "budget": return ["", "chart", `<b>Budget</b> “${name}”: ${money(Number(c.old_value), { exact: true })} → ${money(Number(c.new_value), { exact: true })}/day`];
    case "duplicate": return ["", "copy", `<b>Duplicated</b> “${short(c.old_value)}”`];
    case "create": return ["made", "made", `<b>Created</b> ${lvl} “${short(c.new_value)}”`];
    case "archive": return ["", "made", `<b>Archived</b> ad “${name}”`];
    case "delete": return ["", "made", `<b>Deleted</b> ad “${name}”`];
    case "rename": return ["", "made", `<b>Renamed</b> “${short(c.old_value)}” → “${short(c.new_value)}”`];
    case "comment_reply": return ["", "made", `<b>Replied</b> to a comment on “${name}”: “${short(c.new_value)}”`];
    case "comment_hide": return ["", "made", `<b>Hid</b> a comment on “${name}”`];
    case "comment_show": return ["", "made", `<b>Showed again</b> a comment on “${name}”`];
    case "recommendation": return ["", "spark", `<b>Applied Meta's suggestion</b> “${short(c.new_value)}”`];
    case "recommendation_check": return ["", "spark", `<b>Meta set a different amount</b> than shown: ${short(c.error)}`];
    case "placement_media": return ["", "spark", c.ok === false ? `<b>9:16 for Reels not added</b> to “${name}”: ${short(c.error)}` : `<b>Added a 9:16 video for Reels</b> to “${name}”`];
    case "update_creative": return ["", "spark", c.ok === false ? `<b>Update not made</b> on “${name}”: ${short(c.error)}` : `<b>Updated</b> “${name}”: ${short(String(c.new_value).replace(/ \(creative .*\)$/, ""))}`];
    case "restore_creative": return ["", "spark", c.ok === false ? `<b>Couldn't switch back</b> “${name}”: ${short(c.error)}` : `<b>Switched back</b> “${name}”: ${short(String(c.new_value).replace(/ \(creative .*\)$/, ""))}`];
    case "enhancement": return ["", "spark", `<b>Changed Meta's automatic changes</b> on “${name}”: ${short(String(c.new_value).replace(/ \(creative .*\)$/, ""))}`];
    case "end": return ["", "tests", `<b>Ended the A/B test</b> “${name}”`];
    case "upload": return ["", "image", `<b>Uploaded</b> ${short(c.new_value)} to the media library`];
    case "subscribe": return ["", "made", "<b>Connected the Page</b> to receive leads"];
    default: return ["made", "made", `<b>${esc((c.action || "Changed").replace(/_/g, " ").replace(/^./, (x) => x.toUpperCase()))}</b> ${lvl} “${name || short(c.new_value)}”`];
  }
}

let loadedAt = 0;
let shown = null;
async function load() {
  loadedAt = Date.now();
  try { shown = await api("/api/home"); render(shown); } catch (err) { showLoadError($("home"), err, load); }
}

me = await boot({ page: "home" });
if (me) {
  $("hello").textContent = `${greeting()}, ${me.name.split(" ")[0]}`;
  $("today-date").textContent = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
  if (me.role === "admin") { $("ask-claude").hidden = false; $("ask-claude").innerHTML = `${icon("spark")}<span>Ask Claude</span>`; }
  $("new-ad").innerHTML = `${icon("plus")}<span>New ad</span>`;
  $("new-ad").href = withFrom("/new-ad.html", "/home.html");
  // New leads every minute. Both this timer and the frame's catch-up fire on the same tick, so
  // whichever reloads second skips: the catch-up when Today loaded in the last 15 s (that load
  // already read what the server pulled), the timer when the catch-up reloaded in the last 50 s.
  onRefresh(load, { auto: () => (Date.now() - loadedAt < 15000 ? null : load()) });
  wireAlerts($("home"), (id) => (shown ? shown.queue.find((r) => r.alert_id === id) : null), load);
  load();
  setInterval(() => { if (!document.hidden && !editing() && Date.now() - loadedAt > 50000) load(); }, 60000);
}


// ---------------------------------------------------------------- Meta's advice (admins)

function adviceHtml(a) {
  const delta = a.previous_score != null && a.score != null && a.previous_score !== a.score
    ? ` <span class="${a.score > a.previous_score ? "good-text" : "bad-text"}">${a.score > a.previous_score ? "▲" : "▼"} ${Math.abs(a.score - a.previous_score)}</span>` : "";
  const score = a.score != null ? `<span class="opp-score" title="Meta's Opportunity Score: how closely the account follows its best practices"><b>${a.score}</b>/100${delta}</span>` : "";
  const items = a.items.length ? `<ul class="advice-list">${a.items.map((r) => {
      const b = r.budget;
      const step = b && b.from ? `<p class="flush small ${b.big || b.recent ? "bad-text" : "muted"}">${money(b.from, { exact: true })} → ${money(b.to, { exact: true })} a day (+${b.pct}%)${b.big ? ": more than +20%, so Meta may restart learning and results can wobble for a few days." : "."}${b.last_words ? ` · last change ${esc(b.last_words)}` : ""}</p>` : "";
      return `<li>
        <div class="advice-text"><span class="ttl"><b>${esc(r.label)}</b>${r.points ? `<span class="pill">+${r.points} points</span>` : ""}</span>
          ${r.lift ? `<p class="flush">${esc(r.lift)}</p>` : ""}${step}
          ${r.note ? `<p class="flush muted small">${esc(r.note)}</p>` : ""}</div>
        <div class="advice-do">${r.can_apply ? `<button type="button" class="btn btn-small" data-apply="${esc(r.signature)}" data-label="${esc(r.label)}" data-big="${b && b.big ? "1" : ""}" data-recent="${b && b.recent ? "1" : ""}" data-last="${esc(b && b.last_words ? b.last_words : "")}" data-step="${b && b.from && b.to ? `${money(b.from, { exact: true })} → ${money(b.to, { exact: true })} a day` : ""}" data-to="${b && b.to ? b.to : ""}" data-does="${esc(r.applies || "")}">Apply</button>` : ""}
          ${r.can_fix ? fixButton(r) : ""}
          ${r.url ? `<a class="btn btn-quiet btn-small" href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">Ads Manager ${icon("external")}</a>` : ""}</div>
      </li>`;
    }).join("")}</ul>` : '<p class="muted flush">No suggestions from Meta right now.</p>';
  const bm = a.benchmarks;
  const bench = bm ? `<div class="bench"><h3>How you compare</h3>${bm.summary ? `<p class="flush">${esc(bm.summary)}</p>` : ""}
      <table class="table middle"><thead><tr><th></th><th class="num">You</th><th class="num">Similar advertisers</th><th class="bench-note"></th></tr></thead>
      <tbody>${bm.items.map((i) => `<tr><th scope="row">${esc(i.label)}</th><td class="num">${esc(i.ours)}</td><td class="num">${esc(i.peers)}${i.note ? `<small class="bench-note-under">${esc(i.note)}</small>` : ""}</td><td class="muted small bench-note">${esc(i.note)}</td></tr>`).join("")}</tbody></table>
      <p class="muted small flush">From Claude's Monday summary, ${esc(bm.as_of)}.</p></div>`
    : '<p class="muted small flush bench-empty">Benchmarks against similar advertisers come with Claude\'s Monday summary (Claude → Schedules).</p>';
  return `<div class="card-head"><h2 id="h-advice">Meta's advice</h2>${score}<span class="spacer"></span>
      <button type="button" class="link-btn" id="advice-fresh">Check again</button></div>
    ${a.error_note ? `<p class="note warn">${esc(a.error_note)}</p>` : ""}${items}
    <p class="muted small flush">Only part of Meta's list comes through its API; Ads Manager may show more.${a.fetched_at ? ` Checked ${esc(when(a.fetched_at))}.` : ""}</p>
    ${bench}`;
}

// Advice the console can't apply goes to Claude on the Mac; its conversation and suggestions show here.
function fixButton(r) {
  const run = r.fix_run;
  // The run's state in the same words as Diagnose with Claude (alertmenu.runChip): waiting, working, N suggestions.
  if (run && (["queued", "claimed", "running"].includes(run.status) || run.waiting)) return runChip(run, { small: true, label: r.label });
  return `<button type="button" class="btn btn-claude-outline btn-small" data-fix="${esc(r.key)}" data-label="${esc(r.label)}" data-plan="${esc(r.fix)}">${icon("spark")}${run ? "Fix again with Claude" : "Fix with Claude"}</button>`;
}

async function loadAdvice(fresh = false) {
  const box = document.getElementById("advice");
  if (!box) return;
  try { box.innerHTML = adviceHtml(await api(`/api/advice${fresh ? "?fresh=1" : ""}`)); box.dataset.loaded = "1"; }
  catch (err) { box.innerHTML = `<div class="card-head"><h2>Meta's advice</h2></div><p class="muted flush">${esc(err.message)}</p>`; }
}

document.addEventListener("click", async (e) => {
  if (e.target.closest("#advice-fresh")) { loadAdvice(true); return; }
  // A decision opens the Accept sheet: Meta read fresh, money items never ticked for you, one by one.
  const acc = e.target.closest("[data-accept], [data-accept-all]");
  if (acc) {
    const ids = (acc.dataset.accept || acc.dataset.acceptAll).split(",").map(Number);
    acceptSheet(ids, load);
    return;
  }
  const fix = e.target.closest("[data-fix]");
  if (fix) {
    const yes = await confirmDialog({
      title: `Fix “${fix.dataset.label}” with Claude?`, claude: true, confirm: "Send to Claude",
      body: `<p>${esc(fix.dataset.plan)}</p><p class="muted">It runs on your Mac and can take a while. Nothing changes on Meta until you accept a suggestion on the Claude page.</p>`,
    });
    if (!yes) return;
    fix.disabled = true;
    try {
      const r = await api("/api/advice/fix", { method: "POST", body: { key: fix.dataset.fix } });
      toast(r.already ? "Claude is already on it" : "Sent to Claude. Follow it on the Claude page.");
      loadAdvice();
    } catch (err) { toast(err.message, "bad"); fix.disabled = false; }
    return;
  }
  const b = e.target.closest("[data-apply]");
  if (!b) return;
  const big = !!b.dataset.big;
  const recent = !!b.dataset.recent;
  const yes = await confirmDialog({
    title: `Apply “${b.dataset.label}”?`,
    body: `<p>${esc(b.dataset.does || "Meta applies it to the account.")}</p>${b.dataset.step ? `<p><b>${esc(b.dataset.step)}</b></p>` : ""}${big ? '<p class="note warn">More than +20% in one step: Meta may restart learning and results can wobble for a few days. The usual rule here is +20% at most, three days apart.</p>' : ""}${recent ? `<p class="note warn"><b>Less than 3 days since the last change</b> (${esc(b.dataset.last)}). Meta is still adjusting to it; another raise now makes results hard to read.</p>` : ""}`,
    confirm: recent ? "Raise anyway" : big ? "Apply anyway" : "Apply", danger: big || recent,
  });
  if (!yes) return;
  b.disabled = true;
  try {
    document.getElementById("advice").innerHTML = adviceHtml(await api("/api/advice/apply", { method: "POST", body: { signature: b.dataset.apply, accept_big: big, accept_recent: recent, confirm_to: b.dataset.to ? Number(b.dataset.to) : null } }));
    toast("Applied on Meta");
  } catch (err) {
    toast(err.message, "bad");
    b.disabled = false;
    if (err.body && err.body.fresh) document.getElementById("advice").innerHTML = adviceHtml(err.body.fresh);
  }
});
