import { api } from "./api.js";
import { boot, esc, fieldError, onRefresh, toast, when } from "./ui.js";
import { count, dayLabel, money } from "./format.js";

const $ = (id) => document.getElementById(id);
let me;
let items = [];
let metrics = {};
let choices = null;
let show = "running";
try { show = localStorage.getItem("ebads-tests") || "running"; } catch (e) {}

const COST = new Set(["cpl", "cpql"]);
const RESULT = { cpl: ["Leads", "leads"], cpql: ["Qualified", "qualified"], ctr: ["Clicks", "link_clicks"], hook: ["3-sec views", "video_3s"] };
const fmtValue = (metric, v) => (v == null ? "—" : COST.has(metric) ? money(v, { exact: true }) : `${(v * 100).toFixed(2)}%`);
const finished = (t) => t.status !== "running";
const SHOWS = { running: (t) => !finished(t), finished, all: () => true };

function statePill(t) {
  if (t.status === "stopped") return '<span class="pill">Stopped</span>';
  if (t.status === "done") return t.winner ? `<span class="pill ok">Finished · ${esc(t.winner)} won</span>` : '<span class="pill">Finished · no winner</span>';
  const j = t.judgement;
  return {
    early: '<span class="pill">Too early</span>',
    even: '<span class="pill">No clear difference</span>',
    leaning: `<span class="pill warn">Leaning ${esc(j.leader)}</span>`,
    winner: `<span class="pill ok">${esc(j.leader)} wins</span>`,
  }[j.state];
}

function dates(t) {
  const end = t.end_day ? dayLabel(t.end_day) : "no end set";
  return `${dayLabel(t.start_day)} – ${end} · ${t.days_run} full day${t.days_run === 1 ? "" : "s"} of data`;
}

function armRows(t) {
  const max = Math.max(...t.arms.map((a) => a.value || 0), 0);
  const [rlabel, rkey] = RESULT[t.metric];
  const lead = t.status === "done" ? t.winner : t.judgement.leader;
  const rows = t.arms.map((a) => {
    const w = a.value != null && max ? Math.max(2, (a.value / max) * 100) : 0;
    const need = !finished(t) && t.judgement.needs[a.label];
    return `<tr class="${a.label === lead ? "lead" : ""}">
      <th scope="row"><span class="arm-label">${esc(a.label)}</span><span class="arm-names">${a.names.map(esc).join(", ")}</span></th>
      <td class="arm-metric"><span class="arm-bar" aria-hidden="true"><i data-w="${w}"></i></span><b>${fmtValue(t.metric, a.value)}</b></td>
      <td class="num" data-label="Spent">${money(a.spend_cents, { exact: true })}</td>
      <td class="num" data-label="${esc(rlabel)}">${count(a[rkey])}</td>
      <td class="arm-need">${need ? `<span class="muted small">needs ${esc(need)}</span>` : ""}</td>
    </tr>`;
  }).join("");
  return `<div class="scroll-x"><table class="table middle arms-table">
    <thead><tr><th>Arm</th><th>${esc(t.metric_label)}</th><th class="num">Spent</th><th class="num">${esc(rlabel)}</th><th><span class="sr-only">Still needs</span></th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

function verdictLine(t) {
  if (t.status === "running") return `<p class="verdict ${t.judgement.state}">${esc(t.judgement.note)}</p>`;
  const closed = t.closed_at ? ` ${when(t.closed_at)}` : "";
  return `<p class="verdict closed"><b>${t.status === "done" ? "Finished" : "Stopped"}${esc(closed)}.</b> ${esc(t.verdict || (t.winner ? `${t.winner} won.` : "No winner."))}</p>`;
}

function testCard(t) {
  return `<article class="panel test" id="t-${t.id}" data-test="${t.id}" tabindex="-1">
    <header class="test-head">
      <div class="test-title"><h2>${esc(t.name)}</h2><p class="test-meta">Decided by ${esc(t.metric_label.toLowerCase())} · ${esc(dates(t))}${t.proposal_id ? " · suggested by Claude" : ""}</p></div>
      ${statePill(t)}
    </header>
    ${t.hypothesis ? `<p class="test-idea">${esc(t.hypothesis)}</p>` : ""}
    ${armRows(t)}
    ${verdictLine(t)}
    ${t.notes ? `<p class="muted small flush test-notes">${esc(t.notes)}</p>` : ""}
    <div class="row test-actions">
      ${t.status === "running" ? `<button type="button" class="btn" data-finish="${t.id}">Finish…</button>` : `<button type="button" class="btn btn-quiet" data-reopen="${t.id}">Reopen</button>`}
      <button type="button" class="btn btn-quiet" data-edit="${t.id}">Edit</button>
    </div>
  </article>`;
}

function render() {
  const counts = Object.fromEntries(Object.entries(SHOWS).map(([k, fn]) => [k, items.filter(fn).length]));
  document.querySelectorAll("#show [data-show]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.show === show)));
  document.querySelectorAll("#show [data-n]").forEach((n) => { n.textContent = counts[n.dataset.n]; });
  const list = items.filter(SHOWS[show]);
  if (!items.length) {
    $("tests").innerHTML = `<section class="panel empty"><h3>No tests yet</h3>
      <p>A test compares two to four ads or ad sets on one number, like cost per lead, over the same days. It says “too early” until each side has spent twice your target cost and has at least 3 leads, and it calls a winner only at 95% confidence.</p>
      <button type="button" class="btn btn-primary" data-new>Set up a test</button></section>`;
    return;
  }
  $("tests").innerHTML = list.length ? list.map(testCard).join("")
    : `<p class="muted">${show === "running" ? "No tests running." : "No finished tests yet."} <button type="button" class="link-btn" data-show-all>Show all</button></p>`;
  document.querySelectorAll(".arm-bar i[data-w]").forEach((i) => { i.style.width = `${i.dataset.w}%`; });
}

async function load() {
  try {
    const d = await api("/api/experiments");
    items = d.items; metrics = d.metrics;
  } catch (err) { toast(err.message, "bad"); return; }
  const focus = Number(location.hash.slice(1));
  const hit = focus && items.find((t) => t.id === focus);
  if (hit && !SHOWS[show](hit)) show = "all";
  render();
  if (hit) {
    const el = $(`t-${focus}`);
    el.classList.add("flash");
    el.scrollIntoView({ block: "start" });
    el.focus({ preventScroll: true });
  }
}

// ---------------------------------------------------------------- new / edit

async function adOptions(selected) {
  if (!choices) choices = (await api("/api/experiments/choices")).adsets;
  const off = (s) => (s === "ACTIVE" ? "" : " (off)");
  return `<option value="">Pick an ad or ad set</option>` + choices.map((s) => `<optgroup label="${esc(s.campaign_name ? `${s.campaign_name} › ${s.name}` : s.name)}">
    <option value="adset:${esc(s.id)}" ${selected === `adset:${s.id}` ? "selected" : ""}>Whole ad set: ${esc(s.name)}${off(s.effective_status)}</option>
    ${s.ads.map((a) => `<option value="ad:${esc(a.id)}" ${selected === `ad:${a.id}` ? "selected" : ""}>${esc(a.name)}${off(a.effective_status)}</option>`).join("")}
  </optgroup>`).join("");
}

const armRef = (a) => (a.ad_ids && a.ad_ids.length ? `ad:${a.ad_ids[0]}` : a.adset_ids && a.adset_ids.length ? `adset:${a.adset_ids[0]}` : "");

async function armField(i, arm = {}) {
  return `<div class="arm-row" data-arm>
    <label class="sr-only" for="arm-label-${i}">Arm name</label>
    <input class="input arm-name" id="arm-label-${i}" data-arm-label value="${esc(arm.label || "ABCD"[i])}" maxlength="40" autocomplete="off">
    <label class="sr-only" for="arm-ref-${i}">Ad or ad set for this arm</label>
    <select class="input" id="arm-ref-${i}" data-arm-ref>${await adOptions(armRef(arm))}</select>
    <button type="button" class="btn btn-quiet btn-small" data-arm-remove aria-label="Remove this arm">Remove</button>
  </div>`;
}

function syncArmButtons(form) {
  const rows = form.querySelectorAll("[data-arm]");
  rows.forEach((r) => { r.querySelector("[data-arm-remove]").hidden = rows.length <= 2; });
  form.querySelector("#arm-add").hidden = rows.length >= 4;
}

const todayIso = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

async function openForm(t = null) {
  let arms;
  try { arms = (await Promise.all((t ? t.arms : [{}, {}]).map((a, i) => armField(i, a)))).join(""); } catch (err) { toast(err.message, "bad"); return; }
  const metric = t ? t.metric : "cpl";
  const dlg = document.createElement("dialog");
  dlg.className = "test-dialog";
  dlg.innerHTML = `<form novalidate>
    <h2>${t ? "Edit the test" : "New test"}</h2>
    <div class="field"><label for="f-name">Name</label><input class="input" id="f-name" name="name" value="${esc(t ? t.name : "")}" placeholder="e.g. Problem hook vs result hook" autocomplete="off"></div>
    <div class="field"><label for="f-idea">What you expect, and why <span class="muted">(optional)</span></label>
      <textarea class="input" id="f-idea" name="hypothesis" rows="2" placeholder="e.g. Naming the pain first gets cheaper leads than showing the result">${esc(t ? t.hypothesis || "" : "")}</textarea></div>
    <div class="field"><label for="f-metric">Decided by</label><select class="input" id="f-metric" name="metric">
      ${Object.entries(metrics).map(([k, l]) => `<option value="${k}" ${k === metric ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>
    <fieldset class="field arms-field"><legend class="label">Arms: what you compare</legend>
      <input type="hidden" name="arms">
      <div id="arm-list">${arms}</div>
      <button type="button" class="btn btn-quiet btn-small" id="arm-add">Add an arm</button>
      <span class="hint">Pick ads or ad sets that run at the same time, to the same people. Different start dates make the comparison unfair.</span>
    </fieldset>
    <div class="row two">
      <div class="field"><label for="f-start">Starts</label><input class="input" type="date" id="f-start" name="start_day" value="${esc(t ? t.start_day : todayIso())}"></div>
      <div class="field"><label for="f-end">Ends <span class="muted">(optional)</span></label><input class="input" type="date" id="f-end" name="end_day" value="${esc(t && t.end_day ? t.end_day : "")}"></div>
    </div>
    <div class="field" id="target-field"><label for="f-target">Target cost <span class="muted">(optional)</span></label>
      <span class="money-input">$<input class="input" id="f-target" name="target" inputmode="decimal" value="${t && t.target_cents ? t.target_cents / 100 : ""}" placeholder="60" autocomplete="off"></span>
      <span class="hint">Each arm has to spend twice this before it's judged. Left empty: the cost-per-lead target from Settings → Alerts, or the test's own average.</span></div>
    ${t ? `<div class="field"><label for="f-notes">Notes</label><textarea class="input" id="f-notes" name="notes" rows="2">${esc(t.notes || "")}</textarea></div>` : ""}
    <div class="row end"><button class="btn" type="button" data-close>Cancel</button><button class="btn btn-primary" type="submit">${t ? "Save" : "Start tracking"}</button></div>
  </form>`;
  document.body.appendChild(dlg);
  const form = dlg.querySelector("form");
  const syncTarget = () => { $("target-field").hidden = !COST.has(form.metric.value); };
  syncTarget();
  syncArmButtons(form);
  form.metric.addEventListener("change", syncTarget);
  form.addEventListener("click", async (e) => {
    if (e.target.closest("[data-close]")) { dlg.close(); return; }
    if (e.target.closest("#arm-add")) {
      const n = form.querySelectorAll("[data-arm]").length;
      form.querySelector("#arm-list").insertAdjacentHTML("beforeend", await armField(n));
      syncArmButtons(form);
      form.querySelector(`#arm-ref-${n}`).focus();
      return;
    }
    const rm = e.target.closest("[data-arm-remove]");
    if (rm) { rm.closest("[data-arm]").remove(); syncArmButtons(form); }
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    fieldError(form, null);
    const arms = [...form.querySelectorAll("[data-arm]")].map((r) => {
      const [kind, id] = (r.querySelector("[data-arm-ref]").value || ":").split(":");
      return { label: r.querySelector("[data-arm-label]").value.trim(), ad_ids: kind === "ad" ? [id] : [], adset_ids: kind === "adset" ? [id] : [] };
    });
    const dollars = form.target.value.trim();
    if (dollars && !(Number(dollars) > 0)) { fieldError(form, "target", "Type the target in dollars, like 60"); return; }
    const body = { name: form.name.value, hypothesis: form.hypothesis.value, metric: form.metric.value, arms,
      start_day: form.start_day.value, end_day: form.end_day.value || null,
      target_cents: COST.has(form.metric.value) && dollars ? Math.round(Number(dollars) * 100) : null };
    if (t) body.notes = form.notes.value;
    try {
      const saved = await api(t ? `/api/experiments/${t.id}` : "/api/experiments", { method: t ? "PATCH" : "POST", body });
      dlg.close();
      toast(t ? "Saved" : "Tracking it");
      history.replaceState(null, "", `#${saved.id}`);
      load();
    } catch (err) {
      if (err.body && err.body.field) fieldError(form, err.body.field, err.message); else toast(err.message, "bad");
    }
  });
  dlg.addEventListener("close", () => dlg.remove());
  dlg.showModal();
  form.name.focus();
}

// ---------------------------------------------------------------- finish

function openFinish(t) {
  const dlg = document.createElement("dialog");
  dlg.className = "test-dialog";
  const j = t.judgement;
  const pick = j.state === "winner" ? j.leader : "";
  dlg.innerHTML = `<form novalidate>
    <h2>Finish “${esc(t.name)}”</h2>
    <p class="verdict ${j.state}">${esc(j.note)}</p>
    <fieldset class="field"><legend class="label">Which arm won?</legend>
      <div class="choice-list">${t.arms.map((a) => `<label class="check"><input type="radio" name="winner" value="${esc(a.label)}" ${a.label === pick ? "checked" : ""}> ${esc(a.label)} <span class="muted">· ${a.names.map(esc).join(", ")}</span></label>`).join("")}
        <label class="check"><input type="radio" name="winner" value="" ${pick ? "" : "checked"}> No winner</label></div>
      ${j.state !== "winner" ? '<span class="hint">The numbers haven\'t called a winner. Picking one anyway is your call; say why below.</span>' : ""}
    </fieldset>
    <div class="field"><label for="f-verdict">What you learned</label><textarea class="input" id="f-verdict" name="verdict" rows="3" placeholder="e.g. Naming the pain first won; next, try it on the order portal ad">${j.state === "early" ? "" : esc(j.note)}</textarea></div>
    <p class="muted small flush">Finishing only closes the record. Nothing changes on Meta: turn ads on or off on the Ads page.</p>
    <div class="row end"><button class="btn" type="button" data-close>Cancel</button>
      <button class="btn btn-quiet" type="button" data-stop>Stop without a result</button>
      <button class="btn btn-primary" type="submit">Finish</button></div>
  </form>`;
  document.body.appendChild(dlg);
  const form = dlg.querySelector("form");
  const save = async (body) => {
    try {
      await api(`/api/experiments/${t.id}`, { method: "PATCH", body });
      dlg.close();
      toast(body.status === "done" ? "Finished" : "Stopped");
      load();
    } catch (err) { toast(err.message, "bad"); }
  };
  form.addEventListener("click", (e) => {
    if (e.target.closest("[data-close]")) dlg.close();
    if (e.target.closest("[data-stop]")) save({ status: "stopped", winner: null, verdict: form.verdict.value });
  });
  form.addEventListener("submit", (e) => { e.preventDefault(); save({ status: "done", winner: form.winner.value || null, verdict: form.verdict.value }); });
  dlg.addEventListener("close", () => dlg.remove());
  dlg.showModal();
}

me = await boot({ page: "experiments", admin: true });
if (me) {
  $("new-test").addEventListener("click", () => openForm());
  document.addEventListener("click", async (e) => {
    const s = e.target.closest("#show [data-show]");
    if (s) { show = s.dataset.show; try { localStorage.setItem("ebads-tests", show); } catch (err) {} render(); return; }
    if (e.target.closest("[data-show-all]")) { show = "all"; render(); return; }
    if (e.target.closest("#tests [data-new]")) { openForm(); return; }
    const byId = (attr) => items.find((t) => t.id === Number(e.target.closest(`[${attr}]`)?.getAttribute(attr)));
    if (e.target.closest("[data-edit]")) openForm(byId("data-edit"));
    else if (e.target.closest("[data-finish]")) openFinish(byId("data-finish"));
    else if (e.target.closest("[data-reopen]")) {
      try { await api(`/api/experiments/${byId("data-reopen").id}`, { method: "PATCH", body: { status: "running" } }); toast("Running again"); load(); }
      catch (err) { toast(err.message, "bad"); }
    }
  });
  window.addEventListener("hashchange", load);
  onRefresh(load);
  load();
}
