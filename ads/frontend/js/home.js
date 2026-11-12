import { api } from "./api.js";
import { boot, confirmDialog, entityLink, esc, icon, onRefresh, skeleton, toast, when, editing, showLoadError, withFrom } from "./ui.js";
import { money, per, plural } from "./format.js";

const $ = (id) => document.getElementById(id);
let me;

const greeting = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"; };
const initials = (name) => (name || "?").split(/\s+/).filter(Boolean).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
const shortAd = (name) => (name || "").split(/\s+-\s+|\s+/)[0];

// The lead clock: teal under 5 minutes, amber up to an hour, rust after that.
function leadClock(iso, now = Date.now()) {
  const mins = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60000));
  const tone = mins < 5 ? "fresh" : mins < 60 ? "warm" : "late";
  const text = mins < 60 ? `${mins} min` : mins < 48 * 60 ? `${Math.floor(mins / 60)} h` : `${Math.floor(mins / 1440)} d`;
  return `<span class="lclock ${tone}">${icon(tone === "late" ? "alarm" : "clock")}${text}${tone === "fresh" ? ", new" : " waiting"}</span>`;
}

const ATT_ICON = { leads: "missed", claude: "spark", money: "chart", status: "ads", system: "alarm" };

function render(d) {
  const attention = d.attention.length
    ? `<ul class="attention" aria-label="Needs you">${d.attention.map((a) => `<li class="${a.level}">${icon(ATT_ICON[a.kind] || "alarm")}<span>${esc(a.text)}</span>${a.href ? `<a class="btn" href="${esc(a.href)}">${esc(a.action || "Open")}</a>` : ""}</li>`).join("")}</ul>`
    : `<p class="all-clear">${icon("spark")}<span>Nothing needs you right now.</span></p>`;

  const call = d.call.length
    ? `<ol>${d.call.map((l) => {
        const mins = (Date.now() - new Date(l.created_time).getTime()) / 60000;
        return `<li>
          <span class="initials ${mins < 5 ? "fresh" : ""}" aria-hidden="true">${esc(initials(l.full_name))}</span>
          <div class="who"><a class="who-link" href="/leads.html#lead=${l.id}"><b>${esc(l.full_name || "Unnamed")}</b></a>
            <span><em>${esc(l.business_type || "No business given")}</em>${l.ad_name ? `<span class="via">via ${entityLink("ad", l.ad_id, shortAd(l.ad_name))}</span>` : ""}</span></div>
          ${leadClock(l.created_time)}
          ${l.phone ? `<a class="btn btn-call" href="tel:${esc(l.phone)}">${icon("phone")}Call</a>` : `<a class="btn btn-call" href="/leads.html#lead=${l.id}">Open</a>`}
          ${l.email ? `<a class="btn mail" href="mailto:${esc(l.email)}" aria-label="Email ${esc(l.full_name || "")}">${icon("mail")}</a>` : ""}
        </li>`;
      }).join("")}</ol>`
    : '<p class="empty-call">Everyone has been contacted. New leads appear here the moment they arrive.</p>';
  const st = d.stages || {};
  const callCard = `<section class="panel call" aria-labelledby="h-call">
    <div class="card-head"><h2 id="h-call">Call these first</h2><span class="hint">${d.waiting ? `${plural(d.waiting, "new lead")}, longest wait on top` : "no one waiting"}</span><a class="more" href="/leads.html">All leads</a></div>
    ${call}
    <div class="call-foot"><span><b>${st.contacted || 0}</b> contacted</span><span><b>${st.qualified || 0}</b> qualified</span><span><b>${st.won || 0}</b> won</span><span class="muted">this week</span>
      <span class="advice">Call within 5 minutes: far more of them book</span></div>
  </section>`;

  const budget = d.daily_budget_cents;
  const spentPct = budget ? Math.min(d.today.spend_cents / budget, 1) * 100 : 0;
  const y = d.yesterday;
  const moneyCard = `<section class="panel money" aria-labelledby="h-money">
    <h2 id="h-money">Money</h2>
    <div>
      <div class="row-top"><span>Spent today</span><small>${d.today.as_of ? `as of ${new Date(d.today.as_of * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}` : ""}</small></div>
      <div class="big"><b>${money(d.today.spend_cents, { exact: true })}</b>${budget ? `<span>of ${money(budget)} a day</span>` : ""}</div>
      ${budget ? `<div class="bar ink"><i data-w="${spentPct.toFixed(1)}"></i></div>` : ""}
      <p class="note-line">${plural(d.today.leads, "lead")} so far. Today keeps filling in; Meta reports late.</p>
    </div>
    <dl>
      <div><dt>Yesterday</dt><dd class="v">${y ? money(y.spend_cents, { exact: true }) : "—"}</dd><dd class="s">${y ? plural(y.leads, "lead") : "no data yet"}</dd></div>
      <div><dt>Cost per lead</dt><dd class="v">${per(d.week.spend_cents, d.week.leads)}</dd><dd class="s">last 7 days, ${plural(d.week.leads, "lead")}</dd></div>
    </dl>
    <a class="btn" href="/performance.html">See all results</a>
  </section>`;

  const strip = d.ad_strip || [];
  const best = strip.reduce((b, a) => (a.leads > (b ? b.leads : 0) ? a : b), null);
  const onCount = strip.filter((a) => a.status === "ACTIVE").length;
  const adsCard = `<section class="panel strip" aria-labelledby="h-ads">
    <div class="card-head"><h2 id="h-ads">Ads</h2><span class="on-count">${onCount} on</span><a class="more" href="/ads.html">Manage</a></div>
    ${strip.length ? `<ul class="thumbs">${strip.slice(0, 5).map((a) => `<li><a href="/ad.html?id=${esc(a.id)}">
        <div class="t ${a.status === "ACTIVE" ? "" : "off"} ${best && best.id === a.id ? "best" : ""}">${a.thumbnail_url ? `<img src="${esc(a.thumbnail_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ""}<span>${esc(shortAd(a.name))}</span></div>
        <p class="${best && best.id === a.id ? "best" : ""}">${plural(a.leads, "lead")}</p><small>${money(a.spend_cents, { exact: true })}</small></a></li>`).join("")}</ul>
      <p class="judge">Last 7 complete days. Judge an ad after it has spent about twice your target cost per lead.</p>`
      : '<p class="muted flush">No ads synced yet.</p>'}
  </section>`;

  let claudeCard = "";
  if (d.desk) {
    const mac = d.bridge.online ? '<span class="mac-dot on">Mac connected</span>' : `<span class="mac-dot">${d.bridge.has_key ? "Mac offline" : "Mac not set up"}</span>`;
    const lastDone = d.desk.find((t) => t.status === "done" && t.summary);
    const pend = d.pending_proposals || 0;
    claudeCard = `<section class="panel claude-card" aria-labelledby="h-claude">
      <div class="card-head">${icon("spark")}<h2 id="h-claude">Claude</h2>${mac}</div>
      <p>${lastDone ? esc(lastDone.summary) : "Ask for a review, a polish audit or new ad ideas."}</p>
      <a class="btn" href="/desk.html">${pend ? `Review ${plural(pend, "idea")}` : "Ask Claude"}</a>
    </section>`;
  }

  const LEVEL = { campaign: "campaign", adset: "ad set", ad: "ad", study: "A/B test", form: "lead form", account: "account" };
  const changes = d.changes.length
    ? `<ul class="chg-list">${d.changes.slice(0, 4).map((c) => {
        const [cls, ic, what] = changeWords(c, LEVEL);
        return `<li class="ic ${cls}">${icon(ic)}<span>${what}${c.ok ? "" : ' <b class="bad-text">(Meta refused)</b>'}<small>${esc(when(c.created_at))}${c.user_name ? `, ${esc(c.user_name)}` : ""}</small></span></li>`;
      }).join("")}</ul>`
    : '<p class="muted flush">No changes made from the dashboard yet.</p>';
  // Today → Inbox: the latest unread (Meta's approvals and rejections, leads, Claude, money), then what you changed.
  const inReview = (d.ads?.IN_PROCESS || 0) + (d.ads?.PENDING_REVIEW || 0);
  const changesCard = `<section class="panel changes-card" aria-labelledby="h-changes"><div class="card-head"><h2 id="h-changes">Inbox</h2>
      ${inReview ? `<span class="pill warn">${inReview} in review</span>` : ""}<a class="more" href="/inbox.html">Open Inbox</a></div>
    <ul class="today-inbox" id="today-inbox"><li>${skeleton()}</li></ul>
    <details class="today-changes"><summary>Changes made from the console</summary>${changes}</details></section>`;

  const adviceCard = d.bridge ? `<section class="panel advice-card" aria-labelledby="h-advice" id="advice"><div class="card-head"><h2 id="h-advice">Meta's advice</h2></div><p class="muted flush">Reading from Meta…</p></section>` : "";
  $("home").innerHTML = `${attention}<div class="today">${callCard}${moneyCard}${adsCard}${claudeCard}${changesCard}${adviceCard}</div>`;
  if (adviceCard) loadAdvice();
  api("/api/inbox?filter=unread").then((ib) => {
    const el = $("today-inbox");
    if (!el) return;
    const tone = { bad: "bad", warn: "warn", ok: "ok", lead: "ok", claude: "claude" };
    const live = ib.items.filter((i) => !i.resolved);
    el.innerHTML = live.length ? live.slice(0, 5).map((i) => `<li><a href="${esc(i.href || "/inbox.html")}"><span class="tone-dot ${tone[i.level] || ""}" aria-hidden="true"></span><span><b>${esc(i.title)}</b><small>${esc(when(i.at))}</small></span></a></li>`).join("")
      + (live.length > 5 ? `<li class="muted small">${live.length - 5} more in the Inbox</li>` : "")
      : '<li class="muted">Nothing new. Approvals, rejections and new leads show up here.</li>';
  }).catch(() => { const el = $("today-inbox"); if (el) el.innerHTML = ""; });
  if (!claudeCard) $("home").querySelector(".changes-card").classList.add("wide");
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
async function load() {
  loadedAt = Date.now();
  try { render(await api("/api/home")); } catch (err) { showLoadError($("home"), err, load); }
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
      const step = b && b.from ? `<p class="flush small ${b.big ? "bad-text" : "muted"}">${money(b.from, { exact: true })} → ${money(b.to, { exact: true })} a day (+${b.pct}%)${b.big ? ": more than +20%, so Meta may restart learning and results can wobble for a few days." : "."}</p>` : "";
      return `<li>
        <div class="advice-text"><span class="ttl"><b>${esc(r.label)}</b>${r.points ? `<span class="pill">+${r.points} points</span>` : ""}</span>
          ${r.lift ? `<p class="flush">${esc(r.lift)}</p>` : ""}${step}
          ${r.note ? `<p class="flush muted small">${esc(r.note)}</p>` : ""}</div>
        <div class="advice-do">${r.can_apply ? `<button type="button" class="btn btn-small" data-apply="${esc(r.signature)}" data-label="${esc(r.label)}" data-big="${b && b.big ? "1" : ""}" data-step="${b && b.from && b.to ? `${money(b.from, { exact: true })} → ${money(b.to, { exact: true })} a day` : ""}" data-to="${b && b.to ? b.to : ""}" data-does="${esc(r.applies || "")}">Apply</button>` : ""}
          ${r.can_fix ? fixButton(r) : ""}
          ${r.url ? `<a class="btn btn-quiet btn-small" href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">Ads Manager ${icon("external")}</a>` : ""}</div>
      </li>`;
    }).join("")}</ul>` : '<p class="muted flush">No suggestions from Meta right now.</p>';
  const bm = a.benchmarks;
  const bench = bm ? `<div class="bench"><h3>How you compare</h3>${bm.summary ? `<p class="flush">${esc(bm.summary)}</p>` : ""}
      <table class="table middle"><thead><tr><th></th><th class="num">You</th><th class="num">Similar advertisers</th><th></th></tr></thead>
      <tbody>${bm.items.map((i) => `<tr><th scope="row">${esc(i.label)}</th><td class="num">${esc(i.ours)}</td><td class="num">${esc(i.peers)}</td><td class="muted small">${esc(i.note)}</td></tr>`).join("")}</tbody></table>
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
  if (run && ["queued", "claimed", "running"].includes(run.status)) {
    return `<a class="btn btn-quiet btn-small" href="/desk.html#r/${run.id}">${icon("spark")}${run.status === "queued" ? "Waiting for your Mac" : "Claude is on it"}</a>`;
  }
  if (run && run.waiting) {
    return `<a class="btn btn-claude btn-small" href="/desk.html#waiting">${icon("spark")}${run.waiting} to accept</a>`;
  }
  return `<button type="button" class="btn btn-claude-outline btn-small" data-fix="${esc(r.key)}" data-label="${esc(r.label)}" data-plan="${esc(r.fix)}">${icon("spark")}${run ? "Fix again with Claude" : "Fix with Claude"}</button>`;
}

async function loadAdvice(fresh = false) {
  const box = document.getElementById("advice");
  if (!box) return;
  try { box.innerHTML = adviceHtml(await api(`/api/advice${fresh ? "?fresh=1" : ""}`)); }
  catch (err) { box.innerHTML = `<div class="card-head"><h2>Meta's advice</h2></div><p class="muted flush">${esc(err.message)}</p>`; }
}

document.addEventListener("click", async (e) => {
  if (e.target.closest("#advice-fresh")) { loadAdvice(true); return; }
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
  const yes = await confirmDialog({
    title: `Apply “${b.dataset.label}”?`,
    body: `<p>${esc(b.dataset.does || "Meta applies it to the account.")}</p>${b.dataset.step ? `<p><b>${esc(b.dataset.step)}</b></p>` : ""}${big ? '<p class="note warn">More than +20% in one step: Meta may restart learning and results can wobble for a few days. The usual rule here is +20% at most, three days apart.</p>' : ""}`,
    confirm: big ? "Apply anyway" : "Apply", danger: big,
  });
  if (!yes) return;
  b.disabled = true;
  try {
    document.getElementById("advice").innerHTML = adviceHtml(await api("/api/advice/apply", { method: "POST", body: { signature: b.dataset.apply, accept_big: big, confirm_to: b.dataset.to ? Number(b.dataset.to) : null } }));
    toast("Applied on Meta");
  } catch (err) {
    toast(err.message, "bad");
    b.disabled = false;
    if (err.body && err.body.fresh) document.getElementById("advice").innerHTML = adviceHtml(err.body.fresh);
  }
});
