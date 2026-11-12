// The builders' stepper (9.4e), shared by New ad, New ad set and New campaign: the steps beside the form,
// each with what was filled in or what is still missing, checked by the server as you type; Create checks
// once more and marks every field that needs something before any confirmation opens.
import { esc, fieldErrors, icon } from "./ui.js";

// "Ad 2: give it a name…" under Ad 2's own field reads better without the prefix.
const short = (m) => { const s = String(m).replace(/^Ad \d+: /, ""); return s.charAt(0).toUpperCase() + s.slice(1); };

// builder({ form, nav, steps: [{ id, name }], summary() → { [step]: text }, check() → Promise<[{ step?, field?, message }]>, onCheck })
// Each step is a `[data-step=<id>]` section of the form; a problem without a step belongs to its field's section.
export function builder({ form, nav, steps, summary, check, onCheck = () => {} }) {
  let problems = null;
  let tried = false;
  let seq = 0;
  let timer;

  const stepOf = (p) => p.step || form.querySelector(`[name="${CSS.escape(p.field || "")}"]`)?.closest("[data-step]")?.dataset.step || "";

  function mark(focus) {
    const seen = new Set();
    const list = (problems || []).filter((p) => p.field && !seen.has(p.field) && seen.add(p.field)).map((p) => ({ field: p.field, message: short(p.message) }));
    return fieldErrors(form, list, { focus });
  }

  function draw() {
    const words = summary();
    nav.innerHTML = `<ol>${steps.map((s, i) => {
      const mine = (problems || []).filter((p) => stepOf(p) === s.id);
      const state = problems === null ? "todo" : !mine.length ? "done" : tried ? "fix" : "todo";
      const line = mine.length ? short(mine[0].message) + (mine.length > 1 ? ` (+${mine.length - 1} more)` : "") : words[s.id] || "";
      const mark = state === "done" ? icon("check") : state === "fix" ? "!" : String(i + 1);
      const said = { done: "done", fix: `${mine.length} to fix`, todo: "to do" }[state];
      return `<li data-state="${state}"><a href="#step-${esc(s.id)}" data-goto-step="${esc(s.id)}"><span class="stepper-n" aria-hidden="true">${mark}</span>
        <span class="stepper-t"><b>${esc(s.name)}<span class="sr-only">, ${said}</span></b>${line ? `<small>${esc(line)}</small>` : ""}</span></a></li>`;
    }).join("")}</ol>`;
  }

  async function run() {
    const mine = ++seq;
    let got;
    try { got = await check(); } catch (err) { return problems; }
    if (mine !== seq) return null;
    problems = got;
    draw();
    if (tried) mark(false);
    onCheck(problems);
    return problems;
  }

  form.querySelectorAll("[data-step]").forEach((sec) => { sec.id = sec.id || `step-${sec.dataset.step}`; });
  nav.addEventListener("click", (e) => {
    const a = e.target.closest("[data-goto-step]");
    if (!a) return;
    e.preventDefault();
    const sec = form.querySelector(`[data-step="${CSS.escape(a.dataset.gotoStep)}"]`);
    if (!sec) return;
    sec.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    const first = sec.querySelector('[aria-invalid="true"]') || sec.querySelector("input:not([type=hidden]):not(.sr-only), select, textarea");
    first?.focus({ preventScroll: true });
  });
  draw();

  return {
    // After any change: checked again a moment after the typing stops.
    soon() { clearTimeout(timer); timer = setTimeout(run, 350); },
    // Before creating: every problem marked at its field (the first one focused). True when nothing is missing.
    async validate() {
      clearTimeout(timer);
      tried = true;
      const mine = ++seq;
      const list = await check();  // a failed check throws to the caller, which says so
      problems = list;
      if (mine === seq) { draw(); onCheck(list); }
      const first = mark(true);
      if (!list.length) return true;
      if (!first) form.querySelector(`[data-step="${CSS.escape(stepOf(list[0]))}"]`)?.scrollIntoView({ block: "start" });
      else if (document.activeElement !== first) {
        // A field whose input can't take focus (Places' hidden list, a file input under another tab):
        // its selected tab or first visible control gets the keyboard instead, so Create always shows where.
        const field = first.closest(".field");
        const usable = (el) => el && !el.disabled && el.getClientRects().length > 0;
        const tab = field.querySelector('[role="tab"][aria-selected="true"]');
        const next = usable(tab) ? tab : [...field.querySelectorAll('input:not([type="hidden"]), select, textarea, button, [tabindex="0"]')].find(usable);
        field.scrollIntoView({ block: "center" });
        next?.focus({ preventScroll: true });
      }
      return false;
    },
    redraw: draw,
    get problems() { return problems; },
  };
}
