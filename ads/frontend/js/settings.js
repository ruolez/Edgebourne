import { api } from "./api.js";
import { boot, confirmDialog, esc, fieldError, toast, when } from "./ui.js";

const $ = (id) => document.getElementById(id);
let s;

function fill(form, section) {
  for (const [key, value] of Object.entries(section)) {
    const input = form.elements[key];
    if (!input) continue;
    if (value && typeof value === "object") {
      input.value = "";
      input.placeholder = value.set ? "Saved. Type to replace." : "";
      const hint = form.querySelector(`[data-hint="${key}"]`);
      if (hint) hint.textContent = value.set ? `Saved (${value.hint}). Leave blank to keep it.` : "Not set yet.";
    } else if (input.tagName === "SELECT") {
      if (value) input.value = value; else input.selectedIndex = 0;
    } else {
      input.value = value;
    }
  }
}

function renderMeta() {
  const m = s.meta;
  const ready = m.meta_app_id && m.meta_app_secret.set && m.meta_system_token.set && m.meta_verify_token.set;
  $("meta-state").innerHTML = s.page_subscribed ? '<span class="pill ok">Receiving leads</span>'
    : ready ? '<span class="pill warn">Saved, not receiving leads yet</span>' : '<span class="pill">Not connected</span>';
  $("graph-default").textContent = `Leave blank for ${s.graph_version_default}.`;
  $("webhook-note").innerHTML = `In your Meta app, under Webhooks, subscribe the <b>Page</b> object to <b>leadgen</b> with callback URL <b>${esc(s.webhook_url)}</b> and the verify token above.`
    + (s.pending_webhooks ? `<br><br><b>${s.pending_webhooks} lead ping(s) waiting.</b> ${esc(s.pending_error || "")} <button class="btn" type="button" id="retry">Try again</button>` : "")
    + (s.last_campaign_sync ? `<br>Campaigns last synced ${when(s.last_campaign_sync)}.` : "");
  $("retry")?.addEventListener("click", async () => {
    const r = await api("/api/settings/webhooks/retry", { method: "POST" });
    toast(`${r.processed} lead(s) fetched`);
    load();
  });
}

// Tracking health: what Meta's dataset has received, and what this console has sent it.
const TR_STATE = { ok: ["ok", "Healthy"], weak: ["warn", "Something to fix"], quiet: ["bad", "Gone quiet"], not_set_up: ["", "Not set up"] };

function trackingHtml(t) {
  const a = t.assessment;
  const events = t.events && Object.keys(t.events).length
    ? Object.entries(t.events).sort((x, y) => y[1] - x[1]).map(([k, v]) => `${esc(k)} ${v}`).join(" · ") : "none";
  const stages = Object.keys(t.sent_by_stage || {}).length ? Object.entries(t.sent_by_stage).map(([k, v]) => `${esc(k)} ${v}`).join(" · ") : "none";
  const match = (t.match || []).length ? t.match.map((m) => `${esc(m.event || m.channel)} ${m.emq}/10`).join(" · ") : "not reported yet";
  return `<p class="flush tr-headline">${esc(a.headline)}</p>
    ${t.dataset ? `<dl class="facts tr-facts">
      <div><dt>Dataset</dt><dd>${esc(t.name || "")} <span class="muted small">${esc(t.dataset)}</span></dd></div>
      <div><dt>Last event</dt><dd>${a.last ? esc(when(a.last)) : "never"}</dd></div>
      <div><dt>Received, last ${t.days} days</dt><dd>${events}</dd></div>
      <div><dt>From a server</dt><dd>${a.server_share != null ? `${a.server_share}% <span class="muted small">(Conversions API; the rest from the website)</span>` : "—"}</dd></div>
      <div><dt>Match quality</dt><dd>${match} <span class="muted small">(6 or more is good)</span></dd></div>
      <div><dt>Sent from here, last 7 days</dt><dd>${stages}${t.crm.pending ? ` · ${t.crm.pending} waiting` : ""}${t.crm.failed ? ` · <span class="bad-text">${t.crm.failed} failed</span>` : ""}${t.crm_on ? "" : ' <span class="muted small">(sending is off)</span>'}</dd></div>
    </dl>` : ""}
    ${a.todo.length ? `<ul class="tr-todo">${a.todo.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    <p class="muted small flush">Instant Form leads are counted by Meta without any website code. The dataset is how Meta learns which of those leads became clients.${t.fetched_at ? ` Checked ${esc(when(t.fetched_at))}.` : ""}</p>`;
}

async function loadTracking(fresh = false) {
  try {
    const t = await api(`/api/tracking${fresh ? "?fresh=1" : ""}`);
    const [cls, label] = TR_STATE[t.assessment.state] || ["", t.assessment.state];
    $("tr-state").innerHTML = `<span class="pill ${cls}">${esc(label)}</span>`;
    $("tr-body").innerHTML = trackingHtml(t);
  } catch (err) { $("tr-body").innerHTML = `<p class="note warn">${esc(err.message)}</p>`; }
}

function renderMetaTests() {
  $("mt-on").checked = !!s.meta_ab_tests;
  $("mt-state").innerHTML = s.meta_ab_tests ? '<span class="pill ok">On</span>' : '<span class="pill">Off</span>';
}

function renderCrm() {
  const c = s.crm;
  const on = s.meta.crm_send_enabled === "1";
  $("meta_dataset_id").value = s.meta.meta_dataset_id || "";
  $("crm_send_enabled").checked = on;
  $("crm-state").innerHTML = !on ? '<span class="pill">Off</span>'
    : c.failed ? `<span class="pill warn">${c.failed} didn't reach Meta</span>` : '<span class="pill ok">On</span>';
  const parts = [`${c.sent} sent`, c.pending && (on ? `${c.pending} waiting` : `${c.pending} saved, sent once you turn this on (Meta takes them up to 7 days back)`), c.failed && `${c.failed} failed`, c.skipped && `${c.skipped} skipped`].filter(Boolean);
  $("crm-result").innerHTML = c.sent || c.pending || c.failed || c.skipped
    ? `<p class="note${c.failed ? " warn" : ""}">${parts.join(", ")}.${c.last_error ? ` Last error: ${esc(c.last_error)}` : ""}</p>` : "";
}

function renderTelegram() {
  const t = s.telegram;
  $("tg-state").innerHTML = t.set ? `<span class="pill ok">@${esc(t.username || "bot")}</span>` : '<span class="pill">Not set up</span>';
  $("tg-steps").hidden = t.set;
  $("tg-remove").hidden = !t.set;
  $("telegram_bot_token").value = "";
  $("telegram_bot_token").placeholder = t.set ? "Saved. Paste a new token to replace it." : "";
  $("tg-result").innerHTML = t.set
    ? `<p class="note${t.failed.n ? " warn" : ""}">${t.linked ? `${t.linked} ${t.linked === 1 ? "person has" : "people have"} connected Telegram.` : "Nobody has connected Telegram yet. Do it from Your account."}${t.failed.n ? ` ${t.failed.n} alert${t.failed.n === 1 ? "" : "s"} didn't arrive in the last 2 days: ${esc(t.failed.last_error || "")}` : ""}</p>`
    : "";
}

// Lead replies: the switch, the booking link and the templates.
let editing = null; // template id being edited, "new", or null
const LABELS = { first_name: "First name", full_name: "Full name", business: "Business", phone: "Their phone", my_name: "My name", my_email: "My email", booking_link: "Booking link" };

function renderReplies() {
  const r = s.replies;
  const auto = r.templates.find((t) => t.id === r.auto_template_id) || r.templates[0];
  $("rp-state").innerHTML = r.auto ? '<span class="pill ok">Automatic reply on</span>' : '<span class="pill">By hand</span>';
  $("booking_link").value = r.booking_link || "";
  $("rp-auto").checked = r.auto;
  $("rp-auto-pick").hidden = !r.auto;
  $("rp-auto-template").innerHTML = r.templates.map((t) => `<option value="${t.id}" ${auto && t.id === auto.id ? "selected" : ""}>${esc(t.name)}</option>`).join("");
  $("rp-auto-hint").textContent = r.auto ? `Sent within a minute, signed by ${r.auto_sender || "the admin who turned it on"}. Test leads never get one.` : "";
  $("tpl-list").innerHTML = r.templates.map((t, i) => `<li><span class="tpl-name"><b>${esc(t.name)}</b>${i === 0 ? ' <span class="pill">Opens first</span>' : ""}<small>${esc(t.subject)}</small></span>
    <button class="btn btn-quiet" type="button" data-edit="${t.id}">Edit</button></li>`).join("");
  $("tpl-chips").innerHTML = r.placeholders.map((k) => `<button type="button" class="chip" data-insert="{${k}}">${esc(LABELS[k] || k)}</button>`).join("");
  $("rp-result").innerHTML = r.sent_7d || r.failed_7d
    ? `<p class="note${r.failed_7d ? " warn" : ""}">${r.sent_7d} sent in the last 7 days.${r.failed_7d ? ` ${r.failed_7d} didn't go out: ${esc(r.last_error || "")}` : ""}</p>` : "";
}

let previewTimer;
function previewTemplate() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    try {
      const p = await api("/api/settings/replies/preview", { method: "POST", body: { subject: $("tpl-subject").value, body: $("tpl-body").value, booking_link: $("booking_link").value } });
      $("tpl-preview").textContent = `${p.subject}\n\n${p.body}`;
    } catch (e) { /* the preview is a convenience */ }
  }, 300);
}

function editTemplate(id) {
  editing = id;
  const t = s.replies.templates.find((x) => x.id === id) || { name: "", subject: "", body: "" };
  $("tpl-name").value = t.name; $("tpl-subject").value = t.subject; $("tpl-body").value = t.body;
  $("tpl-delete").hidden = id === "new" || s.replies.templates.length < 2;
  $("tpl-form").hidden = false;
  $("tpl-add").hidden = true;
  fieldError($("tpl-form"));
  previewTemplate();
  $("tpl-name").focus();
}

function closeTemplate() { editing = null; $("tpl-form").hidden = true; $("tpl-add").hidden = false; }

// Alerts: one row per rule, a switch and its numbers.
const RULE_UI = [
  ["ad_rejected", "An ad is rejected or has issues", []],
  ["no_delivery", "An ad is on but nobody has seen it", [["hours", "after", "hours"]]],
  ["fatigue", "An ad looks tired", [["frequency", "seen more than", "times a week,"], ["ctr_drop", "clicks down", "%,"], ["cpm_rise", "cost per 1,000 views up", "%"]]],
  ["day_overspend", "One day's spend is high (shown on Today only)", [["times", "more than", "× the daily budget"]]],
  ["week_overspend", "The week's spend is high", [["times", "more than", "× the daily budget in 7 days"]]],
  ["spend_cap", "The account spending limit is nearly used", [["percent", "at", "%"]]],
  ["cap_soon", "The spending limit will run out soon at this pace", [["days", "within", "days"]]],
  ["pace_over", "The month is heading over your monthly target (set it on Results)", [["percent", "by more than", "%"]]],
  ["cpl_high", "Leads cost too much", [["target_cents", "target $", "per lead,"], ["times", "alert above", "× the target"]]],
  ["no_leads", "No leads while the ads spend", [["days", "for", "days in a row"]]],
  ["tracking", "Leads Meta counted aren't reaching the inbox", []],
  ["stale_data", "Meta stops answering", [["hours", "for", "hours"]]],
  ["events_quiet", "Lead stages stop reaching Meta's dataset (two days)", []],
];

function renderAlerts() {
  const rules = s.alerts.rules;
  $("al-rules").innerHTML = RULE_UI.map(([id, label, fields]) => {
    const r = rules[id];
    const inputs = fields.map(([k, before, after]) => {
      const v = k === "target_cents" ? (r[k] ? r[k] / 100 : "") : r[k];
      return `<label class="al-num">${esc(before)} <input class="input" type="number" min="0" step="any" inputmode="decimal" data-rule="${id}" data-key="${k}" value="${esc(String(v ?? ""))}" ${k === "target_cents" ? 'placeholder="not set"' : ""}> ${esc(after)}</label>`;
    }).join(" ");
    const hint = id === "cpl_high" && !r.target_cents ? '<small class="muted">Off until you set a target. Your brief\'s $60 is per qualified lead; this one counts every form lead.</small>' : "";
    return `<li><label class="check"><input type="checkbox" data-rule="${id}" data-key="on" ${r.on ? "checked" : ""}> ${esc(label)}</label>${inputs ? `<div class="al-fields">${inputs}</div>` : ""}${hint}</li>`;
  }).join("");
  const recent = s.alerts.recent;
  $("al-recent").innerHTML = recent.length ? `<h3 class="section-title">Recent alerts</h3><ul class="history">${recent.map((a) =>
    `<li>${when(a.created_at)}: ${esc(a.title)}${a.resolved_at ? ` <span class="muted">(cleared ${when(a.resolved_at)})</span>` : ""}</li>`).join("")}</ul>` : '<p class="muted small">No alerts yet.</p>';
}

const every = (m) => (m === 60 ? "Every hour" : `Every ${m} minutes`);

function renderAuto() {
  $("auto-minutes").innerHTML = s.auto_refresh_choices.map((m) => `<option value="${m}">${every(m)}</option>`).join("");
  $("auto-minutes").value = String(s.auto_refresh_minutes);
  $("auto-state").innerHTML = `<span class="pill ok">${esc(every(s.auto_refresh_minutes))}</span>`;
}

async function load() {
  s = await api("/api/settings");
  fill($("meta-form"), s.meta);
  fill($("smtp-form"), s.smtp);
  const use = s.smtp_in_use || { source: "none" };
  const note = $("smtp-source");
  note.hidden = false;
  note.textContent = use.source === "website"
    ? `Using the website's email settings: ${use.host}, sending from ${use.from_email}. Nothing to fill in here. Change them in the website admin under Email, or enter a different mailbox below to send ad alerts from it instead.`
    : use.source === "own"
      ? `Using the mailbox below (${use.host}). Clear the SMTP server and save to go back to the website's email settings.`
      : "Email isn't set up yet. Set it up once in the website admin under Email and it's used here too, or enter a mailbox below.";
  renderMeta();
  renderCrm();
  renderAuto();
  renderMetaTests();
  loadTracking();
  renderTelegram();
  renderAlerts();
  if (editing === null) renderReplies();
  const rows = await api("/api/settings/activity");
  $("activity").innerHTML = rows.length ? `<thead><tr><th>When</th><th>Who</th><th>What</th></tr></thead><tbody>${rows.map((r) =>
    `<tr><td class="muted">${when(r.at)}</td><td>${esc(r.who || ({ meta: "Meta", claude: "Claude", system: "System" }[r.actor] || r.actor))}</td><td>${esc(describe(r))}${r.subject && !r.action.startsWith("lead.") ? ` <span class="muted">${esc(r.subject)}</span>` : ""}</td></tr>`).join("")}</tbody>`
    : '<tbody><tr><td class="muted">Nothing yet.</td></tr></tbody>';
}

function values(form) {
  const out = {};
  for (const el of form.elements) if (el.name) out[el.name] = el.value;
  return out;
}

async function run(btn, fn) {
  btn.disabled = true;
  try { await fn(); } catch (err) { toast(err.message, "bad"); } finally { btn.disabled = false; }
}

const ACTIONS = {
  "auth.password_changed": "Changed their password",
  "settings.meta": "Changed the Meta settings",
  "settings.smtp": "Changed the email settings",
  "desk.task_created": "Asked Claude something on the Desk",
  "desk.task_cancelled": "Cancelled a Desk request",
  "desk.task_done": "Claude finished a Desk request",
  "desk.task_failed": "A Desk request didn't finish",
  "desk.key_created": "Created a Mac key for the Desk",
  "desk.key_revoked": "Disconnected the Mac from the Desk",
  "settings.page_connected": "Connected the Page to receive leads",
  "sync.manual": "Synced campaigns and leads",
  "team.added": "Added a teammate",
  "team.updated": "Changed a teammate's access",
  "team.password_reset": "Reset a teammate's password",
  "settings.crm_test": "Sent a test lead stage to Meta",
  "settings.meta_ab_tests": "Changed whether A/B tests can be created on Meta",
  "settings.telegram": "Changed the Telegram bot",
  "settings.replies": "Changed the lead reply settings",
  "settings.reply_template": "Changed a lead reply template",
  "settings.alerts": "Changed the alerts",
  "settings.refresh": "Changed how often the latest comes from Meta",
  "crm.failed": "A lead stage didn't reach Meta",
  "lead.received": "New lead arrived",
  "lead.status": "Moved a lead",
  "lead.owner": "Changed a lead's owner",
  "lead.email_failed": "A lead alert email failed",
};
const describe = (r) => ACTIONS[r.action] || r.action;

const me = await boot({ page: "settings", admin: true });
if (me) {
  await load();
  $("meta-form").addEventListener("submit", (e) => { e.preventDefault(); run(e.submitter, async () => { s = await api("/api/settings/meta", { method: "PUT", body: values(e.target) }); toast("Meta settings saved"); load(); }); });
  $("smtp-form").addEventListener("submit", (e) => { e.preventDefault(); run(e.submitter, async () => { s = await api("/api/settings/smtp", { method: "PUT", body: values(e.target) }); toast("Email settings saved"); load(); }); });
  $("tg-form").addEventListener("submit", (e) => { e.preventDefault(); run(e.submitter, async () => {
    fieldError(e.target);
    try {
      s = await api("/api/settings/telegram", { method: "PUT", body: { token: $("telegram_bot_token").value } });
    } catch (err) {
      if (err.body?.field) { fieldError(e.target, err.body.field, err.message); return; }
      throw err;
    }
    toast(`Telegram bot @${s.telegram.username} is ready`); renderTelegram();
  }); });
  $("tg-remove").addEventListener("click", (e) => run(e.currentTarget, async () => {
    if (!(await confirmDialog({ title: "Remove the Telegram bot?", body: "Nobody gets Telegram alerts until a bot is added again. People's links are kept.", confirm: "Remove", danger: true }))) return;
    s = await api("/api/settings/telegram", { method: "PUT", body: { remove: true } });
    toast("Telegram bot removed"); renderTelegram();
  }));
  $("rp-form").addEventListener("submit", (e) => { e.preventDefault(); run(e.submitter, async () => {
    fieldError(e.target);
    const auto = $("rp-auto").checked;
    if (auto && !s.replies.auto) {
      const t = s.replies.templates.find((x) => String(x.id) === $("rp-auto-template").value) || s.replies.templates[0];
      const ok = await confirmDialog({ title: "Reply to every new lead by itself?",
        body: `<p>From now on every new lead that left an email gets <b>${esc(t.name)}</b> from you within a minute, before anyone has looked at it. Test leads never do.</p><p>Check the wording in the template first.</p>`,
        confirm: "Turn it on" });
      if (!ok) return;
    }
    try {
      s = await api("/api/settings/replies", { method: "PUT", body: { booking_link: $("booking_link").value, auto, auto_template_id: Number($("rp-auto-template").value) || null } });
    } catch (err) {
      if (err.body?.field) { fieldError(e.target, err.body.field, err.message); return; }
      throw err;
    }
    toast(auto ? "Saved. New leads get a reply by themselves." : "Saved"); renderReplies();
  }); });
  $("rp-auto").addEventListener("change", (e) => { $("rp-auto-pick").hidden = !e.target.checked; });
  $("tpl-list").addEventListener("click", (e) => { const b = e.target.closest("[data-edit]"); if (b) editTemplate(Number(b.dataset.edit)); });
  $("tpl-add").addEventListener("click", () => editTemplate("new"));
  $("tpl-cancel").addEventListener("click", closeTemplate);
  ["tpl-subject", "tpl-body"].forEach((id) => $(id).addEventListener("input", previewTemplate));
  $("tpl-chips").addEventListener("click", (e) => {
    const b = e.target.closest("[data-insert]");
    if (!b) return;
    const body = $("tpl-body");
    const at = body.selectionStart ?? body.value.length;
    body.setRangeText(b.dataset.insert, at, body.selectionEnd ?? at, "end");
    body.focus();
    previewTemplate();
  });
  $("tpl-form").addEventListener("submit", (e) => { e.preventDefault(); run(e.submitter, async () => {
    fieldError(e.target);
    const body = { name: $("tpl-name").value, subject: $("tpl-subject").value, body: $("tpl-body").value };
    try {
      s = editing === "new" ? await api("/api/settings/replies/templates", { method: "POST", body })
        : await api(`/api/settings/replies/templates/${editing}`, { method: "PUT", body });
    } catch (err) {
      if (err.body?.field) { fieldError(e.target, err.body.field, err.message); return; }
      throw err;
    }
    toast("Template saved"); closeTemplate(); renderReplies();
  }); });
  $("tpl-delete").addEventListener("click", (e) => run(e.currentTarget, async () => {
    const t = s.replies.templates.find((x) => x.id === editing);
    if (!(await confirmDialog({ title: `Delete “${t.name}”?`, body: "Emails already sent keep their text.", confirm: "Delete", danger: true }))) return;
    s = await api(`/api/settings/replies/templates/${editing}`, { method: "DELETE" });
    toast("Template deleted"); closeTemplate(); renderReplies();
  }));
  $("al-form").addEventListener("submit", (e) => { e.preventDefault(); run(e.submitter, async () => {
    const rules = {};
    $("al-rules").querySelectorAll("[data-rule]").forEach((el) => {
      const r = (rules[el.dataset.rule] ||= {});
      if (el.type === "checkbox") r.on = el.checked;
      else r[el.dataset.key] = el.dataset.key === "target_cents" ? (el.value === "" ? null : Math.round(Number(el.value) * 100)) : el.value;
    });
    s = await api("/api/settings/alerts", { method: "PUT", body: { rules } });
    toast("Alerts saved"); renderAlerts();
  }); });
  $("auto-form").addEventListener("submit", (e) => { e.preventDefault(); run(e.submitter, async () => {
    s = await api("/api/settings/refresh", { method: "PUT", body: { minutes: Number($("auto-minutes").value) } });
    toast(`The latest now comes from Meta ${every(s.auto_refresh_minutes).toLowerCase()}`); renderAuto();
  }); });
  $("tr-fresh").addEventListener("click", () => loadTracking(true));
  $("mt-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const on = $("mt-on").checked;
    if (on && !s.meta_ab_tests && !(await confirmDialog({ title: "Allow A/B tests on Meta?",
      body: "<p>Admins can then create A/B tests on Meta from the Tests page. Each test shows its dates and cost and needs its own yes before anything is created. Ad tests spend a test budget on top of the campaign's.</p>",
      confirm: "Allow" }))) { $("mt-on").checked = false; return; }
    run(e.submitter, async () => {
      s = await api("/api/settings/meta-tests", { method: "PUT", body: { on } });
      toast(on ? "Meta A/B tests are on" : "Meta A/B tests are off"); renderMetaTests();
    });
  });
  $("crm-form").addEventListener("submit", (e) => { e.preventDefault(); run(e.submitter, async () => {
    s = await api("/api/settings/meta", { method: "PUT", body: { meta_dataset_id: $("meta_dataset_id").value, crm_send_enabled: $("crm_send_enabled").checked ? "1" : "" } });
    toast($("crm_send_enabled").checked ? "Lead stages now go to Meta" : "Lead stages are no longer sent"); load();
  }); });
  $("crm-test").addEventListener("click", (e) => run(e.currentTarget, async () => {
    const r = await api("/api/settings/meta/crm-test", { method: "POST", body: { code: $("crm-code").value } });
    $("crm-result").innerHTML = `<p class="note ok">Meta received ${esc(String(r.received ?? 0))} event. Check Test events in Events Manager.</p>`;
  }));
  $("smtp-test").addEventListener("click", (e) => run(e.currentTarget, async () => { const r = await api("/api/settings/smtp/test", { method: "POST" }); toast(`Test email sent to ${r.sent_to}${r.source === "website" ? " using the website's mailbox" : ""}`); }));
  $("meta-test").addEventListener("click", (e) => run(e.currentTarget, async () => {
    const r = await api("/api/settings/meta/test", { method: "POST" });
    $("meta-result").innerHTML = `<p class="note ok">Connected as <b>${esc(r.system_user)}</b>. Page: ${esc(r.page)}${r.page_token ? "" : " (can't act for it)"}. Ad account: ${esc(r.ad_account)} (${esc(r.currency)}).</p>`;
  }));
  $("meta-connect").addEventListener("click", (e) => run(e.currentTarget, async () => { await api("/api/settings/meta/connect-page", { method: "POST" }); toast("The Page now sends new leads here"); load(); }));
  $("meta-sync").addEventListener("click", (e) => run(e.currentTarget, async () => { const r = await api("/api/settings/meta/sync", { method: "POST", body: { days: 30 } }); toast(`${r.campaigns} campaign(s) synced, ${r.new_leads} new lead(s)`); load(); }));
}
