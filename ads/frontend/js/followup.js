// Follow-ups and booked calls (L1): the call outcome dialog, the next step, the booked call, the Follow-up box on
// a lead and its chip. Used by Leads and Today. Times come worded from the server (the account's time zone).
// Names start with fu- (never ad-like words, which ad blockers hide).
import { api } from "./api.js";
import { esc, toast } from "./ui.js";
import { FOLLOW, acctHour, zoneCity, zoneDiffers, zoneTag } from "./format.js";

export const OUTCOMES = [["reached", "Talked to them"], ["no_answer", "No answer"], ["voicemail", "Left a voicemail"],
  ["booked", "Booked a call"], ["wrong_number", "Wrong number"]];
export const NEXT_KINDS = [["call_back", "Call back"], ["proposal", "Send a quote"], ["follow_up", "Follow up"], ["other", "Something else…"]];
// What each outcome suggests as the next step (Booked a call asks when the call is instead; Wrong number has none).
const DEFAULT_NEXT = { no_answer: ["call_back", "later_today"], voicemail: ["call_back", "later_today"], reached: ["follow_up", "in_3_days"] };
const STAGE = { new: "New", contacted: "Contacted", qualified: "Qualified", won: "Won", lost: "Lost" };
const PRESET_ORDER = ["later_today", "tomorrow_9", "in_3_days"];
const PENDING = "fu-pending";
const PENDING_MS = 2 * 3600 * 1000;

const firstName = (lead) => String(lead.full_name || "").trim().split(/\s+/)[0] || "them";

export function chipHtml(chip) {
  return chip ? `<span class="fu-chip${chip.tone ? ` ${chip.tone}` : ""}">${esc(chip.text)}</span>` : "";
}

// ---------------------------------------------------------------- the dialog

// One <dialog> whose content moves between steps; resolves with the step's answer, or null for Not now / Escape.
function openDialog(label) {
  const dlg = document.createElement("dialog");
  dlg.className = "fu-dialog";
  dlg.setAttribute("aria-label", label);
  dlg.innerHTML = '<form method="dialog" novalidate></form>';
  document.body.appendChild(dlg);
  let settle;
  const done = new Promise((resolve) => { settle = resolve; });
  let result = null;
  dlg.addEventListener("close", () => { dlg.remove(); settle(result); });
  return { dlg, form: dlg.querySelector("form"), done, finish: (value) => { result = value; dlg.close(); } };
}

const pressed = (root, attr, value) => root.querySelectorAll(`[${attr}]`).forEach((b) => b.setAttribute("aria-pressed", String(b.getAttribute(attr) === value)));

function showError(form, message, field) {
  const err = form.querySelector("#fu-err");
  err.textContent = message;
  err.hidden = false;
  const input = field && form.querySelector(`[data-field="${field}"]`);
  if (input) input.focus();
}

// Step 2: the next step. Returns {kind, text?, preset | at} or null ("No next step").
function nextStepHtml(title, presets, sub = "") {
  const times = [...PRESET_ORDER.filter((k) => presets[k]).map((k) => [k, presets[k].label]), ["pick", "Pick a date…"]];
  return `<h2>${esc(title)}</h2>${sub}
    <fieldset class="fu-set"><legend>Next step</legend><div class="fu-kinds">${NEXT_KINDS.map(([k, l]) =>
      `<button type="button" class="fu-opt" data-kind="${k}" aria-pressed="false">${esc(l)}</button>`).join("")}</div></fieldset>
    <div class="field" id="fu-other" hidden><label for="fu-text">What's the next step?</label>
      <input class="input" id="fu-text" data-field="text" maxlength="120" autocomplete="off" placeholder="e.g. Send the case study"></div>
    <fieldset class="fu-set"><legend>When</legend><div class="fu-times">${times.map(([k, l]) =>
      `<button type="button" class="fu-opt" data-when="${k}" aria-pressed="false">${esc(l)}</button>`).join("")}</div></fieldset>
    <div class="field" id="fu-pick" hidden><label for="fu-at">Date and time</label><input class="input" type="datetime-local" id="fu-at" data-field="when"></div>
    <p class="err" id="fu-err" role="alert" hidden></p>
    <div class="row end"><button type="button" class="btn" data-fu-skip>No next step</button><button type="submit" class="btn btn-primary" id="fu-save">Save</button></div>`;
}

function wireNextStep(form, { kind, preset }) {
  const pick = { kind, when: preset };
  const sync = () => {
    pressed(form, "data-kind", pick.kind);
    pressed(form, "data-when", pick.when);
    form.querySelector("#fu-other").hidden = pick.kind !== "other";
    form.querySelector("#fu-pick").hidden = pick.when !== "pick";
  };
  form.addEventListener("click", (e) => {
    const k = e.target.closest("[data-kind]");
    const w = e.target.closest("[data-when]");
    if (k) { pick.kind = k.dataset.kind; sync(); if (pick.kind === "other") form.querySelector("#fu-text").focus(); }
    if (w) { pick.when = w.dataset.when; sync(); if (pick.when === "pick") form.querySelector("#fu-at").focus(); }
  });
  sync();
  return () => {
    if (!pick.kind) return { problem: ["Pick a next step", null] };
    if (!pick.when) return { problem: ["Pick when", null] };
    const out = { kind: pick.kind };
    if (pick.kind === "other") out.text = form.querySelector("#fu-text").value;
    if (pick.when === "pick") {
      const at = form.querySelector("#fu-at").value;
      if (!at) return { problem: ["Pick a date and time", "when"] };
      out.at = at;
    } else out.preset = pick.when;
    return { value: out };
  };
}

// The booked call: today / tomorrow at a time, a date, or not sure yet.
function meetingHtml(title, sub = "") {
  return `<h2>${esc(title)}</h2>${sub}
    <fieldset class="fu-set"><legend>Day</legend><div class="fu-times">${[["today", "Today"], ["tomorrow", "Tomorrow"], ["pick", "Pick a date…"]].map(([k, l]) =>
      `<button type="button" class="fu-opt" data-day="${k}" aria-pressed="false">${esc(l)}</button>`).join("")}</div></fieldset>
    <div class="fu-when-row">
      <div class="field" id="fu-date-f" hidden><label for="fu-date">Date</label><input class="input" type="date" id="fu-date" data-field="when"></div>
      <div class="field"><label for="fu-time">Time</label><input class="input" type="time" id="fu-time" value="${meetingDefault().time}" step="900"${zoneDiffers() ? ' aria-describedby="fu-zone"' : ""}>
        ${zoneDiffers() ? `<small class="hint" id="fu-zone">Times are ${esc(zoneCity())} time</small>` : ""}</div>
    </div>
    <p class="err" id="fu-err" role="alert" hidden></p>
    <div class="row end"><button type="button" class="btn" data-fu-unsure>Not sure yet</button><button type="submit" class="btn btn-primary" id="fu-save">Save</button></div>`;
}

// Today at the next full hour on the account's clock (the server reads the time as account time, FU-C); from 8 PM
// on, tomorrow at 10:00 (a Save straight away is never in the past).
export function meetingDefault(now = new Date()) {
  const h = acctHour(now) + 1;
  return h >= 21 ? { day: "tomorrow", time: "10:00" } : { day: "today", time: `${String(h).padStart(2, "0")}:00` };
}

function wireMeeting(form) {
  const pick = { day: meetingDefault().day };
  const sync = () => { pressed(form, "data-day", pick.day); form.querySelector("#fu-date-f").hidden = pick.day !== "pick"; };
  form.addEventListener("click", (e) => {
    const d = e.target.closest("[data-day]");
    if (d) { pick.day = d.dataset.day; sync(); if (pick.day === "pick") form.querySelector("#fu-date").focus(); }
  });
  sync();
  return () => {
    const time = form.querySelector("#fu-time").value;
    if (!time) return { problem: ["Pick a time", null] };
    if (pick.day === "pick") {
      const day = form.querySelector("#fu-date").value;
      if (!day) return { problem: ["Pick a date", "when"] };
      return { value: { at: `${day}T${time}` } };
    }
    return { value: { preset: pick.day, time } };
  };
}

// Run one step: submit sends `send(value)`; a refusal with a field stays in the dialog with the message.
function runStep(box, read, send, { skip = null, unsure = null } = {}) {
  const { form, finish } = box;
  form.onsubmit = async (e) => {
    e.preventDefault();
    const got = read();
    if (got.problem) { showError(form, ...got.problem); return; }
    const btn = form.querySelector("#fu-save");
    btn.disabled = true;
    try { finish(await send(got.value)); } catch (err) { btn.disabled = false; showError(form, err.message, err.body && err.body.field); }
  };
  form.querySelector("[data-fu-skip]")?.addEventListener("click", async () => finish(skip ? await skip() : null));
  form.querySelector("[data-fu-unsure]")?.addEventListener("click", async () => {
    try { finish(await unsure()); } catch (err) { showError(form, err.message); }
  });
}

function outcomeHtml(lead) {
  return `<h2>How did the call with ${esc(firstName(lead))} go?</h2>
    <div class="fu-outcomes" role="group" aria-label="How the call went">${OUTCOMES.map(([k, l]) =>
      `<button type="button" class="fu-opt fu-out" data-outcome="${k}">${esc(l)}</button>`).join("")}</div>
    <div class="field"><label for="fu-note">Note (optional)</label><textarea class="input" id="fu-note" rows="2" placeholder="What did they say?"></textarea></div>
    <p class="err" id="fu-err" role="alert" hidden></p>
    <div class="row end"><button type="button" class="btn" data-fu-close>Not now</button></div>`;
}

const forget = () => { try { sessionStorage.removeItem(PENDING); } catch (e) { /* storage off */ } };

// The outcome dialog: how it went, then what's next (or when the booked call is). Posts once, at the end.
// Resolves with the updated lead (with `logged` and `undo`), or null when nothing was saved.
export async function logCall(lead, { after = null } = {}) {
  const box = openDialog(`Call with ${firstName(lead)}`);
  const { form, dlg, finish } = box;
  const presets = (lead.follow && lead.follow.presets) || lead.presets || {};
  let note = "";
  const post = (body) => api(`/api/leads/${lead.id}/calls`, { method: "POST", body: { ...body, note } });
  const step1 = () => {
    form.innerHTML = outcomeHtml(lead);
    form.querySelector("#fu-note").value = note;
    form.querySelector("[data-fu-close]").addEventListener("click", () => finish(null));
    form.onsubmit = (e) => e.preventDefault();
    form.querySelector(".fu-outcomes").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-outcome]");
      if (!b) return;
      note = form.querySelector("#fu-note").value;
      const outcome = b.dataset.outcome;
      const back = `<p class="fu-sub">${esc(OUTCOMES.find(([k]) => k === outcome)[1])} · <button type="button" class="link-btn" data-fu-back>Change</button></p>`;
      if (outcome === "wrong_number") {
        b.disabled = true;
        try { finish(await post({ outcome })); } catch (err) { b.disabled = false; showError(form, err.message); }
        return;
      }
      if (outcome === "booked") {
        form.innerHTML = meetingHtml("When is the call?", back);
        runStep(box, wireMeeting(form), (meeting) => post({ outcome, meeting }), { unsure: () => post({ outcome, meeting: { unscheduled: true } }) });
      } else {
        const [kind, preset] = DEFAULT_NEXT[outcome];
        form.innerHTML = nextStepHtml("What's next?", presets, back);
        runStep(box, wireNextStep(form, { kind, preset }), (next_step) => post({ outcome, next_step }), { skip: () => post({ outcome }) });
      }
      form.querySelector("[data-fu-back]").addEventListener("click", step1);
      form.querySelector("#fu-save").focus();
    });
  };
  step1();
  dlg.showModal();
  form.querySelector("[data-outcome]").focus();
  const updated = await box.done;
  forget();
  if (updated && updated.logged) {
    toast(updated.logged.text, "", { undo: () => undoCall(lead.id, updated.undo.event_id, after) });
  }
  return updated;
}

export async function undoCall(leadId, eventId, after) {
  try {
    const lead = await api(`/api/leads/${leadId}/events/${eventId}/undo`, { method: "POST" });
    toast(lead.undone && lead.undone.to ? `Call taken back. Back to ${STAGE[lead.undone.to] || lead.undone.to}.` : "Call taken back");
    if (after) after(lead);
    return lead;
  } catch (err) { toast(err.message, "bad"); return null; }
}

// Step 2 alone: after a stage move, Add next step, Change, a No-show. Resolves with the updated lead or null.
export async function askNext(lead, { title = "What's next?", kind = null, preset = null, presets = null } = {}) {
  const box = openDialog(title);
  const cur = lead.follow && lead.follow.next;
  box.form.innerHTML = nextStepHtml(title, presets || (lead.follow && lead.follow.presets) || {});
  const read = wireNextStep(box.form, { kind: kind || (cur && cur.kind) || null, preset });
  if (cur && cur.kind === "other") box.form.querySelector("#fu-text").value = cur.text || "";
  runStep(box, read, (next_step) => api(`/api/leads/${lead.id}`, { method: "PATCH", body: { next_step } }));
  box.dlg.showModal();
  box.form.querySelector(kind || (cur && cur.kind) ? "#fu-save" : "[data-kind]").focus();
  return box.done;
}

// When is the booked call? (Set the time, Moved.) Resolves with the updated lead or null.
export async function askMeeting(lead, { title = "When is the call?" } = {}) {
  const box = openDialog(title);
  box.form.innerHTML = meetingHtml(title);
  const send = (meeting) => api(`/api/leads/${lead.id}`, { method: "PATCH", body: { meeting } });
  runStep(box, wireMeeting(box.form), send, { unsure: () => send({ unscheduled: true }) });
  box.dlg.showModal();
  box.form.querySelector("#fu-time").focus();
  return box.done;
}

// A Call link: the phone dials, and the outcome dialog is already waiting when they come back. A page that was
// reloaded meanwhile (a phone app starting again) opens it from sessionStorage.
// A client who can't update leads only dials: no dialog it could never save.
const canLog = () => {
  const c = document.documentElement.classList;
  return !c.contains("read-only") || c.contains("client-leads");
};

export function armDial(link, lead, after) {
  if (!link) return;
  link.addEventListener("click", () => {
    if (!canLog()) return;
    try { sessionStorage.setItem(PENDING, JSON.stringify({ lead_id: lead.id, at: Date.now() })); } catch (e) { /* storage off */ }
    setTimeout(async () => { const updated = await logCall(lead, { after }); if (updated && after) after(updated); }, 400);
  });
}

export function resumePending(open) {
  let p = null;
  try { p = JSON.parse(sessionStorage.getItem(PENDING) || "null"); } catch (e) { p = null; }
  if (!p || !p.lead_id || Date.now() - p.at > PENDING_MS || !canLog() || document.querySelector("dialog.fu-dialog")) return;
  open(p.lead_id);
}

// Back from the phone app: the dialog is open underneath; put the keyboard on its first answer.
document.addEventListener("visibilitychange", () => {
  if (document.hidden) return;
  const first = document.querySelector("dialog.fu-dialog[open] [data-outcome]");
  if (first && !document.querySelector("dialog.fu-dialog[open]").contains(document.activeElement)) first.focus();
});

// ---------------------------------------------------------------- the Follow-up box on a lead

const act = (fu, label, cls = "btn btn-small") => `<button type="button" class="${cls}" data-fu="${fu}">${esc(label)}</button>`;

export function boxHtml(lead) {
  const f = lead.follow;
  if (!f) return "";
  const s = f.summary;
  const n = s.call_attempts || 0;
  const lines = [];
  lines.push(`<p class="fu-line" id="fu-calls">${n ? `Last try: ${esc(s.last_words)} · ${n} ${n === 1 ? "try" : "tries"}, ${s.ever_reached ? "talked to them before" : "not reached yet"}` : "No calls yet."}</p>`);
  const open = f.open;
  if (open && s.last_outcome === "wrong_number") {
    lines.push(`<p class="fu-line warn">Wrong number.<span class="fu-actions">${lead.email ? act("email", "Email them") : act("lost-wrong", "Move to Lost")}</span></p>`);
  }
  const m = f.meeting;
  if (m) {
    const how = { call: "booked by phone", manual: "marked by hand" }[m.source] || "booked";
    const state = m.state;
    if (state === "unscheduled") lines.push(`<p class="fu-line" id="fu-meeting">Call booked, time not set.<span class="fu-actions">${act("set-time", "Set the time")}</span></p>`);
    else if (state === "check") lines.push(`<p class="fu-line warn" id="fu-meeting">Did the call ${esc(m.on)} happen?<span class="fu-actions">${act("held", "It happened")}${act("no_show", "No-show")}${act("moved", "Moved")}</span></p>`);
    else if (state === "upcoming" || state === "soon") lines.push(`<p class="fu-line" id="fu-meeting">Call booked for <b>${esc(m.when)}${m.at ? esc(zoneTag(new Date(m.at))) : ""}</b> (${how}).<span class="fu-actions">${act("moved", "Moved")}${act("canceled", "Canceled")}</span></p>`);
    else if (state === "held") lines.push(`<p class="fu-line ok" id="fu-meeting">The call ${esc(m.on)} happened.</p>`);
    else if (state === "no_show") lines.push(`<p class="fu-line" id="fu-meeting">No-show ${esc(m.on)}.<span class="fu-actions">${act("rebook", "Book again")}</span></p>`);
    else if (state === "canceled") lines.push(`<p class="fu-line" id="fu-meeting">Call ${m.on ? `${esc(m.on)} ` : ""}canceled.<span class="fu-actions">${act("rebook", "Book again")}</span></p>`);
  }
  const x = f.next;
  if (x) {
    lines.push(x.overdue
      ? `<p class="fu-line warn" id="fu-next">Overdue: <b>${esc(x.words)}</b> · was due ${esc(x.short)}<span class="fu-actions">${act("done", "Done")}${act("change", "Change")}</span></p>`
      : `<p class="fu-line" id="fu-next">Next: <b>${esc(x.words)}</b> · ${esc(x.when)}<span class="fu-actions">${act("done", "Done")}${act("change", "Change")}</span></p>`);
  } else if (open) {
    lines.push(`<p class="fu-line muted" id="fu-next">No next step.<span class="fu-actions">${act("add", "Add next step")}</span></p>`);
  }
  if (f.suggestion) {
    const label = f.suggestion === "went_quiet" ? "Lost: went quiet" : "Lost: couldn't reach";
    lines.push(`<p class="fu-line" id="fu-suggest">${s.unanswered_streak} tries, no answer.<span class="fu-actions"><button type="button" class="btn btn-small" id="fu-lost" data-fu="lost">${esc(label)}</button></span></p>`);
  }
  return `<section class="fu-box" id="fu-box" aria-labelledby="fu-h"><h3 class="fu-h" id="fu-h">${FOLLOW.title}</h3>${lines.join("")}</section>`;
}
