// A lead form sketched on a phone, one screen per step: the builder on Lead forms and a form Claude shows in a
// conversation draw it the same way. A close sketch, not Meta's exact layout.
import { esc } from "./ui.js";

export const FORM_SAMPLE = { FULL_NAME: "Maria Lopez", EMAIL: "maria@example.com", PHONE: "(555) 123-4567", COMPANY_NAME: "Lopez Plumbing", JOB_TITLE: "Owner", CITY: "Fontana", ZIP: "92335" };
const FIELD_WORDS = { FULL_NAME: "Full name", EMAIL: "Email", PHONE: "Phone number", COMPANY_NAME: "Company name", JOB_TITLE: "Job title", CITY: "City", ZIP: "Zip code" };
export const FORM_STEPS = { intro: "Intro", questions: "Questions", review: "Review", thanks: "Thanks" };

export const formSteps = (spec) => ["intro", "questions", ...(spec.higher_intent ? ["review"] : []), "thanks"];

// {step: html} for a form spec ({intro_title, intro_bullets, standard, custom, higher_intent, thanks_*}).
// `labels` are Meta's names for the standard questions when the page has them.
export function formScreens(spec, biz, labels = {}) {
  const s = spec;
  const word = (t) => labels[t] || FIELD_WORDS[t] || t;
  const head = `<div class="ph-brand"><span class="ph-logo">${esc(biz.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase())}</span><b>${esc(biz)}</b></div>`;
  const btn = (t) => `<span class="ph-btn">${esc(t)}</span>`;
  const bullets = s.intro_bullets || [], custom = s.custom || [];
  return {
    intro: `${head}<h4>${esc(s.intro_title || "Your headline")}</h4>${bullets.length ? `<ul>${bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : ""}${btn("Continue")}`,
    questions: `${head}<p class="ph-sub">Contact information</p>${["FULL_NAME", "EMAIL", "PHONE", ...(s.standard || [])].map((t) => `<label class="ph-field"><small>${esc(word(t))}</small><span>${esc(FORM_SAMPLE[t] || "")}</span></label>`).join("")}
      ${custom.map((q) => `<p class="ph-q">${esc(q.label || "Your question")}</p>${(q.options || []).length ? q.options.map((o) => `<span class="ph-opt">${esc(o)}</span>`).join("") : '<span class="ph-field"><span class="muted">Type your answer</span></span>'}`).join("")}
      <p class="ph-legal">By clicking Submit, you agree to send your info to ${esc(biz)}, who agrees to use it according to their <u>privacy policy</u>.</p>${btn(s.higher_intent ? "Next" : "Submit")}`,
    review: `${head}<h4>Review your info</h4><p class="ph-sub">Make sure everything is correct before you submit.</p>${["FULL_NAME", "EMAIL", "PHONE"].map((t) => `<p class="ph-review"><small>${esc(word(t))}</small>${esc(FORM_SAMPLE[t])}</p>`).join("")}${btn("Submit")}`,
    thanks: `${head}<div class="ph-done">✓</div><h4>${esc(s.thanks_title || "Thanks, you're all set")}</h4>${s.thanks_body ? `<p>${esc(s.thanks_body)}</p>` : ""}${s.thanks_button === "website" ? btn(s.thanks_button_text || "Visit our website") : ""}`,
  };
}
