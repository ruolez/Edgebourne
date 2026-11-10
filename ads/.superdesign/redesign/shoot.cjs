// Screenshots every frame of a.html / b.html / c.html (plus A in dark) into shots/.
const fs = require('fs');
const PW = fs.readdirSync(process.env.HOME + '/.npm/_npx').map((d) => `${process.env.HOME}/.npm/_npx/${d}/node_modules/playwright-core`)
  .find((p) => fs.existsSync(p + '/package.json') && /"version": "1\.6[4-9]/.test(fs.readFileSync(p + '/package.json', 'utf8')));
const { chromium } = require(PW);
const EXE = process.env.HOME + '/Library/Caches/ms-playwright/chromium-1248/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';
(async () => {
  fs.mkdirSync(__dirname + '/shots', { recursive: true });
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1.5 });
  for (const [file, dark] of [['a', false], ['b', false], ['c', false], ['a', true], ['b', true], ['c', true]]) {
    await page.goto('file://' + __dirname + `/${file}.html`);
    await page.evaluate(() => document.fonts.ready);
    await page.evaluate((d) => document.body.classList.toggle('dark', d), dark);
    for (const id of ['s-manager', 's-ad', 's-compare', 's-inbox', 's-phone']) {
      if (dark && id !== 's-manager') continue;
      await page.locator('#' + id).screenshot({ path: `${__dirname}/shots/${file}${dark ? '-dark' : ''}-${id.slice(2)}.png` });
    }
  }
  await browser.close();
  console.log('shots done');
})();
