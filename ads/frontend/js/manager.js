// The Ads manager: one table for campaigns, ad sets or ads (used by the Ads page and by the campaign
// and ad set pages). Built-in views, sortable columns, selection with a bulk bar (compare, on/off,
// budget, archive: every money move previewed and confirmed), and a peek drawer. File and class names
// avoid "ad"-like tokens: ad blockers hide those.
import { api } from "./api.js";
import { confirmDialog, esc, icon, switchHtml, toast, when } from "./ui.js";
import { columnChart } from "./charts.js";
import { editBudget, toggleEntity } from "./controls.js";
import { LEARNING, PROBLEM_STATES, REVIEW_STATES, count, money, moneyWhole, pct, per, statusOf } from "./format.js";

export const LEVEL_WORDS = { campaign: ["campaign", "campaigns"], adset: ["ad set", "ad sets"], ad: ["ad", "ads"] };
const isOn = (s) => s === "ACTIVE";
// Only these can still be switched or given a budget; deleted and archived ones are history.
export const LIVE = ["ACTIVE", "PAUSED"];
export const isTest = (r) => /\b(test|qa)\b|flow copy/i.test(r.name || "");
const learningOf = (r) => (r.level === "adset" ? r.learning_stage : r.adset?.learning_stage);
const lifetimeQuiet = (r) => r.level === "ad" && r.effective_status === "ACTIVE" && !r.lifetime_impressions;

export const VIEWS = {
  all: ["All", () => true],
  delivering: ["Delivering", (r) => r.effective_status === "ACTIVE"],
  review: ["In review", (r) => REVIEW_STATES.includes(r.effective_status) || r.effective_status === "PREAPPROVED"],
  attention: ["Needs attention", (r) => PROBLEM_STATES.includes(r.effective_status) || lifetimeQuiet(r) || r.pending_proposals > 0 || learningOf(r) === "FAIL"],
  learning: ["Learning", (r) => ["LEARNING", "FAIL"].includes(learningOf(r))],
  off: ["Off", (r) => r.status === "PAUSED"],
  tests: ["Tests", isTest],
};

// Rows for each level, each knowing its parents, from the /api/ads tree.
export function flatten(data) {
  const campaigns = [], adsets = [], ads = [];
  for (const c of data.campaigns) {
    campaigns.push(Object.assign(c, { level: "campaign" }));
    for (const s of c.adsets) {
      adsets.push(Object.assign(s, { level: "adset", campaign: c, can_control: c.can_control }));
      for (const a of s.ads) ads.push(Object.assign(a, { level: "ad", campaign: c, adset: s, can_control: c.can_control }));
    }
  }
  return { campaign: campaigns, adset: adsets, ad: ads };
}

const rate = (a, b) => (b ? a / b : null);
const cpl = (m) => (m && m.leads ? m.spend_cents / m.leads : null);
function delta(now, before, lowerBetter) {
  if (now == null || before == null || !before) return '<span class="delta d-mute">–</span>';
  const p = Math.round(((now - before) / before) * 100);
  if (!p) return '<span class="delta d-mute">0%</span>';
  const good = lowerBetter ? p < 0 : p > 0;
  return `<span class="delta ${good ? "d-good" : "d-bad"}">${p > 0 ? "+" : "−"}${Math.abs(p)}%</span>`;
}

// The signature: one bar per day of the last 14 complete days, whatever the dates picked; green = it
// spent that day; the last bar shows the review or rejection now.
function track(r) {
  const days = r.track || [];
  if (!days.length) return "";
  const last = REVIEW_STATES.includes(r.effective_status) ? "d-review" : PROBLEM_STATES.includes(r.effective_status) ? "d-bad" : null;
  return `<span class="trk" aria-hidden="true">${days.map((d, i) => `<i class="${i === days.length - 1 && last ? last : d.on ? "d-on" : ""}"></i>`).join("")}</span>`;
}

export function statusCell(r) {
  const [cls, label] = statusOf(r.effective_status);
  const learn = r.level === "adset" && LEARNING[r.learning_stage];
  return `<span class="st st-${cls || "mute"}">${esc(label)}</span>${learn ? `<span class="st st-${learn[0]} st-2">${esc(learn[1])}</span>` : ""}`;
}

function thumb(r) {
  const img = r.image_url || r.thumbnail_url;
  return img ? `<img class="tbl-th" src="${esc(img)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '<span class="tbl-th ph"></span>';
}

export function href(r) {
  return r.level === "ad" ? `/ad.html?id=${encodeURIComponent(r.id)}` : r.level === "adset" ? `/adset.html?id=${encodeURIComponent(r.id)}` : `/campaign.html?id=${encodeURIComponent(r.id)}`;
}

function nameCell(r) {
  const sub = r.level === "ad" ? r.adset?.name : r.level === "adset" ? r.campaign?.name : r.objective ? r.objective.replace("OUTCOME_", "").toLowerCase() : "Campaign";
  const tags = `${isTest(r) ? '<span class="mini-tag">Test</span>' : ""}${r.pending_proposals ? `<span class="mini-tag claude" title="Claude has an idea for this">${icon("spark")}</span>` : ""}`;
  return `<span class="tbl-name">${r.level === "ad" ? thumb(r) : ""}<span><span class="tbl-l1"><a href="${href(r)}" class="tbl-link">${esc(r.name)}</a>${tags}</span><small>${esc(sub || "")}</small></span></span>`;
}

function budgetCell(r) {
  const cents = r.daily_budget_cents;
  if (!cents) return '<span class="muted">—</span>';
  const label = `${money(cents, { exact: cents % 100 !== 0 })}/day`;
  return r.can_control && LIVE.includes(r.status) ? `<button type="button" class="chip" data-budget="${r.level}:${r.id}" data-current="${cents}" data-name="${esc(r.name)}" title="Change the daily budget">${esc(label)}</button>` : esc(label);
}

// "vs before" compares month ranges with the same days of the month before, other ranges with the days just before.
export const vsTitle = (range) => `Cost per lead against ${["mtd", "lastmonth"].includes(range) ? "the same days of the month before" : "the same number of days just before"}`;
const num = (key, label, value, show, opts = {}) => ({ key, label, num: true, sort: value, cell: (r) => show(r), ...opts });
const C = {
  name: { key: "name", label: "Name", sort: (r) => r.name.toLowerCase(), cell: nameCell, cls: "c-name" },
  status: { key: "status", label: "Delivery", sub: "last 14 days", sort: (r) => r.effective_status || "", cell: (r) => `${track(r)}${statusCell(r)}`, cls: "c-st" },
  budget: { key: "budget", label: "Budget", num: true, sort: (r) => r.daily_budget_cents || 0, cell: budgetCell },
  spend: num("spend", "Spent", (r) => r.m.spend_cents, (r) => money(r.m.spend_cents, { exact: true })),
  leads: num("leads", "Leads", (r) => r.m.leads || 0, (r) => count(r.m.leads)),
  cpl: num("cpl", "Per lead", (r) => cpl(r.m) ?? Infinity, (r) => `<b>${per(r.m.spend_cents, r.m.leads)}</b>`),
  vs: num("vs", "vs before", (r) => (r.prev && cpl(r.prev) && cpl(r.m) ? cpl(r.m) / cpl(r.prev) : Infinity), (r) => delta(cpl(r.m), cpl(r.prev), true), { title: vsTitle() }),
  qualified: num("qualified", "Qualified", (r) => r.m.qualified || 0, (r) => count(r.m.qualified)),
  ctr: num("ctr", "Click rate", (r) => -(rate(r.m.link_clicks, r.m.impressions) || 0), (r) => pct(r.m.link_clicks, r.m.impressions)),
  hook: num("hook", "Hook rate", (r) => -(rate(r.m.video_3s, r.m.video_impressions) || 0), (r) => (r.m.video_impressions ? pct(r.m.video_3s, r.m.video_impressions) : "—"), { title: "3-second views ÷ impressions of the video ads" }),
  hold: num("hold", "Hold", (r) => -(rate(r.m.thruplays, r.m.video_3s) || 0), (r) => pct(r.m.thruplays, r.m.video_3s), { title: "ThruPlays ÷ 3-second views" }),
  impressions: num("impressions", "Views", (r) => r.m.impressions || 0, (r) => count(r.m.impressions), { title: "Times it was shown (impressions)" }),
  reach: num("reach", "People", (r) => r.m.reach || 0, (r) => count(r.m.reach), { title: "Different people who saw it at least once" }),
  freq: num("freq", "Times each", (r) => rate(r.m.impressions, r.m.reach) || 0, (r) => (r.m.reach ? (r.m.impressions / r.m.reach).toFixed(2) : "—")),
  cpm: num("cpm", "Per 1,000", (r) => rate(r.m.spend_cents * 1000, r.m.impressions) ?? Infinity, (r) => (r.m.impressions ? money((r.m.spend_cents * 1000) / r.m.impressions, { exact: true }) : "—")),
  on: { key: "on", label: "On", cell: (r) => (r.can_control && LIVE.includes(r.status) ? switchHtml(isOn(r.status), `data-toggle="${r.level}:${r.id}" data-name="${esc(r.name)}"`, `${r.name} on or off`) : ""), cls: "c-on" },
  spark: { key: "spark", label: "Leads / day", cell: (r) => sparkline(r.spark), cls: "c-sp" },
};
export const COLUMN_SETS = {
  results: ["Results", { ad: ["name", "status", "spend", "impressions", "reach", "leads", "cpl", "vs", "qualified", "ctr", "hook", "on", "spark"],
    adset: ["name", "status", "budget", "spend", "impressions", "reach", "leads", "cpl", "vs", "qualified", "on"],
    campaign: ["name", "status", "budget", "spend", "impressions", "reach", "leads", "cpl", "vs", "qualified", "on"] }],
  delivery: ["Delivery", { ad: ["name", "status", "spend", "impressions", "reach", "freq", "cpm", "ctr", "on"],
    adset: ["name", "status", "budget", "spend", "impressions", "reach", "freq", "cpm", "on"],
    campaign: ["name", "status", "budget", "spend", "impressions", "reach", "freq", "cpm", "on"] }],
  video: ["Video", { ad: ["name", "status", "spend", "impressions", "hook", "hold", "leads", "cpl", "on"],
    adset: ["name", "status", "spend", "impressions", "hook", "hold", "leads", "cpl", "on"],
    campaign: ["name", "status", "spend", "impressions", "hook", "hold", "leads", "cpl", "on"] }],
};

function sparkline(series) {
  if (!series || !series.length) return "";
  const pts = series.slice(-14);
  const max = Math.max(...pts.map((d) => d.leads), 1);
  const w = 84, h = 22, step = w / Math.max(pts.length - 1, 1);
  const line = pts.map((d, i) => `${(i * step).toFixed(1)},${(h - 2 - (d.leads / max) * (h - 4)).toFixed(1)}`).join(" ");
  return `<svg class="tbl-sp" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${line}"/></svg>`;
}

// ---------------------------------------------------------------- the table

export function tableHtml({ level, rows, cols, sort, dir, selected, selectable, range }) {
  const defs = COLUMN_SETS[cols]?.[1][level] || COLUMN_SETS.results[1][level];
  const columns = defs.map((k) => C[k]);
  const sorter = columns.find((c) => c.key === sort) || C.spend;
  const sorted = [...rows].sort((a, b) => {
    const ka = sorter.sort(a), kb = sorter.sort(b);
    return (ka < kb ? -1 : ka > kb ? 1 : 0) * (dir === "asc" ? 1 : -1) * (sorter.key === "name" ? -1 : 1);
  });
  const allOn = selectable && rows.length && rows.every((r) => selected.has(r.id));
  const someOn = selectable && rows.some((r) => selected.has(r.id));
  const head = `<tr>${selectable ? `<th class="c-cb"><input type="checkbox" class="tbl-cb" data-all aria-label="Select all" ${allOn ? "checked" : ""} ${someOn && !allOn ? 'data-mixed="1"' : ""}></th>` : ""}${columns.map((c) => {
    const s = c.sort ? (c.key === sorter.key ? (dir === "asc" ? "ascending" : "descending") : "none") : null;
    const title = c.key === "vs" ? vsTitle(range) : c.title;
    return `<th class="${c.num ? "num" : ""} ${c.cls || ""}" ${s ? `aria-sort="${s}"` : ""} ${title ? `title="${esc(title)}"` : ""}>${c.sort ? `<button type="button" data-sort="${c.key}">${esc(c.label)}${c.sub ? ` <small>${esc(c.sub)}</small>` : ""}<span class="arrow">${icon("back")}</span></button>` : esc(c.label)}</th>`;
  }).join("")}</tr>`;
  const body = sorted.map((r) => `<tr data-row="${r.level}:${esc(r.id)}" class="${selected.has(r.id) ? "is-sel" : ""} ${["PAUSED", "ARCHIVED"].includes(r.status) ? "is-off" : ""}">
      ${selectable ? `<td class="c-cb"><input type="checkbox" class="tbl-cb" data-pick="${esc(r.id)}" aria-label="Select ${esc(r.name)}" ${selected.has(r.id) ? "checked" : ""}></td>` : ""}
      ${columns.map((c) => `<td class="${c.num ? "num" : ""} ${c.cls || ""}">${c.cell(r)}</td>`).join("")}</tr>`).join("");
  return `<div class="tbl-wrap"><table class="tbl"><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
}

// Phones: one compact line per row instead of a wide table (same checkboxes, switches and quick look).
export const narrow = () => matchMedia("(max-width: 960px)").matches;
export function listHtml({ rows, selected, sort, dir }) {
  const sorter = C[sort] && C[sort].sort ? C[sort] : C.spend;
  const sorted = [...rows].sort((a, b) => { const ka = sorter.sort(a), kb = sorter.sort(b); return (ka < kb ? -1 : ka > kb ? 1 : 0) * (dir === "asc" ? 1 : -1) * (sorter.key === "name" ? -1 : 1); });
  return `<ul class="pl">${sorted.map((r) => `<li data-row="${r.level}:${esc(r.id)}" class="${selected.has(r.id) ? "is-sel" : ""}">
    <input type="checkbox" class="tbl-cb" data-pick="${esc(r.id)}" aria-label="Select ${esc(r.name)}" ${selected.has(r.id) ? "checked" : ""}>
    ${r.level === "ad" ? thumb(r) : ""}
    <span class="pl-b"><a href="${href(r)}" class="tbl-link">${esc(r.name)}</a><span class="pl-st">${statusCell(r)}</span>
      <small class="tnum">${money(r.m.spend_cents, { exact: true })} · ${count(r.m.impressions)} views · ${count(r.m.leads)} leads · ${per(r.m.spend_cents, r.m.leads)}${r.prev && cpl(r.prev) && cpl(r.m) ? ` ${delta(cpl(r.m), cpl(r.prev), true)}` : ""}</small></span>
    ${C.on.cell(r)}</li>`).join("")}</ul>`;
}

// Cards (the old creative grid) for people who'd rather look at the pictures.
export function cardsHtml(rows) {
  return `<div class="cr-grid">${rows.map((ad) => {
    const [cls, label] = statusOf(ad.effective_status);
    const img = ad.image_url || ad.thumbnail_url;
    const m = ad.m;
    return `<article class="cr-card ${PROBLEM_STATES.includes(ad.effective_status) ? "has-issue" : ""}" data-row="ad:${esc(ad.id)}">
      <a class="cr-media" href="${href(ad)}" aria-label="Open ${esc(ad.name)}">
        ${img ? `<img src="${esc(img)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '<span class="ph"></span>'}
        ${ad.object_type === "VIDEO" ? `<span class="play">${icon("play")}</span>` : ""}
        <span class="pill ${cls} on-media">${esc(label)}</span></a>
      <div class="cr-body"><div class="cr-title-row"><a class="cr-name" href="${href(ad)}">${esc(ad.name)}</a>
        ${ad.can_control && ["ACTIVE", "PAUSED"].includes(ad.status) ? switchHtml(isOn(ad.status), `data-toggle="ad:${ad.id}" data-name="${esc(ad.name)}"`, `${ad.name} on or off`) : ""}</div>
        ${ad.title ? `<p class="cr-headline">${esc(ad.title)}</p>` : ""}
        <dl class="cr-stats"><div><dt>Spent</dt><dd>${money(m.spend_cents, { exact: true })}</dd></div><div><dt>Leads</dt><dd>${count(m.leads)}</dd></div>
          <div><dt>Per lead</dt><dd>${per(m.spend_cents, m.leads)}</dd></div><div><dt>${ad.object_type === "VIDEO" ? "Hook rate" : "Click rate"}</dt><dd>${ad.object_type === "VIDEO" ? pct(m.video_3s, m.video_impressions) : pct(m.link_clicks, m.impressions)}</dd></div></dl>
      </div></article>`;
  }).join("")}</div>`;
}

// ---------------------------------------------------------------- figures with "vs before"

// What figures hold that no listed ad shows: deleted or archived versions still spent (audit A3-36).
export function unlistedNote(m, listed) {
  const spend = m.spend_cents - listed.reduce((n, a) => n + (a.m.spend_cents || 0), 0);
  const leads = m.leads - listed.reduce((n, a) => n + (a.m.leads || 0), 0);
  if (spend <= 0 && leads <= 0) return "";
  return ` The figures include ${money(spend, { exact: true })} and ${count(leads)} lead${leads === 1 ? "" : "s"} from ads no longer listed (deleted or archived versions).`;
}

// "today 37 · all time 1,955" under a views or people figure (null parts are left out).
function todayEver(today, ever, key) {
  const t = today && today[key], e = ever && ever[key];
  if (t == null && e == null) return "";
  return `<span class="fig-s">${t != null ? `today ${count(t)}` : ""}${t != null && e != null ? " · " : ""}${e != null ? `all time ${count(e)}` : ""}</span>`;
}

export function figuresHtml(m, prev, target, { today = null, ever = null } = {}) {
  const f = (label, value, d) => `<div class="fig"><span class="fig-l">${label}</span><b class="fig-v">${value}</b>${d || ""}</div>`;
  const qcpl = m.qualified ? m.spend_cents / m.qualified : null;
  return `<div class="figs">
    ${f("Spent", money(m.spend_cents, { exact: true }), prev ? delta(m.spend_cents, prev.spend_cents, null).replace(/d-(good|bad)/, "d-mute") : "")}
    ${f("Views", count(m.impressions), `${prev ? delta(m.impressions, prev.impressions, false) : ""}${todayEver(today, ever, "impressions")}`)}
    ${f("People reached", count(m.reach) + (m.reach_summed ? "*" : ""), `${prev && !m.reach_summed ? delta(m.reach, prev.reach, false) : ""}${todayEver(today, ever, "reach")}`)}
    ${f("Leads", count(m.leads), prev ? delta(m.leads, prev.leads, false) : "")}
    ${f("Cost per lead", per(m.spend_cents, m.leads), prev ? delta(cpl(m), cpl(prev), true) : "")}
    ${f("Qualified", count(m.qualified), prev ? delta(m.qualified, prev.qualified, false) : "")}
    ${f("Per qualified lead", qcpl ? money(qcpl, { exact: true }) : "—", target ? `<span class="delta d-mute">target ${money(target)}</span>` : "")}
  </div>`;
}

// ---------------------------------------------------------------- selection, bulk bar, peek

const BULK = {
  ad: [["compare", "Compare", "compare"], ["on", "Turn on", "power"], ["off", "Turn off", "power"], ["archive", "Archive", "table"]],
  adset: [["on", "Turn on", "power"], ["off", "Turn off", "power"], ["budget", "Budget", "chart"]],
  campaign: [["on", "Turn on", "power"], ["off", "Turn off", "power"], ["budget", "Budget", "chart"]],
};

export function bulkBarHtml(level, picked, canControl) {
  if (!picked.length) return "";
  const thumbs = level === "ad" ? `<span class="bk-film">${picked.slice(0, 6).map((r) => thumb(r)).join("")}</span>` : "";
  const actions = BULK[level].filter(([k]) => k === "compare" || (canControl && (k !== "archive" || window.ebadsMe?.role === "admin"))).map(([k, label, ic]) => {
    const disabled = k === "compare" && (picked.length < 2 || picked.length > 6);
    return `<button type="button" class="btn ${k === "compare" ? "btn-primary" : "btn-quiet"} btn-small" data-bulk="${k}" ${disabled ? `disabled title="Pick 2 to 6 ads to compare"` : ""}>${icon(ic)}<span>${label}</span></button>`;
  }).join("");
  return `<div class="bk" role="toolbar" aria-label="${picked.length} selected"><span class="bk-n"><b>${picked.length}</b> selected</span>${thumbs}${actions}
    <button type="button" class="icon-btn bk-x" data-bulk="clear" aria-label="Clear the selection">×</button></div>`;
}

async function bulkRun(level, ids, action, value, after) {
  const words = LEVEL_WORDS[level];
  const body = { action: action === "on" || action === "off" ? "status" : action === "archive" ? "archive" : value.mode, level, ids,
    value: action === "on" ? "ACTIVE" : action === "off" ? "PAUSED" : value?.amount };
  let pv;
  try { pv = await api("/api/ads/bulk/preview", { method: "POST", body }); }
  catch (err) { toast(err.message, "bad"); return; }
  const t = pv.totals;
  const line = (l) => `<li class="${l.skip ? "skip" : ""}"><span>${esc(l.name)}</span><span class="tnum">${l.skip ? esc(l.skip)
    : body.action.startsWith("budget") ? `${money(l.from, { exact: true })} → <b>${money(l.to, { exact: true })}</b>${l.big ? ' <span class="pill warn">+' + l.pct + "%</span>" : ""}`
    : action === "archive" ? "Archive" : action === "on" ? "On" : "Off"}</span></li>`;
  if (!t.count) {
    await confirmDialog({ title: "Nothing to change", body: `<ul class="bk-lines">${pv.lines.map(line).join("")}</ul>`, confirm: "OK" });
    return;
  }
  let summary = "";
  let confirm = `${action === "on" ? "Turn on" : action === "off" ? "Turn off" : action === "archive" ? "Archive" : "Change"} ${t.count} ${t.count === 1 ? words[0] : words[1]}`;
  if (action === "on" && (t.daily_cents || t.lifetime_cents)) {
    const amounts = [t.daily_cents ? `up to <b>${money(t.daily_cents, { exact: true })} a day</b>` : "",
      t.lifetime_cents ? `up to <b>${money(t.lifetime_cents, { exact: true })} in total</b> from lifetime budgets` : ""].filter(Boolean).join(" plus ");
    summary = `<p>Turning these on spends ${amounts}, from ${t.budgets.map(esc).join(", ")}.${t.daily_cents ? ` About ${money(t.daily_cents * 30)} a month.` : ""}</p>`;
    if (t.daily_cents) confirm += ` · ${money(t.daily_cents, { exact: true })}/day`;
    if (t.lifetime_cents) confirm += ` · ${money(t.lifetime_cents, { exact: true })} total`;
  }
  if (body.action.startsWith("budget")) {
    summary = `<p>Daily budgets together: ${money(t.from_cents, { exact: true })} → <b>${money(t.to_cents, { exact: true })}</b> a day.</p>${t.big ? "<p><b>Some steps are more than +20%:</b> Meta may restart learning and results can wobble for a few days.</p>" : ""}`;
    if (t.big) confirm = "Apply anyway";
  }
  if (action === "archive") summary = "<p>Archived ads stop for good: Meta can't turn them back on. Their results stay.</p>";
  const ok = await confirmDialog({ title: `${confirm.split(" · ")[0]}?`, body: `${summary}<ul class="bk-lines">${pv.lines.map(line).join("")}</ul>`, confirm, danger: action === "off" || action === "archive" });
  if (!ok) return;
  try {
    const r = await api("/api/ads/bulk/apply", { method: "POST", body: { plan_token: pv.plan_token, confirm_total_cents: t.daily_cents, confirm_lifetime_cents: t.lifetime_cents, accept_big: !!t.big } });
    const failed = r.results.filter((x) => !x.ok);
    toast(failed.length ? `${r.done} done, ${failed.length} not: ${failed[0].error}` : `${r.done} ${r.done === 1 ? words[0] : words[1]} changed`, failed.length ? "bad" : "");
    after();
  } catch (err) { toast(err.message, "bad"); }
}

async function askBudget(level, count_) {
  const v = await confirmDialog({
    title: `Budget for ${count_} ${count_ === 1 ? LEVEL_WORDS[level][0] : LEVEL_WORDS[level][1]}`,
    body: "<p>A change in percent (for example <b>+20</b> or <b>-10</b>), or a new amount per day for each (for example <b>$25</b>). You see every line before anything changes.</p>",
    confirm: "Check the changes",
    field: { label: "Change", value: "+20%", validate: (s) => (/^\s*[+-]?\d+(\.\d+)?\s*%\s*$|^\s*\$?\s*\d+(\.\d+)?\s*$/.test(s) ? null : "Type a percent like +20% or an amount like $25") },
  });
  if (!v) return null;
  if (v.includes("%")) return { mode: "budget_pct", amount: Number(v.replace(/[%\s+]/g, "")) };
  return { mode: "budget_set", amount: Math.round(Number(v.replace(/[$,\s]/g, "")) * 100) };
}

// Wires one manager area: row clicks (peek), checkboxes, sort headers, switches, budget chips, bulk bar.
export function wire(root, ctx) {
  root.addEventListener("click", async (e) => {
    const t = e.target.closest("[data-toggle]");
    if (t) { toggleEntity(t, ctx.reload); return; }
    const b = e.target.closest("[data-budget]");
    if (b) { const [level, id] = b.dataset.budget.split(":"); editBudget({ level, id, name: b.dataset.name, current: Number(b.dataset.current) }, ctx.reload); return; }
    const s = e.target.closest("[data-sort]");
    if (s) { ctx.sortBy(s.dataset.sort); return; }
    const k = e.target.closest("[data-bulk]");
    if (k) {
      const picked = ctx.picked();
      const ids = picked.map((r) => r.id);
      const level = ctx.level();
      if (k.dataset.bulk === "clear") { ctx.clear(); return; }
      if (k.dataset.bulk === "compare") { location.href = `/compare.html?ids=${ids.map(encodeURIComponent).join(",")}&range=${ctx.range()}&vs=1`; return; }
      if (k.dataset.bulk === "budget") { const v = await askBudget(level, ids.length); if (v) bulkRun(level, ids, "budget", v, ctx.reload); return; }
      bulkRun(level, ids, k.dataset.bulk, null, ctx.reload);
      return;
    }
    if (e.target.closest("a, button, input, select, label")) return;
    const row = e.target.closest("[data-row]");
    if (row) ctx.peek(row.dataset.row);
  });
  root.addEventListener("change", (e) => {
    const all = e.target.closest("[data-all]");
    if (all) { ctx.pickAll(all.checked); return; }
    const one = e.target.closest("[data-pick]");
    if (one) ctx.pick(one.dataset.pick, one.checked, ctx.lastShift);
  });
  root.addEventListener("click", (e) => { const one = e.target.closest("[data-pick]"); if (one) ctx.lastShift = e.shiftKey; }, true);
}

// ---------------------------------------------------------------- peek drawer

let drawer = null;
const RANK_TONE = { ABOVE_AVERAGE: "ok", AVERAGE: "mute", BELOW_AVERAGE_35: "warn", BELOW_AVERAGE_20: "bad", BELOW_AVERAGE_10: "bad" };

// Everything we know about one row, without leaving the list: the period's figures against the period
// before, the rest of the numbers, a daily chart, Meta's own rankings and watch funnel (ads), who it's
// shown to and learning (ad sets), the words, and the timeline.
function moreNumbers(r) {
  const m = r.m || {};
  const cell = (label, value, title = "") => `<div ${title ? `title="${esc(title)}"` : ""}><dt>${label}</dt><dd>${value}</dd></div>`;
  const video = (m.video_impressions || 0) > 0;
  return `<dl class="pk-grid">
    ${cell("Times each person saw it", m.reach ? (m.impressions / m.reach).toFixed(2) : "—", "Views ÷ people reached (frequency)")}
    ${cell("Link clicks", count(m.link_clicks))}
    ${cell("Click rate", pct(m.link_clicks, m.impressions), "Link clicks ÷ views")}
    ${cell("Cost per click", per(m.spend_cents, m.link_clicks))}
    ${cell("Cost per 1,000 views", m.impressions ? money((m.spend_cents * 1000) / m.impressions, { exact: true }) : "—", "CPM")}
    ${cell("Leads per 1,000 views", m.impressions ? ((m.leads * 1000) / m.impressions).toFixed(2) : "—")}
    ${video ? cell("Hook rate", pct(m.video_3s, m.video_impressions), "3-second views ÷ views of the video ads") : ""}
    ${video ? cell("Hold rate", pct(m.thruplays, m.video_3s), "ThruPlays ÷ 3-second views") : ""}
    ${video ? cell("ThruPlays", count(m.thruplays), "Watched 15 s or to the end") : ""}
    ${cell("Lead rate", pct(m.leads, m.link_clicks), "Leads ÷ link clicks")}
    ${r.level === "ad" && r.created_time ? cell("Created", esc(when(r.created_time))) : ""}
  </dl>`;
}

function context(r) {
  const parts = [];
  if (r.level === "ad") {
    if (r.title) parts.push(`<div class="pk-words"><span class="pk-lbl">Headline</span><p>${esc(r.title)}</p></div>`);
    const s = r.adset;
    if (s) parts.push(`<div class="pk-where"><span class="pk-lbl">Runs in</span><p><a href="${href(s)}">${esc(s.name)}</a> · <a href="${href(r.campaign)}">${esc(r.campaign.name)}</a></p>
      ${s.targeting_summary ? `<p class="muted small">${esc(s.targeting_summary)}</p>` : ""}</div>`);
  }
  if (r.level === "adset") {
    const learn = LEARNING[r.learning_stage];
    parts.push(`<div class="pk-where"><span class="pk-lbl">Who sees it</span><p>${esc(r.targeting_summary || "—")}</p>
      ${learn || r.learning_stage === "SUCCESS" ? `<p class="small">${learn ? `<span class="st st-${learn[0]}">${learn[1]}</span>` : '<span class="st st-ok">Finished learning</span>'}</p>` : ""}
      <p><a href="${href(r.campaign)}">${esc(r.campaign.name)}</a></p></div>`);
  }
  if (r.level === "campaign") {
    parts.push(`<div class="pk-where"><span class="pk-lbl">Inside</span><p>${count((r.adsets || []).length)} ad sets · ${count((r.adsets || []).reduce((n, s) => n + (s.ads || []).length, 0))} ads${r.objective ? ` · goal: ${esc(r.objective.replace("OUTCOME_", "").toLowerCase())}` : ""}</p></div>`);
  }
  const fb = r.review_feedback && (r.review_feedback.global || r.review_feedback);
  if (fb && typeof fb === "object" && Object.keys(fb).length) parts.unshift(`<div class="note bad">${Object.values(fb).map((t) => esc(String(t))).join("<br>")}</div>`);
  return parts.join("");
}

async function diagnostics(r) {
  const box = drawer.querySelector(".pk-diag");
  if (r.level !== "ad") { box.remove(); return; }
  try {
    const d = await api(`/api/insights/ad/${encodeURIComponent(r.id)}/diagnostics`);
    const ranks = [["quality_ranking", "Quality"], ["engagement_rate_ranking", "Engagement"], ["conversion_rate_ranking", "Conversion"]];
    const f = d.funnel || {};
    const steps = r.object_type === "VIDEO" && f.impressions ? [["Views", f.impressions], ["3 seconds", f.video_3s], ["25%", f.p25], ["50%", f.p50], ["75%", f.p75], ["To the end", f.p100]] : [];
    const top = Math.max(...steps.map(([, v]) => v), 1);
    box.innerHTML = `<h3 class="pk-h">How Meta rates it <small>last 30 days, against ads competing for the same people</small></h3>
      <dl class="pk-ranks">${ranks.map(([k, label]) => { const v = d.rankings[k] || {}; return `<div><dt>${label}</dt><dd><span class="st st-${RANK_TONE[v.value] || "mute"}">${esc(v.label || "Not enough data yet")}</span></dd></div>`; }).join("")}</dl>
      ${d.avg_watch_seconds ? `<p class="small muted">Average watch: <b>${d.avg_watch_seconds} s</b></p>` : ""}
      ${steps.length ? `<h3 class="pk-h">Who watched how far <small>since it started</small></h3><ul class="pk-funnel">${steps.map(([label, v]) => `<li><span>${label}</span><span class="pk-bar"><i data-w="${((v / top) * 100).toFixed(1)}"></i></span><b class="tnum">${count(v)}</b><small class="tnum">${f.impressions ? `${((v / f.impressions) * 100).toFixed(1)}%` : ""}</small></li>`).join("")}</ul>` : ""}
      ${d.error ? `<p class="muted small">Meta didn't answer for the rankings: ${esc(d.error)}</p>` : ""}`;
    box.querySelectorAll("[data-w]").forEach((i) => { i.style.width = `${i.dataset.w}%`; });
  } catch (err) { box.innerHTML = ""; }
}

export async function peek(r, { onClose } = {}) {
  if (!drawer) {
    drawer = document.createElement("aside");
    drawer.className = "pk";
    drawer.setAttribute("role", "dialog");
    drawer.setAttribute("aria-label", "Quick look");
    document.body.append(drawer);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && drawer.classList.contains("open")) closePeek(); });
  }
  drawer._onClose = onClose;
  const m = r.m || {};
  const word = LEVEL_WORDS[r.level][0].replace(/^./, (c) => c.toUpperCase());
  drawer.innerHTML = `<div class="pk-head">${r.level === "ad" ? thumb(r) : ""}<div><p class="pk-kicker">${esc(word)}</p>
      <h2>${esc(r.name)}</h2><p>${statusCell(r)}</p></div><button type="button" class="icon-btn pk-x" aria-label="Close">${icon("back")}</button></div>
    <div class="row pk-actions"><a class="btn btn-primary btn-small" href="${href(r)}">Open ${esc(LEVEL_WORDS[r.level][0])}</a>
      ${r.can_control && ["ACTIVE", "PAUSED"].includes(r.status) ? `<span class="pk-sw">${switchHtml(isOn(r.status), `data-toggle="${r.level}:${r.id}" data-name="${esc(r.name)}"`, `${r.name} on or off`)} ${isOn(r.status) ? "On" : "Off"}</span>` : ""}
      ${r.level !== "ad" && r.daily_budget_cents ? budgetCell(r) : ""}
      ${r.level === "ad" ? `<a class="btn btn-small" href="/leads.html?ad=${encodeURIComponent(r.id)}">Its leads</a>` : ""}</div>
    ${context(r)}
    <h3 class="pk-h">This period ${r.prev ? "<small>against the same days before</small>" : ""}</h3>
    ${figuresHtml(m, r.prev, null, { today: r.today, ever: r.ever }).replace('class="figs"', 'class="figs pk-figs"')}
    ${moreNumbers(r)}
    ${(r.spark || []).length ? `<h3 class="pk-h">Day by day</h3><div class="pk-charts"><p class="pk-cap">Spent</p><div class="chart" id="pk-spend"></div><p class="pk-cap">Leads</p><div class="chart" id="pk-leads"></div></div>` : ""}
    <div class="pk-diag"><p class="muted small">Asking Meta how it rates this ad…</p></div>
    <h3 class="pk-h">What happened</h3><ol class="pk-tl"><li class="muted">Loading…</li></ol>`;
  drawer.classList.add("open");
  drawer.scrollTop = 0;
  drawer.querySelector(".pk-x").addEventListener("click", closePeek);
  drawer.onclick = (e) => {
    const t = e.target.closest("[data-toggle]");
    if (t) toggleEntity(t, () => { closePeek(); onClose && onClose(true); });
    const b = e.target.closest("[data-budget]");
    if (b) { const [level, id] = b.dataset.budget.split(":"); editBudget({ level, id, name: b.dataset.name, current: Number(b.dataset.current) }, () => { closePeek(); onClose && onClose(true); }); }
  };
  if ((r.spark || []).length) {
    columnChart({ el: drawer.querySelector("#pk-spend"), series: r.spark, key: "spend_cents", color: "var(--chart-spend)", title: "Spend per day", height: 120,
      format: (v) => money(v, { exact: true }), axisFormat: (v) => moneyWhole(v) });
    columnChart({ el: drawer.querySelector("#pk-leads"), series: r.spark, key: "leads", color: "var(--chart-leads)", title: "Leads per day", height: 120, integer: true,
      format: (v) => `${v} lead${v === 1 ? "" : "s"}`, axisFormat: (v) => String(Math.round(v)) });
  }
  diagnostics(r);
  const tlBox = drawer.querySelector(".pk-tl");  // this row's: another row's quick look builds its own
  try {
    const tl = await api(`/api/timeline/${r.level}/${encodeURIComponent(r.id)}`);
    const items = tl.items.slice(0, 8);
    tlBox.innerHTML = items.length ? items.map((i) => `<li class="tl-${i.tone || "n"}"><span class="tl-dot"></span><span class="tl-w">${esc(when(i.at))}</span><span class="tl-t"><b>${esc(i.title)}</b>${i.by ? `<small>${esc(i.by)}</small>` : ""}</span></li>`).join("")
      : '<li class="muted">Nothing recorded yet: status changes show here from the next refresh.</li>';
  } catch (err) { tlBox.innerHTML = `<li class="muted">${esc(err.message)}</li>`; }
}

export function closePeek() {
  if (!drawer || !drawer.classList.contains("open")) return;
  drawer.classList.remove("open");
  const cb = drawer._onClose;
  drawer._onClose = null;
  if (cb) cb(false);
}
