// Accepting suggestions, one or many, in one go. The server reads Meta fresh for all of them and
// sorts them (money first); each is then approved on its own, so every money rule still applies
// and a refusal never stops the rest.
import { api } from "./api.js";
import { confirmDialog, esc, toast } from "./ui.js";
import { money } from "./format.js";
import { spendWords } from "./controls.js";
import { confirmBig, confirmRemove, limitLine, limitMoney } from "./spendlimit.js";

const GROUPS = {
  money: "Spending", live: "Changes to what's running", create: "New ads, created switched off",
  mac: "For Claude to do on your Mac", local: "Only in this console", blocked: "Can't be accepted",
};

function line(item) {
  const p = item.plan;
  if (item.blocked) return esc(item.blocked);
  if (p.kind === "budget") {
    const pct = p.pct == null ? "" : ` (${p.pct > 0 ? "+" : ""}${p.pct}%)`;
    return `${esc(p.name)}: <del>${money(p.from, { exact: true })}</del> → <ins>${money(p.to, { exact: true })}</ins> a day${pct}${p.big ? ' <span class="pill warn">Over the +20% rule</span>' : ""}`;
  }
  if (p.kind === "spend_limit") return limitLine(p);
  if (p.kind === "status" && p.to === "ACTIVE") return `Turns on <b>${esc(p.name)}</b>${spendWords(p.spend)}`;
  if (p.kind === "status" && p.already) return `<b>${esc(p.name)}</b> is already off on Meta, so nothing is sent.`;
  if (p.kind === "status") return `Turns off <b>${esc(p.name)}</b> right away. Nothing is deleted.`;
  if (p.kind === "vertical") return `<b>${esc(p.name)}</b>: Reels and Stories get Claude's 9:16 video. Meta reviews the ad again.`;
  if (p.kind === "update") return `Goes on <b>${esc(p.name)}</b> itself: same ad, results kept. Meta reviews the ad again.`;
  if (p.kind === "create") return "Nothing spends until you turn it on.";
  if (p.kind === "render") return "Joins the queue on your Mac (10–40 minutes), then comes back for a yes or no.";
  if (p.kind === "experiment") return "Starts tracking on the Tests page. Nothing changes on Meta.";
  if (p.kind === "tags") return "Saves the labels. Nothing changes on Meta.";
  return "Claude picks this up on your Mac and answers in the conversation.";
}

function itemRow(item, i) {
  const why = item.conflict ? '<em class="sheet-why">Changes the same thing as another suggestion here. Tick one.</em>'
    : item.note ? `<em class="sheet-why">${esc(item.note)} Tick this yourself if you still want it.</em>`
    : item.needs_tick ? '<em class="sheet-why">Tick this yourself if you want it.</em>' : "";
  return `<li class="sheet-item" data-i="${i}">
    ${item.blocked ? '<span class="sheet-state" aria-hidden="true">–</span>' : `<input type="checkbox" data-item="${i}" ${item.tick ? "checked" : ""} aria-label="${esc(item.title)}">`}
    <div class="sheet-text"><b>${esc(item.title)}</b><span>${line(item)}</span>${why}<span class="sheet-result" hidden></span></div>
  </li>`;
}

function totals(items) {
  const budget = items.filter((i) => i.plan.kind === "budget").reduce((n, i) => n + i.plan.to - i.plan.from, 0);
  // Each budget once, by the campaign or ad set that holds it (two can share a name).
  const on = new Map(items.filter((i) => i.plan.kind === "status" && i.plan.to === "ACTIVE" && i.plan.spend && i.plan.spend.holder)
    .map((i) => [i.plan.spend.holder, i.plan.spend]));
  const spending = [...on.values()].reduce((n, s) => n + (s.daily_cents || 0), 0);
  const lifetime = [...on.values()].reduce((n, s) => n + (s.lifetime_cents || 0), 0);
  const runs = items.filter((i) => i.plan.kind === "render" || i.plan.kind === "record").length;
  const limit = items.find((i) => i.plan.kind === "spend_limit");
  return [
    budget ? `Daily budgets ${budget > 0 ? "+" : "−"}${money(Math.abs(budget), { exact: true })} a day` : "",
    limit ? `Spending limit ${limitMoney(limit.plan.from)} → ${limitMoney(limit.plan.to)}` : "",
    spending ? `Starts spending up to ${money(spending, { exact: true })} a day` : "",
    lifetime ? `Up to ${money(lifetime, { exact: true })} in total from lifetime budgets` : "",
    runs ? `${runs} new ${runs === 1 ? "run" : "runs"} on your Mac` : "",
  ].filter(Boolean).join(" · ");
}

async function applyOne(item) {
  const p = item.plan;
  if (p.kind === "spend_limit" && p.remove) {
    // Removing the account's limit is its own yes, asked before anything is sent.
    if (!(await confirmRemove())) throw new Error("Not removed: the limit stays as it is.");
    return api(`/api/proposals/${item.id}/approve`, { method: "POST", body: { ...item.body, confirm_remove: true } });
  }
  if (p.kind === "spend_limit" && p.big) {
    // So is more than doubling it.
    if (!(await confirmBig(p))) throw new Error("Not changed: the limit stays as it is.");
    return api(`/api/proposals/${item.id}/approve`, { method: "POST", body: { ...item.body, accept_big: true } });
  }
  if (p.kind === "render") {
    await api(`/api/ads/ad/${encodeURIComponent(p.ad_id)}/render`, { method: "POST", body: { from_task: p.from_task, from_proposal: item.id, direction: p.note } });
  }
  return api(`/api/proposals/${item.id}/approve`, { method: "POST", body: item.body });
}

function resultWords(item, r) {
  if (item.plan.kind === "render") return "In the queue";
  if (r.task_id) return `Claude is on it · <a href="/desk.html#r/${r.task_id}">Follow it</a>`;
  if (r.updated_ad) return `Updated, Meta reviews it next · <a href="/ad.html?id=${encodeURIComponent(r.updated_ad)}">Open it</a>`;
  if (r.ad_id) return `Created, off · <a href="/ad.html?id=${encodeURIComponent(r.ad_id)}">Open it</a>`;
  if (r.experiment_id) return `Tracking · <a href="/experiments.html#${r.experiment_id}">Open it</a>`;
  return r.status === "applied" ? "Done" : "Recorded";
}

export async function acceptSheet(ids, onDone) {
  const dlg = document.createElement("dialog");
  dlg.className = "confirm accept-sheet";
  dlg.innerHTML = '<form method="dialog"><h2>Checking with Meta…</h2><p class="muted flush">Reading today’s numbers so what you accept is live.</p></form>';
  document.body.appendChild(dlg);
  dlg.showModal();
  let items;
  try { ({ items } = await api("/api/proposals/review", { method: "POST", body: { ids } })); }
  catch (err) { dlg.close(); dlg.remove(); toast(err.message, "bad"); return; }
  if (!items.length) { dlg.close(); dlg.remove(); toast("Those were already decided"); onDone(); return; }

  const groups = Object.keys(GROUPS).map((g) => {
    const rows = items.map((item, i) => [item, i]).filter(([item]) => item.group === g);
    return rows.length ? `<section class="sheet-group"><h3>${esc(GROUPS[g])}</h3><ul>${rows.map(([item, i]) => itemRow(item, i)).join("")}</ul></section>` : "";
  }).join("");
  const held = items.filter((i) => i.needs_tick).length;
  dlg.innerHTML = `<form method="dialog" novalidate>
    <h2 id="sheet-title">Accept these suggestions?</h2>
    <p class="muted sheet-lead">Read from Meta just now.${held ? ` ${held === 1 ? "One waits" : `${held} wait`} for your own tick: ${held === 1 ? "it spends money or goes past a rule" : "they spend money or go past a rule"}.` : ""}</p>
    <div class="sheet-list">${groups}</div>
    <p class="sheet-sum" id="sheet-sum"></p>
    <div class="row end"><button class="btn" type="button" id="cd-cancel">Cancel</button>
      <button class="btn btn-claude" type="submit" id="cd-ok"></button></div>
  </form>`;
  const boxes = [...dlg.querySelectorAll("[data-item]")];
  const chosen = () => boxes.filter((b) => b.checked).map((b) => items[Number(b.dataset.item)]);
  const ok = dlg.querySelector("#cd-ok");
  const refresh = () => {
    const list = chosen();
    ok.textContent = list.length ? `Accept ${list.length}` : "Nothing ticked";
    ok.disabled = !list.length;
    dlg.querySelector("#sheet-sum").textContent = totals(list);
  };
  dlg.addEventListener("change", (e) => {
    const box = e.target.closest("[data-item]");
    if (!box || !box.checked) { refresh(); return; }
    const key = items[Number(box.dataset.item)].conflict;
    if (key) boxes.filter((b) => b !== box && items[Number(b.dataset.item)].conflict === key).forEach((b) => { b.checked = false; });
    refresh();
  });
  refresh();
  // The sheet's content arrived: focus starts on Cancel, never on Accept.
  dlg.querySelector("#cd-cancel").focus();
  let busy = false;
  dlg.addEventListener("cancel", (e) => { if (busy) e.preventDefault(); });
  const finish = () => { dlg.close(); dlg.remove(); };
  dlg.querySelector("#cd-cancel").addEventListener("click", finish);
  dlg.querySelector("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (dlg.dataset.done) { finish(); onDone(); return; }
    const list = chosen();
    busy = true;
    ok.disabled = true;
    ok.textContent = "Working…";
    dlg.querySelector("#cd-cancel").hidden = true;
    boxes.forEach((b) => { b.disabled = true; });
    let accepted = 0;
    for (const item of list) {
      const li = dlg.querySelector(`.sheet-item[data-i="${items.indexOf(item)}"]`);
      const out = li.querySelector(".sheet-result");
      li.dataset.state = "running";
      out.hidden = false;
      out.textContent = "Working…";
      try {
        out.innerHTML = resultWords(item, await applyOne(item));
        li.dataset.state = "ok";
        accepted += 1;
      } catch (err) {
        out.textContent = err.message;
        li.dataset.state = "bad";
      }
    }
    busy = false;
    const failed = list.length - accepted;
    const left = items.length - list.length;
    dlg.querySelector("#sheet-title").textContent = failed ? `${accepted} accepted, ${failed} didn't go through` : `${accepted} accepted`;
    dlg.querySelector(".sheet-lead").textContent = [failed ? "What didn't go through is still waiting for you." : "", left ? `${left} left waiting.` : ""].filter(Boolean).join(" ") || "All done.";
    dlg.querySelector("#sheet-sum").textContent = "";
    dlg.dataset.done = "1";
    ok.disabled = false;
    ok.textContent = "Done";
    ok.focus();
  });
}

export async function declineMany(ids, onDone) {
  const yes = await confirmDialog({ title: `Decline ${ids.length} suggestion${ids.length === 1 ? "" : "s"}?`, body: "<p>Nothing changes on Meta.</p>", confirm: `Decline ${ids.length}` });
  if (!yes) return;
  const results = await Promise.allSettled(ids.map((id) => api(`/api/proposals/${id}/decline`, { method: "POST" })));
  const failed = results.filter((r) => r.status === "rejected").length;
  toast(failed ? `${ids.length - failed} declined, ${failed} couldn't be` : `${ids.length} declined`, failed ? "bad" : "");
  onDone();
}
