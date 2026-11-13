// FU-A All accounts: every account the person can see in one row (the owner: every open account; anyone else: their
// own), on the shared dates (GET /api/accounts/overview, figures from stored data in each account's own days).
// Each row opens that account; amounts are never added up across currencies.
import { api, startLoad } from "./api.js";
import { boot, emptyState, esc, onRefresh, pairNote, showLoadError, sourceNote } from "./ui.js";
import { RANGES, count, rangeSelect, rememberRange, sharedRange } from "./format.js";

const $ = (id) => document.getElementById(id);
let range = new URLSearchParams(location.search).get("range") || sharedRange("7");
if (!RANGES.some(([k]) => k === range)) range = "7";
let me = null;

// Each account in its own currency (format.money uses the open account's).
const money = (cents, currency) => {
  if (cents == null) return "—";
  const v = cents / 100;
  const digits = Math.abs(v) < 100 ? 2 : 0;
  return v.toLocaleString(undefined, { style: "currency", currency: currency || "USD", minimumFractionDigits: digits, maximumFractionDigits: digits });
};
const dash = (n, f) => (n ? f(n) : "—");
const openHref = (r) => `/home.html?acct=${r.id}`;
const needHref = (r) => `/inbox.html?acct=${r.id}&box=need`;
const connectLine = (r) => (r.connected ? "" : `<small class="ovw-off">Not connected to Meta yet${me.role === "admin" ? ` · <a href="/settings.html?acct=${r.id}#meta">Connect</a>` : ""}</small>`);
const capWords = (r) => (!r.cap ? "" : r.cap.limit_cents ? `${money(r.cap.spent_cents, r.currency)} of ${money(r.cap.limit_cents, r.currency)}` : "No limit");
const needWords = (r) => (r.needs_you ? `<a href="${needHref(r)}">${count(r.needs_you)}</a>` : "—");

function tableHtml(d, admin) {
  const head = `<tr><th scope="col">Account</th><th scope="col" class="num">Spent</th><th scope="col" class="num">Leads</th><th scope="col" class="num">Cost per lead</th>
    <th scope="col" class="num">Delivering</th><th scope="col" class="num">Needs you</th>${admin ? '<th scope="col" class="num">Spending limit</th>' : ""}</tr>`;
  const rows = d.rows.map((r, n) => `<tr class="ovw-row${r.id === d.current ? " is-here" : ""}" data-id="${r.id}" data-href="${openHref(r)}" tabindex="${n === 0 ? 0 : -1}"
    aria-label="Open ${esc(r.name)}" aria-describedby="ovw-keys">
    <th scope="row" class="ovw-name"><a class="ovw-open" href="${openHref(r)}" tabindex="-1">${esc(r.name)}</a>${r.id === d.current ? ' <span class="pill">Open now</span>' : ""}${connectLine(r)}${sourceNote(r.source)}</th>
    <td class="num ovw-spend" data-cents="${r.spend_cents}">${dash(r.spend_cents, (c) => money(c, r.currency))}</td>
    <td class="num ovw-leads">${dash(r.leads, count)}${pairNote({ meta: r.leads, received: r.received })}</td>
    <td class="num">${money(r.cpl_cents, r.currency)}</td>
    <td class="num">${dash(r.delivering, count)}</td>
    <td class="num ovw-need">${needWords(r)}</td>
    ${admin ? `<td class="num ovw-cap">${capWords(r) || "—"}</td>` : ""}</tr>`).join("");
  const t = d.totals;
  const foot = d.rows.length < 2 ? "" : t ? `<tfoot><tr><th scope="row">All accounts</th><td class="num">${money(t.spend_cents, d.rows[0].currency)}</td><td class="num">${count(t.leads)}</td>
      <td class="num">${money(t.cpl_cents, d.rows[0].currency)}</td><td colspan="${admin ? 3 : 2}"></td></tr></tfoot>` : "";
  return `<section class="panel scroll-x ovw-wide"><p class="sr-only" id="ovw-keys">Press Enter to open this account. Up and down arrows move between accounts.</p><table class="table ovw-table"><caption class="sr-only">Every account on the same dates</caption><thead>${head}</thead><tbody>${rows}</tbody>${foot}</table></section>`;
}

// Links can't sit inside the card's own link: what needs him and Connect go in a row under it.
function cardLinks(r) {
  const links = [];
  if (r.needs_you) links.push(`<a class="ovw-card-link" href="${needHref(r)}">${r.needs_you === 1 ? "1 needs you" : `${count(r.needs_you)} need you`}</a>`);
  if (!r.connected && me.role === "admin") links.push(`<a class="ovw-card-link" href="/settings.html?acct=${r.id}#meta">Connect to Meta</a>`);
  return links.length ? `<span class="ovw-card-links">${links.join("")}</span>` : "";
}

function cardsHtml(d) {
  return `<ul class="ovw-cards" aria-label="Accounts">${d.rows.map((r) => `<li class="ovw-item">
    <a class="ovw-card" href="${openHref(r)}" data-id="${r.id}">
      <span class="ovw-card-name">${esc(r.name)}</span>
      <span class="ovw-figs">
        <span><small>Spent</small><b>${dash(r.spend_cents, (c) => money(c, r.currency))}</b></span>
        <span><small>Leads</small><b>${dash(r.leads, count)}</b></span>
        <span><small>Cost per lead</small><b>${money(r.cpl_cents, r.currency)}</b></span>
      </span>
      <span class="ovw-card-foot">${count(r.delivering)} delivering${r.connected ? "" : " · Not connected to Meta yet"}</span>
    </a>${cardLinks(r)}${sourceNote(r.source)}</li>`).join("")}</ul>`;
}

function render(d) {
  const admin = me.role === "admin";
  if (!d.rows.length) {
    $("ovw").innerHTML = emptyState({ title: "No accounts yet", body: "Add one from Settings → Accounts." });
    return;
  }
  const notes = [esc(d.range.label), d.own_days ? "Each account uses its own days." : "",
    d.rows.length > 1 && !d.same_currency ? "Totals aren't added up: the accounts use different currencies." : ""].filter(Boolean);
  $("ovw").innerHTML = `<p class="muted small flush ovw-note" id="ovw-note">${notes.join(" · ")}</p>${tableHtml(d, admin)}${cardsHtml(d)}`;
}

async function load() {
  if ($("range-pick")) $("range-pick").value = range; else $("range-box").outerHTML = rangeSelect("range-pick", range);
  const superseded = startLoad("ovw");
  let d;
  try { d = await api(`/api/accounts/overview?${new URLSearchParams({ range })}`); }
  catch (err) { if (!superseded()) showLoadError($("ovw"), err, load); return; }
  if (superseded()) return;
  render(d);
}

me = await boot({ page: "accounts" });
if (me) {
  document.querySelector(".page-head").addEventListener("change", (e) => {
    if (e.target.id !== "range-pick") return;
    range = e.target.value;
    rememberRange(range);
    history.replaceState(null, "", `?range=${encodeURIComponent(range)}`);
    load();
  });
  // The rows are one Tab stop: ↑ ↓ move between accounts, Enter opens the one in focus (links inside a row stay reachable).
  $("ovw").addEventListener("keydown", (e) => {
    const row = e.target.matches && e.target.matches("tr.ovw-row") ? e.target : null;
    if (!row || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "Enter") { e.preventDefault(); location.href = row.dataset.href; return; }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const rows = [...$("ovw").querySelectorAll("tr.ovw-row")];
      const next = rows[rows.indexOf(row) + (e.key === "ArrowDown" ? 1 : -1)];
      if (next) { rows.forEach((r) => { r.tabIndex = r === next ? 0 : -1; }); next.focus(); }
    }
  });
  $("ovw").addEventListener("click", (e) => {
    if (e.target.closest("a, button, summary, details")) return;
    const row = e.target.closest("tr.ovw-row");
    if (row) location.href = row.dataset.href;
  });
  onRefresh(load);
  load();
}
