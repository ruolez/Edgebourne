// What an admin does with an alert, the same in the Inbox, on Today and on the ad page (W1a):
// Got it… (snooze: no messages until a day, or until it gets worse), Wake it now, and Diagnose with Claude
// (an editable request → a read-only run on the Mac). Nothing here changes Meta: a snooze only stops the
// messages, and anything Claude suggests comes back as a suggestion accepted the usual way.
import { api } from "./api.js";
import { confirmDialog, esc, icon, toast } from "./ui.js";
import { RUN_STATE, suggestions } from "./format.js";

const ACTIVE = new Set(["queued", "claimed", "running"]);
const MAX = 4000;

// The run a Diagnose (or Fix with Claude) started: where it is, as one button that links to it.
export function runChip(run, { label = "", small = false } = {}) {
  if (!run) return "";
  const go = (cls, text, href = `/desk.html#r/${run.id}`) => `<a class="btn ${cls}${small ? " btn-small" : ""} al-chip" href="${href}"${label ? ` aria-label="${esc(`${text}: ${label}`)}"` : ""}>${icon("spark")}${esc(text)}</a>`;
  if (ACTIVE.has(run.status)) return go("btn-quiet", RUN_STATE[run.status]);
  if (run.waiting) return go("btn-claude", suggestions(run.waiting), "/desk.html#waiting");
  if (run.status === "done") return go("btn-quiet", "Read Claude's answer");
  return "";
}

// Diagnose with Claude, or where the last diagnosis is (with Diagnose again once it has answered).
export function diagnoseHtml(target, run) {
  const attrs = target.alertId ? `data-al-diag="${esc(target.alertId)}"` : `data-al-diag-ad="${esc(target.adId)}"`;
  const chip = runChip(run);
  if (run && ACTIVE.has(run.status)) return chip;
  const again = Boolean(chip);
  return `${chip}<button type="button" class="btn ${again ? "" : "btn-claude-outline"}" ${attrs}>${again ? "" : icon("spark")}${again ? "Diagnose again" : "Diagnose with Claude"}</button>`;
}

// "Snoozed until Fri, Nov 14 · Eugene", with Wake it now for admins.
export function snoozeChip(s, { canWake = false, alertId = null } = {}) {
  if (!s) return "";
  return `<p class="al-snoozed">${icon("clock")}<span>${esc(s.words)}${s.by ? ` · ${esc(s.by)}` : ""}</span>${canWake ? `<button type="button" class="link-btn" data-al-wake="${esc(alertId)}">Wake it now</button>` : ""}</p>`;
}

// The buttons beside Open on an alert: Diagnose (or its run), Got it…, Done. `actions` come from the server.
export function alertButtons(item) {
  const acts = item.actions || [];
  return [
    acts.includes("diagnose") ? diagnoseHtml({ alertId: item.alert_id }, item.diagnose) : "",
    acts.includes("snooze") ? `<button type="button" class="btn" data-al-snooze="${esc(item.alert_id)}" aria-label="Got it: snooze this alert">Got it…</button>` : "",
    acts.includes("done") ? `<button type="button" class="btn" data-done="${esc(item.alert_id)}">Done</button>` : "",
  ].join("");
}

export async function wake(alertId, after) {
  try {
    await api(`/api/alerts/${encodeURIComponent(alertId)}/snooze`, { method: "DELETE" });
    toast("Woken: it's back in Needs action");
    after && after();
  } catch (err) { toast(err.message, "bad"); }
}

export async function snoozeDialog(item, after) {
  const choice = await confirmDialog({
    title: "Got it. When should this come back?", extra: "al-choice", confirm: null,
    body: `<p class="muted">${esc(item.title)}</p>`,
    choices: { submitOnPick: true, options: (item.choices || []).map((c) => ({ value: c.mode === "days" ? `days:${c.days}` : "worse", label: c.label, hint: c.hint })) },
  });
  if (!choice) return null;
  const body = choice === "worse" ? { mode: "worse" } : { mode: "days", days: Number(choice.split(":")[1]) };
  try {
    const r = await api(`/api/alerts/${encodeURIComponent(item.alert_id)}/snooze`, { method: "POST", body });
    const s = r.snooze || {};
    // Another admin got there first: theirs stands, and there is nothing of ours to undo.
    if (r.already) { toast(`Already snoozed${s.by ? ` by ${s.by}` : ""}: ${(s.words || "Snoozed").replace(/^Snoozed /, "")}`); after && after(); return s; }
    toast(s.mode === "worse" ? "Snoozed: you'll hear if it gets worse" : (s.words || "Snoozed").split(",")[0], "", { undo: () => wake(item.alert_id, after) });
    after && after();
    return s;
  } catch (err) { toast(err.message, "bad"); return null; }
}

// One run per problem: a second Diagnose points at the run already filed.
function already(taskId) {
  toast("Claude is already on this one.", "", taskId ? { open: `/desk.html#r/${taskId}` } : {});
}

export async function diagnoseDialog(target, after) {
  const q = target.alertId ? `alert_id=${encodeURIComponent(target.alertId)}` : `ad_id=${encodeURIComponent(target.adId)}`;
  let d;
  try { d = await api(`/api/diagnose/draft?${q}`); } catch (err) { toast(err.message, "bad"); return null; }
  if (d.run && ACTIVE.has(d.run.status)) { already(d.run.id); after && after(); return d.run.id; }
  const mac = !d.bridge.has_key ? "Set up your Mac on the Claude page first; this waits until then."
    : !d.bridge.online ? "Your Mac is offline, so this waits until it's back." : "";
  const text = await confirmDialog({
    title: "Diagnose with Claude", claude: true, wide: true, confirm: "Send to Claude", extra: "dg-form",
    body: `<p>Claude reads your ads on your Mac and tells you what's wrong and what to do. It changes nothing on Meta: any change comes back as a suggestion for you to accept or decline.</p>
      <p class="muted small">Uses the “${esc(d.playbook.label)}” checklist.</p>${mac ? `<p class="note">${esc(mac)}</p>` : ""}`,
    field: {
      label: "What Claude will look at", rows: 8, value: d.prompt,
      hint: (v) => `<span class="dg-count${v.length > MAX ? " bad-text" : ""}">${v.length.toLocaleString()} / ${MAX.toLocaleString()}</span>`,
      validate: (v) => (!v.trim() ? "Tell Claude what you'd like" : v.length > MAX ? "Keep it under 4,000 characters" : null),
    },
  });
  if (text === false) return null;
  try {
    const r = await api("/api/diagnose", { method: "POST", body: { ...(target.alertId ? { alert_id: Number(target.alertId) } : { ad_id: target.adId }), prompt: text } });
    if (r.already) already(r.task_id); else toast("Sent to Claude. Follow it on the Claude page.");
    after && after();
    return r.task_id;
  } catch (err) { toast(err.message, "bad"); return null; }
}

// Phones: one ⋯ per Today row holds Diagnose with Claude (or its run), Got it… and Done, so rows keep one button.
export function moreButton(item) {
  const acts = item.actions || [];
  if (!["diagnose", "snooze", "done"].some((a) => acts.includes(a))) return "";
  return `<button type="button" class="btn al-more" data-al-more="${esc(item.alert_id)}" aria-label="More for ${esc(item.title)}">${icon("dots")}</button>`;
}

async function moreMenu(item, after) {
  const acts = item.actions || [];
  const run = item.diagnose;
  const options = [];
  if (acts.includes("diagnose")) {
    if (run && (ACTIVE.has(run.status) || run.waiting || run.status === "done")) {
      options.push({ value: "run", label: ACTIVE.has(run.status) ? RUN_STATE[run.status] : run.waiting ? suggestions(run.waiting) : "Read Claude's answer", hint: "Open it on the Claude page." });
    }
    const answered = run && (run.waiting || run.status === "done");
    if (!run || !ACTIVE.has(run.status)) options.push({ value: "diagnose", label: answered ? "Diagnose again" : "Diagnose with Claude", hint: "Claude looks into it on your Mac. Nothing changes on Meta." });
  }
  if (acts.includes("snooze")) options.push({ value: "snooze", label: "Got it…", hint: "Stop the messages about this for a while." });
  if (acts.includes("done")) options.push({ value: "done", label: "Done", hint: "You've dealt with it: it moves to For your information." });
  const pick = await confirmDialog({ title: item.title, extra: "al-choice", confirm: null, choices: { submitOnPick: true, options } });
  if (pick === "run") location.href = run.waiting ? "/desk.html#waiting" : `/desk.html#r/${run.id}`;
  if (pick === "diagnose") diagnoseDialog({ alertId: item.alert_id }, after);
  if (pick === "snooze") snoozeDialog(item, after);
  if (pick === "done") done(item.alert_id, null, after);
}

// Done on an event that waits for a person (an outside budget change that broke a money rule): it is read and
// moves to For your information.
async function done(alertId, btn, after) {
  if (btn) btn.disabled = true;
  try {
    await api(`/api/alerts/${encodeURIComponent(alertId)}/done`, { method: "POST", body: {} });
    await api("/api/inbox/read", { method: "POST", body: { keys: [`alert:${alertId}`] } });
    toast("Done: it moves to For your information");
    after && after();
  } catch (err) { toast(err.message, "bad"); if (btn) btn.disabled = false; }
}

// One click handler for a list of alert items (`find(alertId)` returns the item).
export function wireAlerts(root, find, after) {
  root.addEventListener("click", (e) => {
    const t = e.target.closest("[data-al-snooze], [data-al-wake], [data-al-diag], [data-al-diag-ad], [data-al-more], [data-done]");
    if (!t || !root.contains(t)) return;
    e.preventDefault();
    if (t.dataset.alWake) { wake(t.dataset.alWake, after); return; }
    if (t.dataset.done) { done(t.dataset.done, t, after); return; }
    if (t.dataset.alDiagAd) { diagnoseDialog({ adId: t.dataset.alDiagAd }, after); return; }
    const item = find(Number(t.dataset.alSnooze || t.dataset.alDiag || t.dataset.alMore));
    if (!item) return;
    if (t.dataset.alSnooze) snoozeDialog(item, after);
    else if (t.dataset.alDiag) diagnoseDialog({ alertId: item.alert_id }, after);
    else moreMenu(item, after);
  });
}
