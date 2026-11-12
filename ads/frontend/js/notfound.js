// The "Page not found" page (nginx error_page): shows the address that was asked for, and Back when there's
// somewhere on this site to go back to.
(function () {
  document.getElementById("nf-path").textContent = location.pathname + location.search;
  var back = document.getElementById("nf-back");
  var fromHere = false;
  try { fromHere = document.referrer && new URL(document.referrer).origin === location.origin; } catch (e) { fromHere = false; }
  if (fromHere && history.length > 1) {
    back.hidden = false;
    back.addEventListener("click", function () { history.back(); });
  }
})();
