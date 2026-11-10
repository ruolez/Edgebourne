// Edge Bourne Ads service worker: makes the console installable, shows push notifications, and
// shows a small offline page when there is no connection. Pages and data always come from the
// network (the console is live data), so nothing stale is ever shown as current.
const OFFLINE = "/offline.html";
const CACHE = "ebads-offline-v1";

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll([OFFLINE, "/img/favicon.svg", "/css/app.css"])).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  if (e.request.mode !== "navigate") return; // everything else goes straight to the network
  e.respondWith(fetch(e.request).catch(() => caches.match(OFFLINE)));
});

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { title: "Edge Bourne Ads", body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "Edge Bourne Ads", {
    body: d.body || "", icon: "/img/app/icon-192.png", badge: "/img/app/badge-96.png",
    tag: d.tag || undefined, renotify: !!d.tag, data: { url: d.url || "/home.html" },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || "/home.html", self.location.origin);
  if (url.origin !== self.location.origin) return;
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
    const open = wins.find((w) => new URL(w.url).origin === url.origin);
    if (open) return open.navigate(url.href).then((w) => (w || open).focus());
    return self.clients.openWindow(url.href);
  }));
});

self.addEventListener("pushsubscriptionchange", (e) => {
  // The browser renewed the subscription: tell the server so alerts keep arriving.
  e.waitUntil(self.registration.pushManager.getSubscription().then((sub) => sub && fetch("/api/me/push", {
    method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subscription: sub.toJSON(), label: "Renewed" }),
  })));
});
