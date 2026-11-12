import { api } from "./api.js";
import { boot, confirmDialog, esc, fieldErrors, icon, toast, when, errorState, guardLeaving, markSaved, withFrom } from "./ui.js";
import { count } from "./format.js";

const $ = (id) => document.getElementById(id);
let meta = { standard: {}, limits: {}, max_custom: 3, max_options: 6, privacy_default: "" };
let spec = null;
let step = "intro";
let createdId = null;
// The builder's state: typed since it opened (closing asks first), fields left once (their errors show),
// a Create tried (every error shows), the last check's errors per field.
let dirty = false, tried = false, fieldList = [];
const touched = new Set();
// A form named elsewhere (a lead's form, a change on Today) links here as #form=<id>: its row is marked.
const linkedForm = () => { const m = location.hash.match(/form=([^&]+)/); return m ? decodeURIComponent(m[1]) : null; };

const EXTRA = ["COMPANY_NAME", "JOB_TITLE", "CITY", "ZIP"];
const SAMPLE = { FULL_NAME: "Maria Lopez", EMAIL: "maria@example.com", PHONE: "(555) 123-4567", COMPANY_NAME: "Lopez Plumbing", JOB_TITLE: "Owner", CITY: "Fontana", ZIP: "92335" };
const blank = () => ({
  name: "", intro_title: "", intro_bullets: [], standard: [], custom: [], higher_intent: false,
  privacy_url: meta.privacy_default, thanks_title: "Thanks, you're all set", thanks_body: "",
  thanks_button: "website", thanks_button_text: "Visit our website", thanks_url: me.account.id === 1 ? "https://edgebourne.com" : "",
});

// ---------------------------------------------------------------- list

async function loadList() {
  try {
    const d = await api("/api/forms");
    meta = d;
    // Leads: the ones stored here (what the Leads list shows), linked to that list; Meta's own count beside it
    // when it differs (it counts test leads and leads from before the console).
    const leadsCell = (f) => {
      const here = f.leads_here || 0, meta_ = f.leads_count || 0;
      const link = here ? `<a class="form-leads" href="/leads.html?form=${encodeURIComponent(f.id)}&amp;status=all">${count(here)} ${here === 1 ? "lead" : "leads"}</a>` : '<span class="muted">No leads</span>';
      return `${link}${meta_ !== here ? `<small class="muted">Meta counts ${count(meta_)}</small>` : ""}`;
    };
    const rows = d.items.map((f) => `<tr class="${f.id === createdId || f.id === linkedForm() ? "flash" : ""}" data-form-row="${esc(f.id)}">
      <td class="form-name"><b>${esc(f.name)}</b></td>
      <td class="form-st">${f.status === "ACTIVE" ? '<span class="pill ok">Active</span>' : `<span class="pill">${esc((f.status || "").toLowerCase())}</span>`}</td>
      <td class="num form-n">${leadsCell(f)}</td>
      <td class="form-made">${f.created_time ? `<span class="form-made-l">Made </span>${esc(when(f.created_time))}` : ""}</td>
      <td class="row-actions"><button type="button" class="btn btn-quiet btn-small" data-copy="${esc(f.id)}">Copy into a new form</button>
        <a class="btn btn-quiet btn-small" href="${esc(withFrom(`/new-ad.html?form=${encodeURIComponent(f.id)}`, "/forms.html"))}">Use in a new ad</a></td>
    </tr>`).join("");
    $("list").innerHTML = d.items.length ? `<div class="scroll-x"><table class="table middle form-tbl"><thead><tr><th>Form</th><th>Status</th><th class="num">Leads</th><th>Made</th><th><span class="sr-only">Actions</span></th></tr></thead><tbody>${rows}</tbody></table></div>`
      : '<p class="muted flush">No forms on the Page yet. Start one with New form.</p>';
  } catch (err) { errorState($("list"), err, loadList); }
}

// ---------------------------------------------------------------- builder

const lim = (k) => meta.limits[k] || 999;
const counter = (id, k) => `<span class="hint" data-count="${id}" data-limit="${lim(k)}"></span>`;

function customRow(q, i) {
  return `<div class="q-row" data-q="${i}">
    <div class="field"><label for="q-label-${i}">Question ${i + 1}</label><input class="input" id="q-label-${i}" name="q${i + 1}_label" data-q-label value="${esc(q.label)}" placeholder="e.g. How many people work at your company?" autocomplete="off"></div>
    <div class="field"><label for="q-opts-${i}">Answers to pick from <span class="muted">(one per line; leave empty for a typed answer)</span></label>
      <textarea class="input" id="q-opts-${i}" name="q${i + 1}_options" data-q-opts rows="3" placeholder="1-5&#10;6-20&#10;21 or more">${esc((q.options || []).join("\n"))}</textarea></div>
    <button type="button" class="btn btn-quiet btn-small" data-q-remove>Remove question</button>
  </div>`;
}

function editor() {
  return `<form class="builder" id="form-edit" novalidate>
    <div class="builder-fields stack">
      <div class="panel-head flush-head"><h2>${spec.name && spec.name.endsWith("(copy)") ? "Copy of a form" : "New form"}</h2><span class="spacer"></span><button type="button" class="btn btn-quiet btn-small" data-close>Close</button></div>
      <div class="field"><label for="f-name">Form name <span class="muted">(only you see it)</span></label><input class="input" id="f-name" name="name" value="${esc(spec.name)}" placeholder="Free intro call · Nov 2026" autocomplete="off"></div>
      <fieldset class="field"><legend class="label">Form type</legend>
        <label class="check"><input type="radio" name="type" value="volume" ${spec.higher_intent ? "" : "checked"}> <span>More leads <span class="muted">· quickest to fill in</span></span></label>
        <label class="check"><input type="radio" name="type" value="intent" ${spec.higher_intent ? "checked" : ""}> <span>Fewer, more serious leads <span class="muted">· adds a "check your details" step; only shows on phones</span></span></label>
      </fieldset>
      <h3 class="b-h" data-step="intro">Intro</h3>
      <div class="field" data-step="intro"><label for="f-intro">Headline</label><input class="input" id="f-intro" name="intro_title" value="${esc(spec.intro_title)}" placeholder="Get a free 20-minute intro call" autocomplete="off">${counter("f-intro", "intro_title")}</div>
      <div class="field" data-step="intro"><label for="f-bullets">Points under it <span class="muted">(one per line, up to 3)</span></label><textarea class="input" id="f-bullets" name="intro_bullets" rows="3" placeholder="We look at how you work today&#10;You leave with one thing to fix first">${esc(spec.intro_bullets.join("\n"))}</textarea></div>
      <h3 class="b-h" data-step="questions">Questions</h3>
      <div data-step="questions">
        <p class="muted small flush">Meta fills these in from the person's profile; they can edit them.</p>
        <div class="chips fixed-q">${["Full name", "Email", "Phone number"].map((l) => `<span class="chip">${l}</span>`).join("")}
          ${EXTRA.map((t) => `<label class="chip check-chip"><input type="checkbox" name="standard" value="${t}" ${spec.standard.includes(t) ? "checked" : ""}> ${esc(meta.standard[t] || t)}</label>`).join("")}</div>
      </div>
      <div id="q-list" data-step="questions">${spec.custom.map(customRow).join("")}</div>
      <button type="button" class="btn btn-small" id="q-add" data-step="questions">Add a question of your own</button>
      <div class="field" data-step="questions"><label for="f-privacy">Privacy policy page</label><input class="input" id="f-privacy" name="privacy_url" value="${esc(spec.privacy_url)}" inputmode="url"><span class="hint">Meta requires a web page (not a PDF).</span></div>
      <h3 class="b-h" data-step="thanks">After they send it</h3>
      <div class="field" data-step="thanks"><label for="f-thanks">Thank-you headline</label><input class="input" id="f-thanks" name="thanks_title" value="${esc(spec.thanks_title)}" autocomplete="off">${counter("f-thanks", "thanks_title")}</div>
      <div class="field" data-step="thanks"><label for="f-thanks-body">Message</label><textarea class="input" id="f-thanks-body" name="thanks_body" rows="2" placeholder="We'll call you today.">${esc(spec.thanks_body)}</textarea></div>
      <fieldset class="field" data-step="thanks"><legend class="label">Button</legend>
        <label class="check"><input type="radio" name="thanks_button" value="website" ${spec.thanks_button === "website" ? "checked" : ""}> Opens a web page (your site or a booking link)</label>
        <label class="check"><input type="radio" name="thanks_button" value="none" ${spec.thanks_button === "website" ? "" : "checked"}> No button</label>
      </fieldset>
      <div class="grid-2" id="thanks-link" data-step="thanks" ${spec.thanks_button === "website" ? "" : "hidden"}>
        <div class="field"><label for="f-url">Page it opens</label><input class="input" id="f-url" name="thanks_url" value="${esc(spec.thanks_url)}" inputmode="url"></div>
        <div class="field"><label for="f-btn">Button text</label><input class="input" id="f-btn" name="thanks_button_text" value="${esc(spec.thanks_button_text)}" maxlength="30"></div>
      </div>
      <div id="f-check" role="status"></div>
      <div class="row"><button class="btn btn-primary" type="submit" id="f-create">Create on Meta</button>
        <span class="muted small">Nothing runs until an ad uses the form.</span></div>
    </div>
    <div class="builder-preview">
      <div class="segmented" id="steps" role="tablist" aria-label="Preview" data-tabpanel="phone">${["intro", "questions", ...(spec.higher_intent ? ["review"] : []), "thanks"].map((s) =>
        `<button type="button" role="tab" data-show-step="${s}" aria-selected="${s === step}">${{ intro: "Intro", questions: "Questions", review: "Review", thanks: "Thanks" }[s]}</button>`).join("")}</div>
      <div class="phone" aria-label="How the form looks on a phone"><div class="phone-screen" id="phone"></div></div>
      <p class="muted small flush">A close sketch, not Meta's exact layout.</p>
    </div>
  </form>`;
}

function readSpec() {
  const f = $("form-edit");
  const lines = (v) => v.split("\n").map((x) => x.trim()).filter(Boolean);
  spec = {
    name: f.name.value, intro_title: f.intro_title.value, intro_bullets: lines(f.intro_bullets.value).slice(0, 3),
    standard: [...f.querySelectorAll('[name="standard"]:checked')].map((c) => c.value),
    custom: [...f.querySelectorAll("[data-q]")].map((r) => ({ label: r.querySelector("[data-q-label]").value, options: lines(r.querySelector("[data-q-opts]").value) })),
    higher_intent: f.querySelector('[name="type"]:checked').value === "intent", privacy_url: f.privacy_url.value.trim(),
    thanks_title: f.thanks_title.value, thanks_body: f.thanks_body.value,
    thanks_button: f.querySelector('[name="thanks_button"]:checked').value, thanks_url: f.thanks_url.value.trim(), thanks_button_text: f.thanks_button_text.value,
  };
  return spec;
}

function phone() {
  const s = spec;
  const biz = me.account.name;
  const head = `<div class="ph-brand"><span class="ph-logo">${esc(biz.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase())}</span><b>${esc(biz)}</b></div>`;
  const btn = (t) => `<span class="ph-btn">${esc(t)}</span>`;
  const screens = {
    intro: `${head}<h4>${esc(s.intro_title || "Your headline")}</h4>${s.intro_bullets.length ? `<ul>${s.intro_bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : ""}${btn("Continue")}`,
    questions: `${head}<p class="ph-sub">Contact information</p>${["FULL_NAME", "EMAIL", "PHONE", ...s.standard].map((t) => `<label class="ph-field"><small>${esc(meta.standard[t] || t)}</small><span>${esc(SAMPLE[t] || "")}</span></label>`).join("")}
      ${s.custom.map((q) => `<p class="ph-q">${esc(q.label || "Your question")}</p>${q.options.length ? q.options.map((o) => `<span class="ph-opt">${esc(o)}</span>`).join("") : '<span class="ph-field"><span class="muted">Type your answer</span></span>'}`).join("")}
      <p class="ph-legal">By clicking Submit, you agree to send your info to ${esc(biz)}, who agrees to use it according to their <u>privacy policy</u>.</p>${btn(s.higher_intent ? "Next" : "Submit")}`,
    review: `${head}<h4>Review your info</h4><p class="ph-sub">Make sure everything is correct before you submit.</p>${["FULL_NAME", "EMAIL", "PHONE"].map((t) => `<p class="ph-review"><small>${esc(meta.standard[t] || t)}</small>${esc(SAMPLE[t])}</p>`).join("")}${btn("Submit")}`,
    thanks: `${head}<div class="ph-done">✓</div><h4>${esc(s.thanks_title || "Thanks, you're all set")}</h4>${s.thanks_body ? `<p>${esc(s.thanks_body)}</p>` : ""}${s.thanks_button === "website" ? btn(s.thanks_button_text || "Visit our website") : ""}`,
  };
  if (!screens[step] || (step === "review" && !s.higher_intent)) step = "intro";
  $("phone").innerHTML = screens[step];
  document.querySelectorAll("#steps [data-show-step]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.showStep === step)));
}

function counts() {
  document.querySelectorAll("[data-count]").forEach((h) => {
    const n = $(h.dataset.count).value.length, max = Number(h.dataset.limit);
    h.textContent = `${n} / ${max}`;
    h.classList.toggle("over", n > max);
  });
}

// Errors show at their field once it has been left or holds something (a prohibited word shows as it is
// typed), and all of them once Create was tried; the field being typed in keeps its focus.
function markFields({ focus = false } = {}) {
  const f = $("form-edit");
  if (!f) return null;
  const shown = fieldList.filter(({ field }) => {
    if (tried) return true;
    const input = f.querySelector(`[name="${CSS.escape(field)}"]`);
    return input && (touched.has(field) || input.value.trim());
  });
  return fieldErrors(f, shown, { focus });
}

let checkSeq = 0;
async function check() {
  const mine = ++checkSeq;
  try {
    const r = await api("/api/forms/check", { method: "POST", body: spec });
    if (mine !== checkSeq) return null;
    fieldList = r.fields || [];
    markFields();
    const box = $("f-check");
    if (r.policy.length) {
      box.innerHTML = `<div class="note bad"><b>Meta would stop ads using this form:</b><ul>${r.policy.map((p) => `<li>${esc(p.where)}: ${esc(p.why)}</li>`).join("")}</ul></div>`;
    } else if (r.problems.length) {
      box.innerHTML = `<div class="note"><b>Still to do:</b><ul>${r.problems.map((p) => `<li>${esc(p.message)}</li>`).join("")}</ul></div>`;
    } else {
      box.innerHTML = '<div class="note ok">Ready. It passes the lead form rules we can check (no prohibited questions, a privacy page).</div>';
    }
    return r;
  } catch (err) { return null; /* the check is advisory; creating checks again */ }
}

let timer;
function changed(e) {
  if (e) dirty = true;
  readSpec();
  counts();
  const tabs = ["intro", "questions", ...(spec.higher_intent ? ["review"] : []), "thanks"];
  if ($("steps").children.length !== tabs.length) {
    $("steps").innerHTML = tabs.map((s) => `<button type="button" role="tab" data-show-step="${s}" aria-selected="${s === step}">${{ intro: "Intro", questions: "Questions", review: "Review", thanks: "Thanks" }[s]}</button>`).join("");
  }
  $("thanks-link").hidden = spec.thanks_button !== "website";
  phone();
  clearTimeout(timer);
  timer = setTimeout(check, 300);
}

// Closing, or starting another form, over typed work asks first.
async function mayDiscard() {
  if (!dirty || !$("form-edit")) return true;
  return confirmDialog({ title: "Throw away this form?", body: "<p>What you typed isn't on Meta yet. Closing it loses it.</p>",
    confirm: "Throw it away", cancel: "Keep editing", danger: true });
}
function closeBuilder() {
  const f = $("form-edit");
  if (f) markSaved(f);
  $("builder").hidden = true; $("builder").innerHTML = "";
  dirty = false;
}

function openBuilder(start) {
  spec = start;
  step = "intro";
  dirty = false; tried = false; fieldList = []; touched.clear();
  const box = $("builder");
  box.hidden = false;
  box.innerHTML = editor();
  const f = $("form-edit");
  syncQ();
  changed();
  f.addEventListener("input", changed);
  f.addEventListener("change", changed);
  f.addEventListener("focusout", (e) => {
    if (e.target.name && e.target.matches("input, textarea")) { touched.add(e.target.name); markFields(); }
  });
  f.addEventListener("focusin", (e) => {
    const s = e.target.closest("[data-step]");
    if (s && s.dataset.step !== step) { step = s.dataset.step; phone(); }
  });
  f.addEventListener("click", (e) => {
    const t = e.target.closest("[data-show-step]");
    if (t) { step = t.dataset.showStep; phone(); return; }
    if (e.target.closest("[data-close]")) { mayDiscard().then((ok) => { if (ok) closeBuilder(); }); return; }
    if (e.target.closest("#q-add")) {
      const n = f.querySelectorAll("[data-q]").length;
      $("q-list").insertAdjacentHTML("beforeend", customRow({ label: "", options: [] }, n));
      syncQ(); step = "questions"; changed(e); $(`q-label-${n}`).focus();
      return;
    }
    const rm = e.target.closest("[data-q-remove]");
    if (rm) {
      rm.closest("[data-q]").remove();
      readSpec();
      $("q-list").innerHTML = spec.custom.map(customRow).join("");
      syncQ(); changed(e);
    }
  });
  f.addEventListener("submit", create);
  box.scrollIntoView({ block: "start" });
  f.name.focus();
}

function syncQ() { $("q-add").hidden = $("form-edit").querySelectorAll("[data-q]").length >= meta.max_custom; }

async function create(e) {
  e.preventDefault();
  const f = $("form-edit");
  const btn = e.submitter || f.querySelector("button[type=submit]");
  if (btn.disabled) return;
  readSpec();
  tried = true;
  clearTimeout(timer);
  const r = await check();
  if (r && r.fields.length) {
    markFields({ focus: true });
    // Count what is marked: a problem with no input of its own (too many questions) is only in the summary.
    const marked = f.querySelectorAll(".field.error").length;
    toast(marked ? `Fix ${marked === 1 ? "the marked field" : `the ${marked} marked fields`} first` : "Fix what's listed above first", "bad");
    if (!marked) $("f-check").scrollIntoView({ block: "nearest" });
    return;
  }
  const yes = await confirmDialog({ title: `Create “${spec.name}” on Meta?`,
    body: "<p>It's saved on the Facebook Page. Meta doesn't allow changes afterwards, so to change it later you copy it into a new form.</p><p class=\"muted\">Nothing runs and nothing is spent until an ad uses it.</p>",
    confirm: "Create form" });
  if (!yes) return;
  btn.disabled = true;  // a second create while Meta answers would make a second form on the Page
  try {
    const made = await api("/api/forms", { method: "POST", body: spec });
    createdId = made.id;
    closeBuilder();
    toast("Form created on the Page");
    await loadList();
  } catch (err) {
    btn.disabled = false;
    if (err.body && err.body.fields && err.body.fields.length) { fieldList = err.body.fields; markFields({ focus: true }); toast(err.message, "bad"); }
    else toast(err.message, "bad");
  }
}

const me = await boot({ page: "forms", admin: true });
if (me) {
  guardLeaving();
  $("crumb").innerHTML = `${icon("back")}<span>Ads</span>`;
  // #form=<id> (a lead's form, the command menu): that form, in view and marked; again when the link changes.
  const showLinked = () => {
    const linked = linkedForm() && document.querySelector(`[data-form-row="${CSS.escape(linkedForm())}"]`);
    if (linked) linked.scrollIntoView({ block: "center" });
    else if (linkedForm()) toast("That form isn't on the Page any more.");
  };
  await loadList();
  showLinked();
  addEventListener("hashchange", async () => { await loadList(); showLinked(); });
  $("new-form").addEventListener("click", async () => { if (await mayDiscard()) openBuilder(blank()); });
  $("list").addEventListener("click", async (e) => {
    const c = e.target.closest("[data-copy]");
    if (!c || !(await mayDiscard())) return;
    try { openBuilder(await api(`/api/forms/${encodeURIComponent(c.dataset.copy)}/copy`)); } catch (err) { toast(err.message, "bad"); }
  });
}
