// From research to a new ad (UX-AUDIT 9.5): "Make something like this" on one saved competitor ad, "Write a brief" on
// several. The server drafts the request from everything saved about them, trimmed to fit (GET /api/swipes/brief); it
// opens here to edit, goes to Claude as a new conversation of kind "creative" and that conversation opens. Claude's ads
// come back as suggestions: nothing reaches Meta until one is accepted, the usual way.
import { api } from "./api.js";
import { confirmDialog, esc, toast } from "./ui.js";
import { count } from "./format.js";

export const BRIEF_MAX = 10;  // swipes.BRIEF_MAX

export async function askForBrief(ids, as = "brief") {
  let d;
  try { d = await api(`/api/swipes/brief?ids=${ids.map(encodeURIComponent).join(",")}&as=${as === "like" ? "like" : "brief"}`); }
  catch (err) { toast(err.message, "bad"); return false; }
  const limit = d.limit;
  const tooLong = (v) => v.trim().length > limit;
  let text = d.prompt;
  let problem = "";
  for (;;) {
    const sent = await confirmDialog({
      title: as === "like" ? "Make something like this" : `Write a brief from ${count(d.count)} saved ad${d.count === 1 ? "" : "s"}`,
      body: `<p>Claude gets this as a new conversation. Change anything first: what to keep, what to avoid, which offer.</p>
        <p>Its ads come back as suggestions. Nothing goes to Meta until you accept one.</p>
        ${d.left_out ? `<p>${esc(count(d.left_out))} more you picked were left out to keep it short.</p>` : ""}
        ${problem ? `<p class="note bad" role="alert">Not sent: ${esc(problem)}</p>` : ""}`,
      field: {
        label: "What Claude gets", value: text, rows: 12,
        hint: (v) => `<span class="${tooLong(v) ? "bad-text" : ""}">${count(v.trim().length)} of ${count(limit)} characters</span>`,
        validate: (v) => (!v.trim() ? "Write what you'd like Claude to make"
          : tooLong(v) ? `Keep it under ${count(limit)} characters: it has ${count(v.trim().length)}` : null),
      },
      confirm: "Send to Claude", claude: true, wide: true,
    });
    if (sent === false) return false;
    text = sent.trim();
    try {
      const task = await api("/api/desk/tasks", { method: "POST", body: { kind: "creative", prompt: text } });
      location.href = `/desk.html#r/${task.id}`;
      return true;
    } catch (err) {
      problem = err.message;  // the dialog opens again with the words as they were, saying why
    }
  }
}
