// AM-D: Ads → Audiences. Every audience of the account (custom, lookalike, saved) with what it is, how big, whether it's ready and
// which ad sets use it; owners and account admins make website, engagement and lookalike audiences in a three-step dialog (Who,
// Details, Name and check). Teammates read; clients never see the page. Meta's names and status are plain text (esc) everywhere.
import { api } from "./api.js";
import { boot, entityLink, esc, errorState, toast, icon, emptyState } from "./ui.js";
import { clock } from "./format.js";
import * as UrlState from "./urlstate.js";

const $ = (id) => document.getElementById(id);
const KINDS = [["all", "All"], ["website", "Website"], ["engagement", "Engagement"], ["lookalike", "Lookalike"], ["saved", "Saved"], ["customer_list", "Customer list"]];
const STATUS = { ready: ["ok", "Ready"], filling: ["info", "Filling"], too_small: ["warn", "Too small to use yet"], problem: ["bad", "Problem"] };
const group = (a) => (a.kind === "saved" ? "saved" : a.kind === "lookalike" ? "lookalike" : a.source_kind === "website" ? "website"
  : a.source_kind === "customer_list" ? "customer_list" : "engagement");
const linked = () => { const m = location.hash.match(/aud=(\d+)/); return m ? m[1] : null; };
let state = { kind: "all", ready: false };
try { state = { ...state, ...JSON.parse(localStorage.getItem("ebads-aud") || "{}") }; } catch (e) { /* defaults */ }
let data = null;
let madeId = null;

function pill(a) {
  if (a.kind === "saved") return '<span class="pill">Saved targeting</span>';
  const [cls, label] = STATUS[a.ready] || ["", a.ready || "—"];
  return `<span class="pill ${cls}"${a.ready === "problem" || a.ready === "too_small" ? ` title="${esc(a.status_words || "")}"` : ""}>${esc(label)}</span>`;
}

function usedHtml(a) {
  if (a.kind === "saved") return '<span class="muted small">Fills in places and ages when an ad set starts from it</span>';
  const all = [...a.used.include.map((s) => [s, "Included"]), ...a.used.exclude.map((s) => [s, "Left out"])];
  if (!all.length) return '<span class="muted">Not used yet</span>';
  return `<details class="aud-usedd"><summary>${esc(a.used_words)}</summary><ul class="aud-usedl">${all.map(([s, how]) =>
    `<li>${entityLink("adset", s.id, s.name)} <span class="muted small">${how}</span></li>`).join("")}</ul></details>`;
}

function rowHtml(a) {
  const mark = a.id === madeId || a.id === linked();
  return `<tr data-aud-row="${esc(a.id)}"${mark ? ' class="flash"' : ""}>
    <td class="aud-name"><b>${esc(a.name)}</b><span class="muted small">${esc(a.describe)}</span>${a.ready === "problem" ? `<span class="aud-why">${esc(a.status_words || "")}</span>` : ""}</td>
    <td class="aud-size">${a.kind === "saved" ? '<span class="muted">—</span>' : esc(a.size_words)}</td>
    <td class="aud-st">${pill(a)}</td>
    <td class="aud-kind">${esc(a.kind_words)}</td>
    <td class="aud-used">${usedHtml(a)}</td>
    <td class="aud-made muted small">${esc(a.made_words)}</td>
  </tr>`;
}

function draw() {
  if (!data) return;
  const counts = Object.fromEntries(KINDS.map(([k]) => [k, data.items.filter((a) => k === "all" || group(a) === k).length]));
  $("aud-kinds").innerHTML = KINDS.filter(([k]) => k === "all" || counts[k]).map(([k, l]) =>
    `<button type="button" class="view-chip" data-aud-kind="${k}" aria-pressed="${state.kind === k}">${l}<span>${counts[k]}</span></button>`).join("");
  $("aud-ready").checked = state.ready;
  const shown = data.items.filter((a) => (state.kind === "all" || group(a) === state.kind) && (!state.ready || a.ready === "ready"));
  const read = data.read_at ? `Read from Meta ${clock(data.read_at)}` : "Not read from Meta yet";
  $("aud-source").textContent = data.error ? `${read}. Meta didn't answer just now: ${data.error}` : read;
  if (!data.items.length) {
    $("aud-list").innerHTML = emptyState({ title: "No audiences yet", panel: false,
      body: data.can_edit ? "Make one from your website visitors, the people who opened your lead form or watched a video, then people like them."
        : "Nobody has made an audience for this account yet." });
    return;
  }
  $("aud-list").innerHTML = shown.length ? `<div class="scroll-x"><table class="table middle aud-tbl"><thead><tr><th>Audience</th><th>Size</th><th>Status</th><th>Kind</th><th>Where it's used</th><th><span class="sr-only">Made</span></th></tr></thead>
    <tbody>${shown.map(rowHtml).join("")}</tbody></table></div>` : '<p class="muted flush">Nothing matches these filters.</p>';
  const flash = document.querySelector("tr.flash");
  if (flash) flash.scrollIntoView({ block: "nearest" });
}

async function load() {
  try {
    data = await api("/api/audiences");
    $("aud-new").hidden = !data.can_edit;
    $("aud-refresh").hidden = !data.can_edit;
    draw();
  } catch (err) { errorState($("aud-list"), err, load, null, { panel: false }); }
}

function remember() { try { localStorage.setItem("ebads-aud", JSON.stringify(state)); } catch (e) { /* private window */ } }

// ---------------------------------------------------------------- New audience

const WHO_CARDS = [
  ["website", "Website visitors", "People who visited your website (from your Pixel)"],
  ["page", "People who engaged with your Facebook Page", "Liked, commented, messaged or visited"],
  ["instagram", "People who engaged with your Instagram account", "Visited the profile, messaged or interacted"],
  ["lead_form", "People who opened or sent a lead form", "From your Instant Forms"],
  ["video", "People who watched a video", "Of the videos in your ad account"],
  ["lookalike", "People like an audience you have", "A lookalike: new people similar to them"],
];
const RATIO_WORDS = { 0.01: "most like them", 0.02: "", 0.03: "", 0.05: "", 0.1: "broader" };
const STEP_NAMES = ["Who", "Details", "Name and check"];

async function openNew() {
  let src;
  try { src = await api("/api/audiences/sources"); } catch (err) { toast(err.message, "bad"); return; }
  const key = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const st = { step: 0, kind: null, who: {}, days: {}, url: "", source: {}, origin: "", country: src.countries[0], ratio: 0.01, name: "", nameTouched: false, describe: "", size: "" };
  const okOrigins = src.origins.filter((o) => !o.why_not);
  const off = { website: !src.pixel && "This account has no Pixel set in Settings → Meta.", page: !src.page && "This account has no Facebook Page set in Settings → Meta.",
    instagram: !src.instagram && "The Facebook Page has no Instagram account connected.", lead_form: !src.forms.length && "No lead forms on the Page yet.",
    video: !src.videos.length && "No videos in the ad account yet.", lookalike: !okOrigins.length && "None of your audiences can be a source yet (they need 100 people and to be ready)." };
  const dlg = document.createElement("dialog");
  dlg.className = "aud-dialog";
  dlg.setAttribute("aria-labelledby", "aud-d-title");
  document.body.appendChild(dlg);

  const daysMax = () => src.retention_max[st.kind] || 30;
  const days = () => Math.min(st.days[st.kind] ?? Math.min(30, daysMax()), daysMax());
  const who = () => st.who[st.kind] || ((src.who[st.kind] || [])[0] || {}).value || "";
  const spec = () => ({ name: st.name, days: days(), who: who(), url: st.url, source_id: st.source[st.kind] || "",
    origin_id: st.origin, country: st.country, ratio: st.ratio });
  const err = (f) => `<p class="err aud-err" id="aud-err-${f}" role="alert" hidden></p>`;
  const radios = (name, list, val) => `<div class="aud-radios" role="radiogroup" aria-label="Who">${list.map((o) =>
    `<label class="check"><input type="radio" name="${name}" value="${esc(o.value)}" ${o.value === val ? "checked" : ""}> ${esc(o.label)}</label>`).join("")}</div>`;
  const select = (id, label, list, val, extra = "") => `<div class="field"><label for="${id}">${label}</label><select class="input" id="${id}">${list.map((o) =>
    `<option value="${esc(o.id)}" ${o.id === val ? "selected" : ""} ${o.disabled ? "disabled" : ""}>${esc(o.label)}</option>`).join("")}</select>${extra}</div>`;

  const details = () => {
    const k = st.kind;
    if (k === "lookalike") {
      const origins = src.origins.map((o) => ({ id: o.id, label: `${o.name} · ${o.why_not ? "can't be a source yet" : o.size_words}`, disabled: Boolean(o.why_not) }));
      if (!st.origin) st.origin = (okOrigins[0] || {}).id || "";
      const pick = src.origins.find((o) => o.id === st.origin);
      return `${select("aud-origin", "People like…", origins, st.origin)}${err("origin")}
        <p class="muted small flush" id="aud-origin-note">${esc(pick ? pick.describe : "")}</p>
        ${select("aud-country", "In which country", src.countries.map((c) => ({ id: c, label: c === "US" ? "United States" : c })), st.country)}${err("country")}
        <div class="field"><span class="label" id="aud-ratio-l">How close</span><div class="segmented wraps" role="group" aria-labelledby="aud-ratio-l">${src.ratios.map((r) =>
          `<button type="button" data-ratio="${r}" aria-pressed="${r === st.ratio}">${Math.round(r * 100)} %${RATIO_WORDS[r] ? ` <span class="muted">${RATIO_WORDS[r]}</span>` : ""}</button>`).join("")}</div>${err("ratio")}
          <span class="hint">Meta needs at least ${src.min_source} people in one country in the source. Smaller is closer; bigger reaches more people.</span></div>`;
    }
    const list = src.who[k];
    let head = "";
    if (k === "lead_form") {
      if (!st.source.lead_form) st.source.lead_form = src.forms[0].id;
      head = `${select("aud-src", "Which lead form", src.forms.map((f) => ({ id: f.id, label: f.name })), st.source.lead_form)}${err("source")}`;
    } else if (k === "video") {
      if (!st.source.video) st.source.video = src.videos[0].id;
      head = `${select("aud-src", "Which video", src.videos.map((v) => ({ id: v.id, label: v.name })), st.source.video)}${err("source")}`;
    } else {
      head = `<p class="small flush">${esc(k === "website" ? `From your Pixel (${src.pixel})` : k === "page" ? `Your Page: ${src.page_name || src.page}` : `Instagram: @${src.instagram_name || src.instagram}`)}</p>${err("source")}`;
    }
    return `${head}
      <fieldset class="aud-set"><legend>Who it includes</legend>${radios("aud-who", list, who())}${err("who")}</fieldset>
      <div class="field" id="aud-url-f" ${k === "website" && who() === "visited_url" ? "" : "hidden"}><label for="aud-url">The page's address contains</label>
        <input class="input" id="aud-url" value="${esc(st.url)}" placeholder="pricing" autocomplete="off" inputmode="url">${err("url")}</div>
      <div class="field"><label for="aud-days">How many days back <output id="aud-days-out" for="aud-days">${days()} days</output></label>
        <input type="range" class="aud-range" id="aud-days" min="1" max="${daysMax()}" value="${days()}">
        <span class="hint">Up to ${daysMax()} days for this kind of audience.</span>${err("days")}</div>`;
  };

  const body = () => {
    if (st.step === 0) {
      // One Tab stop (the picked card, or the first that can be picked); arrows move between the cards that can be picked.
      const stop = st.kind && !off[st.kind] ? st.kind : (WHO_CARDS.find(([k]) => !off[k]) || [])[0];
      return `<div class="aud-kinds" role="radiogroup" aria-label="Who">${WHO_CARDS.map(([k, t, sub]) => `<button type="button" class="aud-kind-opt" data-aud-k="${k}" role="radio"
        aria-checked="${st.kind === k}" tabindex="${k === stop ? 0 : -1}" ${off[k] ? 'aria-disabled="true"' : ""}><b>${esc(t)}</b><span class="muted small">${esc(off[k] || sub)}</span></button>`).join("")}</div>${err("kind")}`;
    }
    if (st.step === 1) return details();
    return `<div class="field"><label for="aud-name">Name <span class="muted">(shown in this console and in Meta's Ads Manager)</span></label><input class="input" id="aud-name" value="${esc(st.name)}" maxlength="200" autocomplete="off">${err("name")}</div>
      <div class="aud-sum"><b>What it is</b><p class="flush" id="aud-describe">${esc(st.describe)}</p>${st.size ? `<p class="muted small flush">${esc(st.size)}</p>` : ""}
        <p class="muted small flush">Meta fills it over the next few hours. Nothing spends: it's used only when an ad set includes it or leaves it out.</p></div>
      <p class="err" id="aud-err-make" role="alert" hidden></p>`;
  };

  const render = () => {
    dlg.innerHTML = `<form method="dialog" novalidate class="aud-form">
      <header class="aud-head"><h2 id="aud-d-title">New audience</h2>
        <button type="button" class="btn btn-quiet aud-x" data-aud-close aria-label="Close">${icon("close")}</button></header>
      <ol class="aud-steps">${STEP_NAMES.map((n, i) => `<li ${i === st.step ? 'aria-current="step"' : ""} data-state="${i < st.step ? "done" : i === st.step ? "now" : "todo"}"><span>${i + 1}</span> ${n}</li>`).join("")}</ol>
      <div class="aud-body" id="aud-body">${body()}</div>
      <footer class="row end aud-foot">${st.step ? '<button type="button" class="btn" id="aud-back">Back</button>' : '<button type="button" class="btn" data-aud-close>Cancel</button>'}
        <button type="submit" class="btn btn-primary" id="aud-next">${st.step === 2 ? "Make the audience" : "Next"}</button></footer>
    </form>`;
    const first = dlg.querySelector(".aud-body input:not([type=hidden]), .aud-body select, .aud-body [data-aud-k]:not([aria-disabled])");
    if (first) first.focus({ preventScroll: true });
  };
  const showErr = (problems) => {
    dlg.querySelectorAll(".aud-err").forEach((e) => { e.hidden = true; });
    let shown = false;
    for (const p of problems) {
      const box = dlg.querySelector(`#aud-err-${p.field}`) || dlg.querySelector("#aud-err-make");
      if (box) { box.textContent = p.message; box.hidden = false; shown = true; }
    }
    if (!shown && problems.length) toast(problems[0].message, "bad");
  };

  let closed = false;
  const onPop = () => { if (!closed) close(true); };
  function close(fromHistory = false) {
    if (closed) return;
    closed = true;
    removeEventListener("popstate", onPop);
    if (dlg.open) dlg.close();
    dlg.remove();
    if (!fromHistory) UrlState.closeLayer(location.pathname + location.search);
  }

  function pickKind(k) {
    st.kind = k.dataset.audK;
    dlg.querySelectorAll("[data-aud-k]").forEach((b) => { b.setAttribute("aria-checked", String(b === k)); b.tabIndex = b === k ? 0 : -1; });
  }
  dlg.addEventListener("keydown", (e) => {
    const k = e.target.closest("[data-aud-k]");
    const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key];
    if (!k || !step) return;
    e.preventDefault();
    const cards = [...dlg.querySelectorAll("[data-aud-k]:not([aria-disabled=true])")];
    const next = cards[(cards.indexOf(k) + step + cards.length) % cards.length];
    if (next) { pickKind(next); next.focus(); }
  });
  dlg.addEventListener("cancel", (e) => { e.preventDefault(); close(); });
  dlg.addEventListener("click", (e) => {
    if (e.target.closest("[data-aud-close]")) { close(); return; }
    if (e.target.closest("#aud-back")) { st.step -= 1; render(); return; }
    const k = e.target.closest("[data-aud-k]");
    if (k) {
      if (k.getAttribute("aria-disabled") === "true") return;
      pickKind(k);
      return;
    }
    const r = e.target.closest("[data-ratio]");
    if (r) { st.ratio = Number(r.dataset.ratio); dlg.querySelectorAll("[data-ratio]").forEach((b) => b.setAttribute("aria-pressed", String(b === r))); }
  });
  dlg.addEventListener("input", (e) => {
    const t = e.target;
    if (t.id === "aud-days") { st.days[st.kind] = Number(t.value); $("aud-days-out").textContent = `${t.value} days`; }
    if (t.id === "aud-url") st.url = t.value;
    if (t.id === "aud-name") { st.name = t.value; st.nameTouched = true; }
  });
  dlg.addEventListener("change", (e) => {
    const t = e.target;
    if (t.name === "aud-who") { st.who[st.kind] = t.value; const f = $("aud-url-f"); if (f) f.hidden = !(st.kind === "website" && t.value === "visited_url"); }
    if (t.id === "aud-src") st.source[st.kind] = t.value;
    if (t.id === "aud-origin") { st.origin = t.value; const o = src.origins.find((x) => x.id === t.value); $("aud-origin-note").textContent = o ? o.describe : ""; }
    if (t.id === "aud-country") st.country = t.value;
  });
  dlg.addEventListener("submit", async (e) => {
    e.preventDefault();
    const next = $("aud-next");
    if (st.step === 0) {
      if (!st.kind) { showErr([{ field: "kind", message: "Pick who the audience is made of." }]); return; }
      st.step = 1; render(); return;
    }
    next.disabled = true;
    try {
      if (st.step === 1) {
        const r = await api("/api/audiences/check", { method: "POST", body: { kind: st.kind, spec: { ...spec(), name: st.name || "x" } } });
        const probs = r.problems.filter((p) => p.field !== "name");
        if (probs.length) { showErr(probs); return; }
        st.describe = r.describe || ""; st.size = r.size || "";
        if (!st.nameTouched || !st.name) st.name = (r.describe || "").slice(0, 200);
        st.step = 2; render(); return;
      }
      const made = await api("/api/audiences", { method: "POST", body: { kind: st.kind, spec: spec(), client_key: key } });
      madeId = made.id;
      close();
      toast(made.adopted ? "Found it: Meta had made it after all. It fills over the next few hours." : "Made. Meta fills it over the next few hours.");
      await load();
    } catch (er) {
      const field = er.body && er.body.field;
      if (field && field !== "name" && st.step === 2) { st.step = 1; render(); }
      showErr(er.body && er.body.problems ? er.body.problems : [{ field: field || "make", message: er.message }]);
    } finally { if (!closed && $("aud-next")) $("aud-next").disabled = false; }
  });

  render();
  UrlState.openLayer(`${location.pathname}${location.search}#new`);
  addEventListener("popstate", onPop);
  dlg.showModal();
  const stop = dlg.querySelector(".aud-body [data-aud-k][tabindex='0']");
  if (stop) stop.focus({ preventScroll: true });
}

// ---------------------------------------------------------------- the page

const me = await boot({ page: "audiences" });
if (me && me.role === "client") location.href = "/home.html";
else if (me) {
  $("aud-kinds").addEventListener("click", (e) => {
    const b = e.target.closest("[data-aud-kind]");
    if (b) { state.kind = b.dataset.audKind; remember(); draw(); }
  });
  $("aud-ready").addEventListener("change", (e) => { state.ready = e.target.checked; remember(); draw(); });
  $("aud-new").addEventListener("click", () => openNew());
  $("aud-refresh").addEventListener("click", async () => {
    $("aud-refresh").disabled = true;
    try { await api("/api/audiences/refresh", { method: "POST", body: {} }); await load(); toast("Read from Meta just now."); }
    catch (err) { toast(err.message, "bad"); }
    finally { $("aud-refresh").disabled = false; }
  });
  await load();
  if (location.hash === "#new" && data && data.can_edit) {
    history.replaceState(null, "", location.pathname + location.search);
    openNew();
  }
}
