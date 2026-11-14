// AM-D: the audience pickers shared by New ad set, New campaign (its ad set step) and an ad set's Edit: "Include people in" and
// "Leave out people in", each a searchable list of the account's custom and lookalike audiences as chips (at most 20 each), and
// "Start from a saved audience". An audience still filling says so; one Meta reports a problem with, or a lookalike in a campaign
// with a special ad category, can't be picked and says why. The server checks every pick again (only this account's audiences).
import { esc, icon } from "./ui.js";

const READY_WORDS = { filling: "Still filling", too_small: "Too small to use yet", problem: "Problem" };

export function audPickHtml(id) {
  const row = (side, label, placeholder) => `<div class="aud-pick-row" data-aud-side="${side}">
      <span class="label" id="${id}-${side}-l">${label}</span>
      <ul class="aud-chips" id="${id}-${side}-chips" aria-labelledby="${id}-${side}-l"></ul>
      <div class="place-add aud-find">
        <label class="sr-only" for="${id}-${side}-q">${placeholder}</label>
        <input class="input" id="${id}-${side}-q" data-aud-q="${side}" placeholder="${placeholder}" autocomplete="off" role="combobox" aria-expanded="false" aria-controls="${id}-${side}-res">
        <ul class="place-results aud-res" id="${id}-${side}-res" role="listbox" hidden></ul>
      </div>
    </div>`;
  return `<div class="aud-pick" id="${id}">
      <input type="hidden" name="audiences">
      ${row("inc", "Include people in", "Add an audience to include")}
      ${row("exc", "Leave out people in", "Add an audience to leave out")}
      <p class="muted small flush aud-adv" id="${id}-adv" hidden></p>
      <p class="muted small flush" id="${id}-none" hidden>No audiences in this account yet. Make one under Ads → Audiences.</p>
    </div>`;
}

export function savedSelectHtml(id, saved) {
  if (!saved || !saved.length) return "";
  return `<div class="field aud-saved"><label for="${id}">Start from a saved audience <span class="muted">(optional)</span></label>
    <select class="input" id="${id}"><option value="">None</option>${saved.map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("")}</select>
    <span class="hint">Fills in places, ages and hints from it. Nothing changes on Meta until you create or save.</span></div>`;
}

// audiences: [{id, name, kind, kind_words, describe, size_words, ready, problem}] · words: {lookalike_special, advantage, max}
// special(): the campaign has a special ad category · advantage(): Advantage+ audience is on · onChange(): after any pick
export function audPicker(id, { audiences = [], words = {}, special = () => false, advantage = () => false, onChange = () => {} }) {
  const root = document.getElementById(id);
  const byId = Object.fromEntries(audiences.map((a) => [a.id, a]));
  const max = words.max || 20;
  const picked = { inc: [], exc: [] };
  const extra = {};  // audiences on the ad set the list doesn't hold (Meta's names)
  const $ = (s) => document.getElementById(`${id}-${s}`);
  const why = (a) => a.problem || (a.kind === "lookalike" && special() ? words.lookalike_special : null);
  const label = (aid) => (byId[aid] || extra[aid] || { name: aid }).name;
  const chip = (side, aid) => {
    const a = byId[aid];
    const note = a ? (a.ready === "ready" ? a.size_words : READY_WORDS[a.ready] || a.size_words) : "";
    const bad = a && why(a);
    return `<li class="aud-chip${bad ? " is-bad" : ""}" data-aud-chip="${esc(aid)}"><span><b>${esc(label(aid))}</b>${note ? ` <span class="muted">${esc(note)}</span>` : ""}${bad ? ` <span class="aud-why">${esc(bad)}</span>` : ""}</span>
      <button type="button" class="btn btn-quiet btn-small" data-aud-drop="${side}:${esc(aid)}" aria-label="Remove ${esc(label(aid))}">${icon("close")}</button></li>`;
  };
  const draw = () => {
    for (const side of ["inc", "exc"]) {
      $(`${side}-chips`).innerHTML = picked[side].length ? picked[side].map((aid) => chip(side, aid)).join("") : '<li class="muted small">None</li>';
    }
    $("adv").hidden = !(advantage() && (picked.inc.length || picked.exc.length));
    $("adv").textContent = words.advantage || "";
    $("none").hidden = audiences.length > 0;
  };
  const hide = (side) => { const r = $(`${side}-res`); if (!r) return; r.hidden = true; $(`${side}-q`).setAttribute("aria-expanded", "false"); };
  const show = (side) => {
    const q = $(`${side}-q`).value.trim().toLowerCase();
    const other = side === "inc" ? "exc" : "inc";
    const list = audiences.filter((a) => !picked[side].includes(a.id) && !picked[other].includes(a.id)
      && (!q || a.name.toLowerCase().includes(q) || (a.describe || "").toLowerCase().includes(q))).slice(0, 30);
    const res = $(`${side}-res`);
    res.innerHTML = list.length ? list.map((a, i) => {
      const bad = why(a);
      return `<li role="option" tabindex="-1" id="${id}-${side}-o${i}" data-aud-pick="${side}:${esc(a.id)}" ${bad ? 'aria-disabled="true" class="is-off"' : ""}>
        <span class="place-kind">${esc(a.kind_words)}</span><span class="aud-opt"><b>${esc(a.name)}</b>
        <span class="muted small">${esc(a.ready === "ready" ? a.size_words : READY_WORDS[a.ready] || a.size_words)}</span>${bad ? `<span class="aud-why">${esc(bad)}</span>` : ""}</span></li>`;
    }).join("") : `<li class="muted" role="option" aria-disabled="true">${audiences.length ? "Nothing else to pick" : "No audiences yet"}</li>`;
    res.hidden = false;
    $(`${side}-q`).setAttribute("aria-expanded", "true");
  };
  const add = (side, aid) => {
    const a = byId[aid];
    if (!a || why(a) || picked[side].includes(aid)) return;
    if (picked[side].length >= max) return;
    picked[side].push(aid);
    $(`${side}-q`).value = "";
    hide(side); draw(); onChange();
  };
  root.addEventListener("focusin", (e) => { const q = e.target.closest("[data-aud-q]"); if (q) show(q.dataset.audQ); });
  root.addEventListener("input", (e) => { const q = e.target.closest("[data-aud-q]"); if (q) { e.stopPropagation(); show(q.dataset.audQ); } });
  root.addEventListener("click", (e) => {
    const p = e.target.closest("[data-aud-pick]");
    if (p) { const [side, aid] = p.dataset.audPick.split(":"); add(side, aid); return; }
    const d = e.target.closest("[data-aud-drop]");
    if (d) { const [side, aid] = d.dataset.audDrop.split(":"); picked[side] = picked[side].filter((x) => x !== aid); draw(); onChange(); }
  });
  root.addEventListener("keydown", (e) => {
    const q = e.target.closest("[data-aud-q]");
    if (q) {
      const side = q.dataset.audQ;
      if (e.key === "ArrowDown") { e.preventDefault(); $(`${side}-res`).querySelector("[data-aud-pick]:not(.is-off)")?.focus(); }
      if (e.key === "Escape") hide(side);
      if (e.key === "Enter") { e.preventDefault(); const first = $(`${side}-res`).querySelector("[data-aud-pick]:not(.is-off)"); if (first) first.click(); }
      return;
    }
    const li = e.target.closest("[data-aud-pick]");
    if (!li) return;
    const side = li.dataset.audPick.split(":")[0];
    if (e.key === "Enter") { e.preventDefault(); li.click(); }
    if (e.key === "ArrowDown") { e.preventDefault(); li.nextElementSibling?.focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); (li.previousElementSibling || $(`${side}-q`)).focus(); }
    if (e.key === "Escape") { hide(side); $(`${side}-q`).focus(); }
  });
  const away = (e) => { if (!document.getElementById(id)) { document.removeEventListener("click", away); return; } if (!e.target.closest(`#${id} .aud-find`)) { hide("inc"); hide("exc"); } };
  document.addEventListener("click", away);
  draw();
  return {
    get: () => ({ include: [...picked.inc], exclude: [...picked.exc] }),
    // inc / exc: ids, or {id, name} objects as Meta reads them on an ad set (kept even if the list doesn't hold them)
    set: (inc = [], exc = []) => {
      const ids = (list) => list.map((x) => { if (x && typeof x === "object") { if (!byId[x.id]) extra[x.id] = { name: x.name || x.id }; return String(x.id); } return String(x); });
      picked.inc = ids(inc); picked.exc = ids(exc).filter((x) => !picked.inc.includes(x));
      draw();
    },
    names: () => ({ include: picked.inc.map(label), exclude: picked.exc.map(label) }),
    redraw: draw,
  };
}

// "In “A”, not in “B”" for a summary line.
export function audWords(names) {
  const q = (l) => l.map((n) => `“${n}”`).join(", ");
  return [names.include.length ? `in ${q(names.include)}` : "", names.exclude.length ? `not in ${q(names.exclude)}` : ""].filter(Boolean).join(", ");
}
