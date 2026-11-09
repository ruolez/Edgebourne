import { api } from "./api.js";
import { boot, confirmDialog, esc, icon, shortWait, switchHtml, toast, when } from "./ui.js";
import { CTA_LABELS, count, money, pct, per, statusOf } from "./format.js";
import { barList, columnChart } from "./charts.js";
import { editBudget, toggleEntity } from "./controls.js";
import { ACTIVE, proposalCard, taskCard, wireTaskActions } from "./tasks.js";

const $ = (id) => document.getElementById(id);
const adId = new URLSearchParams(location.search).get("id");
let me, data, passes;
let format = "MOBILE_FEED_STANDARD";
try { format = localStorage.getItem("ebads-preview") || format; } catch (e) {}
let tab = (location.hash.match(/tab=(\w+)/) || [])[1] || "overview";
let audienceBy = "placement";
let audienceRange = "7";
let pollTimer;
const openReports = new Set();

const LEVEL = { campaign: "campaign", adset: "ad set", ad: "ad" };
const TABS = [
  ["overview", "Overview"], ["polish", "Polish"], ["audience", "Audience"], ["video", "Video"], ["comments", "Comments"], ["history", "History"],
];

function changeLine(c) {
  let what;
  if (c.action === "status") what = `${c.new_value === "ACTIVE" ? "Turned on" : "Turned off"} the ${LEVEL[c.level]}`;
  else if (c.action === "budget") what = `Changed the ${LEVEL[c.level]} budget ${money(Number(c.old_value), { exact: true })} → ${money(Number(c.new_value), { exact: true })} a day`;
  else if (c.action === "duplicate") what = `Duplicated as “${c.new_value}”`;
  else what = `Created “${c.new_value || ""}”`;
  return `<li><span>${esc(what)}${c.ok ? "" : ` <b class="bad-text">(Meta refused: ${esc(c.error || "")})</b>`}</span><small>${esc(when(c.created_at))}${c.user_name ? ` · ${esc(c.user_name)}` : ""}${c.proposal_id ? " · Claude's proposal" : ""}</small></li>`;
}

function reviewNotes(ad) {
  const out = [];
  const fb = ad.review_feedback && (ad.review_feedback.global || ad.review_feedback);
  if (fb && typeof fb === "object") Object.entries(fb).forEach(([k, v]) => { if (typeof v === "string") out.push(`${k.replace(/_/g, " ")}: ${v}`); });
  (ad.issues || []).forEach((i) => out.push(i.error_message || i.error_summary || JSON.stringify(i)));
  return out;
}

// ---------------------------------------------------------------- header + tabs

function renderHead() {
  const { ad } = data;
  document.title = `${ad.name} | Edge Bourne Ads`;
  $("crumb").innerHTML = `${icon("back")}<span>${esc(ad.campaign_name || "Ads")}</span>`;
  $("ad-name").textContent = ad.name;
  const [cls, label] = statusOf(ad.effective_status);
  $("ad-status").innerHTML = `<span class="pill ${cls}">${esc(label)}</span>`;
  $("ad-actions").innerHTML = `
    ${["ACTIVE", "PAUSED"].includes(ad.status) ? `<span class="switch-label">${ad.status === "ACTIVE" ? "On" : "Off"}</span>${switchHtml(ad.status === "ACTIVE", `data-toggle="ad:${ad.id}" data-name="${esc(ad.name)}"`, "Ad on or off")}` : ""}
    <button class="btn" type="button" id="dup">${icon("copy")}<span>Duplicate</span></button>
    <a class="btn" href="/new-ad.html?from=${encodeURIComponent(ad.id)}">${icon("plus")}<span>New ad from this</span></a>
    <button class="btn btn-claude" type="button" data-goto="polish">${icon("spark")}<span>Polish</span></button>`;
  const tabs = TABS.filter(([id]) => id !== "video" || ad.object_type === "VIDEO");
  $("ad-tabs").innerHTML = tabs.map(([id, l]) => `<button type="button" role="tab" data-tab="${id}" aria-selected="${id === tab}">${esc(l)}${id === "comments" && data.comment_total ? ` <span class="n">${data.comment_total}</span>` : ""}</button>`).join("");
}

function showTab(next) {
  tab = next;
  history.replaceState(null, "", `${location.pathname}${location.search}#tab=${tab}`);
  document.querySelectorAll("#ad-tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
  clearTimeout(pollTimer);
  ({ overview: renderOverview, polish: renderPolish, audience: renderAudience, video: renderVideo, comments: renderComments, history: renderHistory }[tab] || renderOverview)();
}

// ---------------------------------------------------------------- overview

async function loadPreview() {
  const box = $("preview-frame");
  if (!box) return;
  document.querySelectorAll("#formats button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.format === format)));
  box.innerHTML = '<p class="muted preview-wait">Loading Meta\'s preview…</p>';
  try {
    const p = await api(`/api/ads/ad/${encodeURIComponent(adId)}/preview?format=${format}`);
    const frame = document.createElement("iframe");
    frame.src = p.src;
    frame.title = "Ad preview from Meta";
    frame.loading = "lazy";
    frame.referrerPolicy = "no-referrer";
    frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-popups");
    frame.style.width = `${Math.min(p.width || 360, 400)}px`;
    frame.style.height = `${p.height || 640}px`;
    box.innerHTML = "";
    box.appendChild(frame);
    $("preview-open").href = p.src;
    $("preview-open").hidden = false;
  } catch (err) {
    box.innerHTML = `<p class="note warn">${esc(err.message)}</p>`;
    $("preview-open").hidden = true;
  }
}

function renderOverview() {
  const { ad, lifetime, series } = data;
  const budgetLevel = ad.adset_budget_cents ? "adset" : ad.campaign_budget_cents ? "campaign" : null;
  const budgetCents = ad.adset_budget_cents || ad.campaign_budget_cents;
  const notes = reviewNotes(ad);
  const leadsHtml = data.leads.length ? `<ul class="lead-mini">${data.leads.map((l) => `<li><a href="/leads.html#lead=${l.id}"><b>${esc(l.full_name || "Unnamed")}</b><span>${esc(l.business_type || "")}</span></a><span class="pill ${l.status}">${esc(l.status)}</span><small>${esc(shortWait(l.created_time))} ago${l.is_test ? " · test" : ""}</small></li>`).join("")}</ul>` : '<p class="muted flush">No leads from this ad yet.</p>';
  const pending = data.proposals.filter((p) => p.status === "pending");
  const hook = lifetime.impressions && data.funnel ? pct(data.funnel.video_3s, lifetime.impressions) : "—";
  $("ad").innerHTML = `
    ${new URLSearchParams(location.search).get("created") ? '<p class="note claude-note">Created and <b>off</b>. Check the previews below, then turn it on with the switch at the top when you\'re happy.</p>' : ""}
    ${notes.length ? `<p class="note bad">${notes.map(esc).join("<br>")}</p>` : ""}
    <div class="ad-layout">
      <section class="panel preview-panel">
        <div class="panel-head"><h2>Preview</h2><p>As Meta renders it</p></div>
        <div class="panel-body stack tight">
          <div class="format-scroll"><div class="segmented" id="formats" role="group" aria-label="Placement">${data.formats.map((f) => `<button type="button" data-format="${f.id}">${esc(f.label)}</button>`).join("")}</div></div>
          <div class="preview-frame" id="preview-frame"></div>
          <a class="small" id="preview-open" target="_blank" rel="noopener noreferrer" hidden>Open this preview in a new tab</a>
        </div>
      </section>
      <div class="stack">
        ${pending.length ? `<section class="panel claude-panel"><div class="panel-head"><h2>Claude suggests</h2></div><div class="panel-body stack tight" id="props">${pending.map(proposalCard).join("")}</div></section>` : ""}
        <section class="panel">
          <div class="panel-head"><h2>Results</h2><p>Since it started</p></div>
          <div class="panel-body">
            <dl class="mini-figs wide six">
              <div><dt>Spent</dt><dd>${money(lifetime.spend_cents, { exact: true })}</dd></div>
              <div><dt>Leads</dt><dd>${count(lifetime.leads)}</dd></div>
              <div><dt>Per lead</dt><dd>${per(lifetime.spend_cents, lifetime.leads)}</dd></div>
              <div><dt>Shown to</dt><dd>${count(lifetime.reach)}</dd></div>
              <div><dt>Click rate</dt><dd>${pct(lifetime.link_clicks, lifetime.impressions)}</dd></div>
              ${ad.object_type === "VIDEO" ? `<div><dt>Hook rate</dt><dd>${hook}</dd></div>` : ""}
            </dl>
            <div class="charts single"><div><h3 class="chart-title">Spend per day, last 30 days</h3><div class="chart" id="c-spend"></div></div>
            <div><h3 class="chart-title">Leads per day</h3><div class="chart" id="c-leads"></div></div></div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Words</h2><span class="spacer"></span><button class="btn btn-small" type="button" data-goto="polish">Improve the words</button></div>
          <div class="panel-body">
            <dl class="facts">
              <div><dt>Headline</dt><dd>${esc(ad.title || "—")} <span class="muted small">(${(ad.title || "").length} characters)</span></dd></div>
              <div><dt>Primary text</dt><dd class="pre">${esc(ad.body || "—")}</dd></div>
              <div><dt>Button</dt><dd>${esc(CTA_LABELS[ad.cta_type] || ad.cta_type || "—")}</dd></div>
              <div><dt>Format</dt><dd>${esc(ad.object_type === "VIDEO" ? "Video" : ad.object_type ? "Image" : "—")}</dd></div>
            </dl>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Where it runs</h2></div>
          <div class="panel-body">
            <dl class="facts">
              <div><dt>Campaign</dt><dd>${esc(ad.campaign_name || "—")}</dd></div>
              <div><dt>Ad set</dt><dd>${esc(ad.adset_name || "—")}</dd></div>
              <div><dt>Audience</dt><dd>${esc(ad.targeting_summary || "—")}<span id="estimate"></span></dd></div>
              <div><dt>Budget</dt><dd>${budgetCents ? `${money(budgetCents, { exact: true })}/day, shared by the ${budgetLevel === "campaign" ? "whole campaign" : "ad set"} <button class="link-btn" type="button" id="edit-budget">Change</button>` : "—"}</dd></div>
              <div><dt>Ad ID</dt><dd><a href="https://adsmanager.facebook.com/adsmanager/manage/ads?selected_ad_ids=${encodeURIComponent(ad.id)}" target="_blank" rel="noopener noreferrer">${esc(ad.id)} ${icon("external")}</a></dd></div>
            </dl>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Leads from this ad</h2></div>
          <div class="panel-body">${leadsHtml}</div>
        </section>
      </div>
    </div>`;
  columnChart({ el: $("c-spend"), series, key: "spend_cents", color: "var(--chart-spend)", title: "Spend per day", height: 160,
    format: (v) => money(v, { exact: true }), axisFormat: (v) => `$${Math.round(v / 100)}` });
  columnChart({ el: $("c-leads"), series, key: "leads", color: "var(--chart-leads)", title: "Leads per day", integer: true, height: 160,
    format: (v) => `${v} lead${v === 1 ? "" : "s"}`, axisFormat: (v) => String(Math.round(v)) });
  loadPreview();
  const eb = $("edit-budget");
  if (eb) eb.addEventListener("click", () => editBudget({ level: budgetLevel, id: budgetLevel === "adset" ? ad.adset_id : ad.campaign_id, name: budgetLevel === "adset" ? ad.adset_name : ad.campaign_name, current: budgetCents }, load));
  if (ad.adset_id) api(`/api/insights/adset/${encodeURIComponent(ad.adset_id)}/estimate`).then((e) => {
    if (e.lower && e.upper && $("estimate")) $("estimate").innerHTML = `<br><span class="muted small">Meta estimates ${count(e.lower)}–${count(e.upper)} people could see ads from this ad set.</span>`;
  }).catch(() => {});
}

// ---------------------------------------------------------------- polish

const PRESET_LABELS = { full: "Full audit", copy: "Words only", design: "Design only", quick: "Quick check" };

async function renderPolish() {
  if (!passes) passes = await api("/api/polish/passes");
  let runs = [];
  try { runs = (await api(`/api/ads/ad/${encodeURIComponent(adId)}/polish-runs`)).tasks; } catch (err) { toast(err.message, "bad"); }
  const last = runs.find((r) => r.kind === "polish" && r.scorecard);
  const selected = new Set(JSON.parse(sessionStorage.getItem("ebads-passes") || "null") || passes.presets.full);
  $("ad").innerHTML = `
    <div class="polish-layout">
      <section class="panel polish-panel">
        <div class="panel-head"><h2>Polish this ad</h2><p>The checks that took N1–N5 from first draft to approved</p></div>
        <form class="panel-body stack" id="polish-form" novalidate>
          <div class="row presets">${Object.entries(PRESET_LABELS).map(([k, l]) => `<button type="button" class="chip" data-preset="${k}">${esc(l)}</button>`).join("")}
            <span class="spacer"></span><label class="check small"><input type="checkbox" id="show-checks"> Show what each pass checks</label></div>
          <div class="pass-grid">${passes.passes.map((p) => `
            <label class="pass ${selected.has(p.id) ? "on" : ""}">
              <input type="checkbox" name="pass" value="${p.id}" ${selected.has(p.id) ? "checked" : ""}>
              <span class="pass-top"><b>${esc(p.label)}</b>${last ? (() => { const r = last.scorecard.passes.find((x) => x.id === p.id); return r && r.score ? `<span class="mini-score s${Math.max(2, Math.min(5, r.score))}">${r.score}/5</span>` : ""; })() : ""}</span>
              <span class="pass-sum">${esc(p.summary)}</span>
              <ul>${p.checks.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>
            </label>`).join("")}</div>
          <div class="field"><label for="direction">Your direction <span class="muted">(optional)</span></label>
            <textarea class="input" id="direction" rows="2" placeholder="e.g. The headline feels long. Keep the AI chip but make it calmer."></textarea></div>
          <div class="row">
            <label class="check"><input type="checkbox" id="variants" checked> Write new copy versions I can turn into ads</label>
            <span class="spacer"></span>
            <button class="btn btn-claude" type="submit" id="run-polish">${icon("spark")}<span>Run polish</span></button>
          </div>
          <p class="muted small flush">Claude runs this on your Mac with your Meta access and the design rules from our rounds. Nothing changes on Meta: new versions come back as proposals you approve.</p>
        </form>
      </section>
      <section class="panel render-panel">
        <div class="panel-head"><h2>Make a new version</h2></div>
        <form class="panel-body stack tight" id="render-form" novalidate>
          <p class="flush muted small">Claude rebuilds the creative on your Mac (same pipeline as N1–N5), uploads it and sends it back as a new ad for you to approve. Takes 10–40 minutes.</p>
          ${last ? `<label class="check"><input type="checkbox" id="use-fixes" checked> Apply the fixes from the latest polish (score ${last.scorecard.overall}/5)</label>` : ""}
          <div class="field"><label for="render-direction">What should change</label>
            <textarea class="input" id="render-direction" rows="3" placeholder="e.g. Shorter headline, bigger Tap below note, AI chip inside the report card."></textarea></div>
          <button class="btn" type="submit">${icon("image")}<span>Make a new version</span></button>
        </form>
      </section>
    </div>
    <h2 class="section-h">Runs</h2>
    <div class="stack" id="runs">${runs.length ? runs.map((t) => taskCard(t, openReports)).join("") : '<section class="panel empty"><h3>No polish runs yet</h3><p>Pick the passes above and run them. Results show here with a score per pass, the fixes, and new versions of the copy you can turn into ads.</p></section>'}</div>`;

  const form = $("polish-form");
  const sync = () => {
    const chosen = [...form.querySelectorAll("input[name=pass]:checked")].map((i) => i.value);
    form.querySelectorAll(".pass").forEach((l) => l.classList.toggle("on", l.querySelector("input").checked));
    sessionStorage.setItem("ebads-passes", JSON.stringify(chosen));
    $("run-polish").querySelector("span").textContent = chosen.length === passes.passes.length ? "Run full audit" : `Run ${chosen.length} pass${chosen.length === 1 ? "" : "es"}`;
    $("run-polish").disabled = !chosen.length;
  };
  form.addEventListener("change", (e) => {
    if (e.target.id === "show-checks") { form.querySelector(".pass-grid").classList.toggle("show-checks", e.target.checked); return; }
    sync();
  });
  form.querySelector(".presets").addEventListener("click", (e) => {
    const b = e.target.closest("[data-preset]");
    if (!b) return;
    const set = new Set(passes.presets[b.dataset.preset]);
    form.querySelectorAll("input[name=pass]").forEach((i) => { i.checked = set.has(i.value); });
    sync();
  });
  sync();
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const chosen = [...form.querySelectorAll("input[name=pass]:checked")].map((i) => i.value);
    try {
      await api(`/api/ads/ad/${encodeURIComponent(adId)}/polish`, { method: "POST", body: { passes: chosen, direction: $("direction").value, variants: $("variants").checked } });
      toast("Sent to Claude");
      renderPolish();
    } catch (err) { toast(err.message, "bad"); }
  });
  $("render-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const useFixes = $("use-fixes") && $("use-fixes").checked;
    const ok = await confirmDialog({
      title: "Make a new version?",
      body: "<p>Claude rebuilds the creative on your Mac and uploads it to your Meta media library. You get it back as a proposal; nothing is shown to anyone until you approve it and switch the new ad on.</p>",
      confirm: "Make it", claude: true,
    });
    if (!ok) return;
    try {
      await api(`/api/ads/ad/${encodeURIComponent(adId)}/render`, { method: "POST", body: { direction: $("render-direction").value, from_task: useFixes ? last.id : null } });
      toast("Sent to Claude");
      renderPolish();
    } catch (err) { toast(err.message, "bad"); }
  });
  if (runs.some((r) => ACTIVE.has(r.status))) pollTimer = setTimeout(() => { if (tab === "polish" && !document.activeElement.closest("form")) renderPolish(); else pollTimer = setTimeout(renderPolish, 6000); }, 6000);
}

// ---------------------------------------------------------------- audience

const BY = [["placement", "Placement"], ["age", "Age"], ["gender", "Gender"], ["device", "Device"], ["region", "Region"], ["hour", "Hour of day"]];

async function renderAudience() {
  $("ad").innerHTML = `
    <section class="panel">
      <div class="panel-head wrap"><h2>Who saw it, and where</h2><span class="spacer"></span>
        <div class="segmented" id="aud-range">${[["7", "7 days"], ["14", "14 days"], ["30", "30 days"], ["lifetime", "All time"]].map(([k, l]) => `<button type="button" data-r="${k}" aria-pressed="${k === audienceRange}">${l}</button>`).join("")}</div></div>
      <div class="panel-body stack">
        <div class="format-scroll"><div class="segmented" id="aud-by">${BY.map(([k, l]) => `<button type="button" data-by="${k}" aria-pressed="${k === audienceBy}">${l}</button>`).join("")}</div></div>
        <div class="aud-grid">
          <div><h3 class="chart-title">Share of spend</h3><div id="aud-spend"><p class="muted">Loading from Meta…</p></div></div>
          <div><h3 class="chart-title">Leads and cost per lead</h3><div id="aud-leads"></div></div>
        </div>
        <p class="muted small flush" id="aud-note"></p>
      </div>
    </section>`;
  $("aud-by").addEventListener("click", (e) => { const b = e.target.closest("[data-by]"); if (b) { audienceBy = b.dataset.by; renderAudience(); } });
  $("aud-range").addEventListener("click", (e) => { const b = e.target.closest("[data-r]"); if (b) { audienceRange = b.dataset.r; renderAudience(); } });
  try {
    const d = await api(`/api/insights/breakdown?level=ad&id=${encodeURIComponent(adId)}&by=${audienceBy}&range=${audienceRange}`);
    const total = d.items.reduce((s, i) => s + i.spend_cents, 0);
    barList($("aud-spend"), d.items, { key: "spend_cents", format: (v) => (total ? `${Math.round((v / total) * 100)}%` : "—"), extra: (i) => money(i.spend_cents) });
    barList($("aud-leads"), d.items, { key: "leads", format: (v) => count(v), extra: (i) => (i.leads ? `${per(i.spend_cents, i.leads)} per lead` : "no leads") });
    $("aud-note").textContent = `Complete days only. Small groups swing a lot: judge a slice only after it has a few leads.${audienceBy === "region" ? " Region is where people are, not where they live." : ""}`;
  } catch (err) { $("aud-spend").innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

// ---------------------------------------------------------------- video

async function renderVideo() {
  $("ad").innerHTML = '<section class="panel"><div class="panel-body"><p class="muted">Loading…</p></div></section>';
  try {
    const d = await api(`/api/insights/ad/${encodeURIComponent(adId)}/diagnostics`);
    const f = d.funnel;
    const steps = [
      { label: "Shown (impressions)", v: f.impressions }, { label: "Watched 3 seconds", v: f.video_3s }, { label: "Watched 25%", v: f.p25 },
      { label: "Watched 50%", v: f.p50 }, { label: "Watched 75%", v: f.p75 }, { label: "Watched to the end", v: f.p100 },
    ];
    const hook = f.impressions ? f.video_3s / f.impressions : null;
    const hold = f.video_3s ? f.thruplays / f.video_3s : null;
    const rank = (k, label) => { const r = d.rankings[k]; const v = r.value || "UNKNOWN"; const cls = v.startsWith("ABOVE") ? "ok" : v === "AVERAGE" ? "" : v.startsWith("BELOW") ? "bad" : ""; return `<div><dt>${label}</dt><dd><span class="pill ${cls}">${esc(r.label || "Not enough data yet")}</span></dd></div>`; };
    $("ad").innerHTML = `
      <div class="video-grid">
        <section class="panel">
          <div class="panel-head"><h2>Watch funnel</h2><p>Since it started</p></div>
          <div class="panel-body"><div id="funnel"></div></div>
        </section>
        <div class="stack">
          <section class="panel">
            <div class="panel-head"><h2>Hook and hold</h2></div>
            <div class="panel-body">
              <dl class="mini-figs wide three">
                <div><dt>Hook rate</dt><dd>${hook == null ? "—" : `${(hook * 100).toFixed(1)}%`}</dd></div>
                <div><dt>Hold rate</dt><dd>${hold == null ? "—" : `${(hold * 100).toFixed(1)}%`}</dd></div>
                <div><dt>Avg. watch</dt><dd>${d.avg_watch_seconds ? `${d.avg_watch_seconds}s` : "—"}</dd></div>
              </dl>
              <p class="muted small flush">Hook rate = people who watched 3 seconds ÷ impressions (stopping the scroll). Hold rate = ThruPlays ÷ 3-second views (staying for the message). Rules of thumb: hook above 25–30%, hold above 30%.</p>
            </div>
          </section>
          <section class="panel">
            <div class="panel-head"><h2>Meta's quality read</h2><p>Last 30 days</p></div>
            <div class="panel-body">
              <dl class="facts">
                ${rank("quality_ranking", "Quality")}${rank("engagement_rate_ranking", "Engagement")}${rank("conversion_rate_ranking", "Conversion")}
                <div><dt>Frequency</dt><dd>${d.frequency ? `${d.frequency.toFixed(2)} times per person` : "—"}</dd></div>
                <div><dt>Cost per 1,000</dt><dd>${d.cpm_cents ? money(d.cpm_cents, { exact: true }) : "—"}</dd></div>
              </dl>
              <p class="muted small flush">Compared with ads competing for the same people. Meta shows these after about 500 impressions. Below average on quality usually means the creative; on conversion, the offer or the form.${d.error ? ` (Meta: ${esc(d.error)})` : ""}</p>
            </div>
          </section>
        </div>
      </div>`;
    barList($("funnel"), steps, { key: "v", format: (v) => count(v), max: f.impressions || 1, extra: (i) => (f.impressions ? `${((i.v / f.impressions) * 100).toFixed(1)}%` : "") });
  } catch (err) { $("ad").innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

// ---------------------------------------------------------------- comments

async function renderComments() {
  $("ad").innerHTML = '<section class="panel"><div class="panel-body"><p class="muted">Loading comments from Facebook…</p></div></section>';
  try {
    const d = await api(`/api/insights/ad/${encodeURIComponent(adId)}/comments`);
    $("ad").innerHTML = `<section class="panel comments-panel">
      <div class="panel-head"><h2>Comments</h2><p>${count(d.total)} on the ad's post</p><span class="spacer"></span>${d.post_url ? `<a class="btn btn-small" href="${esc(d.post_url)}" target="_blank" rel="noopener noreferrer">Reply on Facebook ${icon("external")}</a>` : ""}</div>
      <div class="panel-body">${d.items.length ? `<ul class="comments">${d.items.map((c) => `<li><div class="c-head"><b>${esc(c.name || "Someone")}</b><small>${esc(when(c.created_time))}${c.likes ? ` · ${c.likes} like${c.likes === 1 ? "" : "s"}` : ""}${c.replies ? ` · ${c.replies} repl${c.replies === 1 ? "y" : "ies"}` : ""}</small></div><p>${esc(c.message || "")}</p></li>`).join("")}</ul>`
        : `<p class="muted flush">${esc(d.note || "No comments yet. Questions here are warm leads: reply within a few hours.")}</p>`}</div></section>`;
  } catch (err) { $("ad").innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

// ---------------------------------------------------------------- history

function renderHistory() {
  const decided = data.proposals.filter((p) => p.status !== "pending");
  $("ad").innerHTML = `
    <section class="panel"><div class="panel-head"><h2>Changes</h2><p>Made from this dashboard</p></div>
      <div class="panel-body">${data.changes.length ? `<ul class="changes">${data.changes.map(changeLine).join("")}</ul>` : '<p class="muted flush">No changes yet.</p>'}</div></section>
    ${decided.length ? `<section class="panel"><div class="panel-head"><h2>Claude's earlier proposals</h2></div><div class="panel-body stack tight">${decided.map(proposalCard).join("")}</div></section>` : ""}`;
}

// ---------------------------------------------------------------- load

async function load() {
  try {
    data = await api(`/api/ads/ad/${encodeURIComponent(adId)}`);
    try { data.funnel = (await api(`/api/insights/ad/${encodeURIComponent(adId)}/diagnostics`)).funnel; } catch (e) { data.funnel = null; }
    renderHead();
    if (tab === "video" && data.ad.object_type !== "VIDEO") tab = "overview";
    showTab(tab);
    api(`/api/insights/ad/${encodeURIComponent(adId)}/comments`).then((c) => { data.comment_total = c.total; renderHead(); }).catch(() => {});
  } catch (err) {
    $("ad").innerHTML = `<section class="panel empty"><h3>Ad not found</h3><p>${esc(err.message)}</p><a class="btn" href="/ads.html">Back to ads</a></section>`;
  }
}

me = await boot({ page: "ads" });
if (me) {
  document.addEventListener("click", async (e) => {
    const t = e.target.closest("#ad-tabs [data-tab]");
    if (t) { showTab(t.dataset.tab); return; }
    const g = e.target.closest("[data-goto]");
    if (g) { showTab(g.dataset.goto); window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    const f = e.target.closest("#formats button[data-format]");
    if (f) { format = f.dataset.format; try { localStorage.setItem("ebads-preview", format); } catch (err) {} loadPreview(); return; }
    const sw = e.target.closest("[data-toggle]");
    if (sw) { toggleEntity(sw, load); return; }
    if (e.target.closest("#dup")) {
      const ad = data.ad;
      const name = await confirmDialog({
        title: `Duplicate “${ad.name}”?`,
        body: "<p>Makes a copy in the same ad set with the same video or image, words and button. The copy starts <b>off</b>, so nothing spends until you turn it on.</p>",
        confirm: "Duplicate",
        field: { label: "Name for the copy", value: `${ad.name} - copy`, validate: (v) => (v.trim() ? null : "Give it a name") },
      });
      if (name === false) return;
      try {
        const r = await api(`/api/ads/ad/${encodeURIComponent(ad.id)}/duplicate`, { method: "POST", body: { name } });
        toast("Copy created (off)");
        location.href = `/ad.html?id=${encodeURIComponent(r.id)}&created=1`;
      } catch (err) { toast(err.message, "bad"); }
    }
  });
  wireTaskActions(document.querySelector(".main"), load, openReports);
  load();
}
