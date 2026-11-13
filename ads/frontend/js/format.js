// Number and date formatting shared by every page.
// The ad account's currency (agency mode: each account has its own); ui.boot sets it from /api/auth/me.
let CURRENCY = "USD";
export const setCurrency = (code) => { if (/^[A-Z]{3}$/.test(code || "")) CURRENCY = code; };
export const currencySymbol = () => {
  const part = (0).toLocaleString(undefined, { style: "currency", currency: CURRENCY }).replace(/[\d.,\s\u00a0]/g, "");
  return part || CURRENCY;
};
export const money = (cents, { exact = false } = {}) => {
  const v = (cents || 0) / 100;
  const digits = exact || Math.abs(v) < 100 ? 2 : 0;
  return v.toLocaleString(undefined, { style: "currency", currency: CURRENCY, minimumFractionDigits: digits, maximumFractionDigits: digits });
};
export const moneyWhole = (cents) => ((cents || 0) / 100).toLocaleString(undefined, { style: "currency", currency: CURRENCY, minimumFractionDigits: 0, maximumFractionDigits: 0 });
export const count = (n) => Number(n || 0).toLocaleString();
export const per = (cents, n) => (n ? money(cents / n, { exact: true }) : "—");
export const pct = (a, b) => (b ? `${((a / b) * 100).toFixed(2)}%` : "—");
export const dayLabel = (iso) => new Date(iso + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" });
export const plural = (n, word, many = word + "s") => `${count(n)} ${n === 1 ? word : many}`;
// The ad account's clock (FU-C): every time on screen reads the account's time zone, with a short zone tag ("PST")
// when the browser's own zone differs, so a laptop or phone set elsewhere shows the same times Eugene works by.
export const acctZone = () => (window.ebadsMe && window.ebadsMe.account && window.ebadsMe.account.tz) || undefined;
const offsetOf = (zone, d) => {
  try {
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: zone, hourCycle: "h23", year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric" })
      .formatToParts(d).map((p) => [p.type, p.value]));
    return Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour % 24, +parts.minute) - Math.floor(d.getTime() / 60000) * 60000;
  } catch (e) { return 0; }
};
export const zoneDiffers = (d = new Date()) => Boolean(acctZone()) && offsetOf(acctZone(), d) !== offsetOf(undefined, d);
export const shortZone = (d = new Date()) => {
  try { return new Intl.DateTimeFormat("en-US", { timeZone: acctZone(), timeZoneName: "short" }).formatToParts(d).find((p) => p.type === "timeZoneName")?.value || ""; } catch (e) { return ""; }
};
export const zoneTag = (d = new Date()) => (zoneDiffers(d) ? ` ${shortZone(d)}` : "");
// "Los Angeles" for a hint: "Times are Los Angeles time".
export const zoneCity = () => (acctZone() || "").split("/").pop().replace(/_/g, " ");
const inZone = (opts) => ({ ...opts, timeZone: acctZone() });
// "2:41 PM" (+ " PST" when the browser's zone differs).
export const clock = (iso) => { const d = new Date(iso); return d.toLocaleTimeString(undefined, inZone({ hour: "numeric", minute: "2-digit" })) + zoneTag(d); };
// "9:40 PM PDT": always with the account's zone, for a deadline read on a phone set elsewhere (full access's end).
export const clockZone = (iso) => { const d = new Date(iso); const z = shortZone(d); return d.toLocaleTimeString(undefined, inZone({ hour: "numeric", minute: "2-digit" })) + (z ? ` ${z}` : ""); };
// The account's calendar day of a moment, "YYYY-MM-DD" (Today / Yesterday grouping, the booking dialog's day).
export const acctDay = (d = new Date()) => new Intl.DateTimeFormat("en-CA", { timeZone: acctZone(), year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
export const acctHour = (d = new Date()) => Number(new Intl.DateTimeFormat("en-US", { timeZone: acctZone(), hour: "numeric", hourCycle: "h23" }).format(d)) % 24;

// words.py twins (00-PLAN S1): "Nov 9", "Thu, Nov 12, 2:00 PM", "today" / "5 hours ago" / "1 day ago".
export const dayWords = (iso) => new Date(iso).toLocaleDateString(undefined, inZone({ month: "short", day: "numeric" }));
export const dayTimeWords = (iso) => { const d = new Date(iso); return d.toLocaleString(undefined, inZone({ weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })) + zoneTag(d); };
export function agoWords(iso, now = Date.now()) {
  const hours = Math.floor((now - new Date(iso).getTime()) / 3600000);
  if (hours < 1) return "today";
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}
// A Claude run started from an alert or Meta's advice, in the console's words (W1a).
export const RUN_STATE = { queued: "Waiting for your Mac", claimed: "Claude is on it", running: "Claude is on it" };
export const suggestions = (n) => plural(n, "suggestion");
// "Did it work?" (D3): the result of a change in the console's words (change_checks.OUTCOME says the same). Words carry
// the meaning; the tone only backs them up (green stays "delivering", so a good result is the neutral ok tone).
export const OUTCOME = {
  better: "Worked", lean_better: "Looks better, not sure yet", same: "No clear change", lean_worse: "Looks worse, not sure yet",
  worse: "Didn't help", too_early: "Too early to tell", waiting: "Not checked yet", on_target: "On target", over_target: "Over target",
  mixed: "Changed again too soon", no_compare: "Nothing to compare", stopped: "Off", not_running: "Not running yet",
};
export const outcomeWords = (state) => OUTCOME[state] || "";
export const OUTCOME_TONE = { better: "ok", lean_better: "ok", on_target: "ok", worse: "bad", lean_worse: "bad", over_target: "warn" };
// Change marks on the charts: the four kinds, in the console's words.
export const CHANGE_CATS = { money: "Budget", switch: "On/off", edit: "Edits", meta: "Meta" };

export const CTA_LABELS = {
  BOOK_TRAVEL: "Book now", SIGN_UP: "Sign up", LEARN_MORE: "Learn more", GET_QUOTE: "Get quote",
  APPLY_NOW: "Apply now", SUBSCRIBE: "Subscribe", DOWNLOAD: "Download", CONTACT_US: "Contact us",
};

// The console's one vocabulary (UX-AUDIT 9.2): every page names these things the same way, from here.
// Meta's "impressions" are Views, "reach" is People reached, Claude's proposals are Suggestions you Accept,
// and the work you start with Claude is a Conversation.
export const WORDS = {
  spend: "Spent", leads: "Leads", qualified: "Qualified leads", impressions: "Views", reach: "People reached",
  frequency: "Views per person", clicks: "Link clicks", cpl: "Cost per lead", cpql: "Cost per qualified lead",
  ctr: "Click rate", hook: "Hook rate", hold: "Hold rate", status: "Status",
  suggestion: "Suggestion", suggestions: "Suggestions", accept: "Accept", accepted: "Accepted",
  conversation: "Conversation", conversations: "Conversations",
};

// Follow-ups and booked calls (L1): a booked call is a "call" (never meeting or appointment), a next step a follow-up.
export const FOLLOW = {
  title: "Follow-up", booked: "Calls booked", cpb: "Cost per booked call", booked_col: "Booked", cpb_col: "Per booked call",
  booked_title: "Leads that booked a call, by the day the lead arrived", no_show: "No-show",
  due: [["", "Any follow-up"], ["today", "Due today"], ["overdue", "Overdue"], ["none", "No next step"], ["booked", "Calls booked"]],
};

// A lead's stages and lead quality (L2), in the words every page uses (Leads, Today, Inbox, Report). The server sends the
// same reasons with each lead (`reasons`); these let a list render before a lead loads.
export const STAGE_LABELS = { new: "New", contacted: "Contacted", qualified: "Qualified", won: "Won", lost: "Lost" };
export const LOST_REASONS = {
  no_response: "No response", not_fit: "Not a fit", too_small: "Too small", price: "Price",
  went_elsewhere: "Went with someone else", spam: "Spam or fake", duplicate: "Duplicate", other: "Other",
};
// [pill class, words] for a lead row's lead-quality chips.
export const LEAD_CHIPS = {
  repeat: ["", "Repeat"], asked: ["", (n) => `Asked ${n}×`], before: ["info", "Asked before"], junk: ["warn", "Looks like junk"],
  page: ["", "From the Page"], test: ["", "Test"],
};

// Plain explanations of Meta's own terms, shown next to the term wherever it appears.
export const EXPLAIN = {
  impressions: "How many times the ad was shown, counting repeats.",
  reach: "Different people who saw it at least once.",
  frequency: "Views ÷ people reached: how often the same person saw it.",
  ctr: "Of the views, the share that clicked the link.",
  hook: "Of the video's views, the share that watched at least 3 seconds: how well the opening stops the scroll.",
  hold: "Of the people who watched 3 seconds, the share who kept watching to the end (or 15 seconds).",
  advantage_audience: "Advantage+ audience lets Meta show the ad to people outside the ages and places you set when it expects cheaper results there. Anything you mark as a hard limit stays a limit.",
  advantage_placements: "Advantage+ placements: Meta puts the ad wherever it costs least (Facebook, Instagram, Messenger and its partner apps), so you don't have to pick.",
  advantage_creative: "Advantage+ creative: small changes Meta may make to an ad on its own for each person, like brightness, music or where the text sits. You choose which ones are allowed.",
  learning: "Learning: Meta is still finding out who responds, so results swing for a few days. It settles after about 50 results in a week.",
  learning_limited: "Learning limited: too few results for Meta to settle (about 50 a week is the goal). Fewer ad sets, a bigger budget or a broader audience usually help; avoid frequent edits.",
  swipe_file: "Swipe file: competitor ads you saved to learn from. Claude can turn one into an idea for your own ad.",
};
export const explain = (key) => EXPLAIN[key] || "";

// The date ranges every page offers, and the one picker that shows them.
// Today and the ranges that reach today show today so far (FU-C); pages whose view needs whole days keep JUDGED_RANGES.
export const RANGES = [["today", "Today"], ["7", "Last 7 days"], ["14", "Last 14 days"], ["30", "Last 30 days"], ["mtd", "This month"], ["lastmonth", "Last month"]];
export const JUDGED_RANGES = RANGES.filter(([k]) => k !== "today");
// One date range for Ads, Campaign, Ad set, Ad, Compare and Results: the last one picked in this browser.
// A page's own ?range= still wins (a shared link opens on its dates); picking one remembers it for the rest.
const RANGE_KEY = "ebads-range";
export function sharedRange(fallback = "7", allowed = RANGES) {
  let r = null;
  try { r = localStorage.getItem(RANGE_KEY); } catch (e) { /* storage off */ }
  return allowed.some(([k]) => k === r) ? r : fallback;
}
export function rememberRange(r) {
  if (!RANGES.some(([k]) => k === r)) return;
  try { localStorage.setItem(RANGE_KEY, r); } catch (e) { /* storage off */ }
}
// The campaign picked last on Results or Compare, in this tab only ("" = all campaigns). Insights' tabs open on it.
const CAMPAIGN_KEY = "ebads-campaign";
export function sharedCampaign() {
  try { return sessionStorage.getItem(CAMPAIGN_KEY) || ""; } catch (e) { return ""; }
}
export function rememberCampaign(id) {
  try { if (id) sessionStorage.setItem(CAMPAIGN_KEY, id); else sessionStorage.removeItem(CAMPAIGN_KEY); } catch (e) { /* storage off */ }
}
const escText = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const rangeSelect = (id, value, ranges = RANGES, label = "Dates") =>
  `<select class="input tool" id="${id}" aria-label="${escText(label)}">${ranges.map(([k, l]) => `<option value="${k}" ${String(k) === String(value) ? "selected" : ""}>${escText(l)}</option>`).join("")}</select>`;

// Meta's effective_status → [pill class, words people use]. The one status vocabulary of the console.
export const STATUS = {
  ACTIVE: ["ok", "Delivering"], PAUSED: ["", "Off"], CAMPAIGN_PAUSED: ["", "Off (campaign is off)"],
  ADSET_PAUSED: ["", "Off (ad set is off)"], IN_PROCESS: ["warn", "In review"], PENDING_REVIEW: ["warn", "In review"],
  PREAPPROVED: ["ok", "Approved, starts on schedule"], DISAPPROVED: ["bad", "Rejected"], WITH_ISSUES: ["bad", "Has issues"],
  ARCHIVED: ["", "Archived"], PENDING_BILLING_INFO: ["bad", "Needs billing"], DELETED: ["", "Deleted"],
};
export const REVIEW_STATES = ["IN_PROCESS", "PENDING_REVIEW"];
export const PROBLEM_STATES = ["DISAPPROVED", "WITH_ISSUES", "PENDING_BILLING_INFO"];
// An ad set's learning phase, in words: LEARNING / SUCCESS / FAIL (Ads Manager's "Learning limited").
export const LEARNING = { LEARNING: ["info", "Learning"], FAIL: ["warn", "Learning limited"] };
export const statusOf = (s) => STATUS[s] || ["", (s || "Unknown").replace(/_/g, " ").toLowerCase()];
// The one status pill: colour, dot and word (never colour alone). `fallback` names a missing status.
export const statusPill = (s, fallback = "Unknown") => {
  const [cls, label] = s ? statusOf(s) : ["", fallback];
  return `<span class="pill ${cls}">${escText(label)}</span>`;
};

// Where every number comes from (D1): the line under a page's figures, Meta's lead count next to the leads received,
// and the Numbers vs Ads Manager check. One wording everywhere (00-PLAN §4: Received, Matches / Differs).
export function syncedWords(iso, now = new Date()) {
  const d = new Date(iso);
  return acctDay(d) === acctDay(now) ? clock(iso) : `${dayWords(iso)}, ${clock(iso)}`;
}
export function sinceWords(iso, now = Date.now()) {
  const minutes = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)} h ago`;
  return agoWords(iso, now);
}
export const NUMBERS = { match: "Matches", off: "Differs", unchecked: "Not checked", couldnt: "Couldn't check" };
// `today`: the page also shows today's live spend. Teammates and clients get the state of the check, never amounts.
// Days on screen older than the nightly check reads were never compared: say how many were.
const partlyChecked = (c) => c.days != null && c.checked_days != null && c.checked_days < c.days;
// The today part of a live figure (FU-C): read from Meta at …, or when Meta didn't answer, the last read that worked.
export function todayWords(t) {
  if (!t || !t.included) return "";
  if (t.skipped) return t.as_of ? `today's numbers are from ${clock(t.as_of)}` : "today's numbers not read yet";
  if (!t.read_ok) return t.as_of ? `today's numbers are from ${clock(t.as_of)} (Meta didn't answer)` : "today's numbers not read yet (Meta didn't answer)";
  return `today so far, Meta still counting${t.as_of ? ` (${clock(t.as_of)})` : ""}`;
}
export function sourceLine(src, { today = false } = {}) {
  const m = src && src.meta;
  if (!m) return "";
  const parts = ["From Meta"];
  const live = todayWords(src.today);
  if (m.behind && m.pulled_at) parts.push(`last synced ${sinceWords(m.pulled_at)}`, "numbers may be behind");
  else if (m.behind) parts.push("not synced yet");
  else if (m.synced_at && !live) parts.push(`synced ${syncedWords(m.synced_at)}`);
  if (live) parts.push(live);
  else if (today) parts.push("today so far, Meta still counting");
  parts.push(`complete days to ${dayLabel(m.complete_to)}`);
  const c = m.check;
  if (c && c.state === "off") parts.push(c.spend_off_cents == null ? "being checked again" : `differs from Ads Manager on ${plural(c.off_days, "day")}`);
  else if (c && c.old && c.checked_at) parts.push(`not checked against Ads Manager since ${dayWords(c.checked_at)}`);
  else if (c && c.state === "match") parts.push(partlyChecked(c) ? `${c.checked_days} of ${c.days} days checked: they match Ads Manager` : "matches Ads Manager");
  return parts.join(" · ");
}
export const leadsPair = (p) => (p && p.meta != null && p.received != null ? `Meta ${count(p.meta)} · Received ${count(p.received)}` : "");
const zoneName = () => {
  const tz = window.ebadsMe && window.ebadsMe.account && window.ebadsMe.account.tz;
  return tz ? ` (${tz.split("/").pop().replace(/_/g, " ")})` : "";
};
export function sourceHelp(src) {
  const c = src && src.meta && src.meta.check;
  const last = !c || !c.checked_at ? "Not checked against Ads Manager yet: the first check runs after 4 AM."
    : c.state === "off" ? `Last checked ${dayTimeWords(c.checked_at)}: ${c.spend_off_cents == null ? "a few days are being checked again" : `${plural(c.off_days, "day")} differ, and they are read again every night`}.`
      : partlyChecked(c) ? `Last checked ${dayTimeWords(c.checked_at)}: the ${plural(c.checked_days, "day")} checked match; the other ${plural(c.days - c.checked_days, "day")} are older than the nightly check reads.`
        : `Last checked ${dayTimeWords(c.checked_at)}: they match.`;
  return [
    src && src.today && src.today.included
      ? `Days in the ad account's time zone${zoneName()}. Today's numbers are read from Meta when the page opens (at most every minute and a half) and keep changing until the day is over; Meta reports some leads a day or two late. Verdicts and comparisons use complete days only.`
      : `Complete days only, in the ad account's time zone${zoneName()}. Today is partial and Meta reports some leads a day or two late.`,
    "Leads are what Meta counted under each ad set's attribution setting: on the day of the ad view or click, not the day the form arrived.",
    "Every night we read the last 28 days and last month again from Meta and compare them with Ads Manager's own totals.",
    last,
  ];
}
export const LEADS_PAIR_HELP = "Meta counts a lead on the day of the ad view or click. Received counts leads by the day they reached your leads list, and leaves out test entries; a person who filled the form twice counts once. A few can land on different days.";
export const SCOPE_NOTE = "The Ads Manager check covers the whole account.";
