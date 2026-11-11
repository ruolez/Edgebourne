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
