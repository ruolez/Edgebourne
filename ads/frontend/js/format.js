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
export const RANGES = [["7", "Last 7 days"], ["14", "Last 14 days"], ["30", "Last 30 days"], ["mtd", "This month"], ["lastmonth", "Last month"]];
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
