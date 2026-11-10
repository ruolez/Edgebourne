const screens = [["manager","Ads manager: views, delivery status, 3 ads selected → bulk bar"],["ad","Ad page: Meta review timeline (the approval tracking you asked for)"],["compare","Compare 3 ads side by side, vs the previous 14 days"],["inbox","Inbox: approvals, rejections with reasons per placement, leads, Claude, money"],["phone","Phone: Today queue and Ads with selection"]];
const dirs = [["a","A · Signal"],["b","B · Ledger"],["c","C · Studio"]];
const rows = document.getElementById("rows");
for (const [key, label] of screens) {
  const s = document.createElement("section");
  s.innerHTML = `<h2>${label}</h2><div class="cols">` + dirs.map(([d, n]) => `<figure><a href="shots/${d}-${key}.png" target="_blank"><img src="shots/${d}-${key}.png" alt="${n} ${key}"></a><figcaption>${n}</figcaption></figure>`).join("") + `</div>`;
  rows.append(s);
}
const dk = document.createElement("section");
dk.innerHTML = `<h2>Dark theme (A shown; every direction gets one)</h2><div class="cols"><figure><a href="shots/a-dark-manager.png" target="_blank"><img src="shots/a-dark-manager.png" alt="A dark"></a><figcaption>A · Signal, dark</figcaption></figure></div>`;
rows.append(dk);
