import { api } from "./api.js";
import { boot, entityLink, esc, fieldError, toast, when, confirmDialog, errorState, onRefresh } from "./ui.js";

const $ = (id) => document.getElementById(id);
let data = { members: [], campaigns: [] };
let editing = null;
let me;

function campaignNames(ids) {
  if (!ids.length) return '<span class="muted">None yet</span>';
  // A campaign still synced links to its page; an id the console no longer knows stays plain.
  return ids.map((id) => { const c = data.campaigns.find((x) => x.id === id); return c ? entityLink("campaign", id, c.name) : esc(id); }).join("<br>");
}

function render() {
  $("team-table").innerHTML = `
    <thead><tr><th>Name</th><th>Access</th><th>Campaigns</th><th>Last signed in</th><th><span class="sr-only">Actions</span></th></tr></thead>
    <tbody>${data.members.map((m) => `
      <tr class="${m.is_active ? "" : "muted"}">
        <td><b>${esc(m.name)}</b><br><span class="muted">${esc(m.email)}</span></td>
        <td data-label="Access">${m.is_active ? (m.access === "admin" ? '<span class="pill ok">Admin, every account</span>' : m.access === "account_admin" ? '<span class="pill ok">Admin of this account</span>' : m.role === "client" ? `<span class="pill claude">Client${me.account.clients_update_leads ? "" : " (read-only)"}</span>` : '<span class="pill">Team member</span>') : '<span class="pill bad">Deactivated</span>'}</td>
        <td data-label="Campaigns">${m.role === "admin" ? '<span class="muted">All campaigns</span>' : m.role === "client" ? '<span class="muted">This whole account</span>' : campaignNames(m.campaign_ids)}</td>
        <td data-label="Last signed in">${m.last_login_at ? when(m.last_login_at) : '<span class="muted">Never</span>'}</td>
        <td class="tm-acts"><div class="row">
          ${m.access === "admin" && !data.owner ? "" : `<button class="btn" data-edit="${m.id}" aria-label="Edit ${esc(m.name)}">Edit</button>`}
          ${m.id === me.id || (m.access === "admin" && !data.owner) ? "" : `<button class="btn btn-quiet" data-reset="${m.id}">Reset password</button>
          <button class="btn btn-quiet ${m.is_active ? "btn-danger" : ""}" data-active="${m.id}">${m.is_active ? "Deactivate" : "Reactivate"}</button>`}
        </div></td>
      </tr>`).join("")}</tbody>`;
}

async function load() {
  data = await api("/api/team");
  render();
}

function openDialog(member) {
  editing = member || null;
  const form = $("member-form");
  form.reset();
  fieldError(form);
  $("member-title").textContent = member ? `Edit ${member.name}` : "Add teammate";
  $("m-save").textContent = member ? "Save" : "Add teammate";
  form.name.value = member ? member.name : "";
  form.email.value = member ? member.email : "";
  form.name.disabled = form.email.disabled = Boolean(member);
  form.role.querySelectorAll("[data-owner-only]").forEach((o) => { o.hidden = o.disabled = !data.owner; });
  form.role.value = member ? member.access : "member";
  $("m-client-note").hidden = form.role.value !== "client";
  const chosen = new Set(member ? member.campaign_ids : []);
  $("m-campaigns").innerHTML = data.campaigns.length
    ? data.campaigns.map((c) => `<label class="check"><input type="checkbox" name="campaign" value="${esc(c.id)}" ${chosen.has(c.id) ? "checked" : ""}> ${esc(c.name)}</label>`).join("")
    : '<p class="muted flush">No campaigns yet. Sync them in Settings first.</p>';
  $("member-dialog").showModal();
}

// Shown once, so it is a notice with one button (the shared dialog, no Cancel), and a Copy beside the password.
function showPassword(name, pw) {
  confirmDialog({
    title: "Temporary password", confirm: "Done", cancel: false,
    body: `<p class="flush">Give this to <b>${esc(name)}</b>. They'll be asked to choose their own the first time they sign in. It won't be shown again.</p>
      <div class="secret-row"><div class="secret-box" id="pw-value">${esc(pw)}</div><button type="button" class="btn" id="pw-copy">Copy</button></div>`,
  });
  const copy = $("pw-copy");
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(pw);
      copy.textContent = "Copied";
      toast("Password copied. Paste it in a message to them.");
    } catch (err) {
      // No clipboard (an older browser, or permission refused): select it so a long press or ⌘C copies it.
      const range = document.createRange();
      range.selectNodeContents($("pw-value"));
      getSelection().removeAllRanges();
      getSelection().addRange(range);
      toast("The password is selected: copy it from there");
    }
  });
}

me = await boot({ page: "team", admin: true });
if (me) {
  $("add-btn").addEventListener("click", () => openDialog(null));
  $("m-cancel").addEventListener("click", () => $("member-dialog").close());
  $("m-role").addEventListener("change", (e) => { $("m-client-note").hidden = e.target.value !== "client"; });
  $("member-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const campaign_ids = [...form.querySelectorAll('input[name="campaign"]:checked')].map((i) => i.value);
    try {
      if (editing) {
        await api(`/api/team/${editing.id}`, { method: "PATCH", body: { role: form.role.value, campaign_ids } });
        toast("Saved");
        $("member-dialog").close();
      } else {
        const res = await api("/api/team", { method: "POST", body: { name: form.name.value, email: form.email.value, role: form.role.value, campaign_ids } });
        $("member-dialog").close();
        showPassword(form.name.value, res.temporary_password);
      }
      load();
    } catch (err) {
      if (err.body.field) fieldError(form, err.body.field, err.message); else toast(err.message, "bad");
    }
  });
  $("team-table").addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    const id = Number(b.dataset.edit || b.dataset.reset || b.dataset.active);
    const m = data.members.find((x) => x.id === id);
    try {
      if (b.dataset.edit) openDialog(m);
      else if (b.dataset.reset) {
        if (!(await confirmDialog({ title: `Reset ${m.name}'s password?`, body: "<p>Their current password stops working. You get a temporary one to pass on.</p>", confirm: "Reset password", danger: true }))) return;
        const res = await api(`/api/team/${id}`, { method: "PATCH", body: { reset_password: true } });
        showPassword(m.name, res.temporary_password);
      } else if (b.dataset.active) {
        if (m.is_active && !(await confirmDialog({ title: `Deactivate ${m.name}?`, body: "<p>They can't sign in any more. Their notes and history stay, and you can reactivate them later.</p>", confirm: "Deactivate", danger: true }))) return;
        await api(`/api/team/${id}`, { method: "PATCH", body: { is_active: !m.is_active } });
        toast(m.is_active ? `${m.name} can no longer sign in` : `${m.name} can sign in again`);
        load();
      }
    } catch (err) { toast(err.message, "bad"); }
  });
  onRefresh(load);
  load().catch((err) => errorState(document.querySelector(".content"), err, () => location.reload()));
}
