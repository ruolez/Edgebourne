// FU-A: Add an ad account. Lists every ad account the console's Meta key reaches (GET /api/accounts/reachable),
// says why one can't be added, and turns the one picked into its own console account (POST /api/accounts/from-meta,
// checked again on the server). When the one wanted isn't listed, the help says how to make it appear.
import { api } from "./api.js";
import { addAccountByName, confirmDialog, esc, skeleton, toast } from "./ui.js";

const VIA = { assigned: "assigned to the console", owned: "your Business", client: "shared with your Business" };
// An amount in the picked ad account's own currency (format.money uses the open account's).
const inCurrency = (cents, currency) => (cents / 100).toLocaleString(undefined, { style: "currency", currency: currency || "USD", minimumFractionDigits: 0, maximumFractionDigits: 2 });
const TONE = { 1: "ok", 201: "ok", 3: "warn", 7: "warn", 8: "warn", 9: "warn" };

function helpHtml(who) {
  return `<summary>Can't see the one you want?</summary>
    <div class="acp-help-body">
      <p><b>Can't see the ad account?</b> If you were added to it as a person, the console's Meta key can't see it yet. Three steps make it appear:</p>
      <ol>
        <li>In Meta <b>Business Settings</b>, open <b>Accounts → Ad accounts</b>, press <b>Add</b>, then <b>Request access to an ad account</b>, and type its ID (the number after act_, from Ads Manager's account menu).</li>
        <li>Its owner accepts the request. Meta tells them in their Business Settings and by notification.</li>
        <li>Back in <b>Business Settings → Ad accounts</b>, pick that ad account, press <b>Assign people</b>, choose <b>System users → ${esc(who)}</b>, and turn on <b>Manage campaigns</b>. Then press <b>Look again</b> here.</li>
      </ol>
      <p>Another way: add it by name now, then paste that ad account's own System User token in its Meta connection.</p>
      <div class="row"><button type="button" class="btn btn-small" data-acp-plain>Add without Meta for now</button></div>
    </div>`;
}

function rowHtml(i) {
  const tone = TONE[i.status] || "bad";
  const via = i.via.map((v) => VIA[v]).filter(Boolean).join(", ");
  return `<li class="acp-row${i.blocked ? " is-blocked" : ""}">
    <label class="acp-pick"><input type="radio" name="acp" value="${esc(i.id)}"${i.blocked ? " disabled" : ""}>
      <span class="acp-text"><b class="acp-name">${esc(i.name || `Ad account ${i.id.slice(-4)}`)}</b>
        <span class="acp-meta"><span class="acp-id">act_${esc(i.id)}</span> · ${esc(i.currency || "?")} <span class="pill ${tone}">${esc(i.status_words)}</span>${via ? ` <span class="muted">${esc(via)}</span>` : ""}</span>
        ${i.blocked ? `<small class="acp-why">${esc(i.blocked)}</small>` : ""}</span></label></li>`;
}

// Opens the picker. Resolves once it is closed; on success the page moves to the new account's Meta connection.
export async function openPicker() {
  let data = null;
  const done = confirmDialog({ title: "Add an ad account", confirm: "Add this account", wide: true, extra: "acp",
    body: `<p class="muted flush">Ad accounts the console's Meta key can reach. Each one becomes its own account here, with its own leads, ads, results, Claude and settings.</p>
      <div id="acp-body">${skeleton("Asking Meta which ad accounts the console can reach…")}</div>
      <div class="field" id="acp-name-box" hidden><label for="acp-name">Name in the console</label>
        <input class="input" id="acp-name" autocomplete="off" maxlength="120"><span class="hint">Usually the business it advertises.</span>
        <span class="err" id="acp-err" role="alert" hidden></span></div>
      <p class="muted small" id="acp-ceiling" hidden></p>
      <details class="acp-help" id="acp-help"></details>
      <div class="row"><button type="button" class="link-btn" id="acp-again">Look again</button></div>` });
  const dlg = document.querySelector("dialog.acp");
  const ok = dlg.querySelector("#cd-ok");
  const name = dlg.querySelector("#acp-name");
  const err = dlg.querySelector("#acp-err");
  const box = dlg.querySelector("#acp-body");
  const help = dlg.querySelector("#acp-help");
  ok.disabled = true;
  help.innerHTML = helpHtml("the console's System User");
  const picked = () => dlg.querySelector('input[name="acp"]:checked');
  const showErr = (text) => { err.textContent = text; err.hidden = !text; };

  const paint = () => {
    const usable = data.items.filter((i) => !i.blocked);
    help.innerHTML = helpHtml(data.system_user || "the console's System User");
    help.open = help.open || usable.length === 0;  // opened by hand stays open
    const partial = data.partial.length ? `<p class="muted small" id="acp-partial">Your Business's own list couldn't be read (the key needs Business management). Showing the accounts assigned to the console only.</p>` : "";
    box.innerHTML = data.items.length
      ? `${partial}<ul class="acp-list" role="radiogroup" aria-label="Ad accounts">${data.items.map(rowHtml).join("")}</ul>
         ${usable.length ? "" : '<p class="note" id="acp-none">Every ad account listed is already in the console or can\'t be run from it. See below to bring in another one.</p>'}`
      : `${partial}<p class="note" id="acp-none">The console's Meta key can't reach any ad account yet. See below.</p>`;
    ok.disabled = true;
    dlg.querySelector("#acp-name-box").hidden = true;
    dlg.querySelector("#acp-ceiling").hidden = true;
  };
  const load = async (fresh) => {
    box.innerHTML = skeleton("Asking Meta which ad accounts the console can reach…");
    ok.disabled = true;
    try {
      data = await api(`/api/accounts/reachable${fresh ? "?fresh=1" : ""}`);
      paint();
    } catch (e) {
      box.innerHTML = `<div class="note bad-text" role="alert">${esc(e.message)} <button type="button" class="btn btn-small" id="acp-retry">Try again</button></div>`;
      box.querySelector("#acp-retry").addEventListener("click", () => load(true));
      help.open = true;
    }
  };

  box.addEventListener("change", () => {
    const r = picked();
    const item = r && data.items.find((i) => i.id === r.value);
    if (!item || item.blocked) return;
    const nameBox = dlg.querySelector("#acp-name-box");
    const ceiling = dlg.querySelector("#acp-ceiling");
    nameBox.hidden = false;
    // The server's default ceiling, in the new account's own currency (its money rule, not Edge Bourne's).
    ceiling.textContent = `It starts with a highest daily budget of ${inCurrency(data.default_max_daily_cents, item.currency)}. Change it in its Settings → Targets.`;
    ceiling.hidden = false;
    name.value = (item.name || `Ad account ${item.id.slice(-4)}`).replace(/\s+/g, " ").trim().slice(0, 120);
    showErr("");
    ok.disabled = false;
    // On a phone the list fills the screen: bring the name field and the Add button into view.
    (dlg.querySelector("#cd-ok") || nameBox).scrollIntoView({ block: "nearest", behavior: "smooth" });
  });
  dlg.querySelector("#acp-again").addEventListener("click", () => load(true));
  dlg.addEventListener("click", (e) => {
    if (!e.target.closest("[data-acp-plain]")) return;
    dlg.addEventListener("close", () => addAccountByName().catch((x) => toast(x.message, "bad")), { once: true });  // after the picker is gone
    dlg.close();
  });
  // The server decides: it reads Meta's list again and refuses an ad account another account holds.
  dlg.querySelector("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const r = picked();
    if (!r) return;
    ok.disabled = true;
    showErr("");
    try {
      const made = await api("/api/accounts/from-meta", { method: "POST", body: { ad_account_id: r.value, name: name.value.trim() } });
      try { sessionStorage.setItem("ebads-toast", `${made.name} added. Its results arrive within a few minutes.`); } catch (x) { /* storage off */ }
      // The new account is chosen by a cookie the answer set: the page loads again in it (also from Settings itself).
      const same = location.pathname === "/settings.html";
      location.href = "/settings.html#meta";
      if (same) location.reload();
    } catch (x) {
      showErr(x.message);
      ok.disabled = false;
      if (x.body && x.body.field === "name") name.focus();
    }
  });
  load(false);
  return done;
}
