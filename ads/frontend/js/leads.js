import { api, startLoad } from "./api.js";
import { boot, entityLink, esc, fieldError, icon, leadClock, onRefresh, phoneDisplay, rememberList, setNewCount, toast, when, showLoadError } from "./ui.js";
import { closeLayer, openLayer } from "./urlstate.js";

const STAGES = [
  { id: "new", label: "New" },
  { id: "contacted", label: "Contacted" },
  { id: "qualified", label: "Qualified" },
  { id: "won", label: "Won" },
  { id: "lost", label: "Lost" },
];
const FILTERS = [{ id: "open", label: "Open" }, ...STAGES, { id: "all", label: "All" }];

const state = { loaded: false, me: null, filter: "open", q: "", tests: false, leads: [], counts: {}, selected: null, seen: new Set() };
const $ = (id) => document.getElementById(id);

// What "filtered" means here: anything other than open leads of every campaign, no search, no test leads.
// Where a lead came from, kept in the URL: the picker offers campaigns and ads; an ad set or a form comes from a link.
const SOURCE_KEYS = ["campaign", "adset", "ad", "form"];
const filtered = () => state.filter !== "open" || Boolean(state.q) || state.tests || SOURCE_KEYS.some((k) => new URLSearchParams(location.search).get(k));

function renderFilters() {
  const c = state.counts;
  const open = (c.new || 0) + (c.contacted || 0) + (c.qualified || 0);
  const all = Object.values(c).reduce((a, b) => a + b, 0);
  const n = { open, all, ...c };
  $("filters").innerHTML = FILTERS.map((f) =>
    `<button type="button" class="view-chip" data-f="${f.id}" aria-pressed="${state.filter === f.id}">${f.label}<span class="n">${n[f.id] || 0}</span></button>`
  ).join("");
  setNewCount(state.newEverywhere ?? c.new ?? 0);
}

const minutesText = (m) => (m < 60 ? `${m} min` : m < 48 * 60 ? `${Math.round(m / 6) / 10} h`.replace(".0 h", " h") : `${Math.round(m / 1440)} days`);

// How fast leads hear back, last 30 days. Half of the contacted leads heard back within the median.
function renderResponse(r) {
  const el = $("response");
  if (!r || !r.leads) { el.hidden = true; return; }
  const parts = [r.median_minutes === null ? "Nobody has been contacted yet" : `half heard back within ${minutesText(r.median_minutes)}`,
    `${r.within_5} of ${r.leads} within 5 min`];
  if (r.untouched) parts.push(`${r.untouched} not contacted`);
  el.textContent = `Last 30 days: ${parts.join(" · ")}`;
  el.hidden = false;
}

function rowHtml(lead) {
  const isNew = lead.status === "new";
  // One urgency rule with Today and the reminders (the server's today.urgency).
  const clock = leadClock(lead);
  return `<li><button type="button" class="lead-row${state.seen.has(lead.id) ? "" : " arrived"}" data-id="${lead.id}" ${state.selected === lead.id ? 'aria-current="true"' : ""}>
    ${clock}
    <span class="who">
      <b>${esc(lead.full_name || "No name given")}</b>
      <span>${esc(lead.business_type || "Business not given")}</span>
      <small>${lead.is_test ? '<span class="pill">Test</span> ' : ""}${isNew ? "" : `<span class="pill ${lead.status}">${esc(STAGES.find((s) => s.id === lead.status).label)}</span> `}${esc(lead.ad_name || (lead.is_organic ? "No ad (organic)" : ""))}${lead.owner_name ? `, ${esc(lead.owner_name)}` : ""}</small>
    </span>
  </button></li>`;
}

function renderList() {
  const list = $("list");
  $("clear-filters").hidden = !filtered();
  if (!state.leads.length) {
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
  const src = new URLSearchParams(location.search);
  for (const k of SOURCE_KEYS) if (src.get(k)) params.set(k, src.get(k));
  const superseded = startLoad("leads");
  try {
    const data = await api("/api/leads?" + params);
    if (superseded()) return;
    renderSources(data.sources || [], src, data.narrowed);
    state.leads = data.leads;
    state.counts = data.counts;
    state.newEverywhere = data.new_everywhere;
    renderResponse(data.response);
    if (!state.loaded) { data.leads.forEach((l) => state.seen.add(l.id)); state.loaded = true; }
    renderFilters();
    renderList();
    if (!state.selected && state.leads.length && window.matchMedia("(min-width: 961px)").matches) {
      select(state.leads[0].id, { push: false });
    }
  } catch (err) {
    if (!quiet && !superseded()) showLoadError($("list"), err, load);
  }
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
    <div class="reach">
      ${lead.phone ? `<a class="btn btn-call" href="tel:${esc(lead.phone)}">${icon("phone")} Call ${esc(phoneDisplay(lead.phone))}</a>` : ""}
      ${lead.email ? `<button type="button" class="btn" id="reply-open" aria-expanded="false" aria-controls="reply-form">${icon("mail")} Email them</button>` : ""}
    </div>
    ${lead.email ? replyForm(lead) : ""}
    <div class="stage">
      <span class="stage-label" id="stage-label">Stage</span>
      <div class="segmented" role="group" aria-labelledby="stage-label" id="stages">
        ${STAGES.map((s) => `<button type="button" data-stage="${s.id}" aria-pressed="${lead.status === s.id}">${s.label}</button>`).join("")}
      </div>
    </div>
    ${metaStages(lead)}
    <dl class="facts">
      <dt>Owner</dt><dd>${state.me.role === "client" ? esc(lead.owner_name || "Nobody yet") : `<label class="sr-only" for="owner">Owner</label><select class="input" id="owner">${owners}</select>`}</dd>
      <dt>Asked</dt><dd>${when(lead.created_time)}</dd>
      <dt>Phone</dt><dd>${esc(phoneDisplay(lead.phone) || "—")}</dd>
      <dt>Email</dt><dd>${esc(lead.email || "—")}</dd>
      <dt>Ad</dt><dd>${lead.ad_name ? entityLink("ad", lead.ad_id, lead.ad_name) : esc(lead.is_organic ? "None: filled in without an ad (organic)" : "—")}</dd>
      ${lead.adset_name ? `<dt>Ad set</dt><dd>${entityLink("adset", lead.adset_id, lead.adset_name)}</dd>` : ""}
      <dt>Campaign</dt><dd>${lead.campaign_name ? entityLink("campaign", lead.campaign_id, lead.campaign_name) : "—"}</dd>
      ${lead.form_name ? `<dt>Form</dt><dd>${entityLink("form", lead.form_id, lead.form_name)}</dd>` : ""}
    </dl>
    ${answers ? `<h3 class="section-title">Their answers</h3><dl class="facts">${answers}</dl>` : ""}
    ${emailsHtml(lead)}
    <h3 class="section-title">Notes</h3>
    <ul class="notes">${lead.notes.map((n) => `<li><div class="meta">${esc(n.author || "Someone")}, ${when(n.created_at)}</div>${esc(n.body)}</li>`).join("") || `<li class="muted">${state.me.role === "client" && !state.me.account.clients_update_leads ? "No notes yet." : "No notes yet. Write down what you learned on the call."}</li>`}</ul>
    <form id="note-form" class="stack tight">
      <label class="sr-only" for="note">Add a note</label>
      <textarea class="input" id="note" name="body" placeholder="What did you learn on the call?"></textarea>
      <div><button class="btn btn-primary" type="submit">Add note</button></div>
    </form>
    ${history ? `<h3 class="section-title">History</h3><ol class="history">${history}</ol>` : ""}`;
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
  note.innerHTML = d.mail_ready ? "" : `Email isn't set up yet, so this can't be sent.${state.me.role === "admin" ? ' <a href="/settings.html">Set it up in Settings → Email</a>.' : " Ask an admin to set it up."}`;
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
  detail.innerHTML = detailHtml(lead);
  $("back")?.addEventListener("click", () => {
    $("layout").classList.remove("showing-detail");
    closeLayer(listUrl());
  });
  wireReply(lead);
  detail.querySelectorAll("[data-stage]").forEach((b) => b.addEventListener("click", () => patch(lead.id, { status: b.dataset.stage })));
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
  } catch (err) { toast(err.message, "bad"); }
}

async function undoMove(id, eventId) {
  try {
    const lead = await api(`/api/leads/${id}/events/${eventId}/undo`, { method: "POST" });
    if (state.selected === id) renderDetail(lead, { keep: true });
    const sent = (lead.undone?.meta_has || []).map(stageLabel);
    toast(`Back to ${stageLabel(lead.status)}${sent.length ? `. Meta already has ${sent.join(", ")}` : ""}`);
    load({ quiet: true });
  } catch (err) { toast(err.message, "bad"); }
}

function clearFilters() {
  state.filter = "open"; state.q = ""; state.tests = false; state.selected = null;
  $("q").value = ""; $("tests").checked = false;
  const u = new URL(location.href);
  [...SOURCE_KEYS, "status"].forEach((k) => u.searchParams.delete(k));
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
  $("filters").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-f]");
    if (!b) return;
    state.filter = b.dataset.f;
    // The stage is kept in the address too (?status=), so a link can open on All and Back keeps it.
    const u = new URL(location.href);
    if (state.filter === "open") u.searchParams.delete("status"); else u.searchParams.set("status", state.filter);
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
