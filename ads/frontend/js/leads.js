import { api, startLoad } from "./api.js";
import { boot, confirmDialog, entityLink, esc, fieldError, icon, leadClock, onRefresh, phoneDisplay, rememberList, setNewCount, toast, when, showLoadError } from "./ui.js";
import { closeLayer, openLayer } from "./urlstate.js";
import { FOLLOW, LEAD_CHIPS, LOST_REASONS, STAGE_LABELS, dayWords, plural } from "./format.js";
import { armDial, askMeeting, askNext, boxHtml, chipHtml, logCall, resumePending } from "./followup.js";

const STAGES = Object.entries(STAGE_LABELS).map(([id, label]) => ({ id, label }));
const FILTERS = [{ id: "open", label: "Open" }, ...STAGES, { id: "all", label: "All" }];

const state = { loaded: false, me: null, filter: "open", q: "", tests: false, due: "", why: "", leads: [], counts: {}, whyCounts: null, selected: null, seen: new Set(), lead: null };
const $ = (id) => document.getElementById(id);

// What "filtered" means here: anything other than open leads of every campaign, no search, no test leads.
// Where a lead came from, kept in the URL: the picker offers campaigns and ads; an ad set or a form comes from a link.
const SOURCE_KEYS = ["campaign", "adset", "ad", "form"];
const filtered = () => state.filter !== "open" || Boolean(state.q) || state.tests || Boolean(state.due) || Boolean(state.why) || SOURCE_KEYS.some((k) => new URLSearchParams(location.search).get(k));
const WHY_KEYS = [...Object.keys(LOST_REASONS), "none"];
const DUE_KEYS = FOLLOW.due.map(([k]) => k).filter(Boolean);

function renderFilters() {
  const c = state.counts;
  const open = (c.new || 0) + (c.contacted || 0) + (c.qualified || 0);
  const all = Object.values(c).reduce((a, b) => a + b, 0) + (state.repeats || 0);
  const n = { open, all, ...c };
  $("filters").innerHTML = FILTERS.map((f) =>
    `<button type="button" class="view-chip" data-f="${f.id}" aria-pressed="${state.filter === f.id}">${f.label}<span class="n">${n[f.id] || 0}</span></button>`
  ).join("");
  setNewCount(state.newEverywhere ?? c.new ?? 0);
}

const minutesText = (m) => (m < 60 ? `${m} min` : m < 48 * 60 ? `${Math.round(m / 6) / 10} h`.replace(".0 h", " h") : `${Math.round(m / 1440)} days`);

// How fast leads got a first try, last 30 days, and the calls logged. Half of the tried leads got it within the median.
function renderResponse(r) {
  const el = $("response");
  if (!r || !r.leads) { el.hidden = true; return; }
  const parts = [r.median_minutes === null ? "Nobody has been tried yet" : `first try within ${minutesText(r.median_minutes)} for half of them`,
    `${r.within_5} of ${r.leads} within 5 min`];
  if (r.untouched) parts.push(`${r.untouched} not tried yet`);
  if (r.calls) parts.push(`${plural(r.calls, "call")}, ${r.talked} talked to (${r.rate}%)`);
  el.textContent = `Last 30 days: ${parts.join(" · ")}`;
  el.hidden = false;
}

// Why Lost leads were lost (L2): shown only on the Lost view, kept in the address (?why=), with a nudge for
// leads that have no reason yet.
function renderWhy() {
  const sel = $("why"), note = $("why-note");
  const on = state.filter === "lost" && state.whyCounts;
  sel.hidden = !on;
  note.hidden = true;
  if (!on) return;
  const n = state.whyCounts;
  const all = Object.values(n).reduce((a, b) => a + b, 0);
  const label = (k) => (k === "none" ? "No reason given" : LOST_REASONS[k]);
  sel.innerHTML = `<option value="">All reasons (${all})</option>` + WHY_KEYS.filter((k) => n[k] || state.why === k)
    .map((k) => `<option value="${k}" ${state.why === k ? "selected" : ""}>${esc(label(k))} (${n[k] || 0})</option>`).join("");
  if (n.none && state.why !== "none") {
    note.hidden = false;
    note.textContent = `${plural(n.none, "lost lead")} ${n.none === 1 ? "has" : "have"} no reason yet. Open one and tap Change to add it.`;
  }
}

// The follow-up filter: its counts beside each choice, kept in the address (?due=).
function renderFollow(counts) {
  const n = { today: counts.due_today, overdue: counts.overdue, none: counts.no_next, booked: counts.booked };
  $("follow").innerHTML = FOLLOW.due.map(([k, l]) => `<option value="${k}" ${state.due === k ? "selected" : ""}>${esc(l)}${k && n[k] ? ` (${n[k]})` : ""}</option>`).join("");
}

const DUE_EMPTY = {
  today: ["Nothing due today", "Next steps you set show up here on their day."],
  overdue: ["Nothing overdue", "Every follow-up is on time."],
  none: ["Every open lead has a next step", "Leads someone has tried show up here when nothing is planned for them."],
  booked: ["No calls booked yet", "Tap Booked a call after a call and it shows up here."],
};

// Lead quality chips (L2): a repeat, the first lead of someone who asked again, someone who asked before, junk.
const chip = ([cls, words], n) => `<span class="pill ${cls}">${esc(typeof words === "function" ? words(n) : words)}</span> `;
function qualityChips(lead) {
  if (lead.repeat_of) return chip(LEAD_CHIPS.repeat);
  return (lead.repeats ? chip(LEAD_CHIPS.asked, Number(lead.repeats) + 1) : "") + (lead.earlier_lead_id ? chip(LEAD_CHIPS.before) : "")
    + (!lead.is_test && lead.junk ? chip(LEAD_CHIPS.junk) : "");  // the server's one junk rule
}

function rowHtml(lead) {
  const isNew = lead.status === "new";
  // One urgency rule with Today and the reminders (the server's today.urgency); a repeat never waits.
  const clock = leadClock(lead);
  return `<li><button type="button" class="lead-row${state.seen.has(lead.id) ? "" : " arrived"}${lead.repeat_of ? " is-repeat" : ""}" data-id="${lead.id}" ${state.selected === lead.id ? 'aria-current="true"' : ""}>
    ${clock}
    <span class="who">
      <b>${esc(lead.full_name || "No name given")}</b>
      <span>${esc(lead.business_type || "Business not given")}</span>
      <small>${lead.is_test ? chip(LEAD_CHIPS.test) : ""}${isNew || lead.repeat_of ? "" : `<span class="pill ${lead.status}">${esc(STAGE_LABELS[lead.status])}</span> `}${qualityChips(lead)}${esc(lead.ad_name || (lead.is_organic ? "No ad (organic)" : ""))}${lead.owner_name ? `, ${esc(lead.owner_name)}` : ""}</small>
      ${lead.repeat_of ? "" : chipHtml(lead.chip)}
    </span>
  </button></li>`;
}

function renderList() {
  const list = $("list");
  $("clear-filters").hidden = !filtered();
  if (!state.leads.length && state.filter === "lost" && state.why) {
    list.innerHTML = `<li class="empty"><h3>Nothing lost for this reason</h3><p>Try another reason or All reasons.</p><button type="button" class="btn" data-clear-why>All reasons</button></li>`;
  } else if (!state.leads.length && DUE_EMPTY[state.due]) {
    const [h, p] = DUE_EMPTY[state.due];
    list.innerHTML = `<li class="empty"><h3>${h}</h3><p>${p}</p><button type="button" class="btn" data-clear-filters>Clear filters</button></li>`;
  } else if (!state.leads.length) {
    list.innerHTML = `<li class="empty">${filtered()
      ? '<h3>Nothing matches</h3><p>Try another stage or search, or start again from every open lead.</p><button type="button" class="btn" data-clear-filters>Clear filters</button>'
      : `<h3>No leads yet</h3><p>When someone fills in one of the ad's lead forms, they show up here within a minute${state.me.role === "admin" ? " and you get an email" : ""}.</p>${state.me.role === "admin" ? '<a class="btn" href="/settings.html">Check the Meta connection</a>' : ""}`}</li>`;
  } else {
    list.innerHTML = state.leads.map(rowHtml).join("");
  }
  state.leads.forEach((l) => state.seen.add(l.id));
}

// Filter by where the lead came from: a campaign, or one ad inside it (kept in the URL: ?campaign= / ?ad=).
// A link from an ad set or a lead form (?adset= / ?form=) shows as its own choice, named.
const NARROW_WORD = { adset: "Ad set", form: "Lead form" };
function renderSources(sources, src, narrowed) {
  const sel = document.getElementById("source");
  const named = narrowed ? `n:${narrowed.kind}` : "";
  const current = named || (src.get("ad") ? `a:${src.get("ad")}` : src.get("campaign") ? `c:${src.get("campaign")}` : "");
  const camps = [...new Map(sources.map((s) => [s.campaign_id, s.campaign_name])).entries()];
  sel.innerHTML = `<option value="">All campaigns and ads</option>${camps.map(([cid, cname]) => `<optgroup label="${esc(cname || "Campaign")}">
      <option value="c:${esc(cid)}">All of “${esc(cname || "this campaign")}”</option>
      ${sources.filter((s) => s.campaign_id === cid && s.ad_id).map((s) => `<option value="a:${esc(s.ad_id)}">${esc(s.ad_name || s.ad_id)} (${s.n})</option>`).join("")}</optgroup>`).join("")}`;
  if (named) sel.insertAdjacentHTML("afterbegin", `<option value="${esc(named)}">${esc(NARROW_WORD[narrowed.kind])}: ${esc(narrowed.name || "this one")}</option>`);
  sel.value = current;
  sel.hidden = !sources.length && !named;
}

async function load({ quiet = false } = {}) {
  const params = new URLSearchParams();
  if (state.filter !== "all") params.set("status", state.filter);
  if (state.q) params.set("q", state.q);
  if (state.tests) params.set("tests", "1");
  if (state.due) params.set("due", state.due);
  if (state.filter === "lost" && state.why) params.set("why", state.why);
  const src = new URLSearchParams(location.search);
  for (const k of SOURCE_KEYS) if (src.get(k)) params.set(k, src.get(k));
  const superseded = startLoad("leads");
  try {
    const data = await api("/api/leads?" + params);
    if (superseded()) return;
    renderSources(data.sources || [], src, data.narrowed);
    state.leads = data.leads;
    state.counts = data.counts;
    state.whyCounts = data.why_counts;
    state.repeats = data.repeats;
    state.newEverywhere = data.new_everywhere;
    renderResponse(data.response);
    renderFollow(data.follow || {});
    if (!state.loaded) { data.leads.forEach((l) => state.seen.add(l.id)); state.loaded = true; }
    renderFilters();
    renderWhy();
    renderList();
    if (!state.selected && state.leads.length && window.matchMedia("(min-width: 961px)").matches) {
      select(state.leads[0].id, { push: false });
    }
  } catch (err) {
    if (!quiet && !superseded()) showLoadError($("list"), err, load);
  }
}

// Who may do what on a lead: the team links leads; a client works stages only when Settings lets them.
const isStaff = () => state.me.role !== "client";
const canWrite = () => isStaff() || Boolean(state.me.account && state.me.account.clients_update_leads);
const reasonLabel = (k) => LOST_REASONS[k] || "No reason given";

// Above the stage: someone asking again (the stage lives on their first lead), someone back after a closed lead,
// or a lead that looks like junk (L2).
function qualityNotes(lead) {
  const out = [];
  const fam = lead.family || {};
  if (lead.repeat_of) {
    const root = fam.root;
    const from = lead.ad_name ? ` from ${esc(lead.ad_name)}` : "";
    out.push(`<div class="note repeat-note" id="repeat-note"><p class="flush">${esc(lead.full_name || "Someone")} asked again on ${esc(dayWords(lead.created_time))}${from}.
      ${fam.can_see_root ? "Work it on the first lead; this one doesn't count twice." : "They asked before in another campaign; this one doesn't count twice."}</p>
      <div class="row">${fam.can_see_root && root ? `<a class="btn btn-small" id="repeat-open" href="#lead=${root.id}">Open the first lead</a>` : ""}
      ${isStaff() ? '<button type="button" class="btn btn-small btn-quiet" id="repeat-unlink">Not the same person</button>' : ""}</div></div>`);
  } else if (lead.earlier) {
    const e = lead.earlier;
    out.push(`<p class="note repeat-before" id="repeat-before">${e.visible
      ? `${esc(e.line)} <a href="#lead=${e.id}">Open that lead</a>${e.ad_name ? ` <span class="muted">(${esc(e.ad_name)})</span>` : ""}`
      : "They asked before in another campaign."}${isStaff() ? ' <button type="button" class="link-btn" id="before-unlink">Not the same person</button>' : ""}</p>`);
  }
  if (lead.junk && lead.junk_text && !lead.is_test && !lead.repeat_of && lead.status !== "lost") {
    out.push(`<div class="note warn junk-note" id="junk-note"><p class="flush">This looks like junk. ${esc(lead.junk_text)}</p>
      ${canWrite() ? `<div class="row"><button type="button" class="btn btn-small" id="junk-lost">Mark as lost: spam or fake</button>
        <button type="button" class="btn btn-small btn-quiet" id="junk-real">It's real</button></div>` : ""}</div>`);
  }
  return out.join("");
}

// Everything else from this person ("Also asked"): each fill folded, with their answers inside.
function familyHtml(lead) {
  const reps = (lead.family && lead.family.repeats) || [];
  const hidden = (lead.family && lead.family.hidden) || 0;
  if (!reps.length && !hidden) return "";
  const CONTACT = new Set(["full_name", "first_name", "last_name", "email", "work_email", "phone_number", "phone"]);
  const items = reps.map((r) => {
    const answers = (r.answers || []).filter((a) => !CONTACT.has(String(a.name).toLowerCase()))
      .map((a) => `<dt>${esc(prettyQuestion(a.name))}</dt><dd>${esc((a.values || []).join(", ") || "—")}</dd>`).join("");
    return `<li><details class="family-item"><summary>${esc(when(r.created_time))}${r.ad_name ? ` · ${esc(r.ad_name)}` : ""}</summary>
      ${answers ? `<dl class="facts">${answers}</dl>` : '<p class="muted small flush">No other answers.</p>'}
      <a class="small" href="#lead=${r.id}">Open this request</a></details></li>`;
  }).join("");
  return `<h3 class="section-title">Also asked</h3><ul class="family-list" id="family-list">${items}</ul>
    ${hidden ? `<p class="muted small flush">${plural(hidden, "more request")} in a campaign you don't see.</p>` : ""}`;
}

function detailHtml(lead) {
  const clock = leadClock(lead, { long: true });
  const CONTACT = new Set(["full_name", "first_name", "last_name", "email", "work_email", "phone_number", "phone"]);
  const answers = (lead.answers || []).filter((a) => !CONTACT.has(String(a.name).toLowerCase())).map((a) =>
    `<dt>${esc(prettyQuestion(a.name))}</dt><dd>${esc((a.values || []).join(", ") || "—")}</dd>`).join("");
  const owners = [`<option value="">Nobody yet</option>`, ...lead.assignable.map((u) =>
    `<option value="${u.id}" ${u.id === lead.owner_id ? "selected" : ""}>${esc(u.name)}</option>`)].join("");
  // Newest first, each line a sentence (the server's lead_history.describe).
  const history = lead.history.map((h) => `<li><time>${esc(when(h.at))}</time><span>${esc(h.text)}</span></li>`).join("");
  return `
    <button type="button" class="btn btn-quiet back-link" id="back">${icon("back")} All leads</button>
    <div class="detail-top">
      <div>
        <h2>${esc(lead.full_name || "No name given")}</h2>
        <p class="sub">${esc(lead.business_type || "Business not given")}</p>
      </div>
      ${clock}
    </div>
    ${lead.is_test ? '<p class="note warn">This is a test lead from Meta\'s testing tool.</p>' : ""}
    ${qualityNotes(lead)}
    <div class="reach">
      ${lead.phone ? `<a class="btn btn-call" id="call-link" href="tel:${esc(lead.phone)}">${icon("phone")} Call ${esc(phoneDisplay(lead.phone))}</a>` : ""}
      ${lead.repeat_of ? "" : '<button type="button" class="btn" id="log-call">Log a call</button>'}
      ${lead.email ? `<button type="button" class="btn" id="reply-open" aria-expanded="false" aria-controls="reply-form">${icon("mail")} Email them</button>` : ""}
    </div>
    ${lead.no_auto_reply ? '<p class="muted small flush" id="no-auto-reply">No automatic reply went out because it looked like a repeat.</p>' : ""}
    ${lead.email ? replyForm(lead) : ""}
    ${lead.repeat_of ? "" : boxHtml(lead)}
    ${lead.repeat_of ? "" : `<div class="stage">
      <span class="stage-label" id="stage-label">Stage</span>
      <div class="segmented" role="group" aria-labelledby="stage-label" id="stages">
        ${STAGES.map((s) => `<button type="button" data-stage="${s.id}" aria-pressed="${lead.status === s.id}">${s.label}</button>`).join("")}
      </div>
    </div>`}
    ${metaStages(lead)}
    <dl class="facts">
      <dt>Owner</dt><dd>${state.me.role === "client" ? esc(lead.owner_name || "Nobody yet") : `<label class="sr-only" for="owner">Owner</label><select class="input" id="owner">${owners}</select>`}</dd>
      <dt>Asked</dt><dd>${when(lead.created_time)}</dd>
      ${lead.status === "lost" ? `<dt>Lost because</dt><dd id="lost-why">${esc(reasonLabel(lead.lost_reason))}${lead.lost_note ? ` — “${esc(lead.lost_note)}”` : ""}${canWrite() ? ' <button type="button" class="link-btn" id="lost-change">Change</button>' : ""}</dd>` : ""}
      ${!lead.repeat_of && lead.max_stage && lead.max_stage !== "new" && lead.max_stage !== lead.status ? `<dt>Got as far as</dt><dd id="max-stage">${esc(STAGE_LABELS[lead.max_stage])}${lead.can_correct ? ' <button type="button" class="link-btn" id="max-correct">Correct</button>' : ""}</dd>` : ""}
      <dt>Phone</dt><dd>${esc(phoneDisplay(lead.phone) || "—")}</dd>
      <dt>Email</dt><dd>${esc(lead.email || "—")}</dd>
      <dt>Ad</dt><dd>${lead.ad_name ? entityLink("ad", lead.ad_id, lead.ad_name) : esc(lead.is_organic ? "None: filled in without an ad (organic)" : "—")}</dd>
      ${lead.adset_name ? `<dt>Ad set</dt><dd>${entityLink("adset", lead.adset_id, lead.adset_name)}</dd>` : ""}
      <dt>Campaign</dt><dd>${lead.campaign_name ? entityLink("campaign", lead.campaign_id, lead.campaign_name) : "—"}</dd>
      ${lead.form_name ? `<dt>Form</dt><dd>${entityLink("form", lead.form_id, lead.form_name)}</dd>` : ""}
    </dl>
    ${isStaff() && !lead.is_test && !lead.repeat_of ? '<div class="row family-actions"><button type="button" class="btn btn-quiet btn-small" id="same-person">Same person as…</button></div>' : ""}
    ${answers ? `<h3 class="section-title">Their answers</h3><dl class="facts">${answers}</dl>` : ""}
    ${familyHtml(lead)}
    ${emailsHtml(lead)}
    <h3 class="section-title">Notes</h3>
    <ul class="notes">${lead.notes.map((n) => `<li><div class="meta">${esc(n.author || "Someone")}, ${when(n.created_at)}</div>${esc(n.body)}</li>`).join("") || `<li class="muted">${state.me.role === "client" && !state.me.account.clients_update_leads ? "No notes yet." : "No notes yet. Write down what you learned on the call."}</li>`}</ul>
    <form id="note-form" class="stack tight">
      <label class="sr-only" for="note">Add a note</label>
      <textarea class="input" id="note" name="body" placeholder="What did you learn on the call?"></textarea>
      ${lead.urgency !== "done" ? '<p class="hint" id="note-hint">Called them? Use Log a call so the reminders stop.</p>' : ""}
      <div><button class="btn btn-primary" type="submit">Add note</button></div>
    </form>
    ${history ? `<h3 class="section-title">History</h3><ol class="history">${history}</ol>${lead.history_gap ? `<p class="muted small flush" id="history-gap">${esc(lead.history_gap)}</p>` : ""}` : ""}`;
}

function replyForm(lead) {
  return `<form class="reply-box stack tight" id="reply-form" hidden novalidate>
      <div class="reply-head"><b>Email to ${esc(lead.email)}</b></div>
      <p class="note warn" id="reply-mail-note" hidden></p>
      <div class="field"><label for="reply-template">Start from</label><select class="input" id="reply-template"></select></div>
      <div class="field"><label for="reply-subject">Subject</label><input class="input" id="reply-subject" name="subject" autocomplete="off"></div>
      <div class="field"><label for="reply-body">Message</label><textarea class="input" id="reply-body" name="body" rows="11"></textarea><span class="hint">Sent from the console's mailbox with your name; their answer comes back to ${esc(state.me.email)}.</span></div>
      ${lead.status === "new" ? '<label class="check"><input type="checkbox" id="reply-contacted" checked> Move to Contacted when it\'s sent</label>' : ""}
      <div class="row"><button class="btn btn-primary" type="submit" id="reply-send">Send email</button><button class="btn btn-quiet" type="button" id="reply-close">Cancel</button>
        <a class="small muted" href="mailto:${esc(lead.email)}">Use my own mail app instead</a></div>
    </form>`;
}

function emailsHtml(lead) {
  const rows = lead.replies || [];
  if (!rows.length) return "";
  const badge = (r) => r.status === "sent" ? "" : r.status === "pending" ? ' <span class="pill">Sending…</span>' : ` <span class="pill bad">Not sent</span>`;
  return `<h3 class="section-title">Emails</h3><ul class="notes">${rows.map((r) => `<li>
      <div class="meta">${r.auto ? "Automatic reply" : esc(r.sender || "Someone")}, ${when(r.sent_at || r.created_at)}${badge(r)}</div>
      <details class="email-sent"><summary>${esc(r.subject)}</summary><div class="email-body">${esc(r.body)}</div></details>
      ${r.status === "failed" && r.error ? `<p class="small muted">${esc(r.error)}</p>` : ""}</li>`).join("")}</ul>`;
}

async function loadDraft(lead, templateId) {
  const d = await api(`/api/leads/${lead.id}/reply${templateId ? `?template=${templateId}` : ""}`);
  $("reply-template").innerHTML = d.templates.map((t) => `<option value="${t.id}" ${t.id === d.template_id ? "selected" : ""}>${esc(t.name)}</option>`).join("");
  $("reply-subject").value = d.subject;
  $("reply-body").value = d.body;
  const note = $("reply-mail-note");
  note.hidden = d.mail_ready;
  note.innerHTML = d.mail_ready ? "" : `Email isn't set up yet, so this can't be sent.${state.me.owner ? ' <a href="/settings.html#email">Set it up in Settings → Email</a>.' : state.me.role === "admin" ? " Ask Edge Bourne to set it up." : " Ask an admin to set it up."}`;
  $("reply-send").disabled = !d.mail_ready;
}

function wireReply(lead) {
  const open = $("reply-open");
  const form = $("reply-form");
  if (!open || !form) return;
  const show = async (on) => {
    form.hidden = !on;
    open.setAttribute("aria-expanded", String(on));
    if (on) {
      try { await loadDraft(lead); $("reply-body").focus(); } catch (err) { toast(err.message, "bad"); }
    }
  };
  open.addEventListener("click", () => show(form.hidden));
  $("reply-close").addEventListener("click", () => { show(false); open.focus(); });
  $("reply-template").addEventListener("change", (e) => loadDraft(lead, e.target.value).catch((err) => toast(err.message, "bad")));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    fieldError(form);
    const btn = $("reply-send");
    btn.disabled = true;
    try {
      const updated = await api(`/api/leads/${lead.id}/reply`, { method: "POST", body: {
        subject: $("reply-subject").value, body: $("reply-body").value,
        template_id: Number($("reply-template").value) || null, mark_contacted: Boolean($("reply-contacted")?.checked) } });
      renderDetail(updated);
      toast(`Email sent to ${lead.email}`);
      load({ quiet: true });
    } catch (err) {
      if (err.body?.field) fieldError(form, err.body.field, err.message); else toast(err.message, "bad");
      btn.disabled = false;
    }
  });
}

function metaStages(lead) {
  const rows = lead.meta_stages;
  if (!rows || !rows.length) return "";
  const label = (id) => (STAGES.find((s) => s.id === id) || { label: id }).label;
  const sent = rows.filter((r) => r.status === "sent");
  const parts = [];
  if (sent.length) parts.push(`Meta has ${sent.map((r) => label(r.stage)).join(", ")} (${when(sent[sent.length - 1].sent_at)})`);
  for (const r of rows.filter((x) => x.status !== "sent")) {
    parts.push(r.status === "pending" ? `${label(r.stage)} ${r.attempts ? "will be sent again" : "is on its way"}`
      : `${label(r.stage)} ${r.status === "failed" ? "didn't reach Meta" : "wasn't sent"}: ${esc(r.last_error || "")}`);
  }
  return `<p class="meta-stages muted" id="meta-stages">${parts.join(". ")}.</p>`;
}

function prettyQuestion(key) {
  const k = String(key || "").replace(/_/g, " ").replace(/\?$/, "").trim();
  const map = { "full name": "Name", "phone number": "Phone", email: "Email" };
  return map[k] || k.charAt(0).toUpperCase() + k.slice(1) + (String(key).endsWith("?") ? "?" : "");
}

// On a phone the lead covers the list, so opening one is a step Back undoes; side by side it's just the selection.
const covers = () => matchMedia("(max-width: 960px)").matches;
const listUrl = () => location.pathname + location.search;

async function select(id, { push = true } = {}) {
  state.selected = id;
  document.querySelectorAll(".lead-row").forEach((r) => r.setAttribute("aria-current", String(Number(r.dataset.id) === id)));
  if (push) { if (covers()) openLayer(`${listUrl()}#lead=${id}`); else history.replaceState(null, "", `${listUrl()}#lead=${id}`); }
  $("layout").classList.add("showing-detail");
  try {
    const lead = await api(`/api/leads/${id}`);
    if (state.selected !== id) return; // another lead was picked while this one loaded
    renderDetail(lead);
  } catch (err) {
    if (state.selected !== id) return;
    $("detail").innerHTML = `<div class="empty"><h3>Can't open this lead</h3><p>${esc(err.message)}</p></div>`;
  }
}

// keep = true when only the stage or owner moved: what's being typed stays.
function renderDetail(lead, { keep = false } = {}) {
  const detail = $("detail");
  const typed = keep ? { note: $("note")?.value, reply: $("reply-form") && !$("reply-form").hidden
    ? { subject: $("reply-subject").value, body: $("reply-body").value, template: $("reply-template").value } : null } : {};
  state.lead = lead;
  detail.innerHTML = detailHtml(lead);
  wireFollow(lead);
  $("back")?.addEventListener("click", () => {
    $("layout").classList.remove("showing-detail");
    closeLayer(listUrl());
  });
  wireReply(lead);
  detail.querySelectorAll("[data-stage]").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.stage === "lost" && lead.status !== "lost") return markLost(lead);
    return patch(lead.id, { status: b.dataset.stage });
  }));
  wireQuality(lead);
  $("owner")?.addEventListener("change", (e) => patch(lead.id, { owner_id: e.target.value ? Number(e.target.value) : null }));
  $("note-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = e.target.body.value.trim();
    const btn = e.target.querySelector("button[type=submit]");
    if (!body || btn.disabled) return;
    btn.disabled = true;
    try {
      renderDetail(await api(`/api/leads/${lead.id}/notes`, { method: "POST", body: { body } }));
      toast("Note added");
    } catch (err) { toast(err.message, "bad"); } finally { btn.disabled = false; }
  });
  if (typed.note) $("note").value = typed.note;
  if (typed.reply && $("reply-form")) {
    $("reply-form").hidden = false;
    $("reply-open").setAttribute("aria-expanded", "true");
    loadDraft(lead, typed.reply.template).then(() => { $("reply-subject").value = typed.reply.subject; $("reply-body").value = typed.reply.body; }).catch(() => {});
  }
}

// A change from the Follow-up box or the call dialog: the lead page and the list redraw, what's typed stays.
function changed(lead) {
  if (lead && state.selected === lead.id) renderDetail(lead, { keep: true });
  load({ quiet: true });
}

const ask = async (fn, ...args) => { const lead = await fn(...args); if (lead) changed(lead); return lead; };

function wireFollow(lead) {
  armDial($("call-link"), lead, changed);
  $("log-call")?.addEventListener("click", () => ask(logCall, lead, { after: changed }));
  $("fu-box")?.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-fu]");
    if (!b || b.disabled) return;
    const what = b.dataset.fu;
    const first = String(lead.full_name || "").trim().split(/\s+/)[0] || "them";
    if (what === "add" || what === "change") return ask(askNext, lead, { title: what === "add" ? `What's next for ${first}?` : "Change the next step" });
    if (what === "moved" || what === "set-time" || what === "rebook") return ask(askMeeting, lead);
    if (what === "email") { $("reply-open")?.click(); return; }
    b.disabled = true;
    try {
      if (what === "done") {
        const updated = await api(`/api/leads/${lead.id}`, { method: "PATCH", body: { next_step_done: true } });
        toast(`Done: ${lead.follow.next.words}`);
        changed(updated);
      } else if (what === "held" || what === "no_show" || what === "canceled") {
        const updated = await api(`/api/leads/${lead.id}`, { method: "PATCH", body: { meeting: { status: what } } });
        changed(updated);
        toast({ held: "Marked: the call happened", no_show: "Marked: no-show", canceled: "Call canceled" }[what]);
        if (what !== "canceled") {
          const opts = what === "no_show" ? { title: `What's next for ${first}?`, kind: "call_back", preset: "later_today" } : { title: `What's next for ${first}?` };
          await ask(askNext, updated, opts);
        }
      } else if (what === "lost") {
        await patch(lead.id, { status: "lost", lost_reason: "no_response", lost_note: lead.follow.lost_notes[lead.follow.suggestion] });
      } else if (what === "lost-wrong") {
        // Wrong number: why it was lost is asked; Spam or fake is picked already only when the lead looks fake (00-PLAN C13).
        await markLost(lead, { preset: (lead.junk_flags || []).length ? "spam" : null });
        b.disabled = false;
      }
    } catch (err) { toast(err.message, "bad"); b.disabled = false; }
  });
}

// Stage events go to Meta from the background worker within seconds; refresh just that line.
let stagesTimer;
function followMetaStages(id, tries = 0) {
  clearTimeout(stagesTimer);
  if (tries >= 4) return;
  stagesTimer = setTimeout(async () => {
    if (state.selected !== id) return;
    try {
      const lead = await api(`/api/leads/${id}`);
      const line = $("meta-stages");
      if (state.selected !== id || !line) return;
      line.outerHTML = metaStages(lead) || "";
      if ((lead.meta_stages || []).some((r) => r.status === "pending")) followMetaStages(id, tries + 1);
    } catch (e) { /* the line stays as it was */ }
  }, 3000 * (tries + 1));
}

const stageLabel = (id) => (STAGES.find((s) => s.id === id) || { label: id }).label;

async function patch(id, body) {
  try {
    const lead = await api(`/api/leads/${id}`, { method: "PATCH", body });
    if (state.selected === id) renderDetail(lead, { keep: true });
    if ((lead.meta_stages || []).some((r) => r.status === "pending")) followMetaStages(id);
    // A stage move can be put back for a few minutes: the toast's Undo (same person, while it's still the last move).
    if (body.status) toast(`Moved to ${stageLabel(body.status)}`, "", lead.undo ? { undo: () => undoMove(id, lead.undo.event_id) } : {});
    load({ quiet: true });
    // Moved on to Contacted or Qualified by hand: what's next for them (No next step is always fine).
    if (lead.undo && ["contacted", "qualified"].includes(body.status) && state.selected === id) {
      const first = String(lead.full_name || "").trim().split(/\s+/)[0] || "them";
      await ask(askNext, lead, { title: `What's next for ${first}?` });
    }
  } catch (err) { toast(err.message, "bad"); }
}

async function undoMove(id, eventId) {
  try {
    const lead = await api(`/api/leads/${id}/events/${eventId}/undo`, { method: "POST" });
    if (state.selected === id) renderDetail(lead, { keep: true });
    const sent = (lead.undone?.meta_has || []).map(stageLabel);
    toast(`Back to ${stageLabel(lead.status)}${sent.length ? `. Meta already has ${sent.join(", ")} and keeps it.` : ""}`);
    changed(null);
  } catch (err) { toast(err.message, "bad"); }
}

// ---------- Lead quality (L2): why it was lost, how far it got, the same person, junk

async function lostDialog(lead, { title = "Why was this lead lost?", confirm = "Mark as lost", preset = null, note = "" } = {}) {
  const options = lead.reasons || Object.entries(LOST_REASONS).map(([value, label]) => ({ value, label }));
  const r = await confirmDialog({ title, confirm, extra: "lost-dialog",
    choices: { options, value: preset, required: "Pick a reason" },
    field: { label: "Anything to add? (optional)", rows: 2, value: note || "" } });
  return r === false ? null : { reason: r.choice, note: r.value.trim() || null };
}

async function markLost(lead, opts = {}) {
  const r = await lostDialog(lead, opts);
  if (r) await patch(lead.id, { status: "lost", lost_reason: r.reason, lost_note: r.note });
}

async function changeReason(lead) {
  const r = await lostDialog(lead, { title: "Change why it was lost", confirm: "Save", preset: lead.lost_reason, note: lead.lost_note });
  if (!r) return;
  try {
    const updated = await api(`/api/leads/${lead.id}`, { method: "PATCH", body: { lost_reason: r.reason, lost_note: r.note } });
    toast(`Lost because: ${reasonLabel(updated.lost_reason)}`);
    changed(updated);
  } catch (err) { toast(err.message, "bad"); }
}

async function correctMax(lead) {
  const stage = await confirmDialog({ title: "Correct how far this lead got", confirm: "Save", extra: "lost-dialog",
    body: '<p class="muted flush">Use this only to fix a wrong click. Meta keeps any stage it was already sent.</p>',
    choices: { options: ["new", "contacted", "qualified", "won"].map((v) => ({ value: v, label: STAGE_LABELS[v] })), value: lead.max_stage, required: "Pick a stage" } });
  if (!stage) return;
  try {
    const updated = await api(`/api/leads/${lead.id}`, { method: "PATCH", body: { max_stage: stage } });
    toast(`Got as far as: ${STAGE_LABELS[updated.max_stage]}`);
    changed(updated);
  } catch (err) { toast(err.message, "bad"); }
}

// "Same person as…": search this account's leads, pick one, link. The older one stays the first lead.
async function samePerson(lead) {
  let picked = null;
  const done = confirmDialog({ title: "Which lead is the same person?", confirm: "Link them", extra: "family-dialog",
    body: '<p class="muted flush">The older one stays the first lead; the newer one counts once, with it.</p>',
    field: { label: "Name, phone or email", inputmode: "search", validate: () => (picked ? null : "Pick the lead to link") } });
  const dlg = document.querySelector("dialog.family-dialog");
  const input = dlg.querySelector("#cd-input");
  const list = document.createElement("ul");
  list.className = "family-pick";
  list.id = "family-pick";
  list.setAttribute("aria-label", "Matching leads");
  dlg.querySelector(".field").after(list);
  let timer;
  const search = async () => {
    const q = input.value.trim();
    if (!q) { list.innerHTML = ""; return; }
    try {
      const d = await api(`/api/leads?q=${encodeURIComponent(q)}`);
      if (input.value.trim() !== q) return;
      const rows = d.leads.filter((l) => l.id !== lead.id && l.repeat_of !== lead.id).slice(0, 8);
      list.innerHTML = rows.length ? rows.map((l) => `<li><button type="button" class="family-row" data-id="${l.id}" aria-pressed="false">
          <b>${esc(l.full_name || "No name given")}</b><span>${esc(l.business_type || "Business not given")} · ${esc(dayWords(l.created_time))} · ${esc(STAGE_LABELS[l.status])}${l.repeat_of ? " · repeat" : ""}</span></button></li>`).join("")
        : '<li class="muted small">No lead matches that.</li>';
    } catch (err) { list.innerHTML = `<li class="muted small">${esc(err.message)}</li>`; }
  };
  input.addEventListener("input", () => { picked = null; clearTimeout(timer); timer = setTimeout(search, 250); });
  list.addEventListener("click", (e) => {
    const b = e.target.closest(".family-row");
    if (!b) return;
    picked = Number(b.dataset.id);
    list.querySelectorAll(".family-row").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    dlg.querySelector("#cd-err").hidden = true;
  });
  if ((await done) === false || !picked) return;
  try {
    const updated = await api(`/api/leads/${lead.id}/same-person`, { method: "POST", body: { other_id: picked } });
    toast(`Linked to ${updated.linked.root_name ? `${updated.linked.root_name}'s` : "their"} first lead`);
    changed(updated);
  } catch (err) { toast(err.message, "bad"); }
}

function wireQuality(lead) {
  const on = (id, fn) => $(id)?.addEventListener("click", fn);
  const unlink = async () => {
    try {
      const updated = await api(`/api/leads/${lead.id}/same-person`, { method: "DELETE" });
      toast("Unlinked: counted as a separate lead");
      changed(updated);
    } catch (err) { toast(err.message, "bad"); }
  };
  on("repeat-unlink", unlink);
  on("before-unlink", unlink);
  on("junk-lost", () => patch(lead.id, { status: "lost", lost_reason: "spam" }));
  on("junk-real", async () => {
    try {
      const updated = await api(`/api/leads/${lead.id}/not-junk`, { method: "POST" });
      toast("Marked as real");
      changed(updated);
    } catch (err) { toast(err.message, "bad"); }
  });
  on("lost-change", () => changeReason(lead));
  on("max-correct", () => correctMax(lead));
  on("same-person", () => samePerson(lead));
}

function clearFilters() {
  state.filter = "open"; state.q = ""; state.tests = false; state.due = ""; state.why = ""; state.selected = null;
  $("q").value = ""; $("tests").checked = false;
  const u = new URL(location.href);
  [...SOURCE_KEYS, "status", "due", "why"].forEach((k) => u.searchParams.delete(k));
  history.replaceState(null, "", u.pathname + u.search);
  rememberList(u.pathname + u.search);
  load();
}

function showEmptyDetail() {
  $("detail").innerHTML = `<div class="empty"><h3>Pick a lead</h3><p>Their answers, the ad that brought them and your notes show up here.</p></div>`;
}

async function main() {
  state.me = await boot({ page: "leads" });
  if (!state.me) return;
  $("search-icon").outerHTML = icon("search");
  const askedStage = new URLSearchParams(location.search).get("status");
  if (FILTERS.some((f) => f.id === askedStage)) state.filter = askedStage;
  const askedWhy = new URLSearchParams(location.search).get("why");
  if (state.filter === "lost" && WHY_KEYS.includes(askedWhy)) state.why = askedWhy;
  const setWhy = (why) => {
    state.why = why;
    const u = new URL(location.href);
    if (why) u.searchParams.set("why", why); else u.searchParams.delete("why");
    history.replaceState(null, "", u.pathname + u.search + u.hash);
    rememberList(u.pathname + u.search);
    state.selected = null;
    load();
  };
  $("why").addEventListener("change", (e) => setWhy(e.target.value));
  $("list").addEventListener("click", (e) => { if (e.target.closest("[data-clear-why]")) setWhy(""); });
  const askedDue = new URLSearchParams(location.search).get("due");
  if (DUE_KEYS.includes(askedDue)) {
    state.due = askedDue;
    // Calls booked can be on leads already won or lost: the list opens on every stage for it.
    if (askedDue === "booked" && !askedStage) state.filter = "all";
  }
  $("follow").addEventListener("change", (e) => {
    state.due = e.target.value;
    const u = new URL(location.href);
    if (state.due) u.searchParams.set("due", state.due); else u.searchParams.delete("due");
    history.replaceState(null, "", u.pathname + u.search + u.hash);
    rememberList(u.pathname + u.search);
    state.selected = null;
    load();
  });
  $("filters").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-f]");
    if (!b) return;
    state.filter = b.dataset.f;
    // The stage is kept in the address too (?status=), so a link can open on All and Back keeps it.
    const u = new URL(location.href);
    if (state.filter === "open") u.searchParams.delete("status"); else u.searchParams.set("status", state.filter);
    if (state.filter !== "lost") { state.why = ""; u.searchParams.delete("why"); }
    history.replaceState(null, "", u.pathname + u.search + u.hash);
    rememberList(u.pathname + u.search);
    load();
  });
  $("tests").addEventListener("change", (e) => { state.tests = e.target.checked; load(); });
  $("clear-filters").addEventListener("click", clearFilters);
  $("list").addEventListener("click", (e) => { if (e.target.closest("[data-clear-filters]")) clearFilters(); });
  $("source").addEventListener("change", (e) => {
    const u = new URL(location.href);
    const [kind, value] = e.target.value.split(":");
    if (kind === "n") return;
    SOURCE_KEYS.forEach((k) => u.searchParams.delete(k));
    if (kind === "c") u.searchParams.set("campaign", value);
    if (kind === "a") u.searchParams.set("ad", value);
    history.replaceState(null, "", u);
    rememberList(u.pathname + u.search);
    state.selected = null;
    load();
  });
  let t;
  $("q").addEventListener("input", (e) => {
    clearTimeout(t);
    t = setTimeout(() => { state.q = e.target.value.trim(); load(); }, 250);
  });
  $("list").addEventListener("click", (e) => {
    const row = e.target.closest(".lead-row");
    if (row) select(Number(row.dataset.id));
  });
  showEmptyDetail();
  const fromHash = Number((location.hash.match(/lead=(\d+)/) || [])[1]);
  onRefresh(() => load());
  if (fromHash) state.selected = fromHash; // so the list doesn't open the newest lead instead
  await load();
  if (fromHash) select(fromHash, { push: false });
  // A call dialled from this page while it was reloaded (a phone app starting again): ask how it went.
  resumePending(async (id) => {
    try { const lead = await api(`/api/leads/${id}`); ask(logCall, lead, { after: changed }); } catch (e) { /* gone or not theirs */ }
  });
  // ⌘K or a notification can point at another lead while this page is open; Back closes the one open.
  const followUrl = () => {
    const id = Number((location.hash.match(/lead=(\d+)/) || [])[1]);
    if (id && id !== state.selected) select(id, { push: false });
    else if (id) $("layout").classList.add("showing-detail");
    else $("layout").classList.remove("showing-detail");
  };
  window.addEventListener("hashchange", followUrl);
  window.addEventListener("popstate", followUrl);
  rememberList(listUrl());
  // New leads appear without a reload; the clocks keep counting.
  setInterval(() => { if (!document.hidden) load({ quiet: true }); }, 30000);
}

main();
