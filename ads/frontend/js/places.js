// The place picker shared by New ad set and New campaign: a list of places (map pins, cities with
// a radius, states, ZIP codes) and Meta's own place search to add more.
import { api } from "./api.js";
import { esc, toast } from "./ui.js";

const KIND = { pin: "Area", city: "City", region: "State", zip: "ZIP" };
export const placeLabel = (l) => (l.kind === "pin" ? l.name || "Map pin" : l.name);

export function placesHtml(id) {
  return `<ul class="places" id="${id}-list"></ul>
    <div class="place-add">
      <label class="sr-only" for="${id}-q">Add a city, state or ZIP code</label>
      <input class="input" id="${id}-q" placeholder="Add a city, state or ZIP code" autocomplete="off" role="combobox" aria-expanded="false" aria-controls="${id}-results">
      <ul class="place-results" id="${id}-results" role="listbox" hidden></ul>
    </div>`;
}

export function placesWidget(id, { cityRadius, pinRadius, onChange }) {
  const $ = (s) => document.getElementById(`${id}-${s}`);
  let locations = [];
  let results = [];
  let seq = 0;
  let timer;
  const radii = (l) => {
    const [lo, hi] = l.kind === "city" ? cityRadius : pinRadius;
    return [...new Set([lo, 10, 15, 20, 25, 30, 40, hi, Number(l.radius)].filter((r) => r >= lo && r <= hi))].sort((a, b) => a - b);
  };
  const render = () => {
    $("list").innerHTML = locations.length ? locations.map((l, i) => `<li>
        <span class="place-kind">${KIND[l.kind]}</span><b>${esc(placeLabel(l))}</b>
        ${l.kind === "pin" || l.kind === "city" ? `<label class="sr-only" for="${id}-r-${i}">Radius for ${esc(placeLabel(l))}</label>
          <select class="input radius" id="${id}-r-${i}" data-radius="${i}">${radii(l).map((r) => `<option value="${r}" ${r === Number(l.radius) ? "selected" : ""}>+ ${r} mi</option>`).join("")}</select>` : ""}
        <button type="button" class="btn btn-quiet btn-small" data-remove="${i}" aria-label="Remove ${esc(placeLabel(l))}">Remove</button>
      </li>`).join("") : '<li class="muted">No places yet. Add one below.</li>';
  };
  const hide = () => { $("results").hidden = true; $("q").setAttribute("aria-expanded", "false"); };
  const show = (list) => {
    results = list;
    $("results").innerHTML = list.map((p, i) => `<li role="option" id="${id}-pr-${i}" data-pick="${i}" tabindex="-1"><span class="place-kind">${KIND[p.kind]}</span>${esc(p.name)}</li>`).join("")
      || '<li class="muted" role="option" aria-disabled="true">Nothing found</li>';
    $("results").hidden = false;
    $("q").setAttribute("aria-expanded", "true");
  };
  const pick = (i) => {
    const p = results[i];
    if (!p) return;
    if (!locations.some((l) => l.key === p.key && l.kind === p.kind)) locations.push({ ...p, ...(p.kind === "city" ? { radius: 25 } : {}) });
    $("q").value = ""; hide(); render(); onChange(); $("q").focus();
  };
  $("list").addEventListener("change", (e) => {
    const r = e.target.closest("[data-radius]");
    if (r) { locations[Number(r.dataset.radius)].radius = Number(r.value); onChange(); }
  });
  $("list").addEventListener("click", (e) => {
    const b = e.target.closest("[data-remove]");
    if (b) { locations.splice(Number(b.dataset.remove), 1); render(); onChange(); }
  });
  $("q").addEventListener("input", (e) => {
    e.stopPropagation();
    clearTimeout(timer);
    const q = $("q").value.trim();
    if (q.length < 2) { hide(); return; }
    timer = setTimeout(async () => {
      const mine = ++seq;
      try { const r = await api(`/api/adsets/places?q=${encodeURIComponent(q)}`); if (mine === seq) show(r.items); }
      catch (err) { if (mine === seq) toast(err.message, "bad"); }
    }, 250);
  });
  $("q").addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" && results.length) { e.preventDefault(); document.getElementById(`${id}-pr-0`)?.focus(); }
    if (e.key === "Escape") hide();
    if (e.key === "Enter") { e.preventDefault(); if (results.length) pick(0); }
  });
  $("results").addEventListener("keydown", (e) => {
    const li = e.target.closest("[data-pick]");
    if (!li) return;
    const i = Number(li.dataset.pick);
    if (e.key === "Enter") { e.preventDefault(); pick(i); }
    if (e.key === "ArrowDown") { e.preventDefault(); document.getElementById(`${id}-pr-${i + 1}`)?.focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); (i ? document.getElementById(`${id}-pr-${i - 1}`) : $("q")).focus(); }
    if (e.key === "Escape") { hide(); $("q").focus(); }
  });
  $("results").addEventListener("click", (e) => { const li = e.target.closest("[data-pick]"); if (li) pick(Number(li.dataset.pick)); });
  document.addEventListener("click", (e) => { if (!e.target.closest(".place-add")) hide(); });
  return {
    get: () => locations,
    set: (list) => { locations = list.map((l) => ({ ...l })); render(); },
  };
}
