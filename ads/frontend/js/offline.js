// The offline page (sw.js shows it in place of a page that couldn't load). It does what it says: it checks
// the connection by itself (when the device says it's back online, and every 10 seconds while it's shown)
// and opens the page that was asked for as soon as the console answers. "Try again now" checks at once.
(function () {
  var state = document.getElementById("off-state");
  var button = document.getElementById("off-retry");
  var direct = location.pathname === "/offline.html";
  var busy = false;
  function open() {
    state.textContent = "Back online. Opening the page…";
    if (direct) location.replace("/home.html"); else location.reload();
  }
  function check(byHand) {
    if (busy) return;
    busy = true;
    if (byHand) { state.textContent = "Checking the connection…"; button.disabled = true; }
    // Straight to the network: the manifest is never kept by the service worker.
    fetch("/manifest.webmanifest", { cache: "no-store", credentials: "same-origin" })
      .then(function () { open(); })
      .catch(function () { state.textContent = "Still no connection. Trying again by itself every 10 seconds."; })
      .then(function () { busy = false; button.disabled = false; });
  }
  button.addEventListener("click", function () { check(true); });
  window.addEventListener("online", function () { check(false); });
  setInterval(function () { if (!document.hidden) check(false); }, 10000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) check(false); });
})();
