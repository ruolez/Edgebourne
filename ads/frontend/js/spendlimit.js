// The ad account's spending limit (FU-B): one set of words and confirmations for the Accept sheet, a suggestion
// accepted from its card, and Settings → Targets. Plans come from the server's fresh read of Meta.
import { confirmDialog, esc } from "./ui.js";
import { money, moneyWhole } from "./format.js";

export const limitMoney = (cents) => (cents == null ? "no limit" : money(cents, { exact: true }));
const moreDays = (n) => `${n} more day${n === 1 ? "" : "s"}`;

// "Spent so far $41.20 · at about $20 a day the ads run about 7 more days (now 5)."
export function paceWords(p) {
  const spent = `Spent so far ${limitMoney(p.spent)}`;
  if (p.remove) return `${spent} · after this only each campaign's daily budget limits spending.`;
  if (p.days_after == null) return `${spent} · not enough recent spend to tell how long it lasts.`;
  return `${spent} · at about ${moneyWhole(p.rate)} a day the ads run about ${moreDays(p.days_after)}${p.days_now == null ? "" : ` (now ${p.days_now})`}.`;
}

// The Accept sheet's line (HTML).
export function limitLine(p) {
  const what = p.remove ? "Removes the account spending limit. Meta then has no ceiling on total spend."
    : `Account spending limit: <del>${limitMoney(p.from)}</del> → <ins>${limitMoney(p.to)}</ins>`;
  return `${what}<small class="sl-pace">${esc(paceWords(p))}</small>`;
}

// The body of the confirmation: old → new from the read just now, spent so far and how long it lasts.
export function limitBody(p) {
  return `<p>The spending limit of <b>${esc(p.name || "the ad account")}</b> on Meta, read just now:</p>
    <p class="big-change"><del>${limitMoney(p.from)}</del> → <ins>${limitMoney(p.to)}</ins></p>
    <p class="muted small">${esc(paceWords(p))}</p>
    <p class="muted small">Meta pauses every ad once this much has been spent in total. Right after the change the console reads it back to check Meta stored exactly this.</p>`;
}

// Removing it is always a second, separate yes (never part of a sheet of several).
export const confirmRemove = () => confirmDialog({
  title: "Remove the spending limit?",
  body: "<p>Your ads could then spend without an account ceiling. Each campaign's daily budget still applies.</p>",
  confirm: "Remove the limit", danger: true,
});

// More than doubling it works almost like removing it, so it's a second, separate yes too (never on a sheet of several).
export const confirmBig = (p) => confirmDialog({
  title: "Raise the limit this much?",
  body: `<p>This more than doubles the account spending limit: <b>+${esc(limitMoney(p.to - (p.from || 0)))}</b>, to ${esc(limitMoney(p.to))}${p.days_after == null ? "" : `, about ${moreDays(p.days_after)} at the current pace`}.</p>
    <p class="muted small">A limit this high hardly stops spending. Each campaign's daily budget still applies.</p>`,
  confirm: `Raise it to ${limitMoney(p.to)}`, danger: true,
});

// A paused note's words: what Meta stored, what was put back.
export function pausedWords(b) {
  const on = b.at ? ` on ${new Date(b.at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}` : "";
  if (b.unread) return `Limit changes are paused:${on} Meta didn't answer when the console read the limit back after sending ${limitMoney(b.wanted_cents)}. Check the limit in Ads Manager.`;
  const got = b.got_raw != null ? `an amount the console can't read (${b.got_raw})` : limitMoney(b.got_cents);
  return `Limit changes are paused:${on} Meta stored ${got} when we sent ${limitMoney(b.wanted_cents)}. We put back ${limitMoney(b.restored_cents)}${b.restored ? "" : " (not confirmed)"}. Check the limit in Ads Manager.`;
}
