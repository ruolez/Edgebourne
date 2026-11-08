// Runs in <head> before first paint: applies the saved theme (system / light / dark).
(function () {
  var t = null;
  try { t = localStorage.getItem("ebads-theme"); } catch (e) {}
  if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
})();
