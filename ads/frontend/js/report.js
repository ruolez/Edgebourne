import { api } from "./api.js";
import { boot, confirmDialog, entityLink, esc, fieldError, guardLeaving, markSaved, pairNote, sourceNote, toast } from "./ui.js";
import { EXPLAIN, WORDS, count, dayLabel, money, setCurrency } from "./format.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const token = params.get("t");
const sentView = params.get("sent") === "1";
let kind = params.get("kind") === "month" ? "month" : "week";
let start = /^\d{4}-\d{2}-\d{2}$/.test(params.get("start") || "") ? params.get("start") : "";
let shown = null;
let me = null;
let noteAt = null;     // the saved note's time as loaded: a save from an older copy is refused (two admins)
let noteDirty = false; // typed since it was loaded or saved: a redraw keeps the typing
let poll = null;

const LEVEL = { campaign: "Campaign", adset: "Ad set", ad: "Ad", form: "Lead form", study: "A/B test", account: "Account" };
const NOTE_MAX = 2000;
const yearDay = (iso) => `${dayLabel(iso)}, ${iso.slice(0, 4)}`;
const who = (to) => (!to.length ? "nobody yet" : to.length === 1 ? to[0] : to.length === 2 ? `${to[0]} and ${to[1]}` : `${to[0]} and ${to.length - 1} others`);
const firstName = (name) => (name || "").trim().split(/\s+/)[0] || "";

function changeLine(c) {
  // Signed in, each name links to its page (share links and frozen copies carry no ids, so their names stay plain).
  const line = c.entity_id && ["campaign", "adset", "ad", "form"].includes(c.level) && c.what
    ? `${esc(LEVEL[c.level] || c.level)} “${entityLink(c.level, c.entity_id, c.name || "")}”: ${esc(c.what)}${c.where === "outside" ? " (in Ads Manager)" : ""}`
    : esc(c.text);
  return `<li><span class="r-date">${esc(dayLabel(c.day))}</span> ${line}</li>`;
}

function noteHtml(text, by) {
  if (!text || !text.trim()) return "";
  return `<h3>Our note</h3><p class="rv-text flush">${esc(text.trim())}</p>${by ? `<p class="muted small flush rv-sign">— ${esc(by)}</p>` : ""}`;
}

function ideasLine(ideas) {
  if (!ideas || !ideas.best) return "";
  const g = (ideas.groups || []).find((x) => x.value === ideas.best);
  // Qualified of the leads received from its ads (the console's count, like the funnel), never of Meta's count.
  const share = g && g.received && g.qualified <= g.received ? `; ${count(g.qualified || 0)} of its ${count(g.received)} lead${g.received === 1 ? "" : "s"} qualified` : "";
  return `<p class="flush">Of the ideas behind the ads, <b>${esc(ideas.best)}</b> brought the cheapest leads${ideas.clear ? ` (${ideas.sure}% sure)${share}.` : `, but only ${ideas.sure}% sure, so it could still be chance${share}.`}</p>`;
}

function reportHtml(r) {
  setCurrency(r.currency);
  const range = `${dayLabel(r.start)} – ${dayLabel(r.end)}, ${r.end.slice(0, 4)}`;
  const n = r.now;
  const received = n.received ?? n.leads;
  const cpl = received ? n.spend_cents / received : null;
  const cpq = n.qualified ? n.spend_cents / n.qualified : null;
  const gap = r.lead_gap;
  const bigGap = gap && gap.diff <= -2 && -gap.diff >= gap.meta * 0.1;
  const note = r.note ? noteHtml(r.note.text, r.note.by) : "";
  return `<header class="r-head">
      <img src="/img/favicon.svg" alt="" width="40" height="40">
      <div><p class="r-kicker">Meta ads report · ${esc(r.kind === "week" ? "Week" : "Month")}</p><h2>${esc(r.account)}</h2><p class="muted flush">${esc(range)}${r.complete ? "" : " (not finished yet: figures will still change)"}</p></div>
    </header>
    <section class="r-sec r-note" id="r-note" ${note ? "" : "hidden"}>${note}</section>
    <section class="r-sec"><h3>1. What happened</h3>
      <p class="r-headline">${esc(r.headline)}</p>
      <div class="r-figs">
        <div><span>Spent</span><b>${money(n.spend_cents)}</b></div>
        <div><span>${WORDS.leads}</span><b>${count(received)}</b>${gap ? `<small>Meta counted ${count(gap.meta)}</small>` : ""}</div>
        <div><span>${WORDS.cpl}</span><b>${cpl ? money(cpl, { exact: true }) : "—"}</b></div>
        <div><span>${WORDS.qualified}</span><b>${count(n.qualified)}</b></div>
        <div><span>Cost per qualified lead</span><b>${cpq ? money(cpq, { exact: true }) : "—"}</b>${r.target_cents ? `<small>target ${money(r.target_cents)}</small>` : ""}</div>
      </div>
      <table class="table r-funnel"><thead><tr><th>Step</th><th class="num">People</th><th class="num">Share</th></tr></thead>
        <tbody>${r.funnel.map((f, i) => `<tr><th scope="row">${esc(f.step)}</th><td class="num">${count(f.n)}${i === 0 && n.meta_leads != null ? pairNote({ meta: n.meta_leads, received }) : ""}</td><td class="num">${f.rate == null ? "" : `${f.rate}% <span class="muted r-of">of ${esc(f.of)}</span>`}</td></tr>`).join("")}</tbody></table>
      ${r.lost_line ? `<p class="small flush r-lost" id="r-lost">${esc(r.lost_line)}</p>` : ""}
      ${r.source ? `<div class="r-src" id="r-src">${sourceNote(r.source)}</div>` : ""}
      ${gap ? `<p class="muted small flush r-gap">${esc(gap.text)}${bigGap && r.review ? ` If this stays, check that new leads reach the console: <a href="/settings.html#meta">Settings → Meta</a>.` : ""}</p>` : ""}
      ${n.median_minutes != null ? `<p class="muted flush small">Half of the leads got a first call or email within ${n.median_minutes < 90 ? `${n.median_minutes} minutes` : `${Math.round(n.median_minutes / 60)} hours`}.</p>` : ""}
    </section>
    <section class="r-sec"><h3>2. Why</h3>
      ${r.ads.length ? `<table class="table r-ads"><thead><tr><th>Ad</th><th class="num">${WORDS.spend}</th><th class="num">${WORDS.leads} (Meta)</th><th class="num">${WORDS.cpl}</th><th class="num" title="${esc(EXPLAIN.ctr)}">${WORDS.ctr}</th><th class="num" title="${esc(EXPLAIN.hook)}">${WORDS.hook}</th></tr></thead>
        <tbody>${r.ads.map((a) => `<tr><th scope="row">${entityLink("ad", a.id, a.name || "")}</th><td class="num">${money(a.spend_cents)}</td><td class="num">${count(a.leads)}</td><td class="num">${a.cpl_cents ? money(a.cpl_cents, { exact: true }) : "—"}</td><td class="num">${a.ctr != null ? `${a.ctr}%` : "—"}</td><td class="num">${a.hook != null ? `${a.hook}%` : "—"}</td></tr>`).join("")}</tbody></table>
        <p class="muted small flush" id="r-top-note">${r.ads_total > r.ads.length ? `Top ${r.ads.length} of ${r.ads_total} ads by spend. ` : ""}Earlier versions of an ad are counted under its name.</p>` : '<p class="muted flush">No ad spent money in this period.</p>'}
      ${ideasLine(r.ideas)}
    </section>
    <section class="r-sec"><h3>3. What we did</h3>
      ${r.changes.length ? `<ul class="r-list">${r.changes.map(changeLine).join("")}</ul>${r.changes_more ? `<p class="muted small flush">and ${count(r.changes_more)} earlier change${r.changes_more === 1 ? "" : "s"}.</p>` : ""}` : '<p class="muted flush">No changes to the ads in this period.</p>'}
    </section>
    <section class="r-sec"><h3>4. What's next</h3>
      ${r.tests.length ? `<ul class="r-list">${r.tests.map((t) => `<li><b>${entityLink("test", t.id, t.name)}</b> (${t.status === "running" ? "running" : "finished"}): ${esc(t.note)}</li>`).join("")}</ul>` : '<p class="muted flush">No tests running; we keep watching cost per lead and lead quality.</p>'}
    </section>
    <section class="r-sec"><h3>5. What we need from you</h3>
      ${r.needs.length ? `<ul class="r-list">${r.needs.map((x) => `<li>A decision on: ${esc(x)}</li>`).join("")}</ul>` : '<p class="flush">Nothing this time. Keep marking leads Contacted, Qualified or Won: it is how we judge which ads bring real customers.</p>'}
    </section>
    <footer class="r-foot">${r.footnotes.map((f) => `<p>${esc(f)}</p>`).join("")}${r.stamp ? `<p class="r-stamp" id="r-stamp">${esc(r.stamp.text)}</p>` : ""}${r.shared_until ? `<p>This link works until ${esc(dayLabel(r.shared_until))}.</p>` : ""}</footer>`;
}

// A client of an account that reviews reports first, on a period not sent yet.
function waitingHtml(r) {
  const last = r.latest_sent;
  const lastLabel = last && `${last.kind === "week" ? "Week" : "Month"} of ${dayLabel(last.start)}`;
  return `<header class="r-head">
      <img src="/img/favicon.svg" alt="" width="40" height="40">
      <div><p class="r-kicker">Meta ads report · ${esc(r.kind === "week" ? "Week" : "Month")}</p><h2>${esc(r.account)}</h2><p class="muted flush">${esc(`${dayLabel(r.start)} – ${dayLabel(r.end)}, ${r.end.slice(0, 4)}`)}</p></div>
    </header>
    <section class="r-sec rv-wait"><p class="flush">This report is still being prepared.${r.emailed ? " It will reach you by email." : ""}</p>
      ${last ? `<p class="flush"><a href="/report.html?kind=${esc(last.kind)}&start=${esc(last.start)}" id="rv-last">Open the last one we sent (${esc(lastLabel)})</a></p>` : '<p class="muted flush">Nothing has been sent yet.</p>'}
    </section>`;
}

// Earlier weeks or months to pick from (signed in only), newest first; the first is the one shown by default.
const monthName = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" });
const PERIOD_STATE = { sent: "sent", waiting: "waiting for you", scheduled: "set to go out", sending: "sending", skipped: "not sending" };
function periodLabel(p, i) {
  const words = kind === "week" ? `${dayLabel(p.start)} – ${dayLabel(p.end)}${p.start.slice(0, 4) !== String(new Date().getFullYear()) ? `, ${p.start.slice(0, 4)}` : ""}` : monthName(p.start);
  const state = p.status && PERIOD_STATE[p.status] ? ` · ${PERIOD_STATE[p.status]}` : "";
  return (i === 0 ? `${words} (last ${kind})` : words) + state;
}
function periodPicker(r) {
  const box = $("period-box");
  if (!box || !r.periods) return;
  const list = r.periods.some((p) => p.start === r.start) ? r.periods : [{ start: r.start, end: r.end }, ...r.periods];
  $("period-label").textContent = kind === "week" ? "Which week" : "Which month";
  $("period").innerHTML = list.map((p) => `<option value="${esc(p.start)}" ${p.start === r.start ? "selected" : ""}>${esc(periodLabel(p, r.periods.indexOf(p)))}</option>`).join("");
  box.hidden = list.length < 2;
}

function syncUrl() {
  history.replaceState(null, "", `?kind=${kind}${start ? `&start=${start}` : ""}`);
}

// ---------- review before it goes out (admins) ----------
const ACTION_BUTTONS = { send_now: "rv-send", send_later: "rv-later", hold: "rv-hold", skip: "rv-skip", undo_skip: "rv-unskip", view_sent: "rv-sent", send_again: "rv-resend" };

function paintNoteCount() {
  const len = $("rv-note").value.length;
  $("rv-count").hidden = len <= 1800;
  $("rv-count").textContent = `${len.toLocaleString()} of ${NOTE_MAX.toLocaleString()}`;
}

function paintNotePreview() {
  const box = $("r-note");
  if (!box) return;
  const by = shown && shown.note && !noteDirty ? shown.note.by : firstName(me && me.name);
  box.innerHTML = noteHtml($("rv-note").value, by);
  box.hidden = !$("rv-note").value.trim();
}

// D1: the days of this period that differ from Ads Manager's own totals, with the way to read them again (admins,
// in the review bar only: never in the report body, a client's view or a copy that goes out).
function paintNumbers(stamp) {
  const box = $("rv-numbers");
  if (!box) return;
  box.hidden = !(stamp && stamp.warning);
  box.innerHTML = box.hidden ? "" : `<p class="note warn flush" id="rv-numbers-say">${esc(stamp.warning)}</p>
    <div class="row"><button class="btn" type="button" id="rv-pull">Pull these days again</button></div>`;
}

async function pullPeriod(b) {
  b.disabled = true;
  b.textContent = "Pulling from Meta…";
  try {
    const r = await api("/api/numbers/pull", { method: "POST", body: { period: kind, start: shown.start } });
    toast(r.message, r.ok ? "" : "bad");
    // A long pull goes on by itself after the answer: wait for it (up to 15 minutes), then show the report again.
    for (let i = 0; (r.running_pull || r.running) && i < 300; i += 1) {
      await new Promise((ok) => { setTimeout(ok, 3000); });
      const n = await api("/api/numbers");
      if (!n.running) { toast(`Done reading from Meta. ${n.headline}.`); break; }
    }
    await load();
  } catch (err) {
    toast(err.message, "bad");
    b.disabled = false;
    b.textContent = "Pull these days again";
  }
}

function paintBar(rv) {
  const bar = $("rv-bar");
  bar.hidden = false;
  const state = `<span class="pill ${esc(rv.pill[0])}">${esc(rv.pill[1])}</span> <span class="rv-line">${esc(rv.line)}</span>`
    + (rv.last_error && rv.status === "scheduled" ? `<span class="rv-line muted small">The last try didn't go out: ${esc(rv.last_error)}. It tries again by itself.</span>` : "")
    + (rv.last_error && rv.status === "waiting" ? `<span class="rv-line muted small">It didn't go out: ${esc(rv.last_error)}.</span>` : "");
  // A live region: rewritten only when the words change, so a screen reader doesn't repeat it every poll.
  if ($("rv-state").dataset.shown !== state) { $("rv-state").innerHTML = state; $("rv-state").dataset.shown = state; }
  if (!noteDirty) { $("rv-note").value = rv.note || ""; noteAt = rv.note_at; }
  paintNoteCount();
  for (const [action, id] of Object.entries(ACTION_BUTTONS)) $(id).hidden = !rv.actions.includes(action);
  $("rv-later").textContent = rv.later_label;
  $("rv-acts").hidden = !rv.actions.length;
  if ($("rv-preview").open) refreshPreview();
}

async function refreshPreview() {
  if (!shown) return;
  try {
    const m = await api("/api/reports/email-preview", { method: "POST", body: { kind, start: shown.start, note: $("rv-note").value } });
    $("rv-mailbox").innerHTML = `<p class="small flush"><b>To:</b> ${esc(m.to.join(", ") || "nobody yet")}</p>
      <p class="small flush"><b>Subject:</b> ${esc(m.subject)}</p><pre class="rv-mail">${esc(m.text)}</pre>`;
  } catch (err) { $("rv-mailbox").innerHTML = `<p class="note warn flush">${esc(err.message)}</p>`; }
}

const body = (extra = {}) => ({ kind, start: shown.start, ...extra });

async function act(path, extra, done) {
  try {
    const r = await api(`/api/reports/${path}`, { method: "POST", body: body(extra) });
    if ("note" in extra) savedNote(); // the send saved the note: take its new time, or the next save is refused
    shown.review = r.review;
    paintBar(r.review);
    if (done) done(r);
    return r;
  } catch (err) {
    if (err.body && err.body.code === "client_list") { toast(err.message, "bad"); load(); return null; }
    toast(err.message, "bad");
    return null;
  }
}

function watchSending() {
  clearInterval(poll);
  const until = Date.now() + 60000;
  poll = setInterval(async () => {
    if (Date.now() > until) { clearInterval(poll); return; }
    try {
      const r = await api(`/api/reports?kind=${kind}&start=${shown.start}`);
      if (!r.review) return;
      shown.review = r.review;
      paintBar(r.review);
      if (r.review.status === "sent") { clearInterval(poll); toast("Report sent"); load(); }
    } catch (err) { /* the next tick tries again */ }
  }, 3000);
}

function savedNote() {
  noteDirty = false;
  markSaved($("rv-form"));
}

async function sendNow() {
  const rv = shown.review;
  const ok = await confirmDialog({ title: "Send the report now?", confirm: "Send now",
    body: `<p>It goes to <b>${esc(who(rv.to))}</b> with a link that works for 90 days. The figures are frozen as they are now.</p>` });
  if (!ok) return;
  const r = await act("send", { when: "now", note: $("rv-note").value, expect_to: rv.to });
  if (r) { savedNote(); watchSending(); }
}

async function sendLater() {
  const rv = shown.review;
  const ok = await confirmDialog({ title: `${rv.later_label}?`, confirm: rv.later_label,
    body: `<p>It goes to <b>${esc(who(rv.to))}</b> on ${esc(rv.later_when)}. You can hold it until then.</p>` });
  if (!ok) return;
  const r = await act("send", { when: "8am", note: $("rv-note").value, expect_to: rv.to });
  if (r) { savedNote(); toast(`Set to go out on ${r.review.pill[1].replace(/^Goes out /, "")}`); }
}

async function resend() {
  const rv = shown.review;
  const ok = await confirmDialog({ title: "Send it again?", confirm: "Send again",
    body: `<p><b>${esc(who(rv.to))}</b> get${rv.to.length === 1 ? "s" : ""} a new email marked “updated”, with today's figures. The copy sent before is replaced.</p>` });
  if (!ok) return;
  if (await act("resend", { expect_to: rv.to })) watchSending();
}

async function saveNote(e) {
  e.preventDefault();
  const form = $("rv-form");
  fieldError(form, null);
  try {
    const r = await api("/api/reports/note", { method: "PUT", body: body({ note: $("rv-note").value, note_at: noteAt }) });
    savedNote();
    shown.review = r.review;
    shown.note = r.note;
    paintBar(r.review);
    paintNotePreview();
    toast(r.review.status === "sent" ? "Note saved. The report link shows the new wording; no new email was sent." : "Note saved");
  } catch (err) {
    if (err.body && err.body.field) fieldError(form, err.body.field, err.message);
    else toast(err.message, "bad");
  }
}

// Another week or month: an unsaved note would be lost, so ask first; then the page has nothing unsaved.
async function leaveNote() {
  if (!noteDirty || !$("rv-form")) return true;
  const ok = await confirmDialog({ title: "Leave without saving the note?", confirm: "Leave it",
    body: "<p>The note you typed for this report isn't saved yet. Press Save note first to keep it.</p>" });
  if (ok) savedNote();
  return ok;
}

let previewTimer = null;
function wireBar() {
  guardLeaving();
  $("rv-form").addEventListener("submit", saveNote);
  $("rv-note").addEventListener("input", () => {
    noteDirty = true;
    paintNoteCount();
    paintNotePreview();
    if ($("rv-preview").open) { clearTimeout(previewTimer); previewTimer = setTimeout(refreshPreview, 600); }
  });
  $("rv-preview").addEventListener("toggle", () => { if ($("rv-preview").open) refreshPreview(); });
  $("rv-send").addEventListener("click", sendNow);
  $("rv-later").addEventListener("click", sendLater);
  $("rv-resend").addEventListener("click", resend);
  $("rv-hold").addEventListener("click", () => act("hold", {}, () => toast("Held. It waits for you now.")));
  $("rv-skip").addEventListener("click", () => act("skip", {}, () => toast("This report won't be sent.", "", { undo: () => act("unskip", {}) })));
  $("rv-unskip").addEventListener("click", () => act("unskip", {}, () => toast("It waits for you again.")));
  $("rv-sent").addEventListener("click", () => { location.href = `/report.html?kind=${kind}&start=${shown.start}&sent=1`; });
  $("rv-numbers").addEventListener("click", (e) => { const b = e.target.closest("#rv-pull"); if (b) pullPeriod(b); });
}

let arrived = location.hash === "#review";
async function load() {
  document.querySelectorAll("#kind [data-kind]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.kind === kind)));
  try {
    const r = token ? await api(`/api/reports/shared?t=${encodeURIComponent(token)}`)
      : sentView ? await api(`/api/reports/sent?kind=${kind}${start ? `&start=${start}` : ""}`)
        : await api(`/api/reports?kind=${kind}${start ? `&start=${start}` : ""}`);
    shown = r;
    $("report").innerHTML = r.waiting ? waitingHtml(r) : reportHtml(r);
    if (r.periods) periodPicker(r);
    else if ($("period-box")) $("period-box").hidden = true;
    document.title = `${r.account} · ${r.kind === "week" ? "Week" : "Month"} of ${dayLabel(r.start)} | Report`;
    if (r.review && !sentView) {
      paintBar(r.review);
      paintNumbers(r.stamp);
      if (noteDirty) paintNotePreview();
    } else if ($("rv-bar")) $("rv-bar").hidden = true;
    if (sentView) {
      $("rv-asent").hidden = false;
      $("rv-asent").innerHTML = `As sent${r.as_sent ? ` on ${esc(yearDay(r.as_sent))}` : ""}. <a href="/report.html?kind=${esc(kind)}&start=${esc(r.start)}">Back to today's figures</a>`;
    }
    if (arrived && r.review) {
      arrived = false;
      $("rv-bar").scrollIntoView({ block: "start" });
      $("rv-note").focus({ preventScroll: true });
    }
  } catch (err) { $("report").innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

// A share link opens this one report, without signing in, for 90 days: say so before making one.
async function share() {
  if (!shown) return;
  const span = `${dayLabel(shown.start)} – ${dayLabel(shown.end)}`;
  const ok = await confirmDialog({
    title: "Share this report with a link?",
    body: `<p>Anyone who has the link can open the report for <b>${esc(span)}</b> without signing in, for 90 days. It shows what was spent, the leads, the ad names and what changed; never a lead's name or contact details, and nothing in it can be changed.</p>
      <p>Your note shows on the link once the report has been sent.</p>
      <p class="muted small">To stop every link made so far, use Stop all shared links in <a href="/settings.html#reports-panel">Settings → Clients and reports</a>.</p>`,
    confirm: "Create the link",
  });
  if (!ok) return;
  try {
    const r = await api("/api/reports/share", { method: "POST", body: { kind, start: shown.start } });
    try { await navigator.clipboard.writeText(r.url); toast(`Link copied. It works until ${dayLabel(r.expires)}.`); }
    catch (err) { prompt("Copy this link", r.url); }
  } catch (err) { toast(err.message, "bad"); }
}

$("pdf").addEventListener("click", () => window.print());
if (token) {
  // A shared link: no sign-in, no menu, just the report.
  document.documentElement.classList.add("shared-report");
  document.querySelector(".rail").remove();
  $("kind").remove();
  $("period-box").remove();
  $("rv-bar").remove();
  document.querySelector(".page-head h1").textContent = "Ads report";
  load();
} else {
  me = await boot({ page: "report" });
  if (me) {
    if (me.role === "member") { location.href = "/home.html"; }
    $("share").hidden = me.role !== "admin";
    if (me.role === "admin") wireBar();
    else $("rv-bar").remove();
    $("kind").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-kind]");
      if (!b || !(await leaveNote())) return;
      kind = b.dataset.kind; start = "";
      syncUrl();
      if (sentView) { location.href = `/report.html?kind=${kind}`; return; }
      load();
    });
    $("period").addEventListener("change", async (e) => {
      if (!(await leaveNote())) { e.target.value = shown.start; return; }
      // The newest one is the default report: no start in the address for it.
      start = e.target.selectedIndex === 0 && shown.periods && shown.periods[0].start === e.target.value ? "" : e.target.value;
      syncUrl();
      if (sentView) { location.href = `/report.html?kind=${kind}${start ? `&start=${start}` : ""}`; return; }
      load();
    });
    $("share").addEventListener("click", share);
    load();
  }
}
