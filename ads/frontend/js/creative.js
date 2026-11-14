import { api, startLoad } from "./api.js";
import { boot, confirmDialog, emptyState, entityLink, esc, icon, onRefresh, previewSkeleton, setCrumbs, skeleton, shortWait, showPreviewFrame, sourceNote, switchHtml, timelineHtml, toast, when, errorState, withFrom } from "./ui.js";
import { CTA_LABELS, EXPLAIN, JUDGED_RANGES, RANGES, WORDS, count, money, pct, per, plural, rangeSelect, rememberRange, sharedRange, statusOf, statusPill, moneyWhole } from "./format.js";
import { barList, columnChart, marksPanel } from "./charts.js";
import { editBudget, restoreVersion, toggleEntity } from "./controls.js";
import { track } from "./manager.js";
import { ACTIVE, proposalCard, taskCard, wireTaskActions } from "./tasks.js";
import { diagnoseHtml, wireAlerts } from "./alertmenu.js";
import { openFromUrl } from "./outcome.js";
import { draftLeftFor, draftLeftHtml } from "./drafts.js";
import { errorsHtml, pictureHtml, sizeExtras } from "./mx.js";

const $ = (id) => document.getElementById(id);
const adId = new URLSearchParams(location.search).get("id");
let me, data, passes;
let format = "MOBILE_FEED_STANDARD";
try { format = localStorage.getItem("ebads-preview") || format; } catch (e) {}
let tab = (location.hash.match(/tab=(\w+)/) || [])[1] || "overview";
let foldAsked = (location.hash.match(/fold=(\w+)/) || [])[1] || null;  // a link can open one fold (the Gallery's "See versions")
let audienceBy = "placement";
// Who saw it: unique people over whole days, so no Today here (FU-C); the daily charts have it.
const AUDIENCE_RANGES = [...JUDGED_RANGES, ["lifetime", "All time"]];
// The overview's daily charts and the Audience tab open on the shared date range (or the link's ?range=).
const linkRange = new URLSearchParams(location.search).get("range");
let chartRange = RANGES.some(([k]) => k === linkRange) ? linkRange : sharedRange("7");
let audienceRange = AUDIENCE_RANGES.some(([k]) => k === linkRange) ? linkRange : sharedRange("7", AUDIENCE_RANGES);
let pollTimer;
let historyShow = "all";
let leftDraft = null;  // AM-B: the Ads Manager draft this new ad was made from ({name, open_url}), once read
// AM-E: the Overview's preview shows Meta's live preview or Meta's picture from Ads Manager (kept per browser).
let pvView = "live";
try { pvView = localStorage.getItem("ebads-preview-view") === "picture" ? "picture" : "live"; } catch (e) {}
let picWait = null;
const openReports = new Set();

const TABS = [
  ["overview", "Overview"], ["polish", "Polish"], ["audience", "Audience"], ["video", "Video"], ["comments", "Comments"], ["history", "History"],
];

// ---------------------------------------------------------------- header + tabs

function renderHead() {
  const { ad } = data;
  document.title = `${ad.name} | Edge Bourne Ads`;
  $("crumb").hidden = true;
  setCrumbs([{ label: "Ads", href: "/ads.html" },
    ...(ad.campaign_id ? [{ label: ad.campaign_name || "Campaign", href: `/campaign.html?id=${encodeURIComponent(ad.campaign_id)}` }] : []),
    ...(ad.adset_id ? [{ label: ad.adset_name || "Ad set", href: `/adset.html?id=${encodeURIComponent(ad.adset_id)}` }] : []),
    { label: ad.name, href: location.pathname + location.search }]);
  $("cr-title").textContent = ad.name;
  const [cls, label] = statusOf(ad.effective_status);
  $("cr-status").innerHTML = `<span class="pill ${cls}">${esc(label)}</span>`;
  // Read-only logins (clients) look: no switch, copy, new ad or Claude.
  const can = ad.can_control;
  $("cr-actions").innerHTML = `
    ${can && ["ACTIVE", "PAUSED"].includes(ad.status) ? `<span class="switch-label">${ad.status === "ACTIVE" ? "On" : "Off"}</span>${switchHtml(ad.status === "ACTIVE", `data-toggle="ad:${ad.id}" data-name="${esc(ad.name)}"`, "Ad on or off")}` : ""}
    ${can ? `<button class="btn" type="button" id="dup">${icon("copy")}<span>Duplicate</span></button>` : ""}
    <a class="btn" href="/compare.html?ids=${encodeURIComponent(ad.id)}">${icon("compare")}<span>Compare</span></a>
    ${can ? `<a class="btn" href="${esc(withFrom(`/new-ad.html?template=${encodeURIComponent(ad.id)}`))}">${icon("plus")}<span>New ad from this</span></a>` : ""}
    ${can ? `<button class="btn btn-claude" type="button" data-goto="polish">${icon("spark")}<span>Polish</span></button>` : ""}
    ${me.role === "admin" && !["ACTIVE", "ARCHIVED", "DELETED"].includes(ad.status) ? '<button class="btn" type="button" id="archive">Archive</button>' : ""}
    ${me.role === "admin" && !["ACTIVE", "DELETED"].includes(ad.status) ? '<button class="btn btn-danger-text" type="button" id="delete">Delete</button>' : ""}`;
  // Clients look, they don't ask Claude for changes: no Polish tab for them.
  const tabs = TABS.filter(([id]) => (id !== "video" || ad.object_type === "VIDEO") && (id !== "polish" || ad.can_control));
  $("cr-tabs").innerHTML = tabs.map(([id, l]) => `<button type="button" role="tab" data-tab="${id}" aria-selected="${id === tab}">${esc(l)}${id === "comments" && data.comment_total ? ` <span class="n">${data.comment_total}</span>` : ""}</button>`).join("");
}

function showTab(next) {
  tab = next;
  history.replaceState(null, "", `${location.pathname}${location.search}#tab=${tab}`);
  document.querySelectorAll("#cr-tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
  clearTimeout(pollTimer);
  startLoad("tab");  // an answer still on its way for the tab left behind is dropped
  ({ overview: renderOverview, polish: renderPolish, audience: renderAudience, video: renderVideo, comments: renderComments, history: renderHistory }[tab] || renderOverview)();
}

// ---------------------------------------------------------------- folds
// The Overview leads with status, results and Claude; the rest folds under a line that says what is inside.
// Each fold remembers whether it was left open (this browser), so a refresh or the next visit keeps it.

const FOLD_KEY = "ebads-folds";
function foldsOpen() {
  try { return JSON.parse(localStorage.getItem(FOLD_KEY) || "{}") || {}; } catch (e) { return {}; }
}
function foldHtml(id, title, sub, body, { open = false, attrs = "" } = {}) {
  const was = foldsOpen()[id];
  return `<details class="panel fold" id="fold-${id}" data-fold="${id}" ${(was ?? open) ? "open" : ""} ${attrs}>
    <summary><span class="fold-t">${esc(title)}</span><span class="fold-s" id="fold-${id}-sub">${sub}</span></summary>
    <div class="panel-body">${body}</div></details>`;
}
document.addEventListener("toggle", (e) => {
  const d = e.target;
  if (!(d instanceof HTMLDetailsElement) || !d.dataset.fold) return;
  try { localStorage.setItem(FOLD_KEY, JSON.stringify({ ...foldsOpen(), [d.dataset.fold]: d.open })); } catch (err) { /* storage off */ }
}, true);
const setFoldSub = (id, html) => { const el = $(`fold-${id}-sub`); if (el) el.innerHTML = html; };

// ---------------------------------------------------------------- preview
// Meta's preview links stop working after a while: a preview older than this is read again when the
// page comes back into view (another tab, the phone unlocked, Back from another page) or sits idle.
const PREVIEW_FRESH_MS = 30 * 60 * 1000;

async function loadPreview() {
  const box = $("preview-frame");
  if (!box) return;
  const superseded = startLoad("preview");
  document.querySelectorAll("#formats button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.format === format)));
  box.innerHTML = previewSkeleton();
  box.dataset.loadedAt = String(Date.now());
  try {
    const p = await api(`/api/ads/ad/${encodeURIComponent(adId)}/preview?format=${format}`);
    if (superseded() || !box.isConnected) return;
    showPreviewFrame(box, p, { title: "Ad preview from Meta", width: Math.min(p.width || 360, 400), height: p.height || 640 });
    box.dataset.loadedAt = String(Date.now());
    $("preview-open").href = p.src;
    $("preview-open").hidden = false;
  } catch (err) {
    if (superseded() || !box.isConnected) return;
    box.innerHTML = `<div class="note warn preview-note"><p class="flush">${esc(err.message)}</p><button class="btn btn-small" type="button" data-preview-again>Try again</button></div>`;
    $("preview-open").hidden = true;
  }
}

function previewStale() {
  const box = $("preview-frame");
  if (!box || !box.dataset.loadedAt) return false;
  return Date.now() - Number(box.dataset.loadedAt) > PREVIEW_FRESH_MS;
}
// Never swap the frame under someone using it (a video playing, a pointer on it).
const previewInUse = () => { const box = $("preview-frame"); return !!box && (box.matches(":hover") || box.contains(document.activeElement)); };
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && previewStale()) loadPreview(); });
window.addEventListener("pageshow", (e) => { if (e.persisted && previewStale()) loadPreview(); });
setInterval(() => { if (document.visibilityState === "visible" && previewStale() && !previewInUse()) loadPreview(); }, 60 * 1000);

// ---------------------------------------------------------------- overview

// This ad, as the Suggestion card's index: its name and words, so a card shows what would change.
const adIndex = () => ({ ads: { [data.ad.id]: data.ad } });

function versionsBody(v, ad) {
  const video = ad.object_type === "VIDEO";
  const day = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const rows = [...v.versions].reverse().map((x) => `<tr>
    <td class="ver-name"><b>Version ${x.number}</b><small>${esc(x.label || "")}${x.started_on ? ` · from ${esc(day(x.started_on))}` : ""}</small>${x.current ? '<span class="pill ok">On the ad now</span>' : ad.can_control ? `<button class="btn btn-small" type="button" data-restore="${x.number}">Switch back</button>` : ""}</td>
    <td class="num">${x.days}</td><td class="num">${money(x.spend_cents, { exact: true })}</td><td class="num">${count(x.leads)}</td>
    <td class="num">${per(x.spend_cents, x.leads)}</td><td class="num">${pct(x.link_clicks, x.impressions)}</td>
    ${video ? `<td class="num">${x.impressions ? pct(x.video_3s, x.impressions) : "—"}</td>` : ""}</tr>`).join("");
  const c = v.changeover;
  return `<div class="stack tight">
      <p class="muted small flush">Results per version, complete days only.</p>
      <div class="tbl-wrap"><table class="tbl ver-tbl"><thead><tr><th>Version</th><th class="num">Days</th><th class="num">Spent</th><th class="num">Leads</th><th class="num">${WORDS.cpl}</th><th class="num">${WORDS.ctr}</th>${video ? `<th class="num">${WORDS.hook}</th>` : ""}</tr></thead><tbody>${rows}</tbody></table></div>
      ${c.days ? `<p class="muted small flush">${c.days} ${c.days === 1 ? "day" : "days"} around a switch count for neither version, because either could have been showing: ${money(c.spend_cents, { exact: true })}, ${count(c.leads)} ${c.leads === 1 ? "lead" : "leads"}.</p>` : ""}
      ${v.versions.some((x) => !x.enough) ? '<p class="muted small flush">Too early to judge: a version needs at least 3 leads and twice your target cost per lead in spend.</p>' : ""}
    </div>`;
}

// The status card: what the ad is doing, in words, and the one thing that helps.
function statusHtml(ad, s) {
  const budgetLevel = ad.adset_budget_cents ? "adset" : ad.campaign_budget_cents ? "campaign" : null;
  const budgetCents = ad.adset_budget_cents || ad.campaign_budget_cents;
  const can = ad.can_control;
  const next = {
    polish: can ? `<button class="btn btn-claude btn-small" type="button" data-goto="polish">${icon("spark")}<span>Ask Claude for a fixed version</span></button>` : "",
    switch: can ? '<p class="muted small flush">Turn it on with the On switch at the top.</p>' : "",
    campaign: ad.campaign_id ? `<p class="small flush">Open the campaign to turn it on: ${entityLink("campaign", ad.campaign_id, ad.campaign_name || "campaign")}</p>` : "",
    adset: ad.adset_id ? `<p class="small flush">Open the ad set to turn it on: ${entityLink("adset", ad.adset_id, ad.adset_name || "ad set")}</p>` : "",
    billing: '<p class="muted small flush">Add a payment method in Meta\'s billing settings (Ads Manager → Billing).</p>',
  }[s.fix] || "";
  const learn = s.learning === "learning_limited" ? ["warn", "Learning limited"] : s.learning === "learning" ? ["info", "Learning"] : null;
  return `<section class="panel cr-state tone-${esc(s.tone || "none")}" id="cr-state" aria-labelledby="cr-state-h">
    <div class="panel-body stack tight">
      <div class="cs-top"><h2 class="cs-h" id="cr-state-h">${statusPill(ad.effective_status)}</h2>${track(ad)}<span class="spacer"></span>
        ${learn ? `<span class="pill ${learn[0]}" title="${esc(EXPLAIN[s.learning])}">${learn[1]}</span>` : ""}</div>
      <p class="cs-line flush">${esc(s.line)}</p>
      ${s.reasons.length ? `<ul class="cs-reasons">${s.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}
      ${learn ? `<p class="muted small flush">${esc(EXPLAIN[s.learning])}</p>` : ""}
      ${errorsHtml(data.meta_errors, { diagnose: me.role === "admin" && data.meta_errors && data.meta_errors.alert_id })}
      ${next}
      ${me.role === "admin" && ["DISAPPROVED", "WITH_ISSUES"].includes(ad.effective_status) ? '<div class="row al-acts" id="cs-diag"></div>' : ""}
      <p class="cs-budget small flush"><span class="muted">Budget</span> ${budgetCents ? `${money(budgetCents, { exact: true })} a day, shared by the ${budgetLevel === "campaign" ? "whole campaign" : "ad set"}${can ? ' · <button class="link-btn" type="button" id="edit-budget">Change</button>' : ""}` : "set on Meta"}</p>
    </div></section>`;
}

function claudeHtml(pending) {
  if (!data.ad.can_control) return "";
  if (pending.length) {
    return `<section class="panel claude-panel" id="cr-claude"><div class="panel-head"><h2>Claude suggests</h2><p>${plural(pending.length, "suggestion")} waiting for you</p></div>
      <div class="panel-body stack tight" id="props">${pending.map((p) => proposalCard(p, null, adIndex())).join("")}</div></section>`;
  }
  const r = data.claude_run;
  const what = r && r.kind === "render" ? "a new version" : "a polish check";
  const line = !r ? "Claude can check this ad against what gets ads approved and working, and suggest better words or a new version."
    : ACTIVE.has(r.status) ? `Claude is working on ${what} of this ad (started ${when(r.created_at)}).`
    : r.status === "done" ? `Last ${r.kind === "render" ? "new version" : "polish check"}: ${r.score ? `scored ${r.score}/5, ` : ""}${when(r.finished_at || r.created_at)}. Nothing is waiting for you.`
    : `The last ${r.kind === "render" ? "new version" : "polish check"} didn't finish (${r.status}).`;
  return `<section class="panel claude-quiet" id="cr-claude"><div class="panel-body row">
      <span class="cq-dot" aria-hidden="true">${icon("spark")}</span><p class="flush small cq-line">${esc(line)}</p><span class="spacer"></span>
      <button class="btn btn-small btn-claude-outline" type="button" data-goto="polish">${r && ACTIVE.has(r.status) ? "See progress" : r ? "Polish again" : "Polish"}</button>
    </div></section>`;
}

function renderOverview() {
  const { ad, lifetime } = data;
  const s = data.status;
  const pending = data.proposals.filter((p) => p.status === "pending");
  const video = ad.object_type === "VIDEO";
  const hook = lifetime.impressions && data.funnel ? pct(data.funnel.video_3s, lifetime.impressions) : "—";
  const fig = (label, value, explain = "") => `<div class="fig"${explain ? ` title="${esc(explain)}"` : ""}><span class="fig-l">${label}</span><b class="fig-v">${value}</b></div>`;
  const leadsHtml = data.leads.length ? `<ul class="lead-mini">${data.leads.map((l) => `<li><a href="/leads.html#lead=${l.id}"><b>${esc(l.full_name || "Unnamed")}</b><span>${esc(l.business_type || "")}</span></a><span class="pill ${l.status}">${esc(l.status)}</span><small>${esc(shortWait(l.created_time))} ago${l.is_test ? " · test" : ""}</small></li>`).join("")}</ul>` : '<p class="muted flush">No leads from this ad yet.</p>';
  const v = data.versions;
  const cur = v && v.versions.find((x) => x.current);
  const reviewNote = ["IN_PROCESS", "PENDING_REVIEW"].includes(ad.effective_status) ? '<p class="note preview-review">Meta is still reviewing this ad, so its preview can stay blank until the review is done (usually within a day).</p>' : "";
  const preview = `
      <section class="panel preview-panel" aria-labelledby="pv-h">
        <div class="panel-head"><h2 id="pv-h">Preview</h2><p>As Meta shows it</p><span class="spacer"></span><button class="btn btn-quiet btn-small" type="button" id="preview-reload">${icon("refresh")}<span>Reload</span></button></div>
        <div class="panel-body stack tight">
          <div class="segmented fill mx-views" id="mx-view" role="group" aria-label="Which view"><button type="button" data-pv-view="live">Live preview</button><button type="button" data-pv-view="picture">Meta's picture</button></div>
          <div class="stack tight" id="pv-live">
          <div class="format-scroll"><div class="segmented" id="formats" role="group" aria-label="Placement">${data.formats.map((f) => `<button type="button" data-format="${f.id}">${esc(f.label)}</button>`).join("")}</div></div>
          <div id="pv-note">${reviewNote}</div>
          <div class="preview-frame" id="preview-frame"></div>
          <a class="small" id="preview-open" target="_blank" rel="noopener noreferrer" hidden>Open this preview in a new tab</a>
          </div>
          <div id="mx-pic-box" hidden></div>
        </div>
      </section>`;
  const side = `
      <div class="stack cr-side">
        ${statusHtml(ad, s)}
        <section class="cr-figs" aria-label="Results since it started">
          <div class="figs four">
            ${fig(WORDS.spend, money(lifetime.spend_cents, { exact: true }))}${fig(WORDS.leads, count(lifetime.leads))}${fig(WORDS.cpl, per(lifetime.spend_cents, lifetime.leads))}
            ${video ? fig(WORDS.hook, hook, EXPLAIN.hook) : fig(WORDS.ctr, pct(lifetime.link_clicks, lifetime.impressions), EXPLAIN.ctr)}
          </div>
          <dl class="fig-more">
            <div title="${esc(EXPLAIN.impressions)}"><dt>${WORDS.impressions}</dt><dd>${count(lifetime.impressions)} <small>today ${count(lifetime.today_impressions)}</small></dd></div>
            <div title="${esc(EXPLAIN.reach)}"><dt>${WORDS.reach}</dt><dd>${count(lifetime.reach)}${lifetime.reach_summed ? "*" : ""} <small>today ${count(lifetime.today_reach)}</small></dd></div>
            ${video ? `<div title="${esc(EXPLAIN.ctr)}"><dt>${WORDS.ctr}</dt><dd>${pct(lifetime.link_clicks, lifetime.impressions)}</dd></div>` : ""}
          </dl>
          <p class="muted small flush">Since it started, today so far included.${lifetime.reach_summed ? " * Added up per day: Meta didn't answer with the true count." : ""}</p>
        </section>
        ${claudeHtml(pending)}
        <section class="panel">
          <div class="panel-head wrap"><h2>Per day</h2><p id="per-day-note">${RANGES.some(([k]) => k === chartRange) && chartRange !== "lastmonth" ? "With today so far, Meta still counting" : "Complete days only"}</p><span class="spacer"></span>${rangeSelect("chart-range", chartRange, RANGES, "Dates in the charts")}</div>
          <div class="panel-body">
            <div class="charts single"><div><h3 class="chart-title">Spend per day</h3><div class="chart" id="c-spend"></div></div>
            <div><h3 class="chart-title">Leads per day</h3><div class="chart" id="c-leads"></div></div></div>
            <div class="fig-foot"><div class="fig-src" id="fig-src"></div><div class="fig-marks" id="chg-panel"></div></div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Leads from this ad</h2><a class="more" href="/leads.html?ad=${encodeURIComponent(ad.id)}">All in Leads</a></div>
          <div class="panel-body">${leadsHtml}</div>
        </section>
        ${foldHtml("where", "Where it runs", [ad.campaign_name, ad.adset_name].filter(Boolean).map(esc).join(" · ") || "—", `
            <dl class="facts">
              <div><dt>Campaign</dt><dd>${ad.campaign_name ? entityLink("campaign", ad.campaign_id, ad.campaign_name) : "—"}</dd></div>
              <div><dt>Ad set</dt><dd>${ad.adset_name ? entityLink("adset", ad.adset_id, ad.adset_name) : "—"}</dd></div>
              ${(data.tests || []).length ? `<div><dt>Tests</dt><dd>${data.tests.map((t) => `${entityLink("test", t.id, t.name)}${t.status === "running" ? " (running)" : ""}`).join(", ")}</dd></div>` : ""}
              <div><dt>Audience</dt><dd>${esc(ad.targeting_summary || "—")}<span id="estimate"></span></dd></div>
              <div><dt>Ad ID</dt><dd><a href="https://adsmanager.facebook.com/adsmanager/manage/ads?${window.ebadsMe && window.ebadsMe.account.ad_account_id ? `act=${encodeURIComponent(window.ebadsMe.account.ad_account_id)}&` : ""}selected_ad_ids=${encodeURIComponent(ad.id)}" target="_blank" rel="noopener noreferrer">${esc(ad.id)} ${icon("external")}</a></dd></div>
            </dl>`, { open: true })}
        ${v ? foldHtml("versions", "Versions", `${plural(v.versions.length, "version")}${cur ? ` · version ${cur.number} on the ad now` : ""}`, versionsBody(v, ad)) : ""}
        ${foldHtml("words", "Words", esc(ad.title || "—"), `
            <dl class="facts">
              <div><dt>Headline</dt><dd>${esc(ad.title || "—")} <span class="muted small">(${(ad.title || "").length} characters)</span></dd></div>
              <div><dt>Primary text</dt><dd class="pre">${esc(ad.body || "—")}</dd></div>
              <div><dt>Button</dt><dd>${esc(CTA_LABELS[ad.cta_type] || ad.cta_type || "—")}</dd></div>
              <div><dt>Format</dt><dd>${esc(video ? "Video" : ad.object_type ? "Image" : "—")}</dd></div>
            </dl>
            ${ad.can_control ? '<div class="row"><button class="btn btn-small" type="button" data-goto="polish">Improve the words</button></div>' : ""}`)}
        ${foldHtml("idea", "The idea", '<span class="muted">Reading…</span>', `<p class="muted small flush">Tags that group ads on <a href="/ideas.html">Ideas</a>, so you can see which ideas work.</p><form class="stack tight" id="idea" novalidate>${skeleton()}</form>`)}
        ${foldHtml("auto", "Meta's automatic changes", '<span class="muted">Reading from Meta…</span>', `<p class="muted small flush">${esc(EXPLAIN.advantage_creative)}</p><div id="enh"><p class="muted flush">Reading from Meta…</p></div>`)}
      </div>`;
  // A refresh redraws the right-hand side only: the preview stays as it is (an iframe put back reloads),
  // unless it has grown old enough for Meta's link to stop working.
  const side0 = document.querySelector("#cr-main .cr-layout > .cr-side");
  if (side0 && $("preview-frame")) {
    // Tags typed but not saved yet come back after the redraw, and so does the place being typed in.
    const typed = Object.fromEntries([...side0.querySelectorAll("#idea input[name]")].map((i) => [i.name, i.value]));
    const focused = side0.contains(document.activeElement) && document.activeElement.id ? document.activeElement.id : null;
    ideaKept = Object.keys(typed).length ? { typed, focused } : null;
    side0.outerHTML = side;
    $("pv-note").innerHTML = reviewNote;
    if (previewStale()) loadPreview();
  } else {
    $("cr-main").innerHTML = `
    ${new URLSearchParams(location.search).get("created") ? '<p class="note claude-note">Created and <b>off</b>. Check the previews, then turn it on with the switch at the top when you\'re happy.</p>' : ""}
    ${new URLSearchParams(location.search).get("created") && leftDraft ? draftLeftHtml(leftDraft) : ""}
    <div class="cr-layout">${preview}${side}</div>`;
    loadPreview();
  }
  if (data.series) drawDaily(data.series, data.marks, data.marks_summary, data.marks_list, data.source); else pickRange(chartRange);
  $("chart-range").addEventListener("change", (e) => pickRange(e.target.value));
  const asked = foldAsked && $(`fold-${foldAsked}`);
  if (asked) { asked.open = true; asked.scrollIntoView({ block: "start" }); foldAsked = null; }
  loadEnhancements();
  loadIdea();
  loadDiagnose();
  loadMxDiagnose();
  if ($("mx-errors")) sizeExtras($("mx-errors"));
  showPvView();
  const budgetLevel = ad.adset_budget_cents ? "adset" : "campaign";
  const eb = $("edit-budget");
  if (eb) eb.addEventListener("click", () => editBudget({ level: budgetLevel, id: budgetLevel === "adset" ? ad.adset_id : ad.campaign_id, name: budgetLevel === "adset" ? ad.adset_name : ad.campaign_name, current: ad.adset_budget_cents || ad.campaign_budget_cents }, load));
  if (ad.adset_id) api(`/api/insights/adset/${encodeURIComponent(ad.adset_id)}/estimate`).then((e) => {
    if (e.lower && e.upper && $("estimate")) $("estimate").innerHTML = `<br><span class="muted small">Meta estimates ${count(e.lower)}–${count(e.upper)} people could see ads from this ad set.</span>`;
  }).catch(() => {});
}

// AM-E: Live preview or Meta's picture (as Ads Manager renders it, read by the Mac's link).
function showPvView() {
  const box = $("mx-pic-box");
  if (!box) return;
  const pic = pvView === "picture";
  document.querySelectorAll("#mx-view [data-pv-view]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.pvView === pvView)));
  $("pv-live").hidden = pic;
  box.hidden = !pic;
  if (pic && !picWait) { box.innerHTML = pictureHtml(data.meta_picture || {}, data.ad.id); sizeExtras(box); }
}

async function getPicture(btn) {
  btn.disabled = true;
  let asked;
  try { asked = (await api(`/api/ads/ad/${encodeURIComponent(adId)}/screenshot/refresh`, { method: "POST", body: {} })).asked_at; }
  catch (err) { toast(err.message, "bad"); btn.disabled = false; return; }
  const note = $("mx-wait");
  if (note) { note.hidden = false; note.textContent = "Asked your Mac for Meta's picture…"; }
  const until = Date.now() + 30000;
  picWait = setInterval(async () => {
    let r = null;
    try { r = await fetch(`/api/ads/ad/${encodeURIComponent(adId)}/screenshot?after=${encodeURIComponent(asked)}`); } catch (err) { /* try again */ }
    if (r && r.status === 200) {
      clearInterval(picWait); picWait = null;
      try { data = { ...data, meta_picture: (await api(`/api/ads/ad/${encodeURIComponent(adId)}`)).meta_picture }; } catch (err) { /* keep the old */ }
      showPvView();
      toast("Meta's picture is here");
    } else if (Date.now() > until) {
      clearInterval(picWait); picWait = null;
      const w = $("mx-wait");
      if (w) { w.hidden = false; w.textContent = "Your Mac hasn't answered yet; it will be here when it does."; }
      if ($("mx-get")) $("mx-get").disabled = false;
    }
  }, 2000);
}

// Diagnose with Claude on Meta's error message (admins): the alert's own run, as in the Inbox.
function loadMxDiagnose() {
  const box = $("mx-diag");
  const id = data.meta_errors && data.meta_errors.alert_id;
  if (!box || !id) return;
  api(`/api/diagnose/draft?alert_id=${encodeURIComponent(id)}`)
    .then((d) => { if ($("mx-diag") === box) box.innerHTML = diagnoseHtml({ alertId: id }, d.run); })
    .catch(() => { if ($("mx-diag") === box) box.innerHTML = diagnoseHtml({ alertId: id }, null); });
}

// A rejected ad or one with issues (admins): Diagnose with Claude, or where that diagnosis is. It shares its run with
// the ad's rejection alert in the Inbox (one run per problem).
function loadDiagnose() {
  const box = $("cs-diag");
  if (!box) return;
  const id = data.ad.id;
  api(`/api/diagnose/draft?ad_id=${encodeURIComponent(id)}`)
    .then((d) => { if ($("cs-diag") === box) box.innerHTML = diagnoseHtml({ adId: id }, d.run); })
    .catch(() => { if ($("cs-diag") === box) box.innerHTML = diagnoseHtml({ adId: id }, null); });
}

function drawDaily(series, marks = [], marksSummary = "", marksList = null, source = null) {
  columnChart({ el: $("c-spend"), series, key: "spend_cents", color: "var(--chart-spend)", title: "Spend per day", height: 160,
    format: (v) => money(v, { exact: true }), axisFormat: (v) => moneyWhole(v), marks, marksSummary });
  columnChart({ el: $("c-leads"), series, key: "leads", color: "var(--chart-leads)", title: "Leads per day", integer: true, height: 160,
    format: (v) => `${v} lead${v === 1 ? "" : "s"}`, axisFormat: (v) => String(Math.round(v)), marks, marksSummary });
  marksPanel($("chg-panel"), marks, marksSummary, marksList);
  if ($("fig-src")) $("fig-src").innerHTML = sourceNote(source);
}

// Dates picked here are the shared range: the address keeps them and the other pages open on them.
function keepRange(r) {
  rememberRange(r);
  const u = new URL(location.href);
  u.searchParams.set("range", r);
  history.replaceState(history.state, "", u);
}

async function pickRange(r) {
  chartRange = r;
  if (AUDIENCE_RANGES.some(([k]) => k === r)) audienceRange = r;
  keepRange(r);
  if ($("per-day-note")) $("per-day-note").textContent = r !== "lastmonth" ? "With today so far, Meta still counting" : "Complete days only";
  const superseded = startLoad("series");
  try {
    const d = await api(`/api/ads/ad/${encodeURIComponent(adId)}/series?range=${encodeURIComponent(r)}`);
    if (superseded() || !$("c-spend")) return;
    data.series = d.series;
    data.marks = d.marks;
    data.marks_summary = d.marks_summary;
    data.marks_list = d.marks_list;
    drawDaily(d.series, d.marks, d.marks_summary, d.marks_list, d.source);
  } catch (err) { if (!superseded()) toast(err.message, "bad"); }
}

// ---------------------------------------------------------------- the idea (concept tags)

function ideaHtml(d) {
  if (!data.ad.can_control) {
    return `<dl class="facts">${d.order.map((k) => `<div><dt>${esc(d.dimensions[k][0])}</dt><dd>${esc(d.tags[k] || "—")}</dd></div>`).join("")}</dl>`;
  }
  return `${d.order.map((k) => [k, d.dimensions[k]]).map(([k, [label, hint]]) => `<div class="field idea-row">
      <label for="tag-${k}">${esc(label)}</label>
      <input class="input" id="tag-${k}" name="${k}" value="${esc(d.tags[k] || "")}" list="tag-list-${k}" placeholder="${esc(hint)}" autocomplete="off" maxlength="80">
      <datalist id="tag-list-${k}">${(d.known[k] || []).map((v) => `<option value="${esc(v)}">`).join("")}</datalist>
    </div>`).join("")}
    <div class="row"><button class="btn btn-small" type="submit">Save</button><span class="muted small">Reuse a value from the list so ads group together.</span></div>`;
}
const ideaSub = (d) => d.order.map((k) => d.tags[k]).filter(Boolean).map(esc).join(" · ") || '<span class="muted">Not labelled yet</span>';

let ideaKept = null;  // what a refresh found typed in The idea, put back once the tags are read again
async function loadIdea() {
  const f = $("idea");
  if (!f) return;
  const kept = ideaKept;
  ideaKept = null;
  try {
    const d = await api(`/api/ads/ad/${encodeURIComponent(adId)}/tags`);
    if (!f.isConnected) return;
    f.innerHTML = ideaHtml(d);
    setFoldSub("idea", ideaSub(d));
    if (kept) {
      for (const [name, value] of Object.entries(kept.typed)) { const i = f.querySelector(`input[name="${CSS.escape(name)}"]`); if (i) i.value = value; }
      if (kept.focused && $(kept.focused)) $(kept.focused).focus({ preventScroll: true });
    }
  }
  catch (err) { f.innerHTML = `<p class="muted flush">${esc(err.message)}</p>`; setFoldSub("idea", '<span class="muted">Didn\'t load</span>'); }
}

document.addEventListener("submit", async (e) => {
  if (e.target.id !== "idea") return;
  e.preventDefault();
  const tags = Object.fromEntries([...e.target.querySelectorAll("input[name]")].map((i) => [i.name, i.value.trim()]));
  try { const d = await api(`/api/ads/ad/${encodeURIComponent(adId)}/tags`, { method: "PUT", body: { tags } }); e.target.innerHTML = ideaHtml(d); setFoldSub("idea", ideaSub(d)); toast("Saved"); }
  catch (err) { toast(err.message, "bad"); }
});

// ---------------------------------------------------------------- Meta's automatic changes

function enhancementsHtml(d) {
  if (!d.features.length) return '<p class="muted flush">The creative doesn\'t list any. Meta applies its defaults; check Advanced preview in Ads Manager.</p>';
  const warn = d.against_advice.length ? `<p class="note warn">On, and they change your words or pictures: ${esc(d.against_advice.join(", "))}. For brand copy the usual advice is to switch them off.</p>` : "";
  return `${warn}<ul class="enh-list">${d.features.map((f) => `<li>
      <div class="enh-text"><b>${esc(f.label)}</b><span class="muted small">${esc(f.about)}${f.advice === "fine" ? " Harmless: it doesn't change what the ad says." : ""}</span></div>
      ${d.can_change ? switchHtml(f.on, `data-enh="${esc(f.key)}" data-label="${esc(f.label)}"`, `${f.label} on or off`) : `<span class="pill ${f.on ? "ok" : ""}">${f.on ? "On" : "Off"}</span>`}
    </li>`).join("")}</ul>
    ${d.can_change ? '<p class="muted small flush">Switching one makes a copy of the creative with the new setting and puts it on this ad. Meta reviews the ad again (usually minutes to a few hours). Results so far stay with the ad; likes and comments stay with the old post.</p>' : ""}`;
}
// The fold's line: how many are on, and a warning pill when one rewrites the words or pictures.
function enhancementsSub(d) {
  const on = d.features.filter((f) => f.on).length;
  const words = !d.features.length ? "None listed" : on ? `${on} of ${d.features.length} on` : "All off";
  return `${esc(words)}${d.against_advice.length ? ` <span class="pill warn">${d.against_advice.length === 1 ? "1 changes" : `${d.against_advice.length} change`} your words or pictures</span>` : ""}`;
}

async function loadEnhancements() {
  const box = $("enh");
  if (!box) return;
  try { const d = await api(`/api/ads/ad/${encodeURIComponent(adId)}/enhancements`); box.innerHTML = enhancementsHtml(d); setFoldSub("auto", enhancementsSub(d)); }
  catch (err) { box.innerHTML = `<p class="muted flush">${esc(err.message)}</p>`; setFoldSub("auto", '<span class="muted">Didn\'t load</span>'); }
}

document.addEventListener("click", async (e) => {
  const sw = e.target.closest("[data-enh]");
  if (!sw) return;
  const on = sw.getAttribute("aria-checked") !== "true";
  const yes = await confirmDialog({ title: `Turn ${on ? "on" : "off"} “${sw.dataset.label}”?`,
    body: "<p>Makes a copy of the creative with this setting and puts it on the ad. Meta reviews the ad again before it delivers with the change.</p><p class=\"note warn\">The copy is a new post: likes, comments and shares on the current one stay behind.</p>",
    confirm: on ? "Turn on" : "Turn off" });
  if (!yes) return;
  sw.disabled = true;
  try {
    const d = await api(`/api/ads/ad/${encodeURIComponent(adId)}/enhancements`, { method: "POST", body: { key: sw.dataset.enh, on } });
    $("enh").innerHTML = enhancementsHtml(d);
    setFoldSub("auto", enhancementsSub(d));
    toast(`${sw.dataset.label} is ${on ? "on" : "off"}. Meta reviews the ad again.`);
  } catch (err) { toast(err.message, "bad"); sw.disabled = false; }
});

// ---------------------------------------------------------------- polish

const PRESET_LABELS = { full: "Full audit", copy: "Words only", design: "Design only", quick: "Quick check" };

async function renderPolish() {
  const superseded = startLoad("tab");
  if (!$("polish-form")) $("cr-main").innerHTML = `<section class="panel"><div class="panel-body">${skeleton("Loading the polish checks…")}</div></section>`;
  let runs;
  try {
    [passes, runs] = await Promise.all([passes || api("/api/polish/passes"), api(`/api/ads/ad/${encodeURIComponent(adId)}/polish-runs`).then((r) => r.tasks)]);
  } catch (err) {
    if (superseded()) return;
    // A refresh that fails keeps the form and what was typed; a first load that fails says so, with Try again.
    if ($("polish-form")) toast(err.message, "bad"); else errorState($("cr-main"), err, renderPolish);
    return;
  }
  if (superseded()) return;
  // A refresh while a run works must not throw away a direction being written.
  const typed = { direction: $("direction")?.value || "", render: $("render-direction")?.value || "" };
  const last = runs.find((r) => r.kind === "polish" && r.scorecard);
  const selected = new Set(JSON.parse(sessionStorage.getItem("ebads-passes") || "null") || passes.presets.full);
  $("cr-main").innerHTML = `
    <div class="polish-layout">
      <section class="panel polish-panel">
        <div class="panel-head"><h2>Polish this ad</h2><p>Claude checks it against what gets ads approved and bringing in leads</p></div>
        <form class="panel-body stack" id="polish-form" novalidate>
          <div class="row presets">${Object.entries(PRESET_LABELS).map(([k, l]) => `<button type="button" class="chip" data-preset="${k}">${esc(l)}</button>`).join("")}
            <span class="spacer"></span><label class="check small"><input type="checkbox" id="show-checks"> Show what each pass checks</label></div>
          <div class="pass-grid">${passes.passes.map((p) => `
            <label class="pass ${selected.has(p.id) ? "on" : ""}">
              <input type="checkbox" name="pass" value="${p.id}" ${selected.has(p.id) ? "checked" : ""}>
              <span class="pass-top"><b>${esc(p.label)}</b>${last ? (() => { const r = last.scorecard.passes.find((x) => x.id === p.id); return r && r.score ? `<span class="mini-score s${Math.max(2, Math.min(5, r.score))}">${r.score}/5</span>` : ""; })() : ""}</span>
              <span class="pass-sum">${esc(p.summary)}</span>
              <ul>${p.checks.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>
            </label>`).join("")}</div>
          <div class="field"><label for="direction">Your direction <span class="muted">(optional)</span></label>
            <textarea class="input" id="direction" rows="2" placeholder="e.g. The headline feels long. Keep the offer but make it calmer."></textarea></div>
          <div class="row">
            <label class="check"><input type="checkbox" id="variants" checked> Write new copy versions I can put on this ad</label>
            <span class="spacer"></span>
            <button class="btn btn-claude" type="submit" id="run-polish">${icon("spark")}<span>Run polish</span></button>
          </div>
          <p class="muted small flush">Claude runs this on your Mac with your Meta access and the design rules learned so far. Nothing changes on Meta until you accept a suggestion: a new version goes on this same ad, so it keeps its results.</p>
        </form>
      </section>
      <section class="panel render-panel">
        <div class="panel-head"><h2>Make a new version</h2></div>
        <form class="panel-body stack tight" id="render-form" novalidate>
          <p class="flush muted small">Claude rebuilds the picture or video on your Mac, the same way your current ads were made, uploads it and sends it back as a suggestion. Accepting it updates this ad. Takes 10–40 minutes.</p>
          ${last ? `<label class="check"><input type="checkbox" id="use-fixes" checked> Apply the fixes from the latest polish (score ${last.scorecard.overall}/5)</label>` : ""}
          <div class="field"><label for="render-direction">What should change</label>
            <textarea class="input" id="render-direction" rows="3" placeholder="e.g. Shorter headline, bigger text, a calmer background."></textarea></div>
          <button class="btn" type="submit">${icon("image")}<span>Make a new version</span></button>
        </form>
      </section>
    </div>
    <h2 class="section-h">Earlier checks and new versions</h2>
    <div class="stack" id="runs">${runs.length ? runs.map((t) => taskCard(t, openReports, adIndex())).join("") : '<section class="panel empty"><h3>No polish checks yet</h3><p>Pick the passes above and run them. Results show here with a score per pass, the fixes, and new versions of the copy you can put on this ad.</p></section>'}</div>`;
  $("direction").value = typed.direction;
  $("render-direction").value = typed.render;

  const form = $("polish-form");
  let polishSending = false, renderSending = false;  // a double click or a tick during the POST queues one run
  const sync = () => {
    const chosen = [...form.querySelectorAll("input[name=pass]:checked")].map((i) => i.value);
    form.querySelectorAll(".pass").forEach((l) => l.classList.toggle("on", l.querySelector("input").checked));
    sessionStorage.setItem("ebads-passes", JSON.stringify(chosen));
    $("run-polish").querySelector("span").textContent = chosen.length === passes.passes.length ? "Run full audit" : `Run ${chosen.length} pass${chosen.length === 1 ? "" : "es"}`;
    $("run-polish").disabled = polishSending || !chosen.length;
  };
  form.addEventListener("change", (e) => {
    if (e.target.id === "show-checks") { form.querySelector(".pass-grid").classList.toggle("show-checks", e.target.checked); return; }
    sync();
  });
  form.querySelector(".presets").addEventListener("click", (e) => {
    const b = e.target.closest("[data-preset]");
    if (!b) return;
    const set = new Set(passes.presets[b.dataset.preset]);
    form.querySelectorAll("input[name=pass]").forEach((i) => { i.checked = set.has(i.value); });
    sync();
  });
  sync();
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const chosen = [...form.querySelectorAll("input[name=pass]:checked")].map((i) => i.value);
    if (polishSending || !chosen.length) return;
    polishSending = true;
    $("run-polish").disabled = true;
    try {
      await api(`/api/ads/ad/${encodeURIComponent(adId)}/polish`, { method: "POST", body: { passes: chosen, direction: $("direction").value, variants: $("variants").checked } });
      toast("Sent to Claude");
      $("direction").value = "";
      renderPolish();
    } catch (err) { toast(err.message, "bad"); polishSending = false; sync(); }
  });
  $("render-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const renderBtn = $("render-form").querySelector("button[type=submit]");
    if (renderSending) return;
    renderSending = true;
    const useFixes = $("use-fixes") && $("use-fixes").checked;
    const ok = await confirmDialog({
      title: "Make a new version?",
      body: "<p>Claude rebuilds the creative on your Mac and uploads it to your Meta media library. You get it back as a suggestion; nothing changes on this ad until you accept it.</p>",
      confirm: "Make it", claude: true,
    });
    if (!ok) { renderSending = false; return; }
    renderBtn.disabled = true;
    try {
      await api(`/api/ads/ad/${encodeURIComponent(adId)}/render`, { method: "POST", body: { direction: $("render-direction").value, from_task: useFixes ? last.id : null } });
      toast("Sent to Claude");
      $("render-direction").value = "";
      renderPolish();
    } catch (err) { toast(err.message, "bad"); renderSending = false; renderBtn.disabled = false; }
  });
  // While a run works: refresh every 6 s, never while the person is in one of the forms.
  const poll = () => {
    if (tab !== "polish") return;
    if (document.activeElement?.closest("form")) pollTimer = setTimeout(poll, 6000);
    else renderPolish();
  };
  if (runs.some((r) => ACTIVE.has(r.status))) pollTimer = setTimeout(poll, 6000);
}

// ---------------------------------------------------------------- audience

const BY = [["placement", "Placement"], ["age", "Age"], ["gender", "Gender"], ["device", "Device"], ["region", "Region"], ["hour", "Hour of day"]];

async function renderAudience() {
  $("cr-main").innerHTML = `
    <section class="panel">
      <div class="panel-head wrap"><h2>Who saw it, and where</h2><span class="spacer"></span>
        ${rangeSelect("aud-range", audienceRange, AUDIENCE_RANGES)}</div>
      <div class="panel-body stack">
        <div class="segmented wraps" id="aud-by" role="group" aria-label="Break down by">${BY.map(([k, l]) => `<button type="button" data-by="${k}" aria-pressed="${k === audienceBy}">${l}</button>`).join("")}</div>
        <div id="aud-body">${skeleton("Loading from Meta…")}</div>
      </div>
    </section>`;
  $("aud-by").addEventListener("click", (e) => { const b = e.target.closest("[data-by]"); if (b) { audienceBy = b.dataset.by; renderAudience(); } });
  $("aud-range").addEventListener("change", (e) => {
    audienceRange = e.target.value;
    if (RANGES.some(([k]) => k === audienceRange)) { chartRange = audienceRange; keepRange(audienceRange); data.series = null; }
    renderAudience();
  });
  const superseded = startLoad("tab");
  try {
    const d = await api(`/api/insights/breakdown?level=ad&id=${encodeURIComponent(adId)}&by=${audienceBy}&range=${audienceRange}`);
    if (superseded()) return;
    const total = d.items.reduce((s, i) => s + i.spend_cents, 0);
    if (!d.items.length || !total) {
      $("aud-body").innerHTML = emptyState({ title: "Nothing to show for these dates", panel: false, variant: "compact",
        body: "Meta has no spend for this ad in these dates. Pick a longer range, or check again once it has been delivering for a day." });
      return;
    }
    $("aud-body").innerHTML = `<div class="aud-grid">
        <div><h3 class="chart-title">Share of spend</h3><div id="aud-spend"></div></div>
        <div><h3 class="chart-title">Leads and cost per lead</h3><div id="aud-leads"></div></div>
      </div>
      <p class="muted small flush" id="aud-note">Complete days only. Small groups swing a lot: judge a slice only after it has a few leads.${audienceBy === "region" ? " Region is where people are, not where they live." : ""}</p>`;
    barList($("aud-spend"), d.items, { key: "spend_cents", format: (v) => `${Math.round((v / total) * 100)}%`, extra: (i) => money(i.spend_cents) });
    barList($("aud-leads"), d.items, { key: "leads", format: (v) => count(v), extra: (i) => (i.leads ? `${per(i.spend_cents, i.leads)} per lead` : "no leads") });
  } catch (err) { if (!superseded()) errorState($("aud-body"), err, renderAudience, null, { panel: false, missing: false }); }
}

// ---------------------------------------------------------------- video

async function renderVideo() {
  $("cr-main").innerHTML = `<section class="panel"><div class="panel-body">${skeleton("Loading the video's numbers from Meta…")}</div></section>`;
  const superseded = startLoad("tab");
  try {
    const d = await api(`/api/insights/ad/${encodeURIComponent(adId)}/diagnostics`);
    if (superseded()) return;
    const f = d.funnel;
    const steps = [
      { label: WORDS.impressions, v: f.impressions }, { label: "Watched 3 seconds", v: f.video_3s }, { label: "Watched 25%", v: f.p25 },
      { label: "Watched 50%", v: f.p50 }, { label: "Watched 75%", v: f.p75 }, { label: "Watched to the end", v: f.p100 },
    ];
    const hook = f.impressions ? f.video_3s / f.impressions : null;
    const hold = f.video_3s ? f.thruplays / f.video_3s : null;
    const rank = (k, label) => { const r = d.rankings[k]; const v = r.value || "UNKNOWN"; const cls = v.startsWith("ABOVE") ? "ok" : v === "AVERAGE" ? "" : v.startsWith("BELOW") ? "bad" : ""; return `<div><dt>${label}</dt><dd><span class="pill ${cls}">${esc(r.label || "Not enough data yet")}</span></dd></div>`; };
    $("cr-main").innerHTML = `
      <div class="video-grid">
        <section class="panel">
          <div class="panel-head"><h2>Watch funnel</h2><p>Since it started</p></div>
          <div class="panel-body"><div id="funnel"></div>
            <p class="muted small flush">Of everyone it was shown to, how many kept watching to each point.</p></div>
        </section>
        <div class="stack">
          <section class="panel">
            <div class="panel-head"><h2>Hook and hold</h2></div>
            <div class="panel-body">
              <dl class="mini-figs wide three">
                <div><dt>${WORDS.hook}</dt><dd>${hook == null ? "—" : `${(hook * 100).toFixed(1)}%`}</dd></div>
                <div><dt>${WORDS.hold}</dt><dd>${hold == null ? "—" : `${(hold * 100).toFixed(1)}%`}</dd></div>
                <div><dt>Average watch</dt><dd>${d.avg_watch_seconds ? `${d.avg_watch_seconds}s` : "—"}</dd></div>
              </dl>
              <p class="muted small flush">${esc(EXPLAIN.hook)} ${esc(EXPLAIN.hold)} Rules of thumb: hook above 25–30%, hold above 30%.</p>
            </div>
          </section>
          <section class="panel">
            <div class="panel-head"><h2>Meta's quality read</h2><p>Last 30 days</p></div>
            <div class="panel-body">
              <dl class="facts">
                ${rank("quality_ranking", "Quality")}${rank("engagement_rate_ranking", "Engagement")}${rank("conversion_rate_ranking", "Conversion")}
                <div><dt>Frequency</dt><dd>${d.frequency ? `${d.frequency.toFixed(2)} times per person` : "—"}</dd></div>
                <div><dt>Cost per 1,000 views</dt><dd>${d.cpm_cents ? money(d.cpm_cents, { exact: true }) : "—"}</dd></div>
              </dl>
              <p class="muted small flush">Compared with ads competing for the same people. Meta shows these after about 500 views. Below average on quality usually means the creative; on conversion, the offer or the form.${d.error ? ` (Meta: ${esc(d.error)})` : ""}</p>
            </div>
          </section>
        </div>
      </div>`;
    barList($("funnel"), steps, { key: "v", format: (v) => count(v), max: f.impressions || 1, extra: (i) => (f.impressions ? `${((i.v / f.impressions) * 100).toFixed(1)}%` : "") });
  } catch (err) { if (!superseded()) errorState($("cr-main"), err, renderVideo, null, { missing: false }); }
}

// ---------------------------------------------------------------- comments

function commentHtml(c) {
  const thread = c.thread.map((r) => `<li class="${r.from_page ? "mine" : ""}"><b>${esc(r.from_page ? "You (the Page)" : r.name || "Someone")}</b><small>${esc(when(r.created_time))}</small><p>${esc(r.message || "")}</p></li>`).join("");
  return `<li class="comment${c.hidden ? " is-hidden" : ""}" data-comment="${esc(c.id)}">
    <div class="c-head"><b>${esc(c.name || "Someone")}</b><small>${esc(when(c.created_time))}${c.likes ? ` · ${c.likes} like${c.likes === 1 ? "" : "s"}` : ""}</small>
      ${c.hidden ? '<span class="pill">Hidden</span>' : c.answered ? '<span class="pill ok">Answered</span>' : '<span class="pill warn">Not answered</span>'}</div>
    <p>${esc(c.message || "")}</p>
    ${thread ? `<ul class="c-thread">${thread}</ul>` : ""}
    ${data.ad.can_control ? `<div class="row c-actions">
      <button type="button" class="btn btn-small" data-reply-open>Reply</button>
      ${c.can_hide ? `<button type="button" class="btn btn-quiet btn-small" data-hide="${c.hidden ? "0" : "1"}">${c.hidden ? "Show again" : "Hide"}</button>` : ""}
    </div>
    <form class="c-reply" hidden novalidate>
      <label class="sr-only" for="r-${esc(c.id)}">Reply to ${esc(c.name || "this comment")}</label>
      <textarea class="input" id="r-${esc(c.id)}" name="message" rows="3" placeholder="Reply publicly as the Page"></textarea>
      <div class="row"><button class="btn btn-primary btn-small" type="submit">Send reply</button><button class="btn btn-quiet btn-small" type="button" data-reply-cancel>Cancel</button>
        <span class="muted small">Everyone who sees the ad can read it.</span></div>
    </form>` : ""}
  </li>`;
}

async function renderComments() {
  // A refresh while a reply is being written keeps it: the list stays up until the new one is in, and the text comes back.
  const typed = Object.fromEntries([...document.querySelectorAll(".comments .c-reply")].filter((f) => !f.hidden)
    .map((f) => [f.closest("[data-comment]").dataset.comment, f.message.value]));
  if (!document.querySelector(".comments-panel")) $("cr-main").innerHTML = `<section class="panel"><div class="panel-body">${skeleton("Loading comments from Facebook…")}</div></section>`;
  const superseded = startLoad("tab");
  try {
    const d = await api(`/api/insights/ad/${encodeURIComponent(adId)}/comments`);
    if (superseded()) return;
    const open = d.items.filter((c) => !c.answered && !c.hidden).length;
    $("cr-main").innerHTML = `<section class="panel comments-panel">
      <div class="panel-head"><h2>Comments</h2><p>${count(d.total)} on the ad's post${open ? ` · ${open} not answered` : ""}</p><span class="spacer"></span>${d.post_url ? `<a class="btn btn-quiet btn-small" href="${esc(d.post_url)}" target="_blank" rel="noopener noreferrer">Open on Facebook ${icon("external")}</a>` : ""}</div>
      <div class="panel-body">${d.items.length ? `<ul class="comments">${d.items.map(commentHtml).join("")}</ul>
        ${data.ad.can_control ? '<p class="muted small flush">Hiding keeps a comment visible to its writer and their friends, and to no one else. Nothing is deleted from here.</p>' : ""}`
        : emptyState({ title: d.note ? "" : "No comments yet", body: esc(d.note || "Questions here are warm leads: reply within a few hours."), panel: false, variant: "compact" })}</div></section>`;
    for (const [id, text] of Object.entries(typed)) {
      const form = document.querySelector(`[data-comment="${CSS.escape(id)}"] .c-reply`);
      if (form) { form.hidden = false; form.message.value = text; }
    }
  } catch (err) {
    if (superseded()) return;
    if (document.querySelector(".comments-panel")) toast(err.message, "bad");
    else errorState($("cr-main"), err, renderComments, null, { missing: false });
  }
}

document.addEventListener("click", async (e) => {
  const li = e.target.closest("[data-comment]");
  if (!li) return;
  const form = li.querySelector(".c-reply");
  if (e.target.closest("[data-reply-open]")) { form.hidden = false; form.message.focus(); return; }
  if (e.target.closest("[data-reply-cancel]")) { form.hidden = true; return; }
  const hb = e.target.closest("[data-hide]");
  if (hb) {
    const hide = hb.dataset.hide === "1";
    if (hide && !(await confirmDialog({ title: "Hide this comment?", body: "<p>Only its writer and their friends will still see it. You can show it again any time.</p>", confirm: "Hide" }))) return;
    try { await api(`/api/insights/ad/${encodeURIComponent(adId)}/comments/${encodeURIComponent(li.dataset.comment)}/hide`, { method: "POST", body: { hidden: hide } }); toast(hide ? "Hidden" : "Shown again"); renderComments(); }
    catch (err) { toast(err.message, "bad"); }
  }
});

document.addEventListener("submit", async (e) => {
  const form = e.target.closest(".c-reply");
  if (!form) return;
  e.preventDefault();
  const li = form.closest("[data-comment]");
  const message = form.message.value.trim();
  if (!message) { form.message.focus(); return; }
  if (!(await confirmDialog({ title: "Post this reply?", body: `<p>It appears publicly under the comment, from the Page:</p><p class="quote">${esc(message)}</p>`, confirm: "Post reply" }))) return;
  try { await api(`/api/insights/ad/${encodeURIComponent(adId)}/comments/${encodeURIComponent(li.dataset.comment)}/reply`, { method: "POST", body: { message } }); toast("Reply posted"); renderComments(); }
  catch (err) { toast(err.message, "bad"); }
});

// ---------------------------------------------------------------- history

// One timeline (the same one as the Campaign and Ad set pages), filtered by who it came from; each line links to
// what it is about. Claude's decided suggestions keep their full cards below it.
const HISTORY_SHOW = [["all", "Everything"], ["meta", "From Meta"], ["console", "Made here"], ["claude", "Claude"]];

function renderHistory() {
  const decided = data.proposals.filter((p) => p.status !== "pending");
  const items = data.history || [];
  const n = (k) => (k === "all" ? items.length : items.filter((i) => i.source === k).length);
  const shown = (data.ad.can_control ? HISTORY_SHOW : HISTORY_SHOW.filter(([k]) => k !== "claude")).filter(([k]) => k === "all" || n(k));
  if (!shown.some(([k]) => k === historyShow)) historyShow = "all";
  const list = items.filter((i) => historyShow === "all" || i.source === historyShow);
  $("cr-main").innerHTML = `
    <section class="panel" aria-labelledby="hist-h">
      <div class="panel-head wrap"><h2 id="hist-h">What happened</h2><p>Meta's review and delivery, changes made here${data.ad.can_control ? ", and Claude's suggestions" : ""}, newest first</p></div>
      <div class="panel-body stack tight">
        ${shown.length > 2 ? `<div class="filters" role="group" aria-label="Show" id="hist-show">${shown.map(([k, l]) => `<button type="button" class="view-chip" data-show="${k}" aria-pressed="${k === historyShow}">${l}<span>${n(k)}</span></button>`).join("")}</div>` : ""}
        ${list.length ? timelineHtml(list, { cards: true }) : emptyState({ title: "Nothing recorded yet", body: "Meta's review and delivery changes show here from the next refresh, with every change made from this console.", panel: false, variant: "compact" })}
      </div></section>
    ${decided.length ? `<section class="panel" id="hist-cards"><div class="panel-head"><h2>Claude's earlier suggestions</h2><p>What each one would have changed, and what became of it</p></div><div class="panel-body stack tight">${decided.map((p) => proposalCard(p, null, adIndex())).join("")}</div></section>` : ""}`;
}

// ---------------------------------------------------------------- load

let urlCheckDone = false;
async function load() {
  try {
    const fresh = await api(`/api/ads/ad/${encodeURIComponent(adId)}?range=${encodeURIComponent(chartRange)}`);
    data = { ...fresh, comment_total: data && data.comment_total };
    renderHead();
    if ((tab === "video" && data.ad.object_type !== "VIDEO") || (tab === "polish" && !data.ad.can_control)) tab = "overview";
    showTab(tab);
    if (!urlCheckDone) { urlCheckDone = true; openFromUrl(); }  // ?check=N: a change's "Did it work?" (Inbox, Today)
    api(`/api/insights/ad/${encodeURIComponent(adId)}/comments`).then((c) => { data.comment_total = c.total; renderHead(); }).catch(() => {});
  } catch (err) {
    // A refresh that fails keeps the page as it was; a first load says what happened, with Try again.
    if (data) toast(err.message, "bad");
    else errorState($("cr-main"), err, load, { href: "/ads.html", label: "Back to Ads" });
  }
}

me = await boot({ page: "ad" });
if (me) {
  // Made from an Ads Manager draft (AM-B, ?created=1&draft_left=<id>): say the draft is still there to discard.
  const q = new URLSearchParams(location.search);
  if (q.get("created") && q.get("draft_left") && me.role === "admin") {
    draftLeftFor(q.get("draft_left")).then((d) => {
      leftDraft = d;
      if (d && !$("dr-left")) document.querySelector("#cr-main .claude-note")?.insertAdjacentHTML("afterend", draftLeftHtml(d));
    });
  }
  wireAlerts(document.body, (id) => (data && data.meta_errors && data.meta_errors.alert_id === id ? { alert_id: id } : null),
    () => { loadDiagnose(); loadMxDiagnose(); });
  document.addEventListener("click", async (e) => {
    const t = e.target.closest("#cr-tabs [data-tab]");
    if (t) { showTab(t.dataset.tab); return; }
    const g = e.target.closest("[data-goto]");
    if (g) { showTab(g.dataset.goto); window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    const f = e.target.closest("#formats button[data-format]");
    if (f) { format = f.dataset.format; try { localStorage.setItem("ebads-preview", format); } catch (err) {} loadPreview(); return; }
    if (e.target.closest("#preview-reload, [data-preview-again]")) { loadPreview(); return; }
    const pv = e.target.closest("#mx-view [data-pv-view]");
    if (pv) { pvView = pv.dataset.pvView; try { localStorage.setItem("ebads-preview-view", pvView); } catch (err) {} showPvView(); return; }
    const get = e.target.closest("#mx-get");
    if (get) { getPicture(get); return; }
    const show = e.target.closest("#hist-show [data-show]");
    if (show) { historyShow = show.dataset.show; renderHistory(); $("hist-show")?.querySelector(`[data-show="${historyShow}"]`)?.focus(); return; }
    const jump = e.target.closest("[data-jump]");
    if (jump) {
      const card = $(jump.dataset.jump);
      if (card) {
        card.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
        card.classList.remove("flash"); void card.offsetWidth; card.classList.add("flash");
        card.setAttribute("tabindex", "-1"); card.focus({ preventScroll: true });
      }
      return;
    }
    const back = e.target.closest("[data-restore]");
    if (back) { restoreVersion({ adId, number: back.dataset.restore }, load, back); return; }
    const sw = e.target.closest("[data-toggle]");
    if (sw) { toggleEntity(sw, load); return; }
    if (e.target.closest("#archive")) {
      const ad = data.ad;
      const yes = await confirmDialog({
        title: `Archive “${ad.name}”?`,
        body: "<p>It disappears from the Ads page (\"Show archived\" brings it back into view) and from Meta's main list. Its numbers stay.</p><p>Meta can't switch an archived ad back on. You can still delete it later. To run it again, duplicate it.</p>",
        confirm: "Archive",
      });
      if (!yes) return;
      try {
        await api(`/api/ads/ad/${encodeURIComponent(ad.id)}/archive`, { method: "POST" });
        toast("Archived");
        load();
      } catch (err) { toast(err.message, "bad"); }
      return;
    }
    if (e.target.closest("#delete")) {
      const ad = data.ad;
      const name = await confirmDialog({
        title: `Delete “${ad.name}”?`,
        body: "<p>Deletes it in Meta. <b>This can't be undone.</b> Its past spend and leads stay in your reports.</p>",
        confirm: "Delete for good", danger: true,
        field: { label: "Type the ad's name to confirm", value: "", validate: (v) => (v.trim() === ad.name.trim() ? null : "The name doesn't match") },
      });
      if (name === false) return;
      try {
        await api(`/api/ads/ad/${encodeURIComponent(ad.id)}/delete`, { method: "POST", body: { name } });
        toast(`Deleted “${ad.name}”`);
        location.href = "/ads.html";
      } catch (err) { toast(err.message, "bad"); }
      return;
    }
    if (e.target.closest("#dup")) {
      const ad = data.ad;
      const name = await confirmDialog({
        title: `Duplicate “${ad.name}”?`,
        body: "<p>Makes a copy in the same ad set with the same video or image, words and button. The copy starts <b>off</b>, so nothing spends until you turn it on.</p>",
        confirm: "Duplicate",
        field: { label: "Name for the copy", value: `${ad.name} - copy`, validate: (v) => (v.trim() ? null : "Give it a name") },
      });
      if (name === false) return;
      try {
        const r = await api(`/api/ads/ad/${encodeURIComponent(ad.id)}/duplicate`, { method: "POST", body: { name } });
        toast("Copy created (off)");
        location.href = `/ad.html?id=${encodeURIComponent(r.id)}&created=1`;
      } catch (err) { toast(err.message, "bad"); }
    }
  });
  wireTaskActions(document.querySelector(".main"), load, openReports);
  onRefresh(load);
  load();
}
