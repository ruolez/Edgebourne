// Settings → Ads Manager link (AM-A). The Mac reads what only Ads Manager shows (drafts, Meta's error messages,
// benchmarks…) through Meta's own Ads tools, and only reads. The owner connects it once on the Mac; the owner and this
// account's admins see what it read for this account and can ask for a fresh read. Words come from the server.
import { api } from "./api.js";
import { confirmDialog, esc, linkNote, switchHtml, toast, when } from "./ui.js";

const PILL = { connected: ["ok", "Connected"], fallback: ["ok", "Through Claude"], connecting: ["warn", "Waiting for your Mac"],
  expired: ["bad", "Reconnect needed"], refused: ["bad", "Refused"], off: ["", "Disconnecting"], not_connected: ["", "Not connected"] };
const WAITING = ["connecting", "off"];
let box = null;
let data = null;
let poll = null;
let recheck = null;

function stateLine(l, owner) {
  if (l.state === "connected" && owner && l.connected_as) {
    return `Connected as <b>${esc(l.connected_as)}</b>${l.last_ok_at ? ` · last read ${esc(when(l.last_ok_at))}` : ""}`;
  }
  return `<b>${esc(l.words)}</b>${l.state === "fallback" && l.last_ok_at ? ` · last read ${esc(when(l.last_ok_at))}` : ""}`;
}

function connectionHtml(l) {
  const connected = ["connected", "fallback", "expired", "refused"].includes(l.state);
  const busy = WAITING.includes(l.state);
  return `<div class="am-conn" id="am-conn">
    <p class="flush am-line" id="am-line">${stateLine(l, true)}</p>
    ${l.state === "fallback" && l.fallback_reason ? `<details class="tech am-why" id="am-why"><summary>Why <small>Meta didn't let the Mac's own helper in</small></summary>
      <p class="flush small">${esc(l.fallback_reason)}</p><p class="flush small muted">Claude on your Mac reads the same things instead, every 30 minutes for drafts and errors. Nothing for you to do.</p></details>` : ""}
    ${l.last_error && !busy ? `<p class="note warn flush" id="am-error">${esc(l.last_error)}</p>` : ""}
    ${!l.helper_ok ? '<p class="note warn flush" id="am-helper">Update the Mac helper first: run ads/bridge/install.sh on the Mac, then press Connect.</p>' : ""}
    ${!l.mac_online && l.mac_set_up ? '<p class="flush small muted" id="am-offline">Your Mac is offline right now. It picks this up when it is back.</p>' : ""}
    <p class="flush small muted">${connected ? "Reconnect opens" : "Connect opens"} a Facebook page on your Mac. Sign in and allow it. Nothing changes in your ads: the link only reads.</p>
    ${l.scope && connected ? `<p class="flush small muted" id="am-scope">Meta allowed: ${esc(l.scope)}</p>` : ""}
    <div class="row am-acts">
      <button class="btn btn-primary" type="button" id="am-connect"${busy || !l.helper_ok ? " disabled" : ""}>${l.state === "connecting" ? "Waiting for your Mac…" : connected ? "Reconnect" : "Connect"}</button>
      ${l.state === "connecting" ? '<button class="btn btn-quiet" type="button" id="am-cancel">Cancel</button>' : ""}
      ${connected ? '<button class="btn btn-quiet" type="button" id="am-disconnect">Disconnect</button>' : ""}
    </div>
    <details class="tech" id="am-adv"><summary>Advanced <small>Use my Meta app for the login</small></summary>
      <label class="check"><input type="checkbox" id="am-use-app" data-no-guard ${l.use_app ? "checked" : ""}${l.app_id_set ? "" : " disabled"}> <span>Use my Meta app for the login
        <span class="explain">${l.app_id_set ? `Add <b>${esc(l.redirect_uri)}</b> to the app's Facebook Login for Business redirect list first (setup guide, part J). Used on the next Connect.`
          : "Set the Meta app in Settings → Meta app first."}</span></span></label>
    </details>
  </div>`;
}

function runLine(r) {
  const words = { open: "reading…", done: r.kept ? `${r.kept} kept` : "nothing new", failed: "didn't finish", no_access: "no access", expired: "didn't finish" }[r.status] || r.status;
  return `<li>${esc(when(r.at))} · ${r.forced ? "Check now · " : ""}${esc(r.mode === "claude" ? "through Claude · " : "")}${esc(words)}${r.error ? ` <span class="muted">(${esc(r.error)})</span>` : ""}</li>`;
}

function switchNote(a) {
  if (a.reading === "changed") return a.can_turn_on ? "This account's ad account changed. Switch reading on again to read the new one." : "This account's ad account changed. The console owner switches reading on again for the new one.";
  if (!a.on && !a.can_turn_on) return "Only the console owner can switch this on: the Mac reads with his Facebook login.";
  return "";
}

function checkNote(a, l, live) {
  if (!live) return "Connect the link first.";
  if (a.check_after) return "Checked a moment ago.";
  if (!a.can_check && a.on && a.ad_account_id && l.mode === "claude") return "Through Claude, only the console owner can ask for a read now.";
  return "Reads everything at once, within a minute while your Mac is on.";
}

function accountHtml(a, l) {
  const live = ["connected", "fallback"].includes(l.state);
  const note = switchNote(a);
  const locked = !a.on && !a.can_turn_on;
  const rows = a.groups.map((g) => `<tr data-group="${esc(g.group)}"><td>${esc(g.label)}</td><td data-label="How often">${esc(g.every)}</td>
    <td data-label="Last read" class="am-last">${esc(g.last ? when(g.last) : g.last_words)}</td></tr>`).join("");
  return `<div class="am-acct" id="am-acct">
    <h3 class="am-title">What it reads for ${esc(a.name || "this account")}</h3>
    ${a.ad_account_id ? "" : '<p class="note warn flush">This account has no ad account yet (Settings → Meta connection).</p>'}
    <div class="row am-switch"><span id="am-on-switch">${switchHtml(a.on, `id="am-on"${locked ? " disabled" : ""}`, "Read this account through the Mac")}</span><b>Read this account through the Mac</b></div>
    ${note ? `<p class="flush small muted" id="am-on-note">${esc(note)}</p>` : ""}
    ${a.no_access ? '<p class="note warn flush" id="am-no-access">Your Facebook login on the Mac can\'t see this ad account. Ask for access in Business Settings, or switch reading off here.</p>' : ""}
    <table class="table am-kinds" id="am-kinds"><thead><tr><th>What it reads</th><th>How often</th><th>Last read</th></tr></thead><tbody>${rows}</tbody></table>
    <div id="am-source">${linkNote(a.source)}</div>
    <div class="row am-acts"><button class="btn" type="button" id="am-check"${a.can_check && !a.check_after ? "" : " disabled"}>Check Ads Manager now</button>
      <span class="small muted" id="am-check-note">${esc(checkNote(a, l, live))}</span></div>
    ${a.runs.length ? `<details class="tech" id="am-runs"><summary>Recent reads <small>${esc(when(a.runs[0].at))}</small></summary><ul class="am-run-list">${a.runs.map(runLine).join("")}</ul></details>` : ""}
  </div>`;
}

function paint() {
  const l = data.link;
  const [cls, label] = PILL[l.state] || ["", l.words];
  document.getElementById("am-state").innerHTML = `<span class="pill ${cls}">${esc(label)}</span>`;
  box.innerHTML = `<p class="flush muted">Reads what only Ads Manager shows (drafts, Meta's error messages, benchmarks, unusual changes, tracking quality) through Meta's own Ads tools on your Mac. It never changes anything in your ads.</p>
    ${data.owner ? connectionHtml(l) : `<p class="flush am-line" id="am-line">${stateLine(l, false)}</p>`}
    ${accountHtml(data.account, l)}`;
  clearTimeout(poll);
  clearTimeout(recheck);
  const reading = data.account.runs.some((r) => r.status === "open");
  if (WAITING.includes(l.state) || reading) poll = setTimeout(load, 3000);
  if (data.account.check_after) recheck = setTimeout(load, data.account.check_after * 1000 + 200);
}

async function act(fn, done) {
  try { data = await fn(); paint(); if (done) toast(done); } catch (err) { toast(err.message, "bad"); }
}

function wire() {
  box.addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b || b.disabled) return;
    if (b.id === "am-connect") {
      act(() => api("/api/am-link/connect", { method: "POST", body: {} }), "Your Mac opens a Facebook page in a moment. Sign in there and allow it.");
    } else if (b.id === "am-cancel") {
      act(() => api("/api/am-link/disconnect", { method: "POST", body: {} }), "Cancelled");
    } else if (b.id === "am-disconnect") {
      const yes = await confirmDialog({ title: "Disconnect the Ads Manager link?", danger: true, confirm: "Disconnect",
        body: "<p>Your Mac removes its Facebook login for the link. Drafts and Meta's extra numbers stop updating here until you connect again. Nothing in your ads changes.</p>" });
      if (yes) act(() => api("/api/am-link/disconnect", { method: "POST", body: {} }), "Disconnecting. Your Mac removes its login in a moment.");
    } else if (b.id === "am-on") {
      const on = b.getAttribute("aria-checked") !== "true";
      act(() => api("/api/am-link/account", { method: "PATCH", body: { on } }), on ? "This account is read through the Mac again" : "This account is no longer read through the Mac");
    } else if (b.id === "am-check") {
      b.disabled = true;
      act(() => api("/api/am-link/check", { method: "POST", body: {} }), "Asked your Mac to read Ads Manager now").then(() => { clearTimeout(poll); poll = setTimeout(load, 3000); });
    }
  });
  box.addEventListener("change", (e) => {
    if (e.target.id !== "am-use-app") return;
    act(() => api("/api/am-link", { method: "PATCH", body: { use_app: e.target.checked } }), e.target.checked ? "The next Connect uses your Meta app" : "The next Connect registers the Mac's helper by itself");
  });
}

export async function load() {
  box = document.getElementById("am-body");
  if (!box) return;
  if (!box.dataset.wired) { wire(); box.dataset.wired = "1"; }
  if (box.closest("[data-section]")?.hidden) { clearTimeout(poll); clearTimeout(recheck); return; }
  try { data = await api("/api/am-link"); paint(); } catch (err) { box.innerHTML = `<p class="note warn flush">${esc(err.message)}</p>`; }
}
