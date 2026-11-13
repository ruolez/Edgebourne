// "Did it work?" (D3): the line under a change in History and under Claude's decided suggestions, the dialog with
// the before/after windows, and Put it back. Put it back only opens the usual confirmation (budget, on/off, version)
// filled in with what it was before; nothing here changes money by itself.
// No top-level use of ui.js: it imports this module for its timeline (the two load each other).
import { api } from "./api.js";
import { esc, entityLink, errorState, refreshPage, skeleton, toast } from "./ui.js";
import { count, money, OUTCOME, OUTCOME_TONE } from "./format.js";
import { changeStatus, editBudget, restoreVersion } from "./controls.js";
import * as UrlState from "./urlstate.js";

const WORSE = new Set(["worse", "lean_worse"]);
const role = () => (window.ebadsMe && window.ebadsMe.role) || "";

// The sentence without its leading state word (the word is the pill in front of it).
function rest(check) {
  const word = OUTCOME[check.state] || "";
  const s = check.sentence || "";
  return word && s.startsWith(`${word}: `) ? s.slice(word.length + 2) : s;
}

function stateHtml(check) {
  if (check.state === "waiting") return "";
  return `<span class="oc-state ${OUTCOME_TONE[check.state] || ""}">${esc(OUTCOME[check.state] || check.state)}</span>`;
}

// One line: the state word, the sentence, Put back on…, then Details (and Put it back while it looks worse).
// `label` names the change for screen readers ("Budget $20.00 → $24.00 a day"), so a list of lines isn't "Details, Details…".
export function outcomeLine(check, { changeId = null, canUndo = false, expect = null, label = "" } = {}) {
  if (!check) return "";
  const id = changeId ?? check.change_id;
  const waiting = check.state === "waiting";
  const back = check.put_back ? ` <span class="oc-back">· ${esc(check.put_back)}</span>` : "";
  const expectLine = expect || check.expected || check.expected_text ? expectHtml(check) : "";
  const acts = id != null ? `<span class="oc-acts"><button type="button" class="btn btn-small btn-quiet oc-btn" data-oc-open="${esc(id)}"${label ? ` aria-label="Did it work? ${esc(label)}"` : ""}>Details</button>${
    canUndo && check.worse && !check.put_back && role() !== "client" ? `<button type="button" class="btn btn-small oc-btn" data-oc-undo="${esc(id)}"${label ? ` aria-label="Put back: ${esc(label)}"` : ""}>Put it back</button>` : ""}</span>` : "";
  return `<span class="oc-line${waiting ? " oc-wait" : ""}" data-oc-state="${esc(check.state)}">${stateHtml(check)}<span class="oc-text">${esc(rest(check))}${back}</span>${acts}</span>${expectLine}`;
}

// Claude's expectation under a decided suggestion: "Expected: cost per lead under $40. Got: $36 over 7 days · Met".
function expectHtml(check) {
  if (check.expected) {
    const met = check.expect_met === true ? " · <b>Met</b>" : check.expect_met === false ? " · <b>Not met</b>" : "";
    const got = check.got ? ` Got: ${esc(check.got)}${met}` : " Too early to say.";
    return `<span class="oc-expect">Expected: ${esc(check.expected)}.${got}</span>`;
  }
  return check.expected_text ? `<span class="oc-expect">Expected: ${esc(check.expected_text)}</span>` : "";
}

// ---------------------------------------------------------------- the dialog

const TOTAL_ROWS = [
  ["Spent", (t) => money(t.spend_cents, { exact: true })],
  ["Spent a day", (t) => (t.days ? money(Math.round(t.spend_cents / t.days), { exact: true }) : "—")],
  ["Leads", (t) => count(t.leads)],
  ["Cost per lead", (t) => (t.cpl_cents != null ? money(t.cpl_cents, { exact: true }) : "—")],
  ["Qualified leads", (t) => count(t.qualified)],
  ["Cost per qualified lead", (t) => (t.cpq_cents != null ? money(t.cpq_cents, { exact: true }) : "—")],
];

function gridHtml(row) {
  if (!row.before && !row.after) return "";
  const head = (label, span) => `<div class="oc-h" role="columnheader"><b>${label}</b>${span ? `<small>${esc(span.label)}</small>` : ""}</div>`;
  const cell = (t, fn) => `<div class="oc-v" role="cell">${t ? esc(fn(t)) : "—"}</div>`;
  return `<div class="oc-grid" role="table" aria-label="Before and after">
    <div class="oc-r" role="row"><div class="oc-h" role="columnheader"><span class="sr-only">What</span></div>${head("Before", row.before_span)}${head("After", row.after_span)}</div>
    ${TOTAL_ROWS.map(([label, fn]) => `<div class="oc-r" role="row"><div class="oc-k" role="rowheader">${esc(label)}</div>${cell(row.before, fn)}${cell(row.after, fn)}</div>`).join("")}
  </div>`;
}

function expectBlock(d, row) {
  if (!d.expect && !d.expected_text) return "";
  if (!d.expect) return `<div class="oc-expect oc-expect-box"><p>Claude expected: ${esc(d.expected_text)}</p></div>`;
  const onTab = row && row.horizon === d.expect_horizon;
  const verdict = !onTab ? `<p class="muted small">Checked on the ${d.expect_horizon}-day tab.</p>`
    : d.expect_met === true ? `<p>Got: ${esc(d.got_words || "")}. <b>Met.</b></p>`
    : d.expect_met === false ? `<p>Got: ${esc(d.got_words || "")}. <b>Not met.</b></p>` : "<p>Too early to say.</p>";
  return `<div class="oc-expect oc-expect-box"><p>Claude expected: ${esc(d.expect_words)}.</p>${verdict}</div>`;
}

function subtitle(d) {
  const from = d.proposal && role() === "admin" ? ` · <a href="/desk.html#p/${esc(d.proposal.id)}">from Claude's suggestion</a>` : d.proposal ? " · from Claude's suggestion" : "";
  return `${esc(d.title)} · ${esc(d.change.day)}${d.change.by ? ` · ${esc(d.change.by)}` : ""}${from}`;
}

function bodyHtml(d, h) {
  const row = d.rows.find((r) => r.horizon === h) || d.headline;
  const tabs = `<div class="oc-tabs" role="tablist" aria-label="Days after the change">${d.rows.map((r) => {
    const off = r.state === "waiting";
    const on = r.horizon === row.horizon;
    return `<button type="button" role="tab" id="oc-tab-${r.horizon}" aria-controls="oc-panel" data-oc-h="${r.horizon}" aria-selected="${on}" tabindex="${on ? 0 : -1}"${off ? " disabled" : ""}>${r.horizon} days${off && r.ready_label ? ` · ${esc(r.ready_label)}` : ""}</button>`;
  }).join("")}</div>`;
  // The ad set or campaign it was measured on links to its page (9.3 entityLink).
  const named = d.scope.name ? `“${esc(d.scope.name)}”` : "";
  const compared = named && d.scope.id !== d.change.entity_id && esc(d.compared).includes(named)
    ? esc(d.compared).replace(named, `“${entityLink(d.scope.level, d.scope.id, d.scope.name)}”`) : esc(d.compared);
  const notes = (row.notes || []).map((n) => `<li>${esc(n)}</li>`).join("");
  const rule = d.needs_target ? `${esc(d.rule)} <a href="/settings.html#tg-targets">Open Targets</a>` : esc(d.rule);
  return `${tabs}
    <div class="oc-panel" role="tabpanel" id="oc-panel" aria-labelledby="oc-tab-${row.horizon}">
      <p class="oc-say">${stateHtml(row)}<span>${esc(rest(row))}</span></p>
      ${gridHtml(row)}
      <p class="oc-note">${compared}</p>
      <p class="oc-note">${rule}</p>
      ${notes ? `<ul class="oc-notes">${notes}</ul>` : ""}
      ${role() !== "client" ? expectBlock(d, row) : ""}
    </div>`;
}

function actsHtml(d) {
  const undone = d.undone_by ? `<p class="oc-note">${esc(d.undone_by.words)}.</p>` : "";
  let put = "";
  if (d.undo && d.undo.plan && role() !== "client") {
    put = `<button type="button" class="btn ${WORSE.has(d.headline.state) ? "btn-primary" : ""}" id="oc-undo">Put it back</button>`;
  } else if (d.undo && d.undo.reason && role() !== "client") {
    put = `<p class="oc-note oc-why">${esc(d.undo.reason)}</p>`;
  }
  return `${undone}<div class="row end oc-end">${put}<button type="button" class="btn" id="oc-close">Close</button></div>`;
}

let openDialog = null;

// Opens the dialog for a change. `push`: Back closes it (a history step with ?check=).
export async function openOutcome(changeId, { push = true } = {}) {
  if (openDialog) openDialog.close();
  const dlg = document.createElement("dialog");
  dlg.className = "oc-sheet";
  dlg.setAttribute("aria-labelledby", "oc-title");
  dlg.innerHTML = `<form method="dialog" novalidate><h2 id="oc-title">Did it work?</h2><p class="oc-sub" id="oc-sub"></p><div id="oc-body">${skeleton("Reading the numbers…")}</div><div id="oc-acts"><div class="row end oc-end"><button type="button" class="btn" id="oc-close">Close</button></div></div></form>`;
  document.body.appendChild(dlg);
  openDialog = dlg;
  if (push) UrlState.openLayer(withCheck(changeId));
  let data = null;
  let horizon = null;
  const paint = () => {
    dlg.querySelector("#oc-sub").innerHTML = subtitle(data);
    dlg.querySelector("#oc-body").innerHTML = bodyHtml(data, horizon);
    dlg.querySelector("#oc-acts").innerHTML = actsHtml(data);
  };
  const load = async () => {
    try {
      data = await api(`/api/changes/${encodeURIComponent(changeId)}/check`);
      horizon = data.headline.horizon;
      paint();
    } catch (err) {
      errorState(dlg.querySelector("#oc-body"), err, () => { dlg.querySelector("#oc-body").innerHTML = skeleton("Reading the numbers…"); load(); }, null, { panel: false });
    }
  };
  dlg.addEventListener("click", async (e) => {
    const tab = e.target.closest("[data-oc-h]");
    if (tab && !tab.disabled) { horizon = Number(tab.dataset.ocH); paint(); dlg.querySelector(`[data-oc-h="${horizon}"]`)?.focus(); return; }
    if (e.target.closest("#oc-close")) { dlg.close(); return; }
    if (e.target.closest("#oc-undo")) { const d = data; dlg.close(); putBack(d); }
  });
  dlg.addEventListener("keydown", (e) => {
    const tab = e.target.closest("[data-oc-h]");
    if (!tab || !["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    const all = [...dlg.querySelectorAll("[data-oc-h]:not([disabled])")];
    const next = all[(all.indexOf(tab) + (e.key === "ArrowRight" ? 1 : all.length - 1)) % all.length];
    if (next) { horizon = Number(next.dataset.ocH); paint(); dlg.querySelector(`[data-oc-h="${horizon}"]`)?.focus(); }
  });
  dlg.addEventListener("close", () => {
    dlg.remove();
    if (openDialog === dlg) openDialog = null;
    if (new URLSearchParams(location.search).has("check")) UrlState.closeLayer(withCheck(null));
  });
  dlg.showModal();
  dlg.querySelector("#oc-close").focus();
  await load();
}

function withCheck(changeId) {
  const u = new URL(location.href);
  if (changeId == null) u.searchParams.delete("check"); else u.searchParams.set("check", String(changeId));
  return u.pathname + u.search + u.hash;
}

// Put it back: the usual dialog, filled in with what it was before the change. The person still confirms; the server
// runs every check it always runs.
export async function putBack(d, after = refreshPage) {
  const plan = d.undo && d.undo.plan;
  // No plan is a normal situation (changed again since, archived, a newer version): said plainly, not as an error.
  if (!plan) { if (d.undo && d.undo.reason) toast(d.undo.reason); return; }
  if (plan.kind === "budget") {
    await editBudget({ level: plan.level, id: plan.id, name: plan.name, current: plan.from_cents, suggest: plan.to_cents, undoOf: d.change.id,
      note: `Before the change on ${esc(d.change.day)} it was <b>${money(plan.to_cents, { exact: true })} a day</b>.` }, after);
  } else if (plan.kind === "status") {
    await changeStatus({ level: plan.level, id: plan.id, name: plan.name, turnOn: plan.to === "ACTIVE", undoOf: d.change.id }, after);
  } else if (plan.kind === "version") {
    await restoreVersion({ adId: plan.id, number: plan.number, undoOf: d.change.id }, after);
  }
}

export async function putBackFor(changeId, after = refreshPage) {
  try { await putBack(await api(`/api/changes/${encodeURIComponent(changeId)}/check`), after); }
  catch (err) { toast(err.message, "bad"); }
}

// A page opened with ?check=N (an Inbox or Today link) shows that change's dialog. The entry it arrived on becomes the
// page without ?check= and the dialog pushes its own step, so Back (a phone's too) closes it and stays on the page.
export function openFromUrl() {
  const id = new URLSearchParams(location.search).get("check");
  if (!id || !/^\d+$/.test(id)) return;
  history.replaceState(history.state, "", withCheck(null));
  openOutcome(Number(id));
}

// Back closes the dialog it opened.
addEventListener("popstate", () => {
  if (openDialog && !new URLSearchParams(location.search).has("check")) openDialog.close();
});

document.addEventListener("click", (e) => {
  const open = e.target.closest("[data-oc-open]");
  if (open) { e.preventDefault(); openOutcome(open.dataset.ocOpen); return; }
  const undo = e.target.closest("[data-oc-undo]");
  if (undo) { e.preventDefault(); putBackFor(undo.dataset.ocUndo); }
});
