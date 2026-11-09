// Local design review: screenshots of each screen in light and dark.
const { chromium } = require('/Users/ruolez/Desktop/Dev/meta-ads/creatives/2026-11-07-new5/src/node_modules/playwright-core');
const EXE = process.env.HOME + '/Library/Caches/ms-playwright/chromium-1248/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';
const OUT = process.argv[2] || 'qa/out';
const BASE = process.env.BASE || 'http://ads.localhost:8090';
(async () => {
  require('fs').mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const errors = [];
  for (const scheme of ['light', 'dark']) {
    for (const [vw, vh, tag] of [[1440, 900, 'desk'], [390, 844, 'phone']]) {
      const ctx = await browser.newContext({ viewport: { width: vw, height: vh }, colorScheme: scheme, deviceScaleFactor: 2 });
      const page = await ctx.newPage();
      page.on('console', (m) => { if (m.type() === 'error') errors.push(`${tag} ${m.text()}`); });
      page.on('pageerror', (e) => errors.push(`${tag} ${e.message}`));
      await page.goto(BASE + '/login.html');
      await page.screenshot({ path: `${OUT}/login-${tag}-${scheme}.png` });
      await page.fill('#email', 'eugene@edgebourne.com');
      await page.fill('#password', 'localdev-pass-123');
      await Promise.all([page.waitForURL('**/home.html**'), page.click('button[type=submit]')]);
      await page.goto(BASE + '/leads.html');
      await page.waitForSelector('.lead-row');
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${OUT}/leads-${tag}-${scheme}.png` });
      if (tag === 'phone') {
        await page.click('.lead-row');
        await page.waitForSelector('#stages');
        await page.screenshot({ path: `${OUT}/lead-detail-${tag}-${scheme}.png`, fullPage: true });
      }
      for (const p of ['home', 'ads', 'ad.html?id=120252672232040312', 'new-ad', 'research', 'desk', 'performance', 'team', 'settings', 'account']) {
        await page.goto(p.includes('.html') ? `${BASE}/${p}` : `${BASE}/${p}.html`);
        await page.waitForTimeout(600);
        await page.screenshot({ path: `${OUT}/${p.split('.')[0]}-${tag}-${scheme}.png`, fullPage: true });
      }
      await ctx.close();
    }
  }
  await browser.close();
  console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'no console errors');
})();
