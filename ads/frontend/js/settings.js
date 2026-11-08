import { api } from "./api.js";
import { boot, esc, toast, when } from "./ui.js";

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
  "settings.page_connected": "Connected the Page to receive leads",
  "sync.manual": "Synced campaigns and leads",
  "team.added": "Added a teammate",
  "team.updated": "Changed a teammate's access",
  "team.password_reset": "Reset a teammate's password",
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
  $("smtp-test").addEventListener("click", (e) => run(e.currentTarget, async () => { const r = await api("/api/settings/smtp/test", { method: "POST" }); toast(`Test email sent to ${r.sent_to}${r.source === "website" ? " using the website's mailbox" : ""}`); }));
  $("meta-test").addEventListener("click", (e) => run(e.currentTarget, async () => {
    const r = await api("/api/settings/meta/test", { method: "POST" });
    $("meta-result").innerHTML = `<p class="note ok">Connected as <b>${esc(r.system_user)}</b>. Page: ${esc(r.page)}${r.page_token ? "" : " (can't act for it)"}. Ad account: ${esc(r.ad_account)} (${esc(r.currency)}).</p>`;
  }));
  $("meta-connect").addEventListener("click", (e) => run(e.currentTarget, async () => { await api("/api/settings/meta/connect-page", { method: "POST" }); toast("The Page now sends new leads here"); load(); }));
  $("meta-sync").addEventListener("click", (e) => run(e.currentTarget, async () => { const r = await api("/api/settings/meta/sync", { method: "POST", body: { days: 30 } }); toast(`${r.campaigns} campaign(s) synced, ${r.new_leads} new lead(s)`); load(); }));
}
