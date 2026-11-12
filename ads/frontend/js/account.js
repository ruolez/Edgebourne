import { api } from "./api.js";
import { applyTheme, boot, canInstall, confirmDialog, currentTheme, esc, fieldError, promptInstall, toast, when } from "./ui.js";

const me = await boot({ page: "account" });
if (me) {
  const choice = document.getElementById("theme-choice");
  const mark = () => choice.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeChoice === currentTheme())));
  mark();
  choice.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-theme-choice]");
    if (!b) return;
    applyTheme(b.dataset.themeChoice);
    mark();
  });
  document.getElementById("account-signout").addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST" });
    location.href = "/login.html";
  });
  const first = new URLSearchParams(location.search).get("first") === "1" || me.must_change_password;
  document.getElementById("first-note").hidden = !first;
  const notify = document.getElementById("notify");
  notify.checked = me.notify_new_leads;
  notify.addEventListener("change", async () => {
    try {
      await api("/api/auth/me", { method: "PATCH", body: { notify_new_leads: notify.checked } });
      toast(notify.checked ? "You'll get an email for each new lead" : "Lead emails turned off");
    } catch (err) { toast(err.message, "bad"); }
  });
  const remind = document.getElementById("remind");
  remind.checked = me.notify_reminders;
  remind.addEventListener("change", async () => {
    try {
      await api("/api/auth/me", { method: "PATCH", body: { notify_reminders: remind.checked } });
      toast(remind.checked ? "You'll be reminded about leads nobody has contacted" : "Reminders turned off");
    } catch (err) { toast(err.message, "bad"); }
  });

  const alertsOn = document.getElementById("alerts-on");
  document.getElementById("alerts-row").hidden = me.role !== "admin";
  alertsOn.checked = me.notify_alerts;
  alertsOn.addEventListener("change", async () => {
    try {
      await api("/api/auth/me", { method: "PATCH", body: { notify_alerts: alertsOn.checked } });
      toast(alertsOn.checked ? "You'll hear about problems with the ads" : "Ad alerts turned off");
    } catch (err) { toast(err.message, "bad"); }
  });

  // Telegram: connect once, then new leads and reminders arrive on the phone.
  const tg = document.getElementById("tg");
  let tgPoll;
  const renderTg = (t) => {
    clearTimeout(tgPoll);
    if (!t.bot) {
      tg.innerHTML = `<p class="muted">Telegram alerts: ${me.role === "admin" ? 'add the bot in <a href="/settings.html">Settings → Telegram</a> first.' : "an admin sets up the bot first."}</p>`;
    } else if (t.linked) {
      tg.innerHTML = `<label class="check"><input type="checkbox" id="tg-on" ${t.enabled ? "checked" : ""}> Send new leads and reminders to my Telegram <span class="muted">(${esc(t.name || "connected")})</span></label>
        <div class="row"><button class="btn" type="button" id="tg-test">Send a test</button><button class="btn btn-danger-text" type="button" id="tg-off">Disconnect Telegram</button></div>`;
    } else if (t.pending) {
      tg.innerHTML = `<p>Open Telegram and tap <b>Start</b> in the chat with @${esc(t.bot)}. This page notices by itself.</p>
        <div class="row"><a class="btn btn-primary" id="tg-open" href="${esc(t.link)}" target="_blank" rel="noopener noreferrer">Open Telegram</a><span class="muted">Waiting for you to tap Start…</span></div>`;
      tgPoll = setTimeout(async () => {
        const next = await api("/api/me/telegram").catch(() => t);
        if (next.linked) toast("Telegram connected. Check your phone.");
        renderTg(next);
      }, 3000);
    } else {
      tg.innerHTML = `<p>Get each new lead on your phone, seconds after it arrives.</p>
        <div class="row"><button class="btn btn-primary" type="button" id="tg-link">Connect Telegram</button></div>`;
    }
  };
  tg.addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    b.disabled = true;
    try {
      if (b.id === "tg-link") renderTg(await api("/api/me/telegram/link", { method: "POST" }));
      if (b.id === "tg-test") { await api("/api/me/telegram/test", { method: "POST" }); toast("Sent. Check Telegram."); }
      if (b.id === "tg-off" && await confirmDialog({ title: "Disconnect Telegram?", body: "New leads and reminders stop going to your Telegram. You can connect again any time.", confirm: "Disconnect", danger: true })) {
        renderTg(await api("/api/me/telegram", { method: "DELETE" }));
        toast("Telegram disconnected");
      }
    } catch (err) { toast(err.message, "bad"); } finally { b.disabled = false; }
  });
  tg.addEventListener("change", async (e) => {
    if (e.target.id !== "tg-on") return;
    try {
      renderTg(await api("/api/me/telegram", { method: "PATCH", body: { enabled: e.target.checked } }));
      toast(e.target.checked ? "New leads go to your Telegram" : "Telegram alerts paused");
    } catch (err) { toast(err.message, "bad"); }
  });
  api("/api/me/telegram").then(renderTg).catch(() => { tg.hidden = true; });

  const form = document.getElementById("pw-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    fieldError(form);
    try {
      await api("/api/auth/password", { method: "POST", body: { current: form.current.value, new: form.new.value } });
      form.reset();
      toast("Password changed");
      if (first) location.href = "/home.html";
    } catch (err) {
      if (err.body.field) fieldError(form, err.body.field, err.message); else toast(err.message, "bad");
    }
  });

  wireDevice();
}

// ---------------------------------------------------------------- this device: app + push

function standalone() { return matchMedia("(display-mode: standalone)").matches || navigator.standalone === true; }
function isIOS() { return /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1); }
function pushSupported() { return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window; }

function deviceLabel() {
  const ua = navigator.userAgent;
  const os = /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) || isIOS() ? "iPad" : /Android/.test(ua) ? "Android" : /Mac/.test(ua) ? "Mac" : /Windows/.test(ua) ? "Windows" : "Computer";
  const browser = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Browser";
  return `${os} · ${browser}${standalone() ? " (app)" : ""}`;
}

function b64ToBytes(b64) {
  const s = atob(b64.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (b64.length % 4)) % 4));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
}

function renderInstall() {
  const box = document.getElementById("install-box");
  if (standalone()) { box.innerHTML = '<p class="flush"><b>Installed.</b> <span class="muted">You\'re using the app.</span></p>'; return; }
  if (isIOS()) {
    box.innerHTML = '<p class="flush"><b>Install on iPhone:</b> tap Share <span aria-hidden="true">⎙</span>, then <b>Add to Home Screen</b>. Notifications on iPhone work only from the installed app.</p>';
    return;
  }
  box.innerHTML = canInstall()
    ? '<div class="row"><button type="button" class="btn" id="install">Install the app</button><span class="muted small">Opens in its own window, with an icon on your dock or home screen.</span></div>'
    : '<p class="muted flush small">To install: use your browser\'s Install option (Chrome and Edge: the icon at the right of the address bar).</p>';
}

async function currentSub() {
  if (!pushSupported()) return null;
  const reg = await navigator.serviceWorker.ready;
  return reg.pushManager.getSubscription();
}

async function renderPush(view) {
  const box = document.getElementById("push-box");
  if (!pushSupported()) {
    box.innerHTML = `<p class="muted flush">${isIOS() && !standalone() ? "Install the app first (above), then turn notifications on from it." : "This browser can't show notifications."}</p>`;
  } else if (Notification.permission === "denied") {
    box.innerHTML = '<p class="note warn flush">Notifications are blocked for this site. Allow them in the browser\'s site settings, then come back here.</p>';
  } else {
    const sub = await currentSub();
    box.innerHTML = sub
      ? `<div class="row"><span class="pill ok">Notifications on</span><button type="button" class="btn btn-small" id="push-test">Send a test</button><button type="button" class="btn btn-quiet btn-small" id="push-off">Turn off on this device</button></div>
         <p class="muted small flush">New leads, reminders and alerts come here instead of email (Telegram still comes first if it's connected).</p>`
      : `<div class="row"><button type="button" class="btn btn-primary" id="push-on">Turn on notifications</button><span class="muted small">New leads, reminders and alerts pop up on this device, even when the console is closed.</span></div>`;
  }
  document.getElementById("devices").innerHTML = view.devices.length
    ? `<ul class="device-list">${view.devices.map((d) => `<li><span><b>${esc(d.label || "A device")}</b><small class="muted">on since ${esc(when(d.created_at))}${d.last_ok_at ? ` · last delivered ${esc(when(d.last_ok_at))}` : ""}</small></span>
        <button type="button" class="link-btn muted" data-device-off="${d.id}">Remove</button></li>`).join("")}</ul>` : "";
}

async function loadPush() {
  try { renderPush(await api("/api/me/push")); } catch (err) { document.getElementById("push-box").innerHTML = `<p class="note warn flush">${esc(err.message)}</p>`; }
}

function wireDevice() {
  renderInstall();
  document.addEventListener("ebads:installable", renderInstall);
  loadPush();
  document.getElementById("device").addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    try {
      if (b.id === "install") { if (await promptInstall()) toast("Installed"); renderInstall(); return; }
      if (b.id === "push-on") {
        b.disabled = true;
        if ((await Notification.requestPermission()) !== "granted") { toast("Notifications weren't allowed", "bad"); loadPush(); return; }
        const view = await api("/api/me/push");
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(view.public_key) });
        renderPush(await api("/api/me/push", { method: "POST", body: { subscription: sub.toJSON(), label: deviceLabel() } }));
        toast("Notifications are on for this device");
      }
      if (b.id === "push-test") { await api("/api/me/push/test", { method: "POST" }); toast("Sent. It should pop up in a moment."); }
      if (b.id === "push-off") {
        const sub = await currentSub();
        if (sub) { await api("/api/me/push/off", { method: "POST", body: { endpoint: sub.endpoint } }); await sub.unsubscribe(); }
        loadPush(); toast("Notifications off for this device");
      }
      if (b.dataset.deviceOff) { renderPush(await api(`/api/me/push/${b.dataset.deviceOff}`, { method: "DELETE" })); toast("Removed"); }
    } catch (err) { toast(err.message, "bad"); b.disabled = false; }
  });
}
