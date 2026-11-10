import { api } from "./api.js";
import { boot, confirmDialog, esc, fieldError, icon, toast, when } from "./ui.js";
import { count } from "./format.js";

const $ = (id) => document.getElementById(id);
let meta = { standard: {}, limits: {}, max_custom: 3, max_options: 6, privacy_default: "" };
let spec = null;
let step = "intro";
let createdId = null;

const EXTRA = ["COMPANY_NAME", "JOB_TITLE", "CITY", "ZIP"];
const SAMPLE = { FULL_NAME: "Maria Lopez", EMAIL: "maria@example.com", PHONE: "(555) 123-4567", COMPANY_NAME: "Lopez Plumbing", JOB_TITLE: "Owner", CITY: "Fontana", ZIP: "92335" };
const blank = () => ({
  name: "", intro_title: "", intro_bullets: [], standard: [], custom: [], higher_intent: false,
  privacy_url: meta.privacy_default, thanks_title: "Thanks, you're all set", thanks_body: "",
  thanks_button: "website", thanks_button_text: "Visit our website", thanks_url: "https://edgebourne.com",
});

// ---------------------------------------------------------------- list

async function loadList() {
  try {
    const d = await api("/api/forms");
    meta = d;
    const rows = d.items.map((f) => `<tr class="${f.id === createdId ? "flash" : ""}">
      <td><b>${esc(f.name)}</b></td>
      <td>${f.status === "ACTIVE" ? '<span class="pill ok">Active</span>' : `<span class="pill">${esc((f.status || "").toLowerCase())}</span>`}</td>
      <td class="num">${count(f.leads_count || 0)}</td>
      <td>${f.created_time ? esc(when(f.created_time)) : ""}</td>
      <td class="row-actions"><button type="button" class="btn btn-quiet btn-small" data-copy="${esc(f.id)}">Copy into a new form</button>
        <a class="btn btn-quiet btn-small" href="/new-ad.html?form=${encodeURIComponent(f.id)}">Use in a new ad</a></td>
    </tr>`).join("");
    $("list").innerHTML = d.items.length ? `<div class="scroll-x"><table class="table middle"><thead><tr><th>Form</th><th>Status</th><th class="num">Leads</th><th>Made</th><th><span class="sr-only">Actions</span></th></tr></thead><tbody>${rows}</tbody></table></div>`
      : '<p class="muted flush">No forms on the Page yet. Start one with New form.</p>';
  } catch (err) { $("list").innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

// ---------------------------------------------------------------- builder

const lim = (k) => meta.limits[k] || 999;
const counter = (id, k) => `<span class="hint" data-count="${id}" data-limit="${lim(k)}"></span>`;

function customRow(q, i) {
  return `<div class="q-row" data-q="${i}">
    <div class="field"><label for="q-label-${i}">Question ${i + 1}</label><input class="input" id="q-label-${i}" data-q-label value="${esc(q.label)}" placeholder="e.g. How many people work at your company?" autocomplete="off"></div>
    <div class="field"><label for="q-opts-${i}">Answers to pick from <span class="muted">(one per line; leave empty for a typed answer)</span></label>
      <textarea class="input" id="q-opts-${i}" data-q-opts rows="3" placeholder="1-5&#10;6-20&#10;21 or more">${esc((q.options || []).join("\n"))}</textarea></div>
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
      <div class="field" data-step="thanks"><label for="f-thanks-body">Message</label><textarea class="input" id="f-thanks-body" name="thanks_body" rows="2" placeholder="Eugene will call you today from (909) …">${esc(spec.thanks_body)}</textarea></div>
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
      <div class="segmented" id="steps" role="tablist" aria-label="Preview">${["intro", "questions", ...(spec.higher_intent ? ["review"] : []), "thanks"].map((s) =>
        `<button type="button" role="tab" data-show-step="${s}" aria-pressed="${s === step}">${{ intro: "Intro", questions: "Questions", review: "Review", thanks: "Thanks" }[s]}</button>`).join("")}</div>
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
  const head = '<div class="ph-brand"><span class="ph-logo">EB</span><b>Edge Bourne Consulting</b></div>';
  const btn = (t) => `<span class="ph-btn">${esc(t)}</span>`;
  const screens = {
    intro: `${head}<h4>${esc(s.intro_title || "Your headline")}</h4>${s.intro_bullets.length ? `<ul>${s.intro_bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : ""}${btn("Continue")}`,
    questions: `${head}<p class="ph-sub">Contact information</p>${["FULL_NAME", "EMAIL", "PHONE", ...s.standard].map((t) => `<label class="ph-field"><small>${esc(meta.standard[t] || t)}</small><span>${esc(SAMPLE[t] || "")}</span></label>`).join("")}
      ${s.custom.map((q) => `<p class="ph-q">${esc(q.label || "Your question")}</p>${q.options.length ? q.options.map((o) => `<span class="ph-opt">${esc(o)}</span>`).join("") : '<span class="ph-field"><span class="muted">Type your answer</span></span>'}`).join("")}
      <p class="ph-legal">By clicking Submit, you agree to send your info to Edge Bourne Consulting, who agrees to use it according to their <u>privacy policy</u>.</p>${btn(s.higher_intent ? "Next" : "Submit")}`,
    review: `${head}<h4>Review your info</h4><p class="ph-sub">Make sure everything is correct before you submit.</p>${["FULL_NAME", "EMAIL", "PHONE"].map((t) => `<p class="ph-review"><small>${esc(meta.standard[t] || t)}</small>${esc(SAMPLE[t])}</p>`).join("")}${btn("Submit")}`,
    thanks: `${head}<div class="ph-done">✓</div><h4>${esc(s.thanks_title || "Thanks, you're all set")}</h4>${s.thanks_body ? `<p>${esc(s.thanks_body)}</p>` : ""}${s.thanks_button === "website" ? btn(s.thanks_button_text || "Visit our website") : ""}`,
  };
  if (!screens[step] || (step === "review" && !s.higher_intent)) step = "intro";
  $("phone").innerHTML = screens[step];
  document.querySelectorAll("#steps [data-show-step]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.showStep === step)));
}

function counts() {
  document.querySelectorAll("[data-count]").forEach((h) => {
    const n = $(h.dataset.count).value.length, max = Number(h.dataset.limit);
    h.textContent = `${n} / ${max}`;
    h.classList.toggle("over", n > max);
  });
}

let checkSeq = 0;
async function check() {
  const mine = ++checkSeq;
  try {
    const r = await api("/api/forms/check", { method: "POST", body: spec });
    if (mine !== checkSeq) return;
    const box = $("f-check");
    if (r.policy.length) {
      box.innerHTML = `<div class="note bad"><b>Meta would stop ads using this form:</b><ul>${r.policy.map((p) => `<li>${esc(p.where)}: ${esc(p.why)}</li>`).join("")}</ul></div>`;
    } else if (r.problems.length) {
      box.innerHTML = `<div class="note"><b>Still to do:</b><ul>${r.problems.map((p) => `<li>${esc(p.message)}</li>`).join("")}</ul></div>`;
    } else {
      box.innerHTML = '<div class="note ok">Ready. It passes the lead form rules we can check (no prohibited questions, a privacy page).</div>';
    }
    $("f-create").disabled = !!(r.policy.length || r.problems.length);
  } catch (err) { /* the check is advisory; creating checks again */ }
}

let timer;
function changed() {
  readSpec();
  counts();
  const tabs = ["intro", "questions", ...(spec.higher_intent ? ["review"] : []), "thanks"];
  if ($("steps").children.length !== tabs.length) {
    $("steps").innerHTML = tabs.map((s) => `<button type="button" role="tab" data-show-step="${s}" aria-pressed="${s === step}">${{ intro: "Intro", questions: "Questions", review: "Review", thanks: "Thanks" }[s]}</button>`).join("");
  }
  $("thanks-link").hidden = spec.thanks_button !== "website";
  phone();
  clearTimeout(timer);
  timer = setTimeout(check, 300);
}

function openBuilder(start) {
  spec = start;
  step = "intro";
  const box = $("builder");
  box.hidden = false;
  box.innerHTML = editor();
  const f = $("form-edit");
  syncQ();
  changed();
  f.addEventListener("input", changed);
  f.addEventListener("change", changed);
  f.addEventListener("focusin", (e) => {
    const s = e.target.closest("[data-step]");
    if (s && s.dataset.step !== step) { step = s.dataset.step; phone(); }
  });
  f.addEventListener("click", (e) => {
    const t = e.target.closest("[data-show-step]");
    if (t) { step = t.dataset.showStep; phone(); return; }
    if (e.target.closest("[data-close]")) { box.hidden = true; box.innerHTML = ""; return; }
    if (e.target.closest("#q-add")) {
      const n = f.querySelectorAll("[data-q]").length;
      $("q-list").insertAdjacentHTML("beforeend", customRow({ label: "", options: [] }, n));
      syncQ(); step = "questions"; changed(); $(`q-label-${n}`).focus();
      return;
    }
    const rm = e.target.closest("[data-q-remove]");
    if (rm) {
      rm.closest("[data-q]").remove();
      readSpec();
      $("q-list").innerHTML = spec.custom.map(customRow).join("");
      syncQ(); changed();
    }
  });
  f.addEventListener("submit", create);
  box.scrollIntoView({ block: "start" });
  f.name.focus();
}

function syncQ() { $("q-add").hidden = $("form-edit").querySelectorAll("[data-q]").length >= meta.max_custom; }

async function create(e) {
  e.preventDefault();
  readSpec();
  const f = $("form-edit");
  fieldError(f, null);
  const yes = await confirmDialog({ title: `Create “${spec.name}” on Meta?`,
    body: "<p>It's saved on the Facebook Page. Meta doesn't allow changes afterwards, so to change it later you copy it into a new form.</p><p class=\"muted\">Nothing runs and nothing is spent until an ad uses it.</p>",
    confirm: "Create form" });
  if (!yes) return;
  try {
    const r = await api("/api/forms", { method: "POST", body: spec });
    createdId = r.id;
    $("builder").hidden = true; $("builder").innerHTML = "";
    toast("Form created on the Page");
    await loadList();
  } catch (err) {
    if (err.body && err.body.field) fieldError(f, err.body.field, err.message); else toast(err.message, "bad");
  }
}

const me = await boot({ page: "ads", admin: true });
if (me) {
  $("crumb").innerHTML = `${icon("back")}<span>Ads</span>`;
  await loadList();
  $("new-form").addEventListener("click", () => openBuilder(blank()));
  $("list").addEventListener("click", async (e) => {
    const c = e.target.closest("[data-copy]");
    if (!c) return;
    try { openBuilder(await api(`/api/forms/${encodeURIComponent(c.dataset.copy)}/copy`)); } catch (err) { toast(err.message, "bad"); }
  });
}
