import { api } from "./api.js";
import { boot, confirmDialog, esc, icon, shortWait, switchHtml, toast, when } from "./ui.js";
import { CTA_LABELS, count, money, pct, per, statusOf } from "./format.js";
import { columnChart } from "./charts.js";
import { editBudget, toggleEntity } from "./controls.js";
import { proposalCard, wireTaskActions } from "./tasks.js";

const $ = (id) => document.getElementById(id);
const adId = new URLSearchParams(location.search).get("id");
let me, data;
let format = "MOBILE_FEED_STANDARD";
try { format = localStorage.getItem("ebads-preview") || format; } catch (e) {}

const ACTIONS = { status: "Turned", budget: "Daily budget", duplicate: "Duplicated", create: "Created" };
const LEVEL = { campaign: "campaign", adset: "ad set", ad: "ad" };

function changeLine(c) {
  let what;
  if (c.action === "status") what = `${c.new_value === "ACTIVE" ? "Turned on" : "Turned off"} the ${LEVEL[c.level]}`;
  else if (c.action === "budget") what = `Changed the ${LEVEL[c.level]} budget ${money(Number(c.old_value), { exact: true })} → ${money(Number(c.new_value), { exact: true })} a day`;
  else if (c.action === "duplicate") what = `Duplicated as “${c.new_value}”`;
  else what = `${ACTIONS[c.action] || c.action} “${c.new_value || ""}”`;
  return `<li><span>${esc(what)}${c.ok ? "" : ` <b class="bad-text">(Meta refused: ${esc(c.error || "")})</b>`}</span><small>${esc(when(c.created_at))}${c.user_name ? ` · ${esc(c.user_name)}` : ""}${c.proposal_id ? " · Claude's proposal" : ""}</small></li>`;
}

function reviewNotes(ad) {
  const out = [];
  const fb = ad.review_feedback && (ad.review_feedback.global || ad.review_feedback);
  if (fb && typeof fb === "object") Object.entries(fb).forEach(([k, v]) => { if (typeof v === "string") out.push(`${k.replace(/_/g, " ")}: ${v}`); });
  (ad.issues || []).forEach((i) => out.push(i.error_message || i.error_summary || JSON.stringify(i)));
  return out;
}

async function loadPreview() {
  const box = $("preview-frame");
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

function render() {
  const { ad, lifetime, series } = data;
  document.title = `${ad.name} | Edge Bourne Ads`;
  $("crumb").innerHTML = `${icon("back")}<span>${esc(ad.campaign_name || "Ads")}</span>`;
  $("ad-name").textContent = ad.name;
  const [cls, label] = statusOf(ad.effective_status);
  $("ad-status").innerHTML = `<span class="pill ${cls}">${esc(label)}</span>`;
  const budgetLevel = ad.adset_budget_cents ? "adset" : ad.campaign_budget_cents ? "campaign" : null;
  const budgetCents = ad.adset_budget_cents || ad.campaign_budget_cents;
  $("ad-actions").innerHTML = `
    ${["ACTIVE", "PAUSED"].includes(ad.status) ? `<span class="switch-label">${ad.status === "ACTIVE" ? "On" : "Off"}</span>${switchHtml(ad.status === "ACTIVE", `data-toggle="ad:${ad.id}" data-name="${esc(ad.name)}"`, "Ad on or off")}` : ""}
    <button class="btn" type="button" id="dup">${icon("copy")}<span>Duplicate</span></button>
    ${me.role === "admin" ? `<a class="btn btn-claude" href="/desk.html?kind=question&campaign=${encodeURIComponent(ad.campaign_id || "")}&ask=${encodeURIComponent(`About the ad “${ad.name}”: `)}">${icon("spark")}<span>Ask Claude</span></a>` : ""}`;

  const notes = reviewNotes(ad);
  const leadsHtml = data.leads.length ? `<ul class="lead-mini">${data.leads.map((l) => `<li><a href="/leads.html#lead=${l.id}"><b>${esc(l.full_name || "Unnamed")}</b><span>${esc(l.business_type || "")}</span></a><span class="pill ${l.status}">${esc(l.status)}</span><small>${esc(shortWait(l.created_time))} ago${l.is_test ? " · test" : ""}</small></li>`).join("")}</ul>` : '<p class="muted flush">No leads from this ad yet.</p>';
  const proposals = data.proposals.length ? `<section class="panel"><div class="panel-head"><h2>Claude's proposals</h2></div><div class="panel-body stack tight" id="props">${data.proposals.map(proposalCard).join("")}</div></section>` : "";

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
        <section class="panel">
          <div class="panel-head"><h2>Results</h2><p>Since it started</p></div>
          <div class="panel-body">
            <dl class="mini-figs wide">
              <div><dt>Spent</dt><dd>${money(lifetime.spend_cents, { exact: true })}</dd></div>
              <div><dt>Leads</dt><dd>${count(lifetime.leads)}</dd></div>
              <div><dt>Per lead</dt><dd>${per(lifetime.spend_cents, lifetime.leads)}</dd></div>
              <div><dt>Shown to</dt><dd>${count(lifetime.reach)}</dd></div>
              <div><dt>Click rate</dt><dd>${pct(lifetime.link_clicks, lifetime.impressions)}</dd></div>
            </dl>
            <div class="charts single"><div><h3 class="chart-title">Spend per day, last 30 days</h3><div class="chart" id="c-spend"></div></div>
            <div><h3 class="chart-title">Leads per day</h3><div class="chart" id="c-leads"></div></div></div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Words</h2></div>
          <div class="panel-body">
            <dl class="facts">
              <div><dt>Headline</dt><dd>${esc(ad.title || "—")}</dd></div>
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
              <div><dt>Audience</dt><dd>${esc(ad.targeting_summary || "—")}</dd></div>
              <div><dt>Budget</dt><dd>${budgetCents ? `${money(budgetCents, { exact: true })}/day, shared by the ${budgetLevel === "campaign" ? "whole campaign" : "ad set"} <button class="link-btn" type="button" id="edit-budget">Change</button>` : "—"}</dd></div>
              <div><dt>Ad ID</dt><dd><a href="https://adsmanager.facebook.com/adsmanager/manage/ads?selected_ad_ids=${encodeURIComponent(ad.id)}" target="_blank" rel="noopener noreferrer">${esc(ad.id)} ${icon("external")}</a></dd></div>
            </dl>
          </div>
        </section>
        ${proposals}
        <section class="panel">
          <div class="panel-head"><h2>Leads from this ad</h2></div>
          <div class="panel-body">${leadsHtml}</div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Changes</h2><p>Made from this dashboard</p></div>
          <div class="panel-body">${data.changes.length ? `<ul class="changes">${data.changes.map(changeLine).join("")}</ul>` : '<p class="muted flush">No changes yet.</p>'}</div>
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
  $("dup").addEventListener("click", async () => {
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
  });
}

async function load() {
  try { data = await api(`/api/ads/ad/${encodeURIComponent(adId)}`); render(); }
  catch (err) { $("ad").innerHTML = `<section class="panel empty"><h3>Ad not found</h3><p>${esc(err.message)}</p><a class="btn" href="/ads.html">Back to ads</a></section>`; }
}

me = await boot({ page: "ads" });
if (me) {
  document.addEventListener("click", (e) => {
    const f = e.target.closest("#formats button[data-format]");
    if (f) { format = f.dataset.format; try { localStorage.setItem("ebads-preview", format); } catch (err) {} loadPreview(); return; }
    const t = e.target.closest("[data-toggle]");
    if (t) toggleEntity(t, load);
  });
  wireTaskActions(document.querySelector(".main"), load);
  load();
}
