// On/off switches and budget changes, with a confirmation that names the change.
import { api } from "./api.js";
import { confirmDialog, toast } from "./ui.js";
import { money } from "./format.js";

const WHAT = { campaign: "campaign", adset: "ad set", ad: "ad" };

export async function toggleEntity(btn, after) {
  const [level, id] = btn.dataset.toggle.split(":");
  const turnOn = btn.getAttribute("aria-checked") !== "true";
  const name = btn.dataset.name;
  const ok = await confirmDialog({
    title: `${turnOn ? "Turn on" : "Turn off"} “${name}”?`,
    body: turnOn
      ? `<p>The ${WHAT[level]} starts delivering again and spends from its budget.${level !== "ad" ? " Ads inside it that are on start too." : ""}</p>`
      : `<p>The ${WHAT[level]} stops showing within a few minutes${level !== "ad" ? ", and every ad inside it stops with it" : ""}. Nothing is deleted; you can turn it back on any time.</p>`,
    confirm: turnOn ? "Turn on" : "Turn off", danger: !turnOn,
  });
  if (!ok) return;
  btn.disabled = true;
  try {
    await api(`/api/ads/${level}/${id}/status`, { method: "POST", body: { status: turnOn ? "ACTIVE" : "PAUSED" } });
    toast(`${name} is ${turnOn ? "on" : "off"}`);
    after();
  } catch (err) { toast(err.message, "bad"); btn.disabled = false; }
}

export async function editBudget({ level, id, name, current }, after) {
  const now = current / 100;
  const value = await confirmDialog({
    title: `Daily budget for “${name}”`,
    body: `<p>Now <b>${money(current, { exact: true })} a day</b>. Meta may spend up to 75% more on a busy day and evens it out over the week.</p>`,
    confirm: "Change budget",
    field: {
      label: "New daily budget", prefix: "$", suffix: "/day", inputmode: "decimal", value: now.toFixed(2),
      validate: (v) => {
        const n = Number(String(v).replace(/[$,\s]/g, ""));
        if (!Number.isFinite(n) || n < 1) return "Enter at least $1";
        if (Math.round(n * 100) === current) return "That's the current budget";
        return null;
      },
      hint: (v) => {
        const n = Number(String(v).replace(/[$,\s]/g, ""));
        if (!Number.isFinite(n) || n <= 0) return "";
        const change = (n * 100 - current) / current;
        const words = `${change > 0 ? "+" : ""}${Math.round(change * 100)}% · about ${money(n * 100 * 30)} a month`;
        return change > 0.2 ? `${words}. <b>Bigger than +20%:</b> Meta may restart learning and results can wobble for a few days.` : words;
      },
    },
  });
  if (value === false) return;
  const cents = Math.round(Number(String(value).replace(/[$,\s]/g, "")) * 100);
  try {
    await api(`/api/ads/${level}/${id}/budget`, { method: "POST", body: { daily_budget_cents: cents } });
    toast(`Budget is now ${money(cents, { exact: true })}/day`);
    after();
  } catch (err) { toast(err.message, "bad"); }
}

