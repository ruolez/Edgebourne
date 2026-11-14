// Something already in the account, shown large in an answer because it was asked for (`desk show` on the Mac):
// an ad exactly as Meta shows it, placement by placement, or a lead form sketched on a phone.
import { api } from "./api.js";
import { esc, previewSkeleton, showPreviewFrame } from "./ui.js";
import { statusPill } from "./format.js";
import { FORM_STEPS, formScreens, formSteps } from "./formsketch.js";

const PLACES = [["MOBILE_FEED_STANDARD", "Feed"], ["INSTAGRAM_REELS", "Reels"], ["INSTAGRAM_STORY", "Stories"]];
const cache = new Map();
const once = (key, load) => { if (!cache.has(key)) cache.set(key, load().catch((err) => { cache.delete(key); throw err; })); return cache.get(key); };

function crShow(s, ix) {
  const known = ix.ads[s.id];
  const name = known ? known.name : s.name || "Ad";
  const start = PLACES.some(([f]) => f === s.placement) ? s.placement : PLACES[0][0];
  return `<section class="cv-show" data-show="cr" aria-label="${esc(name)}, as Meta shows it">
    <div class="cv-show-media">
      <div class="segmented fill" role="tablist" aria-label="Placement">${PLACES.map(([f, l]) => `<button type="button" role="tab" data-show-place="${f}" aria-selected="${f === start}">${l}</button>`).join("")}</div>
      <div class="decision-preview" data-show-cr="${esc(s.id)}" data-format="${start}">${previewSkeleton()}</div>
    </div>
    <div class="cv-show-side">
      <span class="cv-show-kind">As Meta shows it</span>
      <b>${esc(name)}</b>
      ${known ? `<span>${statusPill(known.effective_status)}</span>` : ""}
      ${s.caption ? `<p>${esc(s.caption)}</p>` : ""}
      <div class="cv-show-do"><a class="btn btn-small" href="/ad.html?id=${encodeURIComponent(s.id)}">Open the ad</a><button class="btn btn-small btn-quiet" type="button" data-view-cr="${esc(s.id)}">Larger</button></div>
    </div>
  </section>`;
}

function formShow(s) {
  return `<section class="cv-show" data-show="form" aria-label="${esc(s.name || "Lead form")}">
    <div class="cv-show-media">
      <div class="segmented fill" role="tablist" aria-label="Step" data-show-steps hidden></div>
      <div class="phone"><div class="phone-screen" data-show-form="${esc(s.id)}" data-step="intro"><p class="ph-sub">Loading the form…</p></div></div>
    </div>
    <div class="cv-show-side">
      <span class="cv-show-kind">Lead form</span>
      <b>${esc(s.name || "Lead form")}</b>
      ${s.caption ? `<p>${esc(s.caption)}</p>` : ""}
      <p>A close sketch, not Meta's exact layout.</p>
      <div class="cv-show-do"><a class="btn btn-small" href="/forms.html#form=${encodeURIComponent(s.id)}">Open Lead forms</a></div>
    </div>
  </section>`;
}

export function showsHtml(t, ix) {
  return (t.shows || []).map((s) => (s.type === "form" ? formShow(s) : crShow(s, ix))).join("");
}

async function fillCr(box) {
  const id = box.dataset.showCr, fmt = box.dataset.format;
  try {
    const p = await once(`cr:${id}:${fmt}`, () => api(`/api/ads/ad/${encodeURIComponent(id)}/preview?format=${fmt}`));
    if (box.dataset.format !== fmt) return;  // another placement was picked while this one loaded
    showPreviewFrame(box, p, { title: "The ad as Meta shows it", height: p.height || 560 });
  } catch (err) {
    box.innerHTML = `<p class="preview-error">${esc(err.message)}</p>`;
  }
}

function drawForm(screen, spec) {
  const steps = formSteps(spec);
  const step = steps.includes(screen.dataset.step) ? screen.dataset.step : "intro";
  const me = window.ebadsMe;
  screen.innerHTML = formScreens(spec, (me && me.account && me.account.name) || "Your business")[step];
  const tabs = screen.closest(".cv-show-media").querySelector("[data-show-steps]");
  tabs.hidden = false;
  tabs.innerHTML = steps.map((s) => `<button type="button" role="tab" data-show-step="${s}" aria-selected="${s === step}">${FORM_STEPS[s]}</button>`).join("");
}

async function fillForm(screen) {
  try {
    drawForm(screen, await once(`form:${screen.dataset.showForm}`, () => api(`/api/forms/${encodeURIComponent(screen.dataset.showForm)}/copy`)));
  } catch (err) {
    screen.innerHTML = `<p class="ph-sub">${esc(err.message)}</p>`;
  }
}

// Fills what a freshly drawn answer shows. Each box is filled once (a redraw makes new boxes).
export function loadShows(root) {
  root.querySelectorAll("[data-show-cr]").forEach(fillCr);
  root.querySelectorAll("[data-show-form]").forEach(fillForm);
}

// The placement and step switches inside a shown card. Returns true when the click was one of them.
export function showClick(e) {
  const place = e.target.closest("[data-show-place]");
  if (place) {
    const media = place.closest(".cv-show-media");
    media.querySelectorAll("[data-show-place]").forEach((b) => b.setAttribute("aria-selected", String(b === place)));
    const box = media.querySelector("[data-show-cr]");
    box.dataset.format = place.dataset.showPlace;
    box.innerHTML = previewSkeleton();
    fillCr(box);
    return true;
  }
  const step = e.target.closest("[data-show-step]");
  if (step) {
    const screen = step.closest(".cv-show-media").querySelector("[data-show-form]");
    screen.dataset.step = step.dataset.showStep;
    fillForm(screen);
    return true;
  }
  return false;
}
