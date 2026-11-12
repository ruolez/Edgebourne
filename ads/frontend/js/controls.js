// On/off switches and budget changes, with a confirmation that names the change.
import { api } from "./api.js";
import { confirmDialog, esc, toast } from "./ui.js";
import { money, currencySymbol } from "./format.js";

const WHAT = { campaign: "campaign", adset: "ad set", ad: "ad" };

// What turning something on can spend, from the server's fresh read: a daily budget, a lifetime budget
// (the total until its end date), or both. Every amount shown is echoed back as the confirmation.
export function spendWords(spend) {
  if (!spend || spend.idle) return spend && spend.idle ? " (nothing inside it is on yet, so it spends nothing until something is)" : "";
  const parts = [];
  if (spend.daily_cents) parts.push(`up to <b>${money(spend.daily_cents, { exact: true })} a day</b>`);
  if (spend.lifetime_cents) {
    const until = spend.end_time ? ` until ${esc(new Date(spend.end_time).toLocaleDateString(undefined, { month: "short", day: "numeric" }))}` : "";
    parts.push(`up to <b>${money(spend.lifetime_cents, { exact: true })} in total</b>${until} (a lifetime budget)`);
  }
  return parts.length ? ` and spends ${parts.join(" plus ")} from ${esc(spend.where)}` : "";
}

export function spendBody(spend) {
  const body = {};
  if (spend && spend.daily_cents) body.confirm_daily_cents = spend.daily_cents;
  if (spend && spend.lifetime_cents) body.confirm_lifetime_cents = spend.lifetime_cents;
  return body;
}

export async function toggleEntity(btn, after) {
  const [level, id] = btn.dataset.toggle.split(":");
  return changeStatus({ level, id, name: btn.dataset.name, turnOn: btn.getAttribute("aria-checked") !== "true" }, after, btn);
}

// The one way anything is turned on or off: the same confirmation from a switch or a plain button (`btn`
// is disabled while it runs).
export async function changeStatus({ level, id, name, turnOn }, after, btn = document.createElement("button")) {
  let spend = null;
  if (turnOn) {
    // Turning on spends money: show the daily budget Meta has right now (the server checks it was seen).
    btn.disabled = true;
    try { spend = await api(`/api/ads/${level}/${id}/spend`); }
    catch (err) { toast(err.message, "bad"); btn.disabled = false; return; }
    btn.disabled = false;
  }
  const daily = spend && spend.daily_cents;
  const ok = await confirmDialog({
    title: `${turnOn ? "Turn on" : "Turn off"} “${name}”?`,
    body: turnOn
      ? `<p>The ${WHAT[level]} starts delivering${spendWords(spend)}.${level !== "ad" ? " Ads inside it that are on start too." : ""}</p>${daily ? `<p class="muted small">About ${money(daily * 30)} a month. Meta may spend up to 75% more on a busy day.</p>` : ""}`
      : `<p>The ${WHAT[level]} stops showing within a few minutes${level !== "ad" ? ", and every ad inside it stops with it" : ""}. Nothing is deleted; you can turn it back on any time.</p>`,
    confirm: turnOn ? "Turn on" : "Turn off", danger: !turnOn,
  });
  if (!ok) return;
  btn.disabled = true;
  try {
    await api(`/api/ads/${level}/${id}/status`, { method: "POST", body: { status: turnOn ? "ACTIVE" : "PAUSED", ...spendBody(spend) } });
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
    // The +20% warning is in the hint; confirming with it showing is the knowing yes the server asks for.
    field: {
      label: "New daily budget", prefix: currencySymbol(), suffix: "/day", inputmode: "decimal", value: now.toFixed(2),
      validate: (v) => {
        const n = Number(String(v).replace(/[$,\s]/g, ""));
        if (!Number.isFinite(n) || n < 1) return `Enter at least ${money(100)}`;
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
  const big = (cents - current) / current > 0.2;
  try {
    await api(`/api/ads/${level}/${id}/budget`, { method: "POST", body: { daily_budget_cents: cents, from_cents: current, accept_big: big } });
    toast(`Budget is now ${money(cents, { exact: true })}/day`);
    after();
  } catch (err) { toast(err.message, "bad"); }
}

