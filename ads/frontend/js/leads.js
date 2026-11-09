import { api } from "./api.js";
import { boot, esc, icon, onRefresh, phoneDisplay, setNewCount, shortWait, toast, waited, when } from "./ui.js";

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

// Fresh = under an hour, late = over a day. Only new leads are "waiting".
function clockClass(lead, now = Date.now()) {
  if (lead.status !== "new") return "done";
  const mins = (now - new Date(lead.created_time).getTime()) / 60000;
  return mins < 60 ? "fresh" : mins > 1440 ? "late" : "";
}

function renderFilters() {
  const c = state.counts;
  const open = (c.new || 0) + (c.contacted || 0) + (c.qualified || 0);
  const all = Object.values(c).reduce((a, b) => a + b, 0);
  const n = { open, all, ...c };
  $("filters").innerHTML = FILTERS.map((f) =>
    `<button type="button" data-f="${f.id}" aria-pressed="${state.filter === f.id}">${f.label}<span class="n">${n[f.id] || 0}</span></button>`
  ).join("");
  setNewCount(c.new || 0);
}

function rowHtml(lead) {
  const isNew = lead.status === "new";
  const clock = isNew
    ? `<span class="clock ${clockClass(lead)}"><b>${shortWait(lead.created_time)}</b><small>waiting</small></span>`
    : `<span class="clock done"><b>${shortWait(lead.created_time)}</b><small>ago</small></span>`;
  return `<li><button type="button" class="lead-row${state.seen.has(lead.id) ? "" : " arrived"}" data-id="${lead.id}" ${state.selected === lead.id ? 'aria-current="true"' : ""}>
    ${clock}
    <span class="who">
      <b>${esc(lead.full_name || "No name given")}</b>
      <span>${esc(lead.business_type || "Business not given")}</span>
      <small>${lead.is_test ? '<span class="pill">Test</span> ' : ""}${isNew ? "" : `<span class="pill ${lead.status}">${esc(STAGES.find((s) => s.id === lead.status).label)}</span> `}${esc(lead.ad_name || "")}${lead.owner_name ? `, ${esc(lead.owner_name)}` : ""}</small>
    </span>
  </button></li>`;
}

function renderList() {
  const list = $("list");
  if (!state.leads.length) {
    const filtered = state.filter !== "open" || state.q;
    list.innerHTML = `<li class="empty">${filtered
      ? "<h3>Nothing matches</h3><p>Try another stage or clear the search.</p>"
      : `<h3>No leads yet</h3><p>When someone asks for a free intro call, they show up here within a minute${state.me.role === "admin" ? " and you get an email" : ""}.</p>${state.me.role === "admin" ? '<a class="btn" href="/settings.html">Check the Meta connection</a>' : ""}`}</li>`;
  } else {
    list.innerHTML = state.leads.map(rowHtml).join("");
  }
  state.leads.forEach((l) => state.seen.add(l.id));
}

async function load({ quiet = false } = {}) {
  const params = new URLSearchParams();
  if (state.filter !== "all") params.set("status", state.filter);
  if (state.q) params.set("q", state.q);
  if (state.tests) params.set("tests", "1");
  try {
    const data = await api("/api/leads?" + params);
    state.leads = data.leads;
    state.counts = data.counts;
    if (!state.loaded) { data.leads.forEach((l) => state.seen.add(l.id)); state.loaded = true; }
    renderFilters();
    renderList();
    if (!state.selected && state.leads.length && window.matchMedia("(min-width: 961px)").matches) {
      select(state.leads[0].id, { push: false });
    }
  } catch (err) {
    if (!quiet) toast(err.message, "bad");
  }
}

function detailHtml(lead) {
  const isNew = lead.status === "new";
  const w = waited(lead.created_time);
  const clock = `<span class="clock ${clockClass(lead)}"><b>${w.text}</b><small>${isNew ? "waiting for a call" : "since they asked"}</small></span>`;
  const CONTACT = new Set(["full_name", "first_name", "last_name", "email", "work_email", "phone_number", "phone"]);
  const answers = (lead.answers || []).filter((a) => !CONTACT.has(String(a.name).toLowerCase())).map((a) =>
    `<dt>${esc(prettyQuestion(a.name))}</dt><dd>${esc((a.values || []).join(", ") || "—")}</dd>`).join("");
  const owners = [`<option value="">Nobody yet</option>`, ...lead.assignable.map((u) =>
    `<option value="${u.id}" ${u.id === lead.owner_id ? "selected" : ""}>${esc(u.name)}</option>`)].join("");
  const history = lead.history.map((h) => `<li>${when(h.at)}: ${esc(describe(h))}</li>`).join("");
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
      ${lead.email ? `<a class="btn" href="mailto:${esc(lead.email)}?subject=${encodeURIComponent("Your free intro call with Edge Bourne")}">${icon("mail")} Email</a>` : ""}
    </div>
    <div class="stage">
      <span class="stage-label" id="stage-label">Stage</span>
      <div class="segmented" role="group" aria-labelledby="stage-label" id="stages">
        ${STAGES.map((s) => `<button type="button" data-stage="${s.id}" aria-pressed="${lead.status === s.id}">${s.label}</button>`).join("")}
      </div>
    </div>
    ${metaStages(lead)}
    <dl class="facts">
      <dt>Owner</dt><dd><label class="sr-only" for="owner">Owner</label><select class="input" id="owner">${owners}</select></dd>
      <dt>Asked</dt><dd>${when(lead.created_time)}</dd>
      <dt>Phone</dt><dd>${esc(phoneDisplay(lead.phone) || "—")}</dd>
      <dt>Email</dt><dd>${esc(lead.email || "—")}</dd>
      <dt>Ad</dt><dd>${esc(lead.ad_name || "—")}</dd>
      <dt>Campaign</dt><dd>${esc(lead.campaign_name || "—")}</dd>
    </dl>
    ${answers ? `<h3 class="section-title">Their answers</h3><dl class="facts">${answers}</dl>` : ""}
    <h3 class="section-title">Notes</h3>
    <ul class="notes">${lead.notes.map((n) => `<li><div class="meta">${esc(n.author || "Someone")}, ${when(n.created_at)}</div>${esc(n.body)}</li>`).join("") || '<li class="muted">No notes yet. Write down what you learned on the call.</li>'}</ul>
    <form id="note-form" class="stack tight">
      <label class="sr-only" for="note">Add a note</label>
      <textarea class="input" id="note" name="body" placeholder="What did you learn on the call?"></textarea>
      <div><button class="btn btn-primary" type="submit">Add note</button></div>
    </form>
    ${history ? `<h3 class="section-title">History</h3><ul class="history">${history}</ul>` : ""}`;
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

function describe(h) {
  const who = h.who || (h.actor === "meta" ? "Meta" : "System");
  if (h.action === "lead.received") return "Arrived from Meta";
  if (h.action === "lead.status") return `${who} moved it from ${h.details.from} to ${h.details.to}`;
  if (h.action === "lead.owner") return `${who} changed the owner`;
  if (h.action === "lead.email_failed") return "The alert email couldn't be sent";
  return h.action;
}

async function select(id, { push = true } = {}) {
  state.selected = id;
  document.querySelectorAll(".lead-row").forEach((r) => r.setAttribute("aria-current", String(Number(r.dataset.id) === id)));
  if (push) history.replaceState(null, "", `#lead=${id}`);
  $("layout").classList.add("showing-detail");
  try {
    const lead = await api(`/api/leads/${id}`);
    renderDetail(lead);
  } catch (err) {
    $("detail").innerHTML = `<div class="empty"><h3>Can't open this lead</h3><p>${esc(err.message)}</p></div>`;
  }
}

function renderDetail(lead) {
  const detail = $("detail");
  detail.innerHTML = detailHtml(lead);
  $("back")?.addEventListener("click", () => {
    $("layout").classList.remove("showing-detail");
    history.replaceState(null, "", location.pathname);
  });
  detail.querySelectorAll("[data-stage]").forEach((b) => b.addEventListener("click", () => patch(lead.id, { status: b.dataset.stage })));
  $("owner").addEventListener("change", (e) => patch(lead.id, { owner_id: e.target.value ? Number(e.target.value) : null }));
  $("note-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = e.target.body.value.trim();
    if (!body) return;
    try {
      renderDetail(await api(`/api/leads/${lead.id}/notes`, { method: "POST", body: { body } }));
      toast("Note added");
    } catch (err) { toast(err.message, "bad"); }
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

async function patch(id, body) {
  try {
    const lead = await api(`/api/leads/${id}`, { method: "PATCH", body });
    renderDetail(lead);
    if ((lead.meta_stages || []).some((r) => r.status === "pending")) followMetaStages(id);
    if (body.status) toast(`Moved to ${STAGES.find((s) => s.id === body.status).label}`);
    load({ quiet: true });
  } catch (err) { toast(err.message, "bad"); }
}

function showEmptyDetail() {
  $("detail").innerHTML = `<div class="empty"><h3>Pick a lead</h3><p>Their answers, the ad that brought them and your notes show up here.</p></div>`;
}

async function main() {
  state.me = await boot({ page: "leads" });
  if (!state.me) return;
  $("search-icon").outerHTML = icon("search");
  $("filters").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-f]");
    if (!b) return;
    state.filter = b.dataset.f;
    load();
  });
  $("tests").addEventListener("change", (e) => { state.tests = e.target.checked; load(); });
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
  await load();
  if (fromHash) select(fromHash, { push: false });
  // New leads appear without a reload; the clocks keep counting.
  setInterval(() => { if (!document.hidden) load({ quiet: true }); }, 30000);
}

main();
