// Claude page → Schedules: Claude's regular checks, each an ordinary run when it's due.
import { api } from "./api.js";
import { esc, skeleton, switchHtml, toast, when } from "./ui.js";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const LAST = { done: "finished", failed: "didn't finish", queued: "waiting for your Mac", claimed: "starting", running: "running", cancelled: "cancelled" };

function ruleForm(s) {
  const r = s.rule;
  const opt = (v, label, cur) => `<option value="${v}" ${String(cur) === String(v) ? "selected" : ""}>${label}</option>`;
  return `<form class="sched-rule" data-rule="${s.id}" novalidate>
      <div class="field"><label for="every-${s.id}">How often</label><select class="input" id="every-${s.id}" name="every">
        ${opt("day", "Every day", r.every)}${opt("days", "Every few days", r.every)}${opt("week", "Once a week", r.every)}${opt("month", "Once a month", r.every)}</select></div>
      <div class="field" data-for="days"><label for="days-${s.id}">Every</label><select class="input" id="days-${s.id}" name="days">
        ${[2, 3, 4, 5, 7, 14].map((d) => opt(d, `${d} days`, r.days || 3)).join("")}</select></div>
      <div class="field" data-for="week"><label for="weekday-${s.id}">On</label><select class="input" id="weekday-${s.id}" name="weekday">
        ${DAYS.map((d, i) => opt(i, d, r.weekday ?? 0)).join("")}</select></div>
      <div class="field" data-for="month"><label for="monthday-${s.id}">On day</label><select class="input" id="monthday-${s.id}" name="monthday">
        ${Array.from({ length: 28 }, (_, i) => opt(i + 1, String(i + 1), r.monthday || 1)).join("")}</select></div>
      <div class="field"><label for="at-${s.id}">At</label><input class="input" type="time" id="at-${s.id}" name="at" value="${esc(r.at)}" step="300"></div>
      <div class="field sched-save"><button class="btn" type="submit">Save time</button></div>
    </form>`;
}

function showFields(form) {
  const every = form.every.value;
  form.querySelectorAll("[data-for]").forEach((f) => { f.hidden = f.dataset.for !== (every === "days" ? "days" : every); });
}

function card(s) {
  const last = s.last_task_id
    ? `Last run ${when(s.last_run_at || "")}: ${LAST[s.last_status] || s.last_status || "removed"}${s.last_status === "done" && s.last_summary ? `. ${esc(s.last_summary)}` : ""} <a href="#runs" data-goto-run="${s.last_task_id}">See it</a>`
    : "Hasn't run yet.";
  return `<article class="panel sched" id="sched-${s.id}">
    <div class="panel-body stack tight">
      <div class="sched-head">
        <div><h3>${esc(s.name)}</h3><p class="muted">${esc(s.about)}</p></div>
        ${switchHtml(s.enabled, `data-sched-toggle="${s.id}"`, `${s.name} on or off`)}
      </div>
      <p class="sched-when"><b>${esc(s.when)}</b>${s.enabled && s.next_run_at ? ` · next ${when(s.next_run_at)}` : s.enabled ? "" : " · off"}</p>
      <p class="small muted">${last}${s.skipped ? ` Skipped ${s.skipped} time${s.skipped === 1 ? "" : "s"} because the run before was still waiting for your Mac.` : ""}</p>
      <details class="sched-edit"><summary>Change when it runs</summary>${ruleForm(s)}</details>
      <div class="row"><button class="btn btn-quiet" type="button" data-sched-run="${s.id}">Run it now</button></div>
    </div>
  </article>`;
}

export function schedulesView(list, mac) {
  if (!list) return `<section class="panel"><div class="panel-body">${skeleton()}</div></section>`;
  const on = list.filter((s) => s.enabled).length;
  const intro = `<p class="muted sched-intro">Claude runs these by itself on your Mac, with the same read-only access as when you ask. It never changes anything: what it finds lands here as a report, and ideas wait for your yes.${mac && !mac.online ? " <b>Your Mac is offline</b>, so runs wait until it's back." : ""} When one finishes you get a message (Telegram if you connected it, otherwise email).</p>`;
  return intro + list.map(card).join("") + (on ? "" : '<p class="muted small">All are off. Switch on the ones you want.</p>');
}

export function wireSchedules(root, reload) {
  root.addEventListener("click", async (e) => {
    const t = e.target.closest("[data-sched-toggle]");
    const r = e.target.closest("[data-sched-run]");
    if (!t && !r) return;
    const btn = t || r;
    btn.disabled = true;
    try {
      if (t) {
        const on = t.getAttribute("aria-checked") !== "true";
        await api(`/api/desk/schedules/${t.dataset.schedToggle}`, { method: "PATCH", body: { enabled: on } });
        toast(on ? "Switched on" : "Switched off");
      } else {
        await api(`/api/desk/schedules/${r.dataset.schedRun}/run`, { method: "POST" });
        toast("Started. Your Mac picks it up in a moment.");
      }
      await reload();
    } catch (err) { toast(err.message, "bad"); } finally { btn.disabled = false; }
  });
  root.addEventListener("change", (e) => { const f = e.target.closest("form[data-rule]"); if (f && e.target.name === "every") showFields(f); });
  root.addEventListener("toggle", (e) => { const f = e.target.querySelector?.("form[data-rule]"); if (f) showFields(f); }, true);
  root.addEventListener("submit", async (e) => {
    const f = e.target.closest("form[data-rule]");
    if (!f) return;
    e.preventDefault();
    const every = f.every.value;
    const rule = { every, at: f.at.value, days: Number(f.days.value), weekday: Number(f.weekday.value), monthday: Number(f.monthday.value) };
    try {
      await api(`/api/desk/schedules/${f.dataset.rule}`, { method: "PATCH", body: { rule } });
      toast("Saved");
      await reload();
    } catch (err) { toast(err.message, "bad"); }
  });
}
