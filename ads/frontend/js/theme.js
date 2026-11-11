// Runs in <head> before first paint: applies the saved theme (system / light / dark).
(function () {
  var t = null;
  try { t = localStorage.getItem("ebads-theme"); } catch (e) {}
  if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
})();

// Phones: the screen must keep its size. iOS can leave the page panned or shrunk after the keyboard,
// a rotation or a pinch, and it ignores the viewport's maximum-scale for pinches.
(function () {
  var root = document.documentElement;
  var meta = document.querySelector('meta[name="viewport"]');
  var vv = window.visualViewport;
  function fit() {
    if (!vv || vv.scale > 1.01) return;
    root.style.setProperty("--app-h", vv.height + "px");
    // The Claude page is exactly one screen tall, so any pan is the keyboard pushing it up.
    if (vv.offsetTop > 0 && document.body && document.body.classList.contains("conv-page")) window.scrollTo(0, 0);
  }
  function settle() {
    var el = document.activeElement;
    if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return;
    window.scrollTo(0, window.scrollY); // makes iOS drop the leftover offset
    fit();
  }
  function rescale() { if (meta) meta.setAttribute("content", meta.getAttribute("content")); fit(); }
  if (vv) { vv.addEventListener("resize", fit); vv.addEventListener("scroll", fit); fit(); }
  document.addEventListener("focusout", function () { setTimeout(settle, 120); setTimeout(settle, 420); });
  window.addEventListener("orientationchange", function () { setTimeout(rescale, 250); });
  ["gesturestart", "gesturechange"].forEach(function (name) {
    document.addEventListener(name, function (e) { e.preventDefault(); }, { passive: false });
  });
})();
