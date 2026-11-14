// Settings' own map: every section under what it is for. The list beside Settings and Team is drawn from it, and
// so are the overview's rows, so the two can't drift apart.
// id = the section's page in the address (/settings.html#<id>); `owner` = whole-console settings only the console's
// owner opens; `href` = a page of its own (Team); `title` = the full name where the group's name isn't beside it.
import { esc } from "./ui.js";

export const SET_GROUPS = [
  ["Account", [
    { id: "targets", label: "Targets and limits", desc: "Cost targets, the highest daily budget, the spending limit" },
    { id: "alerts", label: "Alerts", desc: "What the console warns about, and what is snoozed" },
    { id: "prefs", label: "Preferences", desc: "Automatic refresh, A/B tests on Meta" },
  ]],
  ["Leads", [
    { id: "replies", label: "Replies", title: "Lead replies", desc: "Email templates, the automatic reply, your booking link" },
    { id: "lead-quality", label: "Quality", title: "Lead quality", desc: "Repeats counted once, junk flagged" },
    { id: "crm", label: "Stages to Meta", title: "Lead stages to Meta", desc: "Tell Meta which leads became clients" },
  ]],
  ["People", [
    { id: "team", label: "Team", href: "/team.html", desc: "Teammates and clients, and what each can open" },
    { id: "reports-panel", label: "Clients and reports", desc: "The report email, and what clients may do" },
    { id: "accounts-panel", label: "Accounts", owner: true, desc: "Every business this console runs ads for" },
  ]],
  ["Connections", [
    { id: "meta", label: "Meta", desc: "The Page and ad account, and the app that receives leads" },
    { id: "am-link", label: "Ads Manager link", desc: "Drafts and Meta's extra insights, through your Mac" },
    { id: "tracking", label: "Tracking health", desc: "What Meta's dataset receives, numbers vs Ads Manager" },
    { id: "email", label: "Email and Telegram", owner: true, desc: "Where alerts and reports are sent from" },
  ]],
  ["History", [
    { id: "activity-panel", label: "Activity", desc: "Every change made here, by anyone" },
  ]],
];

export const setItems = (owner) => SET_GROUPS.map(([name, items]) => [name, items.filter((i) => owner || !i.owner)]).filter(([, items]) => items.length);
export const setItem = (id) => SET_GROUPS.flatMap(([, items]) => items).find((i) => i.id === id) || null;
// On Settings itself a section is a place on the page (#id); from Team it is a link back to Settings.
export const setHref = (item, onSettings) => item.href || `${onSettings ? "" : "/settings.html"}#${item.id}`;

export function settingsNavHtml({ owner, current, onSettings }) {
  const link = (i) => `<a href="${setHref(i, onSettings)}" data-set="${i.id}" ${i.id === current ? 'aria-current="page"' : ""}>${esc(i.label)}</a>`;
  return `<a href="${onSettings ? "#overview" : "/settings.html"}" data-set="overview" ${current === "overview" ? 'aria-current="page"' : ""}>Overview</a>${
    setItems(owner).map(([name, items]) => `<span class="set-group">${esc(name)}</span>${items.map(link).join("")}`).join("")}`;
}
