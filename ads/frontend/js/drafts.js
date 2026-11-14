// AM-B: drafts Eugene (or Claude on his Mac) started in Ads Manager, read through the Mac link. Ads → Campaigns shows
// them above the table (owner and account admins): what each holds, what's missing, Meta's problems, Finish in the console
// (a builder filled in from it, created off as always), Apply in the console for a staged edit (the usual budget or on/off
// confirmation) and Open in Ads Manager. Nothing here writes to Meta or touches the draft: Eugene discards it in Ads Manager.
// Meta's words are untrusted: esc() everywhere, links built by the server from digits.
import { api } from "./api.js";
import { esc, linkNote, toast, when, withFrom } from "./ui.js";
import { count, money, plural } from "./format.js";
import { changeStatus, editBudget } from "./controls.js";

const FRESH_MS = 5 * 60 * 1000;
const WAIT_MS = 20000;
const LEVEL = { campaign: "campaign", adset: "ad set", ad: "ad" };

export async function loadDrafts() {
  try { return await api("/api/drafts"); } catch (err) { return null; }
}

const hasAny = (d) => Boolean(d && d.drafts && d.drafts.length);
export const draftCount = (d) => (d ? d.open : 0);

function value(row, v) {
  if (v === null || v === undefined || v === "") return '<span class="muted">not set</span>';
  if (row.kind === "money" && Number.isFinite(v)) return esc(money(v, { exact: true }));
  if (row.kind === "status") return v === "ACTIVE" ? "On" : v === "PAUSED" ? "Off" : esc(String(v).toLowerCase());
  if (typeof v === "object") return '<span class="muted">changed</span>';
  return esc(String(v));
}

function applyCell(d, row) {
  if (row.applied) return '<span class="pill ok dr-applied">Applied</span>';
  if (row.apply === "budget" || row.apply === "status") {
    return `<button type="button" class="btn btn-small" data-dr-apply="${esc(d.id)}" data-field="${esc(row.field)}">Apply in the console</button>`;
  }
  return d.open_url ? `<a class="btn btn-small btn-quiet" href="${esc(d.open_url)}" target="_blank" rel="noopener noreferrer">Change it in Ads Manager</a>`
    : '<span class="muted small">Change it in Ads Manager</span>';
}

function editsHtml(d) {
  return `<table class="table dr-edits"><thead><tr><th scope="col">Setting</th><th scope="col">Now</th><th scope="col">In the draft</th><th scope="col"><span class="sr-only">Apply</span></th></tr></thead>
    <tbody>${d.edits.map((r) => `<tr data-field="${esc(r.field)}">
      <td data-label="Setting">${esc(r.label)}</td>
      <td data-label="Now">${value(r, r.now ?? r.old)}${r.stale ? '<span class="dr-stale">Ads Manager changed this since the draft</span>' : ""}</td>
      <td data-label="In the draft">${value(r, r.new)}</td>
      <td class="dr-apply-cell">${applyCell(d, r)}</td></tr>`).join("")}</tbody></table>`;
}

function itemHtml(d) {
  const problems = d.problems.length
    ? `<div class="dr-sec"><span class="dr-k">Meta's problems</span><ul class="dr-problems">${d.problems.map((p) => `<li>${esc(p.message)}</li>`).join("")}</ul></div>` : "";
  const missing = d.kind === "edit" || d.finished ? ""
    : d.missing.length ? `<div class="dr-sec"><span class="dr-k">What's missing</span><ul class="dr-missing">${d.missing.map((m) => `<li>${esc(m)}</li>`).join("")}</ul></div>`
      : '<p class="dr-ready flush">Ready to create</p>';
  const target = d.kind !== "edit" && d.target && d.target.name ? `<p class="dr-target small flush">Goes in the ${esc(LEVEL[d.target.level] || d.target.level)} “${esc(d.target.name)}”</p>` : "";
  const other = d.other_fields.length ? `<details class="dr-more"><summary>What else it sets</summary><p class="small flush">${esc(d.other_fields.join(", ").replace(/_/g, " "))}</p></details>` : "";
  const open = d.open_url ? `<a class="btn btn-quiet" href="${esc(d.open_url)}" target="_blank" rel="noopener noreferrer" data-dr-open>Open in Ads Manager</a>` : "";
  let acts;
  if (d.finished) {
    acts = `<p class="dr-done flush">Finished in the console ${esc(when(d.finished.at))}${d.finished.href ? ` · <a href="${esc(d.finished.href)}">Open it</a>` : ""}</p>
      <p class="muted small flush">Discard the draft in Ads Manager when you're done.</p>
      <div class="dr-btns">${open}${d.finish_url && !d.gone ? `<a class="btn btn-quiet" href="${esc(withFrom(`${d.finish_url}&again=1`))}" data-dr-again>Make another from this draft</a>` : ""}</div>`;
  } else if (d.kind === "edit") {
    acts = `<div class="dr-btns">${open}</div>`;
  } else if (d.finish_blocked) {
    acts = `<div class="dr-btns"><button type="button" class="btn btn-primary" disabled aria-describedby="dr-why-${esc(d.id)}">Finish in the console</button>${open}</div>
      <p class="dr-why small flush" id="dr-why-${esc(d.id)}">${esc(d.finish_blocked)}</p>`;
  } else {
    acts = `<div class="dr-btns"><a class="btn btn-primary" href="${esc(withFrom(d.finish_url))}" data-dr-finish="${esc(d.id)}">Finish in the console</a>${open}</div>`;
  }
  return `<li class="dr-item${d.finished ? " is-done" : ""}${d.kind === "edit" ? " is-edit" : ""}" id="draft-${esc(d.id)}" data-draft="${esc(d.id)}">
    <div class="dr-main">
      <div class="dr-title"><b class="dr-name">${esc(d.name)}</b><span class="pill dr-pill">Draft</span>${d.gone ? '<span class="pill">Gone from Ads Manager</span>' : ""}</div>
      <p class="dr-what flush">${esc(d.what)}</p>
      ${target}
      <p class="muted small flush">Edited in Ads Manager ${esc(when(d.edited_at))}</p>
    </div>
    <div class="dr-body">
      ${d.kind === "edit" ? editsHtml(d) : `<p class="dr-holds flush"><span class="dr-k">What it holds</span> ${esc(d.holds)}</p>`}
      ${missing}${problems}${other}
    </div>
    <div class="dr-acts">${acts}</div>
  </li>`;
}

// The panel above Ads → Campaigns (the first few; every one under the Drafts view). Empty when there's nothing to show.
const ABOVE = 3;
export function draftsHtml(d, { alone = false } = {}) {
  if (!hasAny(d)) {
    return alone ? `<section class="panel dr-panel" id="dr-panel"><div class="panel-body stack tight"><p class="flush">No drafts from Ads Manager right now.</p>${linkNote(d && d.source)}</div></section>` : "";
  }
  const n = d.open;
  const done = d.drafts.filter((x) => x.finished).length;
  const sub = [n ? `${plural(n, "draft")} you started in Ads Manager` : "", done ? `${count(done)} finished here` : ""].filter(Boolean).join(" · ");
  return `<section class="panel dr-panel" id="dr-panel" aria-labelledby="dr-h">
    <div class="panel-head dr-head"><h2 id="dr-h">Drafts in Ads Manager</h2><p>${sub}</p></div>
    <div class="panel-body stack tight">
      <div class="dr-src">${linkNote(d.source)}${d.link && d.link.can_check ? '<button type="button" class="btn btn-small btn-quiet" id="dr-check">Check Ads Manager now</button>' : ""}</div>
      <ul class="dr-list">${(alone ? d.drafts : d.drafts.slice(0, ABOVE)).map(itemHtml).join("")}</ul>
      ${!alone && d.drafts.length > ABOVE ? `<p class="flush"><button type="button" class="link-btn" data-view="drafts" id="dr-all">See all ${d.drafts.length} drafts</button></p>` : ""}
    </div></section>`;
}

// #draft=<id>: mark it (from the Inbox), and scroll to it the first time it shows.
let scrolled = false;
export function showTarget() {
  const m = location.hash.match(/^#draft=(\d+)$/);
  const el = m && document.getElementById(`draft-${m[1]}`);
  if (!el) return;
  el.classList.add("dr-hit");
  if (!scrolled) { scrolled = true; el.scrollIntoView({ block: "center" }); }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Before Finish or Apply: when the last read is old, ask the Mac for a fresh one and wait up to 20 s for it (never blocks).
async function freshen(d, id, btn) {
  const at = d.source && d.source.fetched_at ? Date.parse(d.source.fetched_at) : 0;
  if (at && Date.now() - at < FRESH_MS) return d;
  const words = btn.textContent;
  btn.textContent = "Checking Ads Manager…";
  btn.setAttribute("aria-busy", "true");
  try {
    const r = await api(`/api/drafts/${encodeURIComponent(id)}/check`, { method: "POST" });
    if (r.asked) {
      for (let waited = 0; waited < WAIT_MS; waited += 2000) {
        await sleep(2000);
        const next = await loadDrafts();
        if (next && next.source && next.source.fetched_at && Date.parse(next.source.fetched_at) > at) return next;
      }
    }
  } catch (err) { /* the source line still says how old the draft is */ }
  finally { btn.textContent = words; btn.removeAttribute("aria-busy"); }
  return d;
}

async function apply(d, id, field, reload, btn) {
  d = await freshen(d, id, btn);
  const item = d.drafts.find((x) => x.id === id);
  const row = item && item.edits.find((r) => r.field === field);
  if (!row || row.applied) { reload(); return; }
  const level = item.target.level;
  const name = item.target.name || item.name;
  const done = async () => {
    try { await api(`/api/drafts/${encodeURIComponent(id)}/applied`, { method: "POST", body: { field } }); }
    catch (err) { toast(err.message, "bad"); }
    reload();
  };
  if (row.apply === "status") {
    await changeStatus({ level, id, name, turnOn: row.new === "ACTIVE" }, done, btn);
    return;
  }
  // The budget dialog starts from what Meta has now (read fresh), with the draft's amount in the field.
  let spend;
  btn.disabled = true;
  try { spend = await api(`/api/ads/${level}/${encodeURIComponent(id)}/spend`); }
  catch (err) { toast(err.message, "bad"); btn.disabled = false; return; }
  btn.disabled = false;
  if (!spend.daily_cents) { toast("Meta has no daily budget on it now. Change it in Ads Manager.", "bad"); return; }
  await editBudget({ level, id, name, current: spend.daily_cents, suggest: row.new,
    note: `From your Ads Manager draft: ${esc(money(row.new, { exact: true }))} a day.${row.stale ? " Ads Manager changed the budget since the draft was made." : ""}` }, done);
}

// Clicks inside the panel. `get()` returns the latest /api/drafts answer; `reload()` reads it again and redraws.
export function wireDrafts(root, { get, reload }) {
  root.addEventListener("click", async (e) => {
    const check = e.target.closest("#dr-check");
    if (check) {
      check.disabled = true;
      try { await api("/api/am-link/check", { method: "POST" }); toast("Asked your Mac to read Ads Manager. It takes a minute."); }
      catch (err) { toast(err.message, "bad"); check.disabled = false; }
      return;
    }
    const fin = e.target.closest("[data-dr-finish]");
    if (fin) {
      e.preventDefault();
      if (fin.getAttribute("aria-busy")) return;
      await freshen(get(), fin.dataset.drFinish, fin);
      location.href = fin.getAttribute("href");
      return;
    }
    const ap = e.target.closest("[data-dr-apply]");
    if (ap) await apply(get(), ap.dataset.drApply, ap.dataset.field, reload, ap);
  });
}

// ---------------------------------------------------------------- the builders (?draft=<id>)

export const draftParam = () => {
  const q = new URLSearchParams(location.search);
  const id = q.get("draft");
  return id && /^\d+$/.test(id) ? { id, again: q.get("again") === "1" } : null;
};

// GET /api/drafts/<id>/spec: {page, spec, notes, draft}; a refusal ({error, finished | open_url}) is shown in the note.
export async function loadDraftSpec(p) {
  try { return await api(`/api/drafts/${encodeURIComponent(p.id)}/spec${p.again ? "?again=1" : ""}`); }
  catch (err) { return { error: err.message, body: err.body || {} }; }
}

export function draftNoteHtml(r) {
  if (r.error) {
    const done = r.body.finished;
    return `<div class="note warn dr-note" id="dr-note" role="status"><p class="flush">${esc(r.error)}</p>
      ${done && done.href ? `<p class="flush"><a href="${esc(done.href)}">Open what was made</a> · <a href="${esc(withFrom(`${location.pathname}?draft=${new URLSearchParams(location.search).get("draft")}&again=1`))}">Make another from this draft</a></p>` : ""}
      ${r.body.open_url ? `<p class="flush"><a href="${esc(r.body.open_url)}" target="_blank" rel="noopener noreferrer">Open in Ads Manager</a></p>` : ""}</div>`;
  }
  return `<div class="note dr-note" id="dr-note" role="status">
    <p class="flush">Filled in from your Ads Manager draft “<b>${esc(r.draft.name)}</b>” (read ${esc(when(r.draft.read_at))}). Nothing is created until you press Create, and it's created off.</p>
    ${r.notes.length ? `<ul class="dr-notes">${r.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
    ${r.draft.open_url ? `<p class="flush small"><a href="${esc(r.draft.open_url)}" target="_blank" rel="noopener noreferrer">Open the draft in Ads Manager</a></p>` : ""}</div>`;
}

// New ad after New ad set, and the ad page after New ad (?draft_left=<id>): the draft's name and link, from the list.
export async function draftLeftFor(id) {
  if (!/^\d+$/.test(id || "")) return null;
  const d = await loadDrafts();
  const x = d && d.drafts && d.drafts.find((i) => i.id === id);
  return x ? { name: x.name, open_url: x.open_url } : null;
}

// What a builder's success says once it made something from a draft.
export function draftLeftHtml(draft) {
  if (!draft) return "";
  return `<p class="note dr-left flush" id="dr-left">The draft “${esc(draft.name)}” is still in Ads Manager: discard it there.${draft.open_url ? ` <a href="${esc(draft.open_url)}" target="_blank" rel="noopener noreferrer">Open in Ads Manager</a>` : ""}</p>`;
}
