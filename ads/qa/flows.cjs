// Local E2E of the Ads controls against the fake Meta server (docker-compose.dev.yml).
// node ads/qa/flows.cjs <out-dir>
// Playwright: $PLAYWRIGHT_CORE, else the first intact copy on this Mac (the render pipeline's copy lost
// its package files on 2026-11-10; any 1.64 drives the Chromium 1248 below).
const PW = [process.env.PLAYWRIGHT_CORE, '/Users/ruolez/Desktop/Dev/meta-ads/creatives/2026-11-07-new5/src/node_modules/playwright-core',
  ...require('fs').readdirSync(process.env.HOME + '/.npm/_npx').map((d) => `${process.env.HOME}/.npm/_npx/${d}/node_modules/playwright-core`)]
  .filter(Boolean).find((p) => require('fs').existsSync(p + '/package.json') && /"version": "1\.6[4-9]/.test(require('fs').readFileSync(p + '/package.json', 'utf8')));
const { chromium } = require(PW);
const EXE = process.env.HOME + '/Library/Caches/ms-playwright/chromium-1248/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';
const BASE = process.env.BASE || 'http://ads.localhost:8090';
const OUT = process.argv[2] || 'qa/out';
const IMG = process.argv[3];
const results = [];
const check = (name, ok, extra = '') => { results.push(`${ok ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); };
const guards = require('./guards.cjs');

(async () => {
  require('fs').mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  // The console's own fetches carry X-Requested-With (api.js); the server refuses writes without it.
  // QA's direct fetch() calls go through the same door.
  const asConsole = () => { const f = window.fetch; window.fetch = (u, o = {}) => f(u, { ...o, headers: { 'X-Requested-With': 'ebads', ...(o.headers || {}) } }); };
  const origNewContext = browser.newContext.bind(browser);
  browser.newContext = async (opts) => { const ctx = await origNewContext(opts); await ctx.addInitScript(asConsole); return ctx; };
  const page = await (await browser.newContext({ viewport: { width: 1360, height: 900 } })).newPage();
  const errors = [];
  page.on('dialog', (d) => (d.type() === 'beforeunload' ? d.accept() : d.dismiss()));
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/facebook\.com|preview_iframe/.test(m.text())) errors.push(m.text()); });
  const sh = (cmd) => require('child_process').execSync(cmd).toString();
  // What the fake Meta holds for an object now (checks read Meta's side, not only the screen).
  const metaHits = (clear) => JSON.parse(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/fake/_hits${clear ? '?clear=1' : ''}').read().decode())"`));
  const metaObj = (id) => JSON.parse(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/v24.0/?ids=${id}').read().decode())"`))[id];
  const getJson = (url) => page.evaluate(async (u) => (await fetch(u)).json(), url);
  // The ad Overview folds Versions, Words, The idea and Meta's automatic changes (9.4c): open one before using it.
  // Settings shows one section at a time (9.4f): open the one a check works in, freshly loaded (the form ids stay).
  const openSettings = async (section, p = page) => {
    const same = p.url().split('#')[0] === `${BASE}/settings.html`;
    await p.goto(`${BASE}/settings.html#${section}`);
    if (same) await p.reload();
    await p.waitForSelector(`#${section}[data-section]:not([hidden])`);
  };
  const openFold = async (id, p = page) => { await p.waitForSelector(`#fold-${id}`, { state: 'attached' }); await p.$eval(`#fold-${id}`, (d) => { d.open = true; }); };
  // D2: the 3-day rule. Moves every budget change back in time, so a check that raises a budget starts from a
  // budget last changed long enough ago (earlier steps and earlier runs changed the same budgets).
  const ageBudget = (days = 4) => sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute(\\"UPDATE meta_changes SET created_at = created_at - interval '${days} days' WHERE action IN ('budget','recommendation','recommendation_check')\\");db.execute(\\"UPDATE status_events SET at = at - interval '${days} days', meta_time = meta_time - interval '${days} days' WHERE field IN ('daily_budget','lifetime_budget')\\")"`);
  // D2: a change made in Ads Manager (the fake's /fake/_outside), then the console's hourly read.
  const outside = (id, params) => JSON.parse(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/fake/_outside?id=${id}&${params}').read().decode())"`));
  const pull = () => sh(`docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -c "import insights;insights.sync_structure()"`);
  const macSeen = (secondsAgo) => sh(`docker exec -w /app edgebourne-ads-backend python -c "import time, settings_store; settings_store.set('bridge_last_seen', str(time.time() - ${secondsAgo})); settings_store.set('bridge_version', '2.0')"`);
  await page.goto(BASE + '/login.html');
  await page.fill('#email', 'eugene@edgebourne.com');
  await page.fill('#password', 'localdev-pass-123');
  await Promise.all([page.waitForURL('**/home.html**'), page.click('button[type=submit]')]);

  // 1. Turn N2 off from the Ads page, through the confirm dialog.
  await page.goto(BASE + '/ads.html');
  const n2 = page.locator('[data-toggle="ad:120252672229400312"]');
  await n2.waitFor();
  const before = await n2.getAttribute('aria-checked');
  await n2.click();
  await page.waitForSelector('dialog.confirm');
  await page.screenshot({ path: `${OUT}/flow-1-confirm-off.png` });
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => document.querySelector('[data-toggle="ad:120252672229400312"]')?.getAttribute('aria-checked') === 'false');
  const offOnMeta = metaObj('120252672229400312').status;
  check('switch turns an ad off after confirming', before === 'true' && offOnMeta === 'PAUSED', `Meta: ${offOnMeta}`);
  // Cancel leaves it alone.
  await page.locator('[data-toggle="ad:120252672229400312"]').click();
  await page.click('dialog.confirm #cd-cancel');
  await page.waitForTimeout(400);
  check('cancel changes nothing', (await page.locator('[data-toggle="ad:120252672229400312"]').getAttribute('aria-checked')) === 'false' && metaObj('120252672229400312').status === 'PAUSED');
  // Back on.
  await page.locator('[data-toggle="ad:120252672229400312"]').click();
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => document.querySelector('[data-toggle="ad:120252672229400312"]')?.getAttribute('aria-checked') === 'true');
  const onOnMeta = metaObj('120252672229400312').status;
  check('switch turns it back on', onOnMeta === 'ACTIVE', `Meta: ${onOnMeta}`);

  // 2. Budget: validation, +20% warning, then a real change (campaign budgets live on the Campaigns level).
  ageBudget();
  await page.goto(BASE + '/ads.html?level=campaign');
  await page.waitForSelector('[data-budget^="campaign:"]');
  const budgetCampaign = (await page.getAttribute('[data-budget^="campaign:"]', 'data-budget')).split(':')[1];
  await page.click('[data-budget^="campaign:"]');
  await page.waitForSelector('dialog.confirm #cd-input');
  await page.fill('#cd-input', '0.5');
  await page.click('dialog.confirm #cd-ok');
  check('budget below $1 is refused in the dialog', await page.isVisible('#cd-err'));
  await page.fill('#cd-input', '40');
  const hint = await page.textContent('#cd-hint');
  check('a big jump shows the learning warning', /Bigger than \+20%/.test(hint), hint.trim());
  await page.screenshot({ path: `${OUT}/flow-2-budget.png` });
  await page.fill('#cd-input', '26');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => /\$26\.00\/day/.test(document.querySelector('[data-budget^="campaign:"]')?.textContent || ''));
  const budgetOnMeta = Number(metaObj(budgetCampaign).daily_budget);
  check('campaign budget changes to $26/day', budgetOnMeta === 2600, `Meta: ${budgetOnMeta} cents`);

  // 3. Ad page: format switch, duplicate.
  await page.goto(BASE + '/ad.html?id=120252672232030312');
  await page.waitForSelector('#formats button');
  await page.click('#formats button[data-format="INSTAGRAM_STORY"]');
  await page.waitForSelector('#preview-frame iframe');
  await page.waitForSelector('#preview-frame iframe:not(.preview-loading)', { timeout: 15000 });
  check('the preview placeholder stays until Meta\'s frame has loaded', (await page.locator('#preview-frame .skeleton').count()) === 0);
  check('preview loads an iframe for Instagram Stories', /INSTAGRAM_STORY/.test(await page.getAttribute('#preview-frame iframe', 'src')));
  await page.click('#dup');
  await page.waitForSelector('dialog.confirm #cd-input');
  await page.fill('#cd-input', 'N4 - Weekly report (flow copy)');
  await Promise.all([page.waitForURL('**created=1**'), page.click('dialog.confirm #cd-ok')]);
  await page.waitForSelector('.claude-note');
  check('duplicate opens the new ad with the "created, off" note', (await page.textContent('#cr-title')).includes('flow copy'));
  await page.screenshot({ path: `${OUT}/flow-3-duplicate.png`, fullPage: true });

  // 4. New ad with an uploaded image (9.4e: steps beside the form, every field marked before anything is
  // sent, one uploader with cancel and retry).
  {
    const png = (kb, name) => {
      if (IMG) return IMG;
      const b = Buffer.alloc(kb * 1024, 7);
      b.write('\x89PNG', 0, 'latin1');
      return { name, mimeType: 'image/png', buffer: b };
    };
    await page.goto(BASE + '/new-ad.html');
    await page.waitForSelector('#stepper li');
    await page.waitForSelector('#template option', { state: 'attached' });
    await page.selectOption('#template', '120252672229040312');
    await page.waitForFunction(() => /to finish first/.test(document.getElementById('ready').textContent));
    let adPosts = 0;
    const countAdPosts = (r) => { if (r.method() === 'POST' && /\/api\/ads\/new$/.test(r.url())) adPosts += 1; };
    page.on('request', countAdPosts);
    await page.click('#create');
    await page.waitForSelector('#new-form .field.error .err');
    const marked = await page.$$eval('#new-form [aria-invalid="true"]', (els) => els.map((e) => e.name));
    check('New ad marks every missing field at once (the media and the name) and sends nothing', marked.join() === 'media,name' && adPosts === 0, marked.join());
    check('the steps beside the form say what each holds or still needs', (await page.getAttribute('#stepper li:nth-child(1)', 'data-state')) === 'done'
      && (await page.getAttribute('#stepper li:nth-child(2)', 'data-state')) === 'fix' && /Choose an image or video/.test(await page.textContent('#stepper li:nth-child(2)')));
    // The media's file input sits under the Upload tab: with another tab open, Create puts the keyboard on that tab.
    await page.click('#mt-library');
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.click('#create');
    await page.waitForFunction(() => document.activeElement?.id === 'mt-library');
    check('Create with the media missing under another tab focuses that tab and brings it into view', await page.evaluate(() => {
      const r = document.getElementById('mt-library').getBoundingClientRect();
      return r.top >= 0 && r.bottom <= innerHeight;
    }) && adPosts === 0);
    await page.click('#mt-upload');
    // A failed upload offers Try again with the same file; a slow one can be cancelled.
    await page.route('**/api/media/upload', (r) => r.abort('failed'), { times: 1 });
    const upSeen = errors.length;
    await page.setInputFiles('#file', png(40, 'qa-first.png'));
    await page.waitForSelector('.upl[data-state="failed"] [data-upl="again"]');
    check('a failed upload says so and offers Try again', /check the connection/.test(await page.textContent('.upl-status')));
    await page.click('[data-upl="again"]');
    await page.waitForSelector('#chosen:not([hidden]) .ok-text');
    errors.splice(upSeen);
    check('Try again sends the same file without choosing it again', /qa-first\.png|\.png/.test(await page.textContent('#chosen')));
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Network.enable');
    await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: 100 * 1024 });
    await page.click('#clear-media');
    await page.setInputFiles('#file', { name: 'qa-slow.png', mimeType: 'image/png', buffer: Buffer.alloc(3 * 1024 * 1024, 7) });
    await page.waitForSelector('[data-upl="cancel"]');
    check('while one file uploads no second one can be chosen', await page.evaluate(() => document.getElementById('file').disabled));
    await page.click('[data-upl="cancel"]');
    await page.waitForSelector('.upl[data-state="failed"]');
    await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    check('an upload can be cancelled while it goes up, and uploaded again', /cancelled/.test(await page.textContent('.upl-status'))
      && (await page.locator('[data-upl="again"]').count()) === 1 && await page.isHidden('#chosen'));
    await page.setInputFiles('#file', png(40, 'qa-new-ad.png'));
    await page.waitForSelector('#chosen:not([hidden]) .ok-text');
    await page.fill('#name', 'N7 - Flow test image ad');
    await page.fill('#title', 'One system for the whole shop');
    await page.waitForFunction(() => /Ready to create/.test(document.getElementById('ready').textContent));
    check('once everything is there the marks clear and every step is done', (await page.locator('#new-form [aria-invalid="true"]').count()) === 0
      && (await page.locator('#stepper li[data-state="done"]').count()) === 3);
    await page.screenshot({ path: `${OUT}/flow-4-new-ad.png`, fullPage: true });
    await Promise.all([page.waitForURL('**/ad.html?id=**created=1**'), page.click('#create')]);
    page.off('request', countAdPosts);
    await page.waitForSelector('#cr-status .pill');
    check('new image ad is created and opens off', (await page.textContent('#cr-status')).includes('Off') && adPosts === 1, await page.textContent('#cr-title'));
  }

  // 4b. Polish: start a run from the ad page, then turn Claude's new-headline proposal into an ad.
  await page.goto(BASE + '/ad.html?id=120252672230740312#tab=polish');
  await page.reload();
  await page.waitForSelector('#polish-form');
  await page.click('[data-preset="quick"]');
  check('quick preset picks 4 passes', (await page.textContent('#run-polish')).includes('Run 4 passes'));
  const polishCount = async () => (await getJson('/api/ads/ad/120252672230740312/polish-runs')).tasks.filter((t) => t.kind === 'polish').length;
  const polishBefore = await polishCount();
  // A slow answer (a phone) and a double click: one run, not two (audit A3-90). Ticking a preset while
  // it sends must not unlock the button, and a submit then is ignored.
  await page.route('**/api/ads/ad/*/polish', async (route) => { await new Promise((r) => setTimeout(r, 900)); await route.continue(); });
  await page.dblclick('#run-polish');
  await page.click('[data-preset="quick"]');
  const lockedWhileSending = await page.evaluate(() => { const b = document.getElementById('run-polish'); document.getElementById('polish-form').requestSubmit(); return b.disabled; });
  for (let i = 0; i < 20 && (await polishCount()) === polishBefore; i++) await page.waitForTimeout(500);
  await page.waitForTimeout(1200);  // a second POST, if one went out, lands by now
  await page.unroute('**/api/ads/ad/*/polish', { behavior: 'wait' });
  check('a double click on Run queues one polish run', (await polishCount()) === polishBefore + 1, `${polishBefore} → ${await polishCount()}`);
  check('picking passes while it sends keeps Run locked', lockedWhileSending === true);
  const polishRun = () => getJson('/api/ads/ad/120252672230740312/polish-runs').then((r) => r.tasks.filter((t) => t.kind === 'polish').sort((a, b) => b.id - a.id)[0]);
  const queuedRun = await polishRun();
  check('polish run is queued for the Mac', queuedRun?.status === 'queued' && queuedRun.options?.passes?.length === 4, `${queuedRun?.status} ${queuedRun?.options?.passes?.length} passes`);
  await page.screenshot({ path: `${OUT}/flow-polish.png`, fullPage: true });
  // Don't leave a real run for a connected Mac to pick up.
  // Cancel this run (earlier cancelled runs are listed too, so wait for this one's button to go).
  await page.click(`#runs [data-cancel="${queuedRun.id}"]`);
  await page.waitForSelector(`#runs [data-cancel="${queuedRun.id}"]`, { state: 'detached' });
  const cancelledRun = await polishRun();
  check('a queued polish run can be cancelled', cancelledRun?.id === queuedRun?.id && cancelledRun.status === 'cancelled', cancelledRun?.status);
  // Make a new version: two quick submits ask once and queue one render run (audit A3-90).
  const renderRuns = async () => (await getJson('/api/ads/ad/120252672230740312/polish-runs')).tasks.filter((t) => t.kind === 'render');
  const rendersBefore = (await renderRuns()).length;
  await page.fill('#render-direction', 'QA: bigger Tap below note');
  await page.route('**/api/ads/ad/*/render', async (route) => { await new Promise((r) => setTimeout(r, 900)); await route.continue(); });
  await page.evaluate(() => { const f = document.getElementById('render-form'); f.requestSubmit(); f.requestSubmit(); });
  await page.waitForSelector('dialog.confirm');
  const renderDialogs = await page.locator('dialog.confirm').count();
  await page.click('dialog.confirm #cd-ok');
  await page.evaluate(() => document.getElementById('render-form').requestSubmit());
  for (let i = 0; i < 20 && (await renderRuns()).length === rendersBefore; i++) await page.waitForTimeout(500);
  await page.waitForTimeout(1200);  // a second POST, if one went out, lands by now
  await page.unroute('**/api/ads/ad/*/render', { behavior: 'wait' });
  const rendersAfter = await renderRuns();
  check('two quick submits on Make a new version ask once and queue one render run',
    renderDialogs === 1 && rendersAfter.length === rendersBefore + 1 && !(await page.locator('dialog.confirm[open]').count()), `${renderDialogs} dialogs, ${rendersBefore} → ${rendersAfter.length}`);
  const newRender = rendersAfter.sort((a, b) => b.id - a.id)[0];
  if (newRender) sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute(\\"UPDATE desk_tasks SET status = 'cancelled' WHERE id = %s\\", (${newRender.id},))"`);
  // The inline Suggestion card on the ad page (9.2b, suggest.js): Accept reads Meta fresh and asks first; Cancel,
  // and Cancel on Decline, change nothing; a new-copy card names the ad (never its id) and creates the ad, off.
  {
    const N3 = '120252672230740312', CAMP0 = '120252638288040312';
    const n3 = (await getJson(`/api/ads/ad/${N3}`)).ad;
    const liveBudget = Number(metaObj(CAMP0).daily_budget);
    const shq = (s) => `'${String(s).replace(/'/g, "'\\''")}'`;
    const seedArgs = [CAMP0, N3, `Raise to $${Math.round(liveBudget * 1.1 / 100)}/day`, n3.title || 'One system for the whole shop'].map(shq).join(' ');
    const seed = JSON.parse(sh(`docker cp dev/qa_inline_suggestions.py edgebourne-ads-backend:/app/qa_inline_suggestions.py && docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python qa_inline_suggestions.py ${seedArgs}; docker exec edgebourne-ads-backend rm -f /app/qa_inline_suggestions.py`).trim().split('\n').pop());
    const propStatus = (id) => sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(db.query('SELECT status FROM desk_proposals WHERE id = ${id}', one=True)['status'])"`).trim();
    await page.goto(BASE + `/ad.html?id=${N3}#tab=overview`);
    await page.reload();
    const budgetCard = page.locator(`#props [data-proposal="${seed.budget}"]`);
    await budgetCard.waitFor();
    await budgetCard.locator('[data-approve]').click();
    await page.waitForSelector('dialog.confirm[open]');
    const ask = (await page.textContent('dialog.confirm[open]')).replace(/\s+/g, ' ');
    await page.click('dialog.confirm[open] #cd-cancel');
    await page.waitForTimeout(500);
    check('Accept on the ad page asks first with the budget read from Meta; Cancel leaves the suggestion and Meta alone',
      /Accept “QA inline budget”/.test(ask) && ask.includes(`$${(liveBudget / 100).toFixed(2)}`) && propStatus(seed.budget) === 'pending'
      && Number(metaObj(CAMP0).daily_budget) === liveBudget && await budgetCard.locator('[data-approve]').isEnabled(), ask.slice(0, 200));
    await budgetCard.locator('[data-decline]').click();
    await page.waitForSelector('dialog.confirm[open]');
    const declineAsk = await page.textContent('dialog.confirm[open] h2');
    await page.click('dialog.confirm[open] #cd-cancel');
    await page.waitForTimeout(400);
    const stillPending = propStatus(seed.budget) === 'pending' && (await budgetCard.count()) === 1;
    await budgetCard.locator('[data-decline]').click();
    await page.click('dialog.confirm[open] #cd-ok');
    await budgetCard.waitFor({ state: 'detached' });
    check('Decline on the ad page asks first: Cancel keeps the suggestion, Decline takes it off the page and Meta is not touched',
      /Decline “QA inline budget”/.test(declineAsk) && stillPending && propStatus(seed.budget) === 'declined' && Number(metaObj(CAMP0).daily_budget) === liveBudget, declineAsk);
    const copyCard = page.locator(`#props [data-proposal="${seed.creative}"]`);
    const copyText = await copyCard.textContent();
    check("a new-copy card on the ad page shows what stays the same and never Meta's ad id",
      !copyText.includes(N3) && /\(same as now\)/.test(copyText) && (await copyCard.locator('[data-as="update"]').count()) === 1, copyText.replace(/\s+/g, ' ').slice(0, 200));
    await copyCard.locator('[data-approve]:not([data-as])').click();
    await page.waitForSelector('dialog.confirm[open]');
    await Promise.all([page.waitForURL('**created=1**'), page.click('dialog.confirm[open] #cd-ok')]);
    await page.waitForSelector('#cr-status .pill');
    check('accepting a new-copy suggestion creates that ad, switched off',
      (await page.textContent('#cr-title')).includes('QA inline copy') && (await page.textContent('#cr-status')).includes('Off') && propStatus(seed.creative) === 'applied', await page.textContent('#cr-title'));
  }

  // Refresh: on every page, pulls from Meta, then the page reloads its data and the label updates.
  require('child_process').execSync(`docker exec -w /app edgebourne-ads-backend python -c "import settings_store,time;settings_store.set('last_refresh_at',str(time.time()-600))"`); // outside the 60 s throttle
  await page.goto(BASE + '/ads.html');
  await page.waitForSelector('.topline [data-refresh]');
  await page.click('.topline [data-refresh]');
  await page.waitForFunction(() => /Updated just now/.test(document.querySelector('.topline [data-updated]')?.textContent || ''), null, { timeout: 60000 });
  const pulledAt = Number(sh(`docker exec -w /app edgebourne-ads-backend python -c "import settings_store;print(settings_store.get('last_refresh_at'))"`));
  check('Refresh pulls from Meta and shows when', Date.now() / 1000 - pulledAt < 90, `${await page.textContent('.topline [data-updated]')} (pulled ${Math.round(Date.now() / 1000 - pulledAt)} s ago)`);
  const again = await page.evaluate(() => fetch('/api/refresh', { method: 'POST' }).then((r) => r.json()));
  check('a second Refresh within a minute does not hit Meta again', again.ran === false);
  const py = (code) => sh(`docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -c "${code}"`).trim();
  check('a pull keeps today\'s spend (for pacing and the overspend alert), stamped with today',
    py("import insights;s=insights.stored_today();print(bool(s and s['campaigns']))") === 'True');
  for (const p of ['leads', 'performance', 'desk', 'research', 'settings', 'team', 'account']) {
    await page.goto(`${BASE}/${p}.html`, { waitUntil: 'networkidle' });
    check(`Refresh is on ${p}`, await page.isVisible('.topline [data-refresh]'));
  }

  // Archive and delete: only for an ad that is off; delete needs the name typed.
  const seen = errors.length;
  const on = await page.evaluate(() => fetch('/api/ads/ad/120252672229400312/archive', { method: 'POST' }).then((r) => r.status));
  await page.waitForTimeout(300);
  errors.splice(seen); // the refused request above logs an expected 400
  const n2Status = await page.evaluate(() => fetch('/api/ads/ad/120252672229400312').then((r) => r.json()).then((d) => d.ad.status));
  check('archive is refused for an ad that is on', n2Status !== 'ACTIVE' || on === 400, `${n2Status} → ${on}`);
  const dup = await page.evaluate(() => fetch('/api/ads/ad/120252672229400312/duplicate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'QA archive me' }) }).then((r) => r.json()));
  await page.goto(`${BASE}/ad.html?id=${dup.id}`);
  await page.click('#archive');
  await page.waitForSelector('dialog.confirm');
  await page.screenshot({ path: `${OUT}/flow-archive-confirm.png` });
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => /Archived/.test(document.querySelector('#cr-status')?.textContent || ''));
  check('Archive marks the ad archived and hides the Archive button', !(await page.isVisible('#archive')), await page.textContent('#cr-status'));
  await page.goto(BASE + '/ads.html', { waitUntil: 'networkidle' });
  const listed = async () => page.evaluate((id) => !!document.querySelector(`[href*="${id}"]`), dup.id);
  check('an archived ad is hidden on the Ads page', !(await listed()));
  await page.click('#archived');
  await page.waitForFunction(() => /Hide archived/.test(document.querySelector('#archived')?.textContent || ''));
  check('Show archived brings it back into view', await listed());
  await page.goto(`${BASE}/ad.html?id=${dup.id}`);
  await page.click('#delete');
  await page.waitForSelector('dialog.confirm #cd-input');
  await page.fill('#cd-input', 'QA archive');
  await page.click('dialog.confirm #cd-ok');
  check('delete refuses a name that does not match', await page.isVisible('#cd-err'), await page.textContent('#cd-err'));
  await page.fill('#cd-input', 'QA archive me');
  await page.screenshot({ path: `${OUT}/flow-delete-confirm.png` });
  await Promise.all([page.waitForURL('**/ads.html'), page.click('dialog.confirm #cd-ok')]);
  const gone = await page.evaluate((id) => fetch(`/api/ads/ad/${id}`).then((r) => r.json()).then((d) => d.ad.status), dup.id);
  check('Delete with the typed name deletes it and returns to Ads', gone === 'DELETED', gone);
  // Meta's lists leave archived ads out: one archived in Ads Manager stays archived here, not deleted.
  const elsewhere = await page.evaluate(() => fetch('/api/ads/ad/120252672229400312/duplicate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'QA archived in Ads Manager' }) }).then((r) => r.json()));
  sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;urllib.request.urlopen(urllib.request.Request('http://localhost:5001/v24.0/${elsewhere.id}?access_token=x', data=b'status=ARCHIVED'))"`);
  py('import insights;insights.sync_structure()');
  const archivedThere = await page.evaluate((id) => fetch(`/api/ads/ad/${id}`).then((r) => r.json()), elsewhere.id);
  check('an ad archived in Ads Manager is stored as archived, not deleted', archivedThere.ad.status === 'ARCHIVED'
    && archivedThere.ad.effective_status === 'ARCHIVED' && archivedThere.timeline[0].new_value === 'ARCHIVED',
    `${archivedThere.ad.status}/${archivedThere.ad.effective_status} · ${archivedThere.timeline.map((t) => t.new_value).join(',')}`);
  // A sync that listed the ads before another stored a new one doesn't mark the new one deleted.
  check('a slower sync never marks an ad stored after its listing as deleted', py("import db,status_history as h;l=db.now();"
    + "db.execute('INSERT INTO ads (id, name, campaign_id, status, effective_status) VALUES (%s,%s,%s,%s,%s)',('qa-fresh-row','QA fresh row','120252638288040312','PAUSED','PAUSED'));"
    + "h.mark_missing('ad',[r['id'] for r in db.query('SELECT id FROM ads WHERE id <> %s',('qa-fresh-row',))],'poll',l);"
    + "print(db.query('SELECT effective_status FROM ads WHERE id = %s',('qa-fresh-row',),one=True)['effective_status']);"
    + "db.execute('DELETE FROM status_events WHERE entity_id = %s',('qa-fresh-row',));db.execute('DELETE FROM ads WHERE id = %s',('qa-fresh-row',))") === 'PAUSED');

  // Lead stages to Meta: a real-looking lead moved to Qualified sends Lead, Contacted and Qualified once each.
  const leadId = Number(require('child_process').execSync(`docker exec edgebourne-ads-backend python -c "
import db
db.execute(\\"DELETE FROM leads WHERE meta_lead_id = '9876543210123456'\\")
r = db.execute(\\"INSERT INTO leads (meta_lead_id, created_time, full_name, campaign_id, campaign_name) VALUES ('9876543210123456', now() - interval '2 hours', 'QA Stage Lead', '120252638288040312', 'Edge Bourne - Free intro call - Leads') RETURNING id\\", returning=True)
print(r['id'])"`).toString().trim());
  await openSettings('crm');
  await page.waitForSelector('#crm-state .pill');
  if (!(await page.isChecked('#crm_send_enabled'))) await page.check('#crm_send_enabled');
  await page.click('#crm-form button[type=submit]');
  await page.waitForSelector('#crm-state .pill.ok');
  check('Settings turns lead stages on', (await getJson('/api/settings')).meta.crm_send_enabled === '1', await page.textContent('#crm-state'));
  await page.goto(`${BASE}/leads.html#lead=${leadId}`);
  await page.waitForSelector('[data-stage="qualified"]');
  await page.click('[data-stage="qualified"]');
  await page.waitForFunction(() => /Meta has New, Contacted, Qualified/.test(document.querySelector('#meta-stages')?.textContent || ''), null, { timeout: 20000 }).catch(() => {});
  const stages = await page.evaluate((id) => fetch(`/api/leads/${id}`).then((r) => r.json()).then((l) => (l.meta_stages || []).map((r) => `${r.stage}:${r.status}`).join(' ')), leadId);
  check('a stage change sends Lead, Contacted and Qualified to Meta', stages === 'new:sent contacted:sent qualified:sent', stages);
  check('the lead page says what Meta got without reopening the lead', /Meta has New, Contacted, Qualified/.test(await page.textContent('#meta-stages')), await page.textContent('#meta-stages'));
  await page.screenshot({ path: `${OUT}/flow-crm-lead.png` });
  // Test leads stay out of the inbox unless asked for.
  require('child_process').execSync(`docker exec edgebourne-ads-backend python -c "
import db
db.execute(\\"DELETE FROM leads WHERE meta_lead_id = 'qa-test-lead'\\")
db.execute(\\"INSERT INTO leads (meta_lead_id, created_time, full_name, is_test) VALUES ('qa-test-lead', now(), 'QA Test Lead', true)\\")"`);
  await page.goto(BASE + '/leads.html');
  await page.waitForSelector('#list .lead-row');
  check('test leads are hidden from the inbox', !/QA Test Lead/.test(await page.textContent('#list')));
  await page.check('#tests');
  await page.waitForFunction(() => /QA Test Lead/.test(document.querySelector('#list')?.textContent || ''));
  check('Show test leads lists them, marked Test', /Test/.test(await page.textContent('#list .lead-row:has-text("QA Test Lead")')));
  await openSettings('crm');
  await page.waitForSelector('#crm-state .pill');
  await page.uncheck('#crm_send_enabled');
  await page.click('#crm-form button[type=submit]');
  await page.waitForFunction(() => document.querySelector('#crm-state')?.textContent === 'Off');
  check('Settings turns lead stages off again', !(await getJson('/api/settings')).meta.crm_send_enabled);

  // Automatic refresh: the interval is set in Settings; open pages reload when the server has newer data.
  await openSettings('auto');
  await page.selectOption('#auto-minutes', '5');
  await page.click('#auto-form button[type=submit]');
  await page.waitForFunction(() => document.querySelector('#auto-state')?.textContent === 'Every 5 minutes');
  check('Settings sets the automatic refresh interval', (await getJson('/api/settings')).auto_refresh_minutes === 5);
  await page.goto(BASE + '/ads.html', { waitUntil: 'networkidle' });
  check('the Refresh button says how often it updates by itself', /every 5 min/.test(await page.getAttribute('.topline [data-refresh]', 'title')));
  const stampPull = () => require('child_process').execSync(`docker exec edgebourne-ads-backend sh -c "cd /app && python -c \\"import settings_store,time;settings_store.set('last_refresh_at',str(time.time()))\\""`);
  let adsLoads = 0;
  const countAds = (r) => { if (/\/api\/ads\?range=/.test(r.url())) adsLoads++; };
  page.on('request', countAds);
  await page.evaluate(() => { const i = document.createElement('input'); i.id = 'qa-typing'; document.querySelector('.page-head').append(i); i.focus(); });
  stampPull();
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await page.waitForTimeout(1500);
  check('a page being typed in is not reloaded under the person', adsLoads === 0, `${adsLoads} loads`);
  await page.evaluate(() => document.getElementById('qa-typing').remove());
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await page.waitForFunction(() => /just now/.test(document.querySelector('[data-updated]')?.textContent || ''));
  await page.waitForTimeout(800);
  check('an open page reloads its data after an automatic pull', adsLoads === 1, `${adsLoads} loads`);
  page.off('request', countAds);
  await openSettings('auto');
  await page.waitForSelector('#auto-state .pill');
  await page.selectOption('#auto-minutes', '15');
  await page.click('#auto-form button[type=submit]');
  await page.waitForFunction(() => document.querySelector('#auto-state')?.textContent === 'Every 15 minutes');

  // Telegram: the admin adds the bot, a person connects their chat, a new lead reaches it within seconds.
  const tgSent = () => JSON.parse(sh(`docker exec edgebourne-ads-backend python -c "import requests;print(requests.get('http://fake-meta:5001/telegram/_sent').text)"`));
  sh(`docker exec edgebourne-ads-backend python -c "import db;db.execute('UPDATE users SET telegram_chat_id=NULL, telegram_name=NULL, telegram_link_code=NULL');db.execute(\\"DELETE FROM leads WHERE full_name = 'Telegram QA Lead'\\")"`);
  await openSettings('telegram');
  await page.waitForSelector('#tg-state .pill');
  if (await page.isVisible('#tg-remove')) {
    await page.click('#tg-remove');
    await page.click('dialog.confirm #cd-ok');
    await page.waitForFunction(() => document.querySelector('#tg-state')?.textContent === 'Not set up');
  }
  const tgSeen = errors.length;
  await page.fill('#telegram_bot_token', '999:wrong');
  await page.click('#tg-form button[type=submit]');
  await page.waitForSelector('#tg-form .field.error .err', { timeout: 5000 }).catch(() => {});
  errors.splice(tgSeen); // the refused token logs an expected 400
  check('Settings refuses a bot token Telegram rejects', /didn't accept/.test(await page.textContent('#tg-form')));
  await page.fill('#telegram_bot_token', '123456:FAKE-token');
  await page.click('#tg-form button[type=submit]');
  await page.waitForFunction(() => document.querySelector('#tg-state')?.textContent === '@EdgeBourneAdsBot');
  const tgSet = (await getJson('/api/settings')).telegram;
  check('Settings connects the Telegram bot', tgSet.set && tgSet.username === 'EdgeBourneAdsBot', JSON.stringify(tgSet));
  await page.goto(BASE + '/account.html');
  const themeWas = await page.evaluate(() => localStorage.getItem('ebads-theme') || 'system');
  await page.click('#theme-choice [data-theme-choice="dark"]');
  const themeNow = await page.evaluate(() => ({ attr: document.documentElement.dataset.theme, saved: localStorage.getItem('ebads-theme'),
    pressed: document.querySelector('#theme-choice [aria-pressed="true"]')?.dataset.themeChoice, others: document.querySelectorAll('[data-theme-btn]').length }));
  check('the theme is chosen in one place, Your account: Dark applies at once and is kept, and the sidebar and More carry no other theme button',
    themeNow.attr === 'dark' && themeNow.saved === 'dark' && themeNow.pressed === 'dark' && themeNow.others === 0, JSON.stringify(themeNow));
  const meCard = await page.evaluate(() => ({ name: document.getElementById('me-name').textContent, email: document.getElementById('me-email').textContent,
    role: document.getElementById('me-role').textContent, out: !!document.querySelector('.me-card #account-signout') }));
  check('Your account opens on who is signed in (name, email, access) with Sign out beside it',
    meCard.name === 'Eugene' && meCard.email === 'eugene@edgebourne.com' && meCard.role === 'Admin of every account' && meCard.out, JSON.stringify(meCard));
  await page.click(`#theme-choice [data-theme-choice="${themeWas}"]`);
  await page.click('#tg-link');
  await page.waitForSelector('#tg-open');
  const tgLink = await page.getAttribute('#tg-open', 'href');
  check('Connect Telegram opens the bot with a one-time code', /^https:\/\/t\.me\/EdgeBourneAdsBot\?start=[\w-]{16}$/.test(tgLink), tgLink);
  sh(`docker exec edgebourne-ads-backend python -c "import requests;requests.post('http://fake-meta:5001/telegram/_start', json={'code': '${tgLink.split('start=')[1]}', 'chat_id': 424242})"`);
  await page.waitForSelector('#tg-on', { timeout: 15000 });
  check('the account page sees the Start tap by itself', await page.isChecked('#tg-on'), await page.textContent('#tg'));
  await page.click('#tg-test');
  await page.waitForTimeout(800);
  const welcome = tgSent().map((m) => m.text);
  check('Telegram got the welcome and the test message', welcome.some((t) => /You're connected/.test(t)) && welcome.some((t) => /Test from Edge Bourne Ads/.test(t)), welcome.slice(-2).join(' | '));
  const tgLead = '7700' + String(Date.now()).slice(-12);
  const t0 = Date.now();
  sh(`docker exec edgebourne-ads-backend python -c "
import json, hmac, hashlib, requests, settings_store
settings_store.get('meta_app_secret') or settings_store.set('meta_app_secret', 'dev-app-secret')
body = json.dumps({'entry': [{'changes': [{'field': 'leadgen', 'value': {'leadgen_id': '${tgLead}'}}]}]}).encode()
sig = 'sha256=' + hmac.new(settings_store.get('meta_app_secret').encode(), body, hashlib.sha256).hexdigest()
print(requests.post('http://localhost:5000/webhooks/meta', data=body, headers={'X-Hub-Signature-256': sig, 'Content-Type': 'application/json'}).status_code)"`);
  let alert = null;
  for (let i = 0; i < 30 && !alert; i++) { await page.waitForTimeout(1000); alert = tgSent().find((m) => /New lead: Telegram QA Lead/.test(m.text)); }
  check('a new lead reaches Telegram in under 30 s, with a link to it', Boolean(alert) && /Phone: \+16197\d{6}/.test(alert.text), alert ? `${Math.round((Date.now() - t0) / 1000)} s` : 'not sent');
  await page.screenshot({ path: `${OUT}/flow-telegram-account.png` });

  // Lead replies: templates in Settings, an email from the lead page, then the automatic reply.
  const mailSent = () => JSON.parse(sh(`docker exec edgebourne-ads-backend python -c "import requests;print(requests.get('http://fake-meta:5001/mail/_sent').text)"`));
  await openSettings('replies');
  await page.evaluate(() => fetch('/api/settings/smtp', { method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ smtp_host: 'fake-meta', smtp_port: '1025', smtp_security: 'none', smtp_username: '', smtp_from_email: 'ads@edgebourne.test', smtp_from_name: 'Edge Bourne Ads' }) }));
  await page.evaluate(() => fetch('/api/settings/replies', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ auto: false, booking_link: '' }) }));
  await page.reload();
  await page.waitForSelector('#tpl-list [data-edit]');
  await page.click('#tpl-list [data-edit]');
  await page.waitForFunction(() => /Hi Maria/.test(document.querySelector('#tpl-preview')?.textContent || ''));
  check('the template preview fills in a sample lead and leaves out the empty booking line', !/pick a time yourself/i.test(await page.textContent('#tpl-preview')), await page.textContent('#tpl-preview'));
  await page.click('#tpl-cancel');
  const rpSeen = errors.length;
  await page.fill('#booking_link', 'cal.com/eugene');
  await page.click('#rp-form button[type=submit]');
  await page.waitForSelector('#rp-form .field.error .err');
  const rawLink = await page.evaluate(async () => (await fetch('/api/settings/replies', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ booking_link: 'cal.com/eugene' }) })).status);
  const keptLink = (await getJson('/api/settings')).replies.booking_link;
  await page.waitForTimeout(300);
  errors.splice(rpSeen); // the refused links log an expected 400
  check('a booking link without https is refused (by the server too)', rawLink === 400 && !keptLink, `${rawLink} ${keptLink}`);
  await page.fill('#booking_link', 'https://cal.com/eugene');
  await page.click('#rp-form button[type=submit]');
  await page.waitForFunction(() => document.querySelector('#rp-state')?.textContent === 'By hand');
  const tgLeadId = await page.evaluate(() => fetch('/api/leads?q=Telegram%20QA%20Lead&status=all').then((r) => r.json()).then((d) => d.leads[0].id));
  await page.goto(`${BASE}/leads.html#lead=${tgLeadId}`);
  await page.waitForSelector('#reply-open');
  await page.click('#reply-open');
  await page.waitForFunction(() => /Hi Telegram,/.test(document.querySelector('#reply-body')?.value || ''));
  const draft = await page.inputValue('#reply-body');
  check('Email them opens a draft filled in for this lead', /\(619\) 7\d\d-\d{4}/.test(draft) && /https:\/\/cal\.com\/eugene/.test(draft), draft.split('\n')[0]);
  await page.fill('#reply-body', draft.replace('Thanks for asking', 'Thanks a lot for asking'));
  const mailsBefore = mailSent().length;
  await page.click('#reply-send');
  await page.waitForSelector('.email-sent');
  const mail = mailSent().slice(mailsBefore).find((m) => m.to.includes(`tgqa+${tgLead.slice(-6)}@qa.edgebourne.com`));
  check('the email goes out with the edits, from Eugene, answers back to him', Boolean(mail) && /Thanks a lot for asking/.test(mail.text) && /Eugene/.test(mail.from) && mail.reply_to === 'eugene@edgebourne.com', mail ? `${mail.from} / ${mail.reply_to}` : 'no mail');
  check('sending moves the lead to Contacted and lists the email', (await page.getAttribute('[data-stage="contacted"]', 'aria-pressed')) === 'true' && /emailed them/.test(await page.textContent('.history')));
  await page.screenshot({ path: `${OUT}/flow-lead-reply.png`, fullPage: true });
  // Email not set up: the note's link opens Settings on the Email section itself (Eugene owns the console).
  const replyRoute = '**/api/leads/*/reply*';
  await page.route(replyRoute, async (r) => {
    if (r.request().method() !== 'GET') return r.continue();
    return r.fulfill({ json: { templates: [], template_id: null, subject: '', body: '', mail_ready: false } });
  });
  await page.reload();
  await page.waitForSelector('#reply-open');
  await page.click('#reply-open');
  await page.waitForSelector('#reply-mail-note:not([hidden]) a');
  await Promise.all([page.waitForURL('**/settings.html#email'), page.click('#reply-mail-note a')]);
  await page.waitForSelector('#email[data-section]:not([hidden])');
  check("the lead page's 'Set it up in Settings → Email' opens the Email section", await page.isHidden('#meta'), page.url());
  await page.unroute(replyRoute);
  await openSettings('replies');
  await page.waitForSelector('#tpl-list li'); // the settings have loaded, so rendering won't untick the box after
  await page.check('#rp-auto');
  await page.click('#rp-form button[type=submit]');
  await page.waitForSelector('dialog.confirm #cd-ok');
  const autoBeforeYes = (await getJson('/api/settings')).replies.auto;
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => document.querySelector('#rp-state')?.textContent === 'Automatic reply on');
  const autoAfterYes = (await getJson('/api/settings')).replies.auto;
  check('the automatic reply needs a confirmation to turn on', autoBeforeYes === false && autoAfterYes === true, `${autoBeforeYes} → ${autoAfterYes}`);
  const autoLead = '7700' + String(Date.now() + 7).slice(-12);
  const mailsBeforeAuto = mailSent().length;
  sh(`docker exec edgebourne-ads-backend python -c "
import json, hmac, hashlib, requests, settings_store
body = json.dumps({'entry': [{'changes': [{'field': 'leadgen', 'value': {'leadgen_id': '${autoLead}'}}]}]}).encode()
sig = 'sha256=' + hmac.new(settings_store.get('meta_app_secret').encode(), body, hashlib.sha256).hexdigest()
requests.post('http://localhost:5000/webhooks/meta', data=body, headers={'X-Hub-Signature-256': sig, 'Content-Type': 'application/json'})"`);
  let autoMail = null;
  const leadMailed = () => mailSent().slice(mailsBeforeAuto).some((m) => /^New lead/.test(m.subject || '')); // sent by the alert queue, just after the reply
  for (let i = 0; i < 30 && !(autoMail && leadMailed()); i++) { await page.waitForTimeout(1000); autoMail = mailSent().slice(mailsBeforeAuto).find((m) => /Your free intro call/.test(m.subject)); }
  check('a new lead gets the automatic reply by itself', Boolean(autoMail), autoMail ? autoMail.subject : 'none');
  const leadMails = mailSent().slice(mailsBeforeAuto).filter((m) => /^New lead/.test(m.subject || ''));
  check("the new-lead email goes to each person separately, never to another account's admin",
    leadMails.length > 0 && leadMails.every((m) => m.to.length === 1 && !/burdanova\.test/.test(m.to[0])) && leadMails.some((m) => m.to[0] === 'eugene@edgebourne.com'),
    JSON.stringify(leadMails.map((m) => m.to)));
  // A lead the catch-up stores before its webhook is processed is still announced, once: one email per
  // person, at most one Telegram alert, one automatic reply, one history line. Filled in without an ad
  // (organic), it is a real lead, not a test one.
  const formLead = '7701' + String(Date.now()).slice(-12);
  sh(`docker exec edgebourne-ads-backend python -c "
import db, requests
db.execute(\\"DELETE FROM leads WHERE full_name = 'Organic QA Lead'\\")
requests.get('http://fake-meta:5001/fake/_form_lead', params={'id': '${formLead}', 'organic': '1', 'name': 'Organic QA Lead', 'email': 'organicqa@qa.edgebourne.com'})"`);
  const mailsBeforeForm = mailSent().length, tgBeforeForm = tgSent().length;
  const caughtUp = sh(`docker exec edgebourne-ads-backend python -c "import leads; print(leads.backfill(days=1))"`).trim();
  check('the catch-up stores a form lead whose webhook has not been handled', caughtUp === '1', caughtUp);
  sh(`docker exec edgebourne-ads-backend python -c "
import json, hmac, hashlib, requests, settings_store
body = json.dumps({'entry': [{'changes': [{'field': 'leadgen', 'value': {'leadgen_id': '${formLead}'}}]}]}).encode()
sig = 'sha256=' + hmac.new(settings_store.get('meta_app_secret').encode(), body, hashlib.sha256).hexdigest()
requests.post('http://localhost:5000/webhooks/meta', data=body, headers={'X-Hub-Signature-256': sig, 'Content-Type': 'application/json'})"`);
  const pingDone = () => sh(`docker exec edgebourne-ads-backend python -c "
import db
r = db.query(\\"SELECT processed_at IS NOT NULL AS done FROM webhook_events WHERE leadgen_id = '${formLead}'\\", one=True)
print(bool(r and r['done']))"`).trim() === 'True';
  let formReply = null;
  for (let i = 0; i < 30 && !(formReply && pingDone()); i++) { await page.waitForTimeout(1000); formReply = mailSent().slice(mailsBeforeForm).find((m) => m.to.includes('organicqa@qa.edgebourne.com')); }
  await page.waitForTimeout(4000); // one more worker pass: anything sent twice shows up here
  const formMails = mailSent().slice(mailsBeforeForm);
  const formAlerts = formMails.filter((m) => /^New lead: Organic QA Lead/.test(m.subject || '')).map((m) => m.to.join(','));
  check('a lead the catch-up found first gets its email, once per person, after its webhook too',
    formAlerts.includes('eugene@edgebourne.com') && new Set(formAlerts).size === formAlerts.length, JSON.stringify(formAlerts));
  check('...and one automatic reply', formMails.filter((m) => m.to.includes('organicqa@qa.edgebourne.com')).length === 1,
    formMails.filter((m) => m.to.includes('organicqa@qa.edgebourne.com')).map((m) => m.subject).join(' | '));
  const formTg = tgSent().slice(tgBeforeForm).filter((m) => /New lead: Organic QA Lead/.test(m.text)).length;
  check('...and at most one Telegram alert', formTg <= 1, `${formTg} alerts`);
  const formRow = (await getJson('/api/leads?q=Organic%20QA%20Lead&status=all')).leads;
  const received = sh(`docker exec edgebourne-ads-backend python -c "
import db
print(db.query(\\"SELECT COUNT(*) AS n FROM activity WHERE action = 'lead.received' AND subject = %s\\", (str(${formRow[0] ? formRow[0].id : 0}),), one=True)['n'])"`).trim();
  check('an organic form lead is a real lead in the inbox, received once in its history',
    formRow.length === 1 && formRow[0].is_test === false && formRow[0].is_organic === true && received === '1',
    `${JSON.stringify(formRow.map((l) => [l.is_test, l.is_organic]))}, ${received} received`);
  await page.goto(BASE + '/leads.html');
  await page.waitForSelector('#list .lead-row:has-text("Organic QA Lead")');
  check('Leads says the organic lead came without an ad', /No ad \(organic\)/.test(await page.textContent('#list .lead-row:has-text("Organic QA Lead")')));
  const toolLead = '7702' + String(Date.now()).slice(-12);
  const toolStored = sh(`docker exec edgebourne-ads-backend python -c "
import db, requests, leads
requests.get('http://fake-meta:5001/fake/_form_lead', params={'id': '${toolLead}', 'organic': '1', 'name': '<test lead: dummy data for full_name>', 'email': 'toolqa@example.com'})
leads.backfill(days=1)
r = db.query(\\"SELECT is_test FROM leads WHERE meta_lead_id = '${toolLead}'\\", one=True)
db.execute(\\"DELETE FROM leads WHERE meta_lead_id = '${toolLead}'\\")
print(r and r['is_test'])"`).trim();
  check('a Testing Tool lead (dummy answers) stays a test lead even when Meta marks it organic', toolStored === 'True', toolStored);
  sh(`docker exec edgebourne-ads-backend python -c "
import json, hmac, hashlib, requests, settings_store, db
db.execute(\\"DELETE FROM webhook_events WHERE leadgen_id = '444444444444'\\")
body = json.dumps({'entry': [{'changes': [{'field': 'leadgen', 'value': {'leadgen_id': '444444444444'}}]}]}).encode()
sig = 'sha256=' + hmac.new(settings_store.get('meta_app_secret').encode(), body, hashlib.sha256).hexdigest()
requests.post('http://localhost:5000/webhooks/meta', data=body, headers={'X-Hub-Signature-256': sig, 'Content-Type': 'application/json'})"`);
  let sample = '';
  for (let i = 0; i < 20 && !sample.startsWith('done'); i++) {
    await page.waitForTimeout(1000);
    sample = sh(`docker exec edgebourne-ads-backend python -c "
import db
r = db.query(\\"SELECT processed_at IS NOT NULL AS done, error, attempts FROM webhook_events WHERE leadgen_id = '444444444444'\\", one=True)
print(('done' if r and r['done'] else 'open') + '|' + str(r and r['error']) + '|' + str(r and r['attempts']))"`).trim();
  }
  check("Meta's webhook Test sample is closed at once, never retried", /^done\|Meta's webhook Test sample.*\|0$/.test(sample), sample);
  await openSettings('replies');
  await page.waitForFunction(() => document.querySelector('#rp-state')?.textContent === 'Automatic reply on');
  await page.uncheck('#rp-auto');
  await page.click('#rp-form button[type=submit]');
  await page.waitForFunction(() => document.querySelector('#rp-state')?.textContent === 'By hand');
  await page.screenshot({ path: `${OUT}/flow-settings-replies.png`, fullPage: true });

  // Reminders: a lead nobody touched for 5 minutes, and one waiting an hour, reach Telegram once each.
  const tgBefore = tgSent().length;
  sh(`docker exec -w /app edgebourne-ads-backend python -c "
import db
db.execute(\\"DELETE FROM leads WHERE full_name LIKE 'Reminder QA%%'\\")
for name, mins in (('Reminder QA Five', 7), ('Reminder QA Hour', 61)):
    db.execute(\\"INSERT INTO leads (meta_lead_id, created_time, full_name, phone, campaign_id, campaign_name) VALUES (%s, now() - make_interval(mins => %s), %s, '+15550002222', '120252638288040312', 'Edge Bourne - Free intro call - Leads')\\", ('qa-' + name, mins, name))"`);
  let reminded = [];
  for (let i = 0; i < 40 && reminded.length < 2; i++) {
    await page.waitForTimeout(1000);
    reminded = tgSent().slice(tgBefore).filter((m) => /Reminder QA/.test(m.text)).map((m) => m.text.split('\n')[0]);
  }
  check('a lead nobody called for 5 min reminds its people on Telegram', reminded.some((t) => /Nobody has called Reminder QA Five yet/.test(t)), reminded.join(' | '));
  check('a lead waiting an hour reminds the admins too', reminded.some((t) => /Reminder QA Hour has waited 1 h/.test(t)), reminded.join(' | '));
  await page.waitForTimeout(31000);
  const remindCount = tgSent().slice(tgBefore).filter((m) => /Reminder QA/.test(m.text)).length;
  check("each reminder goes out once, and a late lead only the hour one", remindCount === 2, `${remindCount} reminder messages`);
  await page.goto(BASE + '/leads.html');
  await page.waitForSelector('#response:not([hidden])');
  check('Leads shows how fast leads get a first try', /Last 30 days: first try within .* for half of them · \d+ of \d+ within 5 min/.test(await page.textContent('#response')), await page.textContent('#response'));

  // Desk schedules: switch one on, change its time, a due schedule files one run (not a pile), the finish reaches Telegram.
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute('UPDATE desk_schedules SET enabled=FALSE, next_run_at=NULL, skipped=0, last_task_id=NULL')"`);
  await page.goto(BASE + '/desk.html#schedules', { waitUntil: 'networkidle' });
  await page.waitForSelector('.sched');
  check('Schedules lists the five checks, all off', (await page.locator('.sched').count()) === 5 && (await page.locator('.sched [aria-checked="true"]').count()) === 0);
  await page.click('#sched-1 [data-sched-toggle]');
  await page.waitForFunction(() => /next/.test(document.querySelector('#sched-1 .sched-when')?.textContent || ''));
  check('switching the daily health check on shows its next run', /Every day at 8:30 AM · next/.test(await page.textContent('#sched-1 .sched-when')), await page.textContent('#sched-1 .sched-when'));
  const deskPoke = async () => {  // a poll that brings something new: the page redraws
    sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute(\\"UPDATE desk_tasks SET progress = md5(random()::text) WHERE id = (SELECT max(id) FROM desk_tasks WHERE status = 'done')\\")"`);
    const seen = page.waitForResponse((r) => /\/api\/desk$/.test(r.url()));
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await seen;
    await page.waitForTimeout(300);
  };
  check('schedules say whose clock they run on: the zone in words and on the next run', /Times are Los Angeles time/.test(await page.textContent('#sched-zone'))
    && /next \w{3} \w{3} \d+, 8:30 AM P[SD]T/.test(await page.textContent('#sched-1 .sched-when')) && /Los Angeles time/.test(await page.textContent('label[for="at-1"]')),
    await page.textContent('#sched-1 .sched-when'));
  await page.click('#sched-1 .sched-edit summary');
  await page.selectOption('#every-1', 'days');
  await page.selectOption('#days-1', '2');
  await page.fill('#at-1', '07:15');
  await page.click('#sched-2 h3');  // typed, not saved, and the cursor elsewhere
  await deskPoke();
  check('a poll keeps a typed time and the open "Change when it runs"', (await page.inputValue('#at-1')) === '07:15' && await page.$eval('#sched-1 .sched-edit', (d) => d.open));
  await page.click('#sched-1 .sched-rule button[type=submit]');
  await page.waitForFunction(() => /Every 2 days at 7:15 AM/.test(document.querySelector('#sched-1 .sched-when')?.textContent || ''));
  const rule1 = JSON.parse(sh(`docker exec -w /app edgebourne-ads-backend python -c "import db,json;print(json.dumps(db.query('SELECT rule FROM desk_schedules WHERE id = 1', one=True)['rule']))"`));
  check('the time can be changed', rule1.every === 'days' && rule1.days === 2 && rule1.at === '07:15', JSON.stringify(rule1));
  await page.focus('#sched-2 [data-sched-run]');
  await deskPoke();
  check('a poll that redraws Schedules keeps the keyboard on the same button', await page.evaluate(() => document.activeElement?.dataset?.schedRun === '2'),
    await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 80)));
  const tasksBefore = Number(sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(db.query('SELECT COUNT(*) AS n FROM desk_tasks', one=True)['n'])"`));
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute(\\"UPDATE desk_schedules SET next_run_at = now() - interval '1 minute' WHERE id = 1\\")"`);
  let made = 0;
  for (let i = 0; i < 40 && !made; i++) { await page.waitForTimeout(1000); made = Number(sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(db.query('SELECT COUNT(*) AS n FROM desk_tasks', one=True)['n'])"`)) - tasksBefore; }
  check('a due schedule files a Desk run by itself', made === 1, `${made} new task(s)`);
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute(\\"UPDATE desk_schedules SET next_run_at = now() - interval '1 minute' WHERE id = 1\\")"`);
  await page.waitForTimeout(32000);
  const sched = JSON.parse(sh(`docker exec -w /app edgebourne-ads-backend python -c "import db,json;print(json.dumps(db.query('SELECT skipped, last_task_id FROM desk_schedules WHERE id = 1', one=True)))"`));
  const after = Number(sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(db.query('SELECT COUNT(*) AS n FROM desk_tasks', one=True)['n'])"`));
  check('while that run still waits for the Mac, the next one is skipped, not piled up', after - tasksBefore === 1 && sched.skipped === 1, JSON.stringify(sched));
  const tgBeforeDesk = tgSent().length;
  sh(`docker exec -w /app edgebourne-ads-backend python -c "
import db, desk_api
db.execute(\\"UPDATE desk_tasks SET status = 'done', finished_at = now(), summary = 'All 5 ads delivering; 4 leads yesterday at \\$5.10 each.' WHERE id = %s\\", (${sched.last_task_id},))
desk_api.tell_finished(${sched.last_task_id})"`);
  let deskMsg = null;
  for (let i = 0; i < 40 && !deskMsg; i++) { await page.waitForTimeout(1000); deskMsg = tgSent().slice(tgBeforeDesk).find((m) => /Daily health check: done/.test(m.text)); }
  check('a finished scheduled run reaches Telegram with its summary', Boolean(deskMsg) && /4 leads yesterday/.test(deskMsg.text), deskMsg ? deskMsg.text.split('\n').slice(0, 2).join(' | ') : 'none');
  await page.click('.subnav [data-sub="chat"]');
  await page.waitForFunction(() => /Daily health check/.test(document.querySelector('#cl-list')?.textContent || ''));
  const schedRun = (await getJson('/api/desk')).tasks.find((t) => t.id === sched.last_task_id);
  check('the run is labelled with its schedule', schedRun?.options?.schedule === 'Daily health check'
    && /Daily health check/.test(await page.textContent(`#cl-list .cl-row[href="#r/${sched.last_task_id}"]`)), JSON.stringify(schedRun?.options));
  await page.screenshot({ path: `${OUT}/flow-schedules.png`, fullPage: true });
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db,json;db.execute('UPDATE desk_schedules SET enabled=FALSE, next_run_at=NULL, skipped=0, last_task_id=NULL, rule=%s WHERE id = 1', (json.dumps({'every': 'day', 'at': '08:30'}),))"`);

  // Alerts: rules in Settings; a rejected ad raises one alert (Telegram + Today), not twice, and it clears by itself.
  await openSettings('alerts');
  await page.waitForSelector('#al-rules li');
  check('Settings lists the alert rules', (await page.locator('#al-rules li').count()) === 19);
  check('W1b: Settings lists the two lead-quality rules, on by default, with their numbers and what junk means',
    /Few leads qualify/.test(await page.textContent('#al-rules')) && /counting only leads someone has worked \(past New, or Lost\)/.test(await page.textContent('#al-rules')) && /Many leads look like junk/.test(await page.textContent('#al-rules'))
    && await page.isChecked('[data-rule="qualified_low"][data-key="on"]') && await page.isChecked('[data-rule="junk_high"][data-key="on"]')
    && (await page.inputValue('[data-rule="qualified_low"][data-key="percent"]')) === '20' && (await page.inputValue('[data-rule="qualified_low"][data-key="min_leads"]')) === '10'
    && (await page.inputValue('[data-rule="junk_high"][data-key="percent"]')) === '30' && (await page.inputValue('[data-rule="junk_high"][data-key="min_leads"]')) === '10'
    && /Junk = marked Spam or fake, or fake-looking details and never contacted\./.test(await page.textContent('#al-rules')));
  check('Settings shows one section at a time, named in the list, the breadcrumb and the tab title', await page.evaluate(() =>
    [...document.querySelectorAll('[data-section]')].filter((x) => !x.hidden).map((x) => x.id).join() === 'alerts'
    && document.querySelector('.settings-nav [aria-current="page"]')?.dataset.set === 'alerts'
    && /Alerts/.test(document.querySelector('.crumbs [aria-current]')?.textContent || '') && /^Alerts · Settings/.test(document.title)));
  await page.fill('[data-rule="no_leads"][data-key="days"]', '4');
  await page.click('#al-form button[type=submit]');
  await page.waitForTimeout(500);
  // Targets live in one place now (audit A19), in their own section: the alert's Change link opens it, the alert reads it.
  await page.click('#al-rules a[href="#targets"]');
  await page.waitForSelector('#targets[data-section]:not([hidden])');
  check("the cost-per-lead alert's Change link opens the Targets section", await page.isHidden('#alerts') && /#targets$/.test(page.url()), page.url());
  await page.fill('#t-lead', '15');
  // Typed and not saved: switching sections keeps it, and the list marks the section until it's saved.
  await page.click('.settings-nav [data-set="alerts"]');
  await page.waitForSelector('#alerts[data-section]:not([hidden])');
  const dirtyDot = await page.evaluate(() => [...document.querySelectorAll('.settings-nav .set-dirty')].map((d) => d.parentElement.dataset.set).join());
  await page.goBack();
  await page.waitForSelector('#targets[data-section]:not([hidden])');
  check('typed work survives switching sections, marked "not saved yet" in the list, and Back returns to the section',
    dirtyDot === 'targets' && (await page.inputValue('#t-lead')) === '15', `${dirtyDot} ${await page.inputValue('#t-lead')}`);
  await page.click('#tg-targets button[type=submit]');
  await page.waitForTimeout(500);
  check('saving takes the "not saved yet" mark away', (await page.locator('.settings-nav .set-dirty').count()) === 0);
  await openSettings('alerts');
  check('alert thresholds are saved', (await page.inputValue('[data-rule="no_leads"][data-key="days"]')) === '4' && (await page.inputValue('#t-lead')) === '15');
  check('the cost-per-lead alert names the target from Targets', /Target \$15\.00 per lead/.test(await page.textContent('#al-rules')));
  await page.fill('[data-rule="no_leads"][data-key="days"]', '3');
  await page.click('#al-form button[type=submit]');
  await page.waitForTimeout(400);
  await page.click('.settings-nav [data-set="targets"]');
  await page.waitForSelector('#targets[data-section]:not([hidden])');
  await page.fill('#t-lead', '');
  await page.click('#tg-targets button[type=submit]');
  await page.waitForTimeout(500);
  check('without a cost-per-lead target the alert uses the qualified-lead target', /uses \$60\.00 per qualified lead/.test(await page.textContent('#al-rules')));
  const tgBeforeAlert = tgSent().length;
  const runAlerts = () => sh(`docker exec -w /app edgebourne-ads-backend python -c "import alerts;print(alerts.run())"`);
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute(\\"DELETE FROM alerts WHERE entity_id = 'qa-rejected'\\");db.execute(\\"INSERT INTO ads (id, name, campaign_id, status, effective_status, created_time) VALUES ('qa-rejected', 'QA rejected ad', '120252638288040312', 'ACTIVE', 'DISAPPROVED', now()) ON CONFLICT (id) DO UPDATE SET effective_status = 'DISAPPROVED'\\")"`);
  runAlerts();
  let alertMsg = null;
  for (let i = 0; i < 40 && !alertMsg; i++) { await page.waitForTimeout(1000); alertMsg = tgSent().slice(tgBeforeAlert).find((m) => /QA rejected ad/.test(m.text)); }
  check('a rejected ad raises an alert on Telegram', Boolean(alertMsg), alertMsg ? alertMsg.text.split('\n')[0] : 'none');
  await page.goto(BASE + '/home.html');
  await page.waitForSelector('#tq-problems');
  check('the alert shows on Today under Fix', /Meta stopped “QA rejected ad”/.test(await page.textContent('.tq-group[aria-labelledby="tq-problems"]')));
  runAlerts();
  await page.waitForTimeout(32000);
  check('the same alert is not sent twice', tgSent().slice(tgBeforeAlert).filter((m) => /QA rejected ad/.test(m.text)).length === 1);
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute(\\"DELETE FROM ads WHERE id = 'qa-rejected'\\")"`);
  runAlerts();
  await page.reload();
  await page.waitForSelector('main');
  await page.waitForTimeout(800);
  check('it clears from Today once the ad is fixed', !/QA rejected ad/.test(await page.textContent('main')));

  // Pacing: this month on Results, with a monthly target that says what a day should cost.
  await page.goto(BASE + '/performance.html');
  await page.waitForSelector('.figures.pace');
  check('Results shows this month: spent, at this pace, the spending limit', /Spent this month.*Month at this pace.*Account spending limit/s.test(await page.textContent('.figures.pace')));
  await page.click('#target-edit');
  const paceSeen = errors.length;
  await page.fill('#target-dollars', 'lots');
  await page.click('#target-form button[type=submit]');
  await page.waitForTimeout(600);
  check('a monthly target that is not an amount is refused', /Type the monthly amount/.test(await page.textContent('#toast, .toast, body')));
  errors.splice(paceSeen); // the refused amount logs an expected 400
  await page.fill('#target-dollars', '600');
  await page.click('#target-form button[type=submit]');
  await page.waitForFunction(() => /\$600/.test(document.querySelector('.figures.pace')?.textContent || ''));
  check('a monthly target shows the daily spend that lands on it', /Land on it with \$[\d.,]+ a day from today|Already spent/.test(await page.textContent('.figures.pace')), await page.textContent('.figures.pace .figure:last-child'));
  await page.screenshot({ path: `${OUT}/flow-pacing.png` });
  await page.evaluate(() => fetch('/api/performance/target', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dollars: '' }) }));

  // Results: the ads table filters, sorts, searches and totals; figures compare with the period before.
  await page.evaluate(() => localStorage.removeItem('ebads-results'));
  await page.goto(BASE + '/performance.html?range=7');
  await page.waitForSelector('.results-table tbody tr');
  const cells = (col) => page.$$eval('.results-table tbody tr', (rows, c) => rows.map((r) => r.children[c].textContent.trim()), col);
  const dollars = (t) => (t === '—' ? null : Number(t.replace(/[$,]/g, '')));
  const spentRows = await cells(2);
  check('Results lists only ads that spent money by default, biggest spend first',
    spentRows.length > 0 && spentRows.every((t) => dollars(t) > 0) && spentRows.map(dollars).every((v, i, a) => !i || a[i - 1] >= v)
    && Number(await page.textContent('#cr-filter [data-filter="spent"] .n')) === spentRows.length, spentRows.join(' '));
  const total = dollars((await page.textContent('.results-table tfoot td.num')).trim());
  check('the total row adds up the ads shown', Math.abs(total - spentRows.map(dollars).reduce((a, b) => a + b, 0)) < 0.01, String(total));
  check('each figure says how it compares with the days before', (await page.locator('.figures:not(.pace) .delta').count()) >= 4, (await page.textContent('.figures:not(.pace) .figure.hero .delta')) || '');
  await page.waitForSelector('#activity .chg-list li');
  check("Meta's history shows a budget change in money, not cents", /\$20\.00 → \$24\.00/.test(await page.textContent('#activity')) && !/2000 → 2400/.test(await page.textContent('#activity')),
    await page.textContent('#activity'));
  check("Meta's history links the ad and the campaign each line is about", (await page.locator('#activity a.ent-link[href^="/ad.html?id="]').count()) === 1
    && (await page.locator('#activity a.ent-link[href^="/campaign.html?id="]').count()) === 1);
  check('"Yesterday" under cost per lead is the real yesterday', await page.evaluate(async () => {
    const [d, y] = [await (await fetch('/api/performance?range=lastmonth')).json(), await (await fetch('/api/performance?range=7')).json()];
    return d.yesterday.day === y.range.end;
  }));
  await page.click('.results-table [data-sort="cpl"]');
  let cpl = (await cells(6)).map(dollars);
  const known = cpl.filter((v) => v !== null);
  check('Cost per lead sorts cheapest first, ads without leads last',
    known.every((v, i) => !i || known[i - 1] <= v) && cpl.slice(known.length).every((v) => v === null)
    && (await page.getAttribute('.results-table th:nth-child(7)', 'aria-sort')) === 'ascending', cpl.join(' '));
  await page.click('.results-table [data-sort="cpl"]');
  cpl = (await cells(6)).map(dollars).filter((v) => v !== null);
  check('a second click turns the order around', cpl.every((v, i) => !i || cpl[i - 1] >= v) && (await page.getAttribute('.results-table th:nth-child(7)', 'aria-sort')) === 'descending');
  await page.reload();
  await page.waitForSelector('.results-table tbody tr');
  check('the chosen order is kept after a reload', (await page.getAttribute('.results-table th:nth-child(7)', 'aria-sort')) === 'descending');
  await page.fill('#cr-q', 'order portal');
  const found = await cells(0);
  check('Find an ad narrows the table to matching names', found.length > 0 && found.every((t) => /order portal/i.test(t)), found.join(' | '));
  const rangeBefore = await page.inputValue('#range-pick');
  await page.$eval('#cr-q', (i) => { i.dataset.old = '1'; });
  await page.selectOption('#range-pick', rangeBefore === '30' ? '14' : '30');
  await page.waitForSelector('#cr-q:not([data-old])');
  await page.waitForSelector('.results-table tbody tr');
  const kept = await cells(0);
  check('changing the dates keeps the search box showing what still filters the table', (await page.inputValue('#cr-q')) === 'order portal' && kept.every((t) => /order portal/i.test(t)), `${await page.inputValue('#cr-q')} / ${kept.join(' | ')}`);
  await page.selectOption('#range-pick', rangeBefore);
  await page.waitForFunction((r) => document.querySelector('#range-pick').value === r && document.querySelector('.results-table tbody tr'), rangeBefore);
  await page.fill('#cr-q', 'zzz no such ad');
  check('no match says so and offers every ad', /No ad called/.test(await page.textContent('#cr-panel')) && await page.isVisible('#cr-panel [data-clear]'));
  await page.click('#cr-panel [data-clear]');
  check('Show all ads brings every ad back', (await page.locator('.results-table tbody tr').count()) === Number(await page.textContent('#cr-filter [data-filter="all"] .n'))
    && (await page.inputValue('#cr-q')) === '');
  await page.click('#cr-filter [data-filter="running"]');
  const st = await cells(1);
  check('Delivering shows only ads that are on', st.length > 0 && st.every((t) => t === 'Delivering'), st.join(' '));
  await page.click('#cr-filter [data-filter="spent"]');
  check('with one campaign there is no campaign picker', await page.isHidden('#campaign-pick'));
  const one = await page.evaluate(async () => {
    const all = await (await fetch('/api/performance?range=7')).json();
    const c = await (await fetch('/api/performance?range=7&campaign=' + all.campaigns[0].id)).json();
    const none = await (await fetch('/api/performance?range=7&campaign=999')).json();
    return [all.totals.spend_cents, c.totals.spend_cents, none.totals.spend_cents, none.ads.length];
  });
  check('a campaign narrows the numbers to that campaign', one[0] === one[1] && one[2] === 0 && one[3] === 0, one.join(' '));
  // 9.4d: deleted ads stay out of the table unless asked for (their spend still counts above); the table points to Ads.
  sh(`docker exec -w /app edgebourne-ads-backend python -c "
import db, account_info, datetime as d
y = account_info.today() - d.timedelta(days=1)
c = db.query('SELECT id FROM campaigns LIMIT 1', one=True)['id']
db.execute(\\"INSERT INTO ads (id, name, campaign_id, status, effective_status) VALUES ('qa-deleted', 'QA deleted ad', %s, 'DELETED', 'DELETED') ON CONFLICT (id) DO UPDATE SET effective_status = 'DELETED'\\", (c,))
db.execute(\\"INSERT INTO ad_daily (day, ad_id, campaign_id, ad_name, spend_cents) VALUES (%s, 'qa-deleted', %s, 'QA deleted ad', 777) ON CONFLICT DO NOTHING\\", (y, c))
db.execute(\\"INSERT INTO ads (id, name, campaign_id, status, effective_status) VALUES ('qa-deleted-0', 'QA unspent deleted ad', %s, 'DELETED', 'DELETED') ON CONFLICT (id) DO UPDATE SET effective_status = 'DELETED'\\", (c,))"`);
  await page.goto(BASE + '/performance.html?range=7');
  await page.waitForSelector('.results-table tbody tr');
  check('Results leaves deleted ads out of the table by default, and says what they spent',
    !/QA deleted ad/.test(await page.textContent('.results-table')) && await page.isVisible('#cr-deleted')
    && /deleted ads? spent \$[\d.,]+ in these days: counted in the figures above/.test(await page.textContent('#cr-note')), await page.textContent('#cr-note'));
  const delN = [await page.textContent('#cr-deleted .n'), (/(\d+) deleted ads? spent/.exec(await page.textContent('#cr-note')) || [])[1]];
  check('the Deleted count is the deleted ads that spent, the same number the note gives', delN[0] === delN[1], delN.join(' vs '));
  await page.click('#cr-filter [data-filter="all"]');
  await page.click('#cr-deleted');
  await page.waitForFunction(() => /QA deleted ad/.test(document.querySelector('.results-table')?.textContent || ''));
  check('Deleted shows them, marked Deleted, and the address keeps it', /Deleted/.test(await page.textContent('.results-table tr:has-text("QA deleted ad")'))
    && new URL(page.url()).searchParams.get('deleted') === '1' && (await page.getAttribute('#cr-deleted', 'aria-pressed')) === 'true');
  check('a deleted ad that spent nothing stays out even with Deleted and All on', !/QA unspent deleted ad/.test(await page.textContent('.results-table')));
  await page.click('#cr-deleted');
  await page.click('#cr-filter [data-filter="running"]');
  const openHref = new URL(BASE + await page.getAttribute('#cr-open', 'href'));
  check('Open in Ads opens the same days with "vs before", on Delivering when that filter is on',
    openHref.pathname === '/ads.html' && openHref.searchParams.get('range') === '7' && openHref.searchParams.get('vs') === '1' && openHref.searchParams.get('view') === 'delivering', openHref.search);
  await Promise.all([page.waitForURL('**/ads.html?**'), page.click('#cr-open')]);
  await page.waitForFunction(() => document.querySelector('#range-pick')?.value === '7');
  check('Ads opens on those days', (await page.inputValue('#range-pick')) === '7');
  await page.goto(BASE + '/performance.html?range=7');
  await page.waitForSelector('.results-table tbody tr');
  await page.click('#cr-filter [data-filter="spent"]');
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute(\\"DELETE FROM ad_daily WHERE ad_id = 'qa-deleted'\\");db.execute(\\"DELETE FROM ads WHERE id IN ('qa-deleted', 'qa-deleted-0')\\")"`);
  await page.screenshot({ path: `${OUT}/flow-results.png`, fullPage: true });

  // 5. Claude page: decisions first, then each ad's story, then every run (dev copy of the real Desk).
  require('child_process').execSync('docker cp dev/seed_desk.py edgebourne-ads-backend:/tmp/seed_desk.py && docker exec edgebourne-ads-backend sh -c "cd /app && python /tmp/seed_desk.py"', { cwd: __dirname + '/..' });
  await page.goto(BASE + '/desk.html', { waitUntil: 'networkidle' });
  await page.waitForSelector('#cv-col .sg');
  check('Claude opens on the conversation with suggestions waiting', (await page.locator('#cv-col .sg').count()) === 2);
  check('the suggestions sit in the conversation they came from', /Polish .N1 - One simple system/.test(await page.textContent('#cv-col .cv-you')));
  check('a new-ad suggestion shows what changes', /Everything in one system → No more digging for numbers/.test(await page.textContent('#cv-col .sg .changes')));
  await page.waitForSelector('#cv-col .decision-preview iframe', { timeout: 10000 });
  const decisionFrame = await page.getAttribute('#cv-col .decision-preview iframe', 'src');
  check('a new-ad suggestion loads Meta\'s preview of the ad', /^https:\/\/[^/]*facebook\.com\//.test(decisionFrame || ''), decisionFrame);
  check('the reply box is always there', await page.isVisible('#prompt'));
  await page.screenshot({ path: `${OUT}/flow-5-claude-waiting.png` });
  await page.click('.subnav [data-sub="ads"]');
  await page.waitForSelector('#view .runs');
  const story = await page.textContent('#view .family');
  check('By ad tells the ad\'s story with outcomes', /Created, off/.test(story) && /made in the New version run/.test(story) && /Not about one ad/.test(await page.textContent('#view')), story.replace(/\s+/g, ' ').trim().slice(0, 60));
  await page.screenshot({ path: `${OUT}/flow-5-claude-ads.png`, fullPage: true });
  const byAdCards = await page.$$eval('#view .sg[data-proposal]', (els) => els.map((e) => [e.dataset.proposal, !!e.querySelector('[data-accept]'), !!e.querySelector('[data-revise]')]));
  const convCards = await getJson('/api/desk').then((d) => d.tasks.flatMap((t) => t.proposals || []).filter((p) => p.status === 'pending').map((p) => String(p.id)));
  check('By ad shows a waiting suggestion as the same card as the conversation (Accept, Ask to change), not a line',
    byAdCards.length > 0 && byAdCards.every(([id, a, r]) => convCards.includes(id) && a && r) && (await page.locator('#view .decide-link').count()) === 0
    && (await page.locator('[id^="p-"]').count()) === (await page.locator('#view [id^="p-"]').count()), JSON.stringify(byAdCards));
  const reviseId = byAdCards[0][0];
  await page.locator(`#view .sg[data-proposal="${reviseId}"] [data-revise]`).click();
  await page.waitForSelector('#cv-chip:not([hidden])');
  check('Ask to change from By ad opens its conversation about that suggestion', /About:/.test(await page.textContent('#cv-chip')) && (await page.locator(`#cv-col .sg[data-proposal="${reviseId}"]`).count()) === 1);
  await page.click('[data-unchip]');
  const second = page.locator('#cv-col .sg', { hasText: 'the next hire' });
  await second.locator('[data-decline-one]').click();
  await page.waitForFunction(() => document.querySelectorAll('#cv-col .sg').length === 1);
  check('declining removes it from the list', /1/.test(await page.textContent('.cl-decide')));
  await page.click('#undo-bar [data-undo]');
  await page.waitForFunction(() => document.querySelectorAll('#cv-col .sg').length === 2);
  const hire = (await getJson('/api/desk')).tasks.flatMap((t) => t.proposals || []).find((p) => /the next hire/.test(p.title));
  check('Undo brings a declined suggestion back', hire?.status === 'pending', hire?.status);
  await page.locator('#cv-col .sg', { hasText: 'the next hire' }).locator('[data-decline-one]').click();
  await page.waitForFunction(() => document.querySelectorAll('#cv-col .sg').length === 1);
  await page.locator('#cv-col .sg [data-accept]').click();
  await page.waitForSelector('dialog.accept-sheet #cd-ok:not(:empty)');
  const sheetFocus = await page.evaluate(() => document.activeElement.id);
  const waitingId = await page.getAttribute('#cv-col .sg', 'data-proposal');
  await page.keyboard.press('Enter');  // a stray Enter lands on Cancel
  await page.waitForSelector('dialog.accept-sheet', { state: 'detached' });
  const stillWaiting = (await getJson('/api/desk')).tasks.flatMap((t) => t.proposals || []).find((p) => String(p.id) === waitingId);
  check('the Accept sheet opens on Cancel: a stray Enter accepts nothing', sheetFocus === 'cd-cancel' && stillWaiting?.status === 'pending', `${sheetFocus} ${stillWaiting?.status}`);
  await page.locator('#cv-col .sg [data-accept]').click();
  await page.waitForSelector('dialog.accept-sheet #cd-ok:not(:empty)');
  await page.click('dialog.accept-sheet #cd-ok');
  await page.waitForFunction(() => document.querySelector('dialog.accept-sheet #cd-ok')?.textContent === 'Done');
  check('accepting a new-ad suggestion creates the ad and stays on the page', /Created, off/.test(await page.textContent('dialog.accept-sheet .sheet-result')));
  const madeHref = await page.getAttribute('dialog.accept-sheet .sheet-result a', 'href');
  await page.click('dialog.accept-sheet #cd-ok');
  await page.goto(BASE + madeHref);
  await page.waitForFunction(() => /angle where it lives/.test(document.querySelector('#cr-title')?.textContent || ''));
  check('the new ad is switched off', /Off/.test(await page.textContent('#cr-status')), await page.textContent('#cr-title'));

  {
  // The board: a busy desk sorted into trays; one Accept across categories; clearing the queue.
  require('child_process').execSync('docker cp dev/seed_desk.py edgebourne-ads-backend:/tmp/seed_desk.py && docker cp dev/seed_board.py edgebourne-ads-backend:/tmp/seed_board.py && docker exec edgebourne-ads-backend sh -c "cd /app && python /tmp/seed_desk.py && python /tmp/seed_board.py"', { cwd: __dirname + '/..' });
  await page.goto(BASE + '/desk.html', { waitUntil: 'networkidle' });
  await page.waitForSelector('#cl-list .cl-group');
  const groupNames = await page.locator('#cl-list .cl-head h2').allTextContents();
  check('the list shows what is on the Mac, then the days', groupNames[0] === 'On your Mac' && groupNames.includes('Today'), groupNames.join());
  check('a finished conversation is marked New until opened', (await page.locator('#cl-list .cl-new-tag').count()) === 4, String(await page.locator('#cl-list .cl-new-tag').count()));
  const freshRow = page.locator('#cl-list .cl-row', { hasText: 'most qualified leads' });
  await freshRow.click();
  await page.waitForFunction(() => /most qualified leads.*Claude.*N1 v2/s.test(document.querySelector('#cv-col')?.textContent || ''));
  check('a conversation shows the question and the answer together', await page.isVisible('#cv-col .cv-claude'));
  await page.click('a.cl-decide');
  await page.waitForSelector('#cv-col .cv-group');
  check('opening it clears New', (await page.locator('#cl-list .cl-new-tag').count()) === 3);
  check('Review all shows every suggestion under its question', (await page.locator('#cv-col .cv-group').count()) === 4 && (await page.locator('#cv-col .sg').count()) === 10, `${await page.locator('#cv-col .cv-group').count()} ${await page.locator('#cv-col .sg').count()}`);
  await page.click('[data-accept-all]');
  await page.waitForSelector('dialog.accept-sheet #cd-ok:not(:empty)');
  const sheet = await page.textContent('dialog.accept-sheet');
  check('the sheet sorts across categories', ['Spending', "Changes to what's running", 'New ads, created switched off', 'For Claude to do on your Mac', 'Only in this console'].every((g) => sheet.includes(g)), sheet.slice(0, 200));
  const on = page.locator('dialog.accept-sheet .sheet-item', { hasText: 'Turn N2 back on' });
  check('turning on is never ticked for you', !(await on.locator('input').isChecked()) && /spends up to/.test(await on.textContent()));
  const raise = page.locator('dialog.accept-sheet .sheet-item', { hasText: 'Raise the campaign budget' });
  check('a budget that moved since Claude read it says so and waits', !(await raise.locator('input').isChecked()) && /Claude saw \$20\.00 a day/.test(await raise.textContent()), await raise.textContent());
  await page.screenshot({ path: `${OUT}/flow-5-accept-sheet.png` });
  // Later flows count running ads, tests and tags, so leave those untouched here.
  for (const title of ['Pause N4', 'Test the order portal', 'Tag N3', 'New headline: Type it once', 'Narrow the age range']) await page.locator('dialog.accept-sheet .sheet-item', { hasText: title }).locator('input').uncheck();
  const ticked = await page.locator('dialog.accept-sheet [data-item]:checked').count();
  check('the button counts what is ticked', (await page.textContent('dialog.accept-sheet #cd-ok')) === `Accept ${ticked}`, String(ticked));
  await page.click('dialog.accept-sheet #cd-ok');
  await page.waitForFunction(() => document.querySelector('dialog.accept-sheet #cd-ok')?.textContent === 'Done', null, { timeout: 60000 });
  const okRows = await page.locator('dialog.accept-sheet .sheet-item[data-state="ok"]').count();
  check('one Accept applies everything ticked, each reported', okRows === ticked, `${okRows} of ${ticked}: ${(await page.textContent('dialog.accept-sheet #sheet-title'))}`);
  await page.click('dialog.accept-sheet #cd-ok');
  await page.waitForFunction((n) => document.querySelectorAll('#cv-col .sg').length === n, 10 - ticked);
  const deskProposals = (await getJson('/api/desk')).tasks.flatMap((t) => t.proposals || []); // newest first
  const unticked = ['Pause N4', 'Test the order portal', 'Tag N3', 'New headline: Type it once', 'Narrow the age range'].map((x) => deskProposals.find((p) => p.title.startsWith(x)));
  check('what you did not tick stays waiting', unticked.every((p) => p?.status === 'pending'), unticked.map((p) => `${p?.title}: ${p?.status}`).join(' | '));
  const madeRun = await page.evaluate(async () => (await (await fetch('/api/desk')).json()).tasks.find((t) => t.kind === 'render' && t.status === 'queued' && t.options.from_proposal));
  check('a new version joins the queue, linked to its suggestion', !!madeRun);
  const desk = () => page.evaluate(async () => (await fetch('/api/desk')).json());
  const openConv = async (text) => { await page.locator('#cl-list .cl-row', { hasText: text }).first().click(); await page.waitForFunction((t) => (document.querySelector('#cv-head h1')?.textContent || '').includes(t), text); await page.waitForTimeout(200); };
  const sendReply = async (text) => { await page.fill('#prompt', text); await page.locator('#cv-btns button[type=submit]').click(); };

  // An answer reads as sections with its pictures.
  await openConv('Audit the whole');
  const secs = await page.locator('#cv-col .cv-sec > summary').allTextContents();
  check('a report is split into its sections', secs.join() === "What the numbers say,What I'd do,Data used", secs.join());
  const openSecs = await page.evaluate(() => [...document.querySelectorAll('#cv-col .cv-sec')].map((d) => d.open));
  check('with suggestions below, only the first section starts open', openSecs.join() === 'true,false,false', openSecs.join());
  check('numbers in a report table line up as numbers', (await page.locator('#cv-col .cv-sec table td.n').count()) >= 6);
  check('every ad the answer names has a preview tile', (await page.locator('#cv-col .cv-cr').count()) >= 3);
  await page.locator('#cv-col .cv-cr').first().click();
  await page.waitForSelector('dialog.viewer iframe', { timeout: 10000 });
  check("a tile opens Meta's preview, with the placements to switch between", (await page.locator('dialog.viewer [data-f]').count()) === 4);
  await page.locator('dialog.viewer [data-f="INSTAGRAM_REELS"]').click();
  await page.waitForFunction(() => /INSTAGRAM_REELS/.test(document.querySelector('dialog.viewer iframe')?.src || ''));
  check('switching placement loads that placement', /INSTAGRAM_REELS/.test(await page.getAttribute('dialog.viewer iframe', 'src')) && (await page.locator('dialog.viewer iframe').count()) === 1
    && (await page.getAttribute('dialog.viewer [data-f="INSTAGRAM_REELS"]', 'aria-selected')) === 'true');
  await page.click('dialog.viewer [data-viewer-close]');
  await page.screenshot({ path: `${OUT}/flow-5-conversation.png` });

  await openConv('IT consultants');
  check('competitor ads Claude found show in its answer', (await page.locator('#cv-col .cv-swipe').count()) === 3);
  await page.locator('#cv-col .cv-swipe').first().click();
  await page.waitForSelector('dialog.viewer .viewer-swipe');
  check('a competitor ad opens with its words', /One outage/.test(await page.textContent('dialog.viewer')));
  await page.click('dialog.viewer [data-viewer-close]');

  // A suggestion can go back to Claude with a note.
  await openConv('Two headlines');
  const headlines = page.locator('#cv-col .sg', { hasText: 'Type it once' });
  await headlines.locator('[data-preview] iframe').waitFor({ timeout: 15000 });
  await headlines.locator('[data-pf="INSTAGRAM_STORY"]').click();
  await page.waitForFunction(() => /INSTAGRAM_STORY/.test(document.querySelector('#cv-col .sg [data-preview] iframe')?.src || ''));
  check('a suggested ad can be previewed per placement in place', /INSTAGRAM_STORY/.test(await headlines.locator('[data-preview] iframe').getAttribute('src'))
    && (await page.isVisible('#cv-col')) && !(await page.locator('dialog.viewer[open]').count()));
  await headlines.locator('[data-compare]').click();
  await page.waitForFunction(() => document.querySelectorAll('dialog.viewer .viewer-panes figure').length === 2);
  check('a suggested ad can be compared with what runs now', /Now.*Suggested/s.test(await page.textContent('dialog.viewer .viewer-panes')));
  await page.click('dialog.viewer [data-viewer-close]');
  await headlines.locator('[data-revise]').click();
  check('Ask to change names the suggestion in the reply box', /About: New headline: Type it once/.test(await page.textContent('#cv-chip')));
  const turnsBefore = await page.locator('#cv-col .cv-turn').count();
  await sendReply('Try it as a question.');
  await page.waitForFunction((n) => document.querySelectorAll('#cv-col .cv-turn').length === n + 1, turnsBefore);
  let d = await desk();
  const sentBack = d.tasks.flatMap((t) => t.proposals).find((p) => p.title === 'New headline: Type it once');
  const revision = d.tasks.find((t) => t.prompt === 'Try it as a question.');
  check('the suggestion is marked sent back and the reply carries it', sentBack.status === 'revised' && revision.options.about.id === sentBack.id && !!revision.thread_id, JSON.stringify(revision.options));
  check('a follow-up goes to the front of the line', d.board.queue[0] === revision.id, d.board.queue.join());
  const payload = JSON.parse(sh(`docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -c "import desk_api,json,account_ctx
with account_ctx.use(1):
    t=desk_api.task_payload(${revision.id}); print(json.dumps({'n':len(t['thread']),'first':t['thread'][0]['you'],'resume':t['resume_from']},default=str))"`));
  check('the Mac gets the whole conversation and the turn to continue', payload.n === 2 && /Two headlines/.test(payload.first) && !!payload.resume, JSON.stringify(payload));
  await page.click('#cv-line [data-cancel]');
  await page.waitForFunction(() => /Cancelled before it started/.test(document.querySelector('#cv-col')?.textContent || ''));
  check('a follow-up can be cancelled and stays in the conversation', await page.isVisible('#prompt'));

  // Clearing: one tap, Undo, and suggestions are only declined when you say so.
  const removed = await page.locator('#cv-col .cv-turn').count();
  const removedId = Number(await page.locator('#cv-col .cv-turn').last().locator('[data-clear-turn]').getAttribute('data-clear-turn'));
  await page.locator('#cv-col .cv-turn').last().locator('[data-clear-turn]').click();
  await page.waitForFunction((n) => document.querySelectorAll('#cv-col .cv-turn').length === n - 1, removed);
  check('one reply can be removed from a conversation', /Reply removed/.test(await page.textContent('#undo-bar')) && !!(await desk()).tasks.find((t) => t.id === removedId)?.archived_at);
  await page.click('[data-undo]');
  await page.waitForFunction((n) => document.querySelectorAll('#cv-col .cv-turn').length === n, removed);
  const putBack = (await desk()).tasks.find((t) => t.id === removedId);
  check('Undo puts the reply back', !!putBack && !putBack.archived_at, JSON.stringify(putBack && putBack.archived_at));
  const waitingBefore = (await desk()).tasks.find((t) => /^Audit the whole/.test(t.prompt)).proposals.filter((p) => p.status === 'pending').length;
  const waitingRow = page.locator('#cl-list .cl-item', { hasText: 'Audit the whole' });
  await waitingRow.locator('[data-clear-thread]').click();
  await page.waitForSelector('dialog.confirm');
  check('clearing with a suggestion waiting asks first', /still waiting/.test(await page.textContent('dialog.confirm')));
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => !/Audit the whole/.test([...document.querySelectorAll('#cl-list .cl-row')].map((r) => r.textContent).join()));
  await page.click('[data-undo]');
  await page.waitForFunction(() => /Audit the whole/.test(document.querySelector('#cl-list')?.textContent || ''));
  d = await desk();
  check('Undo also brings its suggestions back', d.tasks.find((t) => /^Audit the whole/.test(t.prompt)).proposals.filter((p) => p.status === 'pending').length === waitingBefore, String(waitingBefore));

  // Accepting what nothing else acts on starts Claude, visibly.
  await openConv('Audit the whole');
  await page.locator('#cv-col .sg', { hasText: 'Narrow the age range' }).locator('[data-accept]').click();
  await page.waitForSelector('dialog.accept-sheet #cd-ok:not(:empty)');
  check('the sheet says Claude will pick it up', /Claude picks this up on your Mac/.test(await page.textContent('dialog.accept-sheet')));
  await page.click('dialog.accept-sheet #cd-ok');
  await page.waitForFunction(() => document.querySelector('dialog.accept-sheet #cd-ok')?.textContent === 'Done');
  check('accepting says Claude is on it', /Claude is on it/.test(await page.textContent('dialog.accept-sheet .sheet-result')));
  await page.click('dialog.accept-sheet #cd-ok');
  await page.waitForFunction(() => /I accepted your suggestion: Narrow the age range/.test(document.querySelector('#cv-col')?.textContent || ''));
  check('the accepted suggestion becomes the next turn, and says so', /Claude is on it/.test(await page.textContent('#cv-col .prows')));
  check('the job shows on the Mac panel', /Narrow the age range/.test(await page.textContent('#cl-list .cl-now')));
  const nowBox = await page.locator('#cl-list .cl-now').boundingBox();
  const rowBox = await page.locator('#cl-list .cl-now .cl-row').first().boundingBox();
  check('the Mac panel is really on screen, not collapsed', nowBox.height > 60 && rowBox.y >= nowBox.y && rowBox.y + 10 < nowBox.y + nowBox.height, JSON.stringify(nowBox));

  await page.click('a.cl-decide');
  await page.waitForSelector('[data-decline-all]');
  await page.click('[data-decline-all]');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => /Nothing to decide/.test(document.querySelector('#cv-head')?.textContent || ''));
  check('Decline all empties the suggestions', !(await page.locator('a.cl-decide').count()));

  // The line, and stopping.
  const lineRows = () => page.evaluate(() => [...document.querySelectorAll('#cl-list .cl-dot.pos')].map((d) => d.closest('.cl-row').querySelector('b').textContent));
  const before5 = await lineRows();
  await openConv('Three new ideas for restaurant');
  await page.click('#cv-line [data-next]');
  await page.waitForFunction(() => /restaurant owners/.test(document.querySelector('#cl-list .cl-dot.pos')?.closest('.cl-row').textContent || ''));
  check('Run next moves a job to the front', (await lineRows())[0].includes('restaurant owners'), before5.join(' | '));
  await page.locator('#cl-list .cl-item', { hasText: 'Why did cost per lead' }).locator('[data-cancel]').click();
  await page.waitForFunction(() => !/Why did cost per lead/.test(document.querySelector('#cl-list')?.textContent.split('Today')[0] || ''));
  const whyJob = (await desk()).tasks.find((t) => t.prompt.includes('Why did cost per lead'));
  check('Cancel is on every waiting job, no hover needed', whyJob?.status === 'cancelled', whyJob?.status);

  await openConv('N2 - Order portal');
  check('a running job shows its steps with a live timer', (await page.locator('#cv-col .cv-trail li').count()) === 3 && /\d:\d\d/.test(await page.textContent('#cv-col .cv-trail li.now time')));
  await page.fill('#prompt', 'And keep the sound.');
  check('typing while it works offers both choices', /Stop and send/.test(await page.textContent('#cv-btns')) && /Send when it.s done/.test(await page.textContent('#cv-btns')));
  await page.locator('#cv-btns button[type=submit]').click();
  await page.waitForFunction(() => /follow-up runs as soon as this finishes/.test(document.querySelector('#cv-line')?.textContent || ''));
  const waitingJobs = (await desk()).tasks;
  const followUp = waitingJobs.find((t) => t.prompt.trim() === 'And keep the sound.');
  const runningN2 = waitingJobs.filter((t) => ['claimed', 'running'].includes(t.status));
  check('a follow-up can wait for the running job', followUp?.status === 'queued' && runningN2.length === 1, `${followUp?.status} behind ${runningN2.length} running`);
  await page.click('#cv-line [data-cancel]');
  await page.waitForSelector('#cv-btns [data-stop]');
  await page.click('#cv-btns [data-stop]');
  await page.waitForFunction(() => /Stop Claude here/.test(document.querySelector('#cv-hint')?.textContent || ''));
  check('Stop asks once, right where you clicked', (await desk()).tasks.filter((t) => ['claimed', 'running'].includes(t.status)).length === 1 && !(await page.locator('dialog.confirm[open]').count()));
  await page.click('#cv-btns [data-stop]');
  await page.waitForFunction(() => /You stopped this after/.test(document.querySelector('#cv-col')?.textContent || ''));
  check('a stopped job stays in its conversation, ready for new directions', (await page.getAttribute('#prompt', 'placeholder')) === 'Reply to Claude…');
  d = await desk();
  check('the Mac is told: the run is cancelled on the server', d.tasks.filter((t) => t.status === 'running' || t.status === 'claimed').length === 0);

  macSeen(3600);  // the Mac went quiet an hour ago
  await page.click('[data-clear="queue"]');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => /Anything you send waits/.test(document.querySelector('#cl-list .cl-now')?.textContent || ''));
  d = await desk();
  check('Clear the line cancels everything not started, and the panel stays', d.tasks.filter((t) => t.status === 'queued').length === 0 && await page.isVisible('#cl-list .cl-now'),
    d.tasks.filter((t) => t.status === 'queued').map((t) => t.prompt.slice(0, 30)).join(' | '));
  check('with the Mac offline the panel says requests wait, not that they start right away (A3-108)',
    /waits until it.s back/.test(await page.textContent('#cl-list .cl-now')) && !/starts right away/.test(await page.textContent('#cl-list .cl-now')));
  await page.waitForFunction(() => /Your Mac is offline/.test(document.querySelector('.rail .claude-now')?.textContent || ''), null, { timeout: 15000 });
  check('the status line says the Mac is offline, not that Claude is idle', !/Claude is idle/.test(await page.textContent('.rail .claude-now')) && (await desk()).tasks.every((t) => !['queued', 'claimed', 'running'].includes(t.status)));
  {
    const now = await getJson('/api/desk/now');
    const rail = await page.textContent('.rail .claude-now b');
    const panel = await page.textContent('#cl-list .cl-now [data-mac]');
    const foot = await page.textContent('#mac-summary');
    check('the Mac status says the same thing in the sidebar, the list and the Mac button (offline vs idle)', now.mac.state === 'offline'
      && rail.startsWith(now.mac.title) && panel.startsWith(`${now.mac.title}.`) && panel.includes(now.mac.detail) && foot.startsWith(now.mac.title) && /last seen/.test(foot),
      `${now.mac.title} | ${rail} | ${panel} | ${foot}`);
  }

  const dayCount = await page.locator('#cl-list .cl-item').count();
  await page.locator('[data-clear-day]').first().click();
  await page.waitForFunction((n) => document.querySelectorAll('#cl-list .cl-item').length < n, dayCount);
  check('a whole day clears in one click, with Undo', /cleared/.test(await page.textContent('#undo-bar')));
  await page.click('[data-show-cleared]');
  const clearedItem = page.locator('#cl-list .cl-item', { hasText: 'most qualified leads' });
  await clearedItem.locator('[data-restore-thread]').click();
  await page.waitForFunction(() => /most qualified leads/.test([...document.querySelectorAll('#cl-list .cl-group')].filter((g) => !g.querySelector('.cl-toggle')).map((g) => g.textContent).join()));
  const restored = (await desk()).tasks.filter((t) => /most qualified leads/.test(t.prompt));
  check('cleared conversations are kept and can be put back', restored.length > 0 && restored.every((t) => !t.archived_at), restored.map((t) => t.archived_at).join());

  // A new conversation.
  await page.click('.cl-new');
  await page.waitForSelector('#cv-seeds:not([hidden])');
  await page.click('[data-seed="review"]');
  const reviewsBefore = (await desk()).tasks.filter((t) => /^Review the last 7 days/.test(t.prompt)).length;
  // Enter, and Enter again while the first send is still on its way (a phone): one conversation (A3-32).
  await page.route('**/api/desk/tasks', async (route) => { await new Promise((r) => setTimeout(r, 700)); await route.continue(); });
  await page.focus('#prompt');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => /Review the last 7 days/.test(document.querySelector('#cv-head h1')?.textContent || ''));
  await page.unroute('**/api/desk/tasks');
  d = await desk();
  const started = d.tasks.find((t) => /^Review the last 7 days/.test(t.prompt));
  check('a starter sets what kind of help it is and opens the conversation', started.kind === 'review' && !started.thread_id, started.kind);
  const reviewsAfter = d.tasks.filter((t) => /^Review the last 7 days/.test(t.prompt)).length;
  check('pressing Enter twice while it sends starts one conversation, not two', reviewsAfter === reviewsBefore + 1, `${reviewsBefore} → ${reviewsAfter}`);

  // Queue up a bunch: several new jobs, several follow-ups, in order, visible from any page.
  await sendReply('First follow-up.');
  await page.waitForFunction(() => /First follow-up/.test(document.querySelector('#cv-col')?.textContent || ''));
  await sendReply('Second follow-up.');
  await page.waitForFunction(() => /Second follow-up/.test(document.querySelector('#cv-col')?.textContent || ''));
  check('several messages can wait in one conversation', /3 messages waiting/.test(await page.textContent('#cv-line')), await page.textContent('#cv-line'));
  check('a waiting message says what it waits for while the Mac is offline', /Your Mac is offline\. It starts when your Mac is back online\./.test(await page.textContent('#cv-col')));
  d = await desk();
  const order = d.board.queue.map((id) => d.tasks.find((t) => t.id === id).prompt.split(' ').slice(0, 2).join(' '));
  check('follow-ups keep the order they were sent', order.indexOf('First follow-up.') >= 0 && order.indexOf('First follow-up.') < order.indexOf('Second follow-up.') && order.indexOf('Review the') < order.indexOf('First follow-up.'), order.join(' | '));
  await page.click('.cl-new');
  await page.waitForSelector('#cv-seeds:not([hidden])');
  for (const job of ['Job one for the line', 'Job two for the line']) {
    await page.fill('#prompt', job);
    await page.click('[data-add-line]');
    await page.waitForFunction((j) => (document.querySelector('#cl-list .cl-now')?.textContent || '').includes(j), job);
  }
  check('Add to line stacks jobs without leaving the page', (await page.inputValue('#prompt')) === '' && await page.isVisible('#cv-seeds'));
  await page.goto(BASE + '/leads.html');
  await page.waitForFunction(() => /5 waiting/.test(document.querySelector('.rail .claude-now')?.textContent || ''), null, { timeout: 15000 });
  check('every page shows what Claude has going on', /Your Mac is offline.*5 waiting\. They start when the Mac is back/.test(await page.textContent('.rail .claude-now')));
  macSeen(0);  // the Mac is back
  await page.goto(BASE + '/desk.html#list', { waitUntil: 'networkidle' });
  await page.click('[data-clear="queue"]');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => /Claude is idle/.test(document.querySelector('#cl-list .cl-now')?.textContent || ''));
  check('with the Mac online an empty line says anything sent starts right away', /starts right away/.test(await page.textContent('#cl-list .cl-now')));
  await page.waitForFunction(() => /Claude is idle/.test(document.querySelector('.rail .claude-now')?.textContent || ''), null, { timeout: 15000 });
  check('the status line says when Claude is idle', /Nothing in line/.test(await page.textContent('.rail .claude-now')));
  await page.screenshot({ path: `${OUT}/flow-5-board-cleared.png` });
  // A helper without passes (before 2.0): the Mac panel asks for the update; 2.0 doesn't.
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import settings_store; settings_store.set('bridge_version', '1.9')"`);
  await page.reload({ waitUntil: 'networkidle' });  // same URL: goto would only move to the hash
  await page.waitForSelector('#mac-update', { state: 'attached', timeout: 10000 });
  const updateNote = await page.textContent('#mac-update');
  macSeen(0);
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('#mac-body dl', { state: 'attached' });
  check('the Mac panel asks to update a helper older than 2.0, and only then',
    /Update the helper on your Mac.*1\.9.*teammates and clients wait/.test(updateNote) && !(await page.locator('#mac-update').count()), updateNote);
  macSeen(3600);
  // The Mac's side against the database: passes, lost and silent runs, the line across accounts.
  const states = JSON.parse(sh('docker cp dev/qa_desk_states.py edgebourne-ads-backend:/app/qa_desk_states.py && docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python qa_desk_states.py; docker exec edgebourne-ads-backend rm -f /app/qa_desk_states.py').trim().split('\n').pop());
  check('a Claude run reaches only its own request and account; lost, silent and stopped runs end right; Run next is first across accounts; mentions stored; 304 when unchanged; a helper before 2.0 takes only the owners\' requests',
    states.failed.length === 0 && states.passed === 23, JSON.stringify(states));
  }

  // Tests (experiments): set one up, read the verdict, finish it; Claude's suggested test becomes one on approval.
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute('DELETE FROM experiments')"`);
  await page.goto(BASE + '/experiments.html');
  await page.waitForSelector('#tests .empty');
  check('Tests explains itself when there are none', /calls a winner only at 95% confidence/.test(await page.textContent('#tests .empty')));
  await page.click('#tests [data-new]');
  await page.waitForSelector('dialog.test-dialog [data-arm-ref]');
  const testsSeen = errors.length;
  await page.fill('dialog #f-name', 'QA problem hook vs result hook');
  await page.selectOption('dialog #arm-ref-0', 'ad:120252672229040312');
  await page.click('dialog button[type=submit]');
  await page.waitForSelector('dialog .field.error .err');
  check('a test needs at least two sides', /at least two sides/.test(await page.textContent('dialog .field.error')));
  errors.splice(testsSeen); // the refused test logs an expected 400
  await page.click('dialog #arm-add');
  await page.click('dialog #arm-add');
  check('up to four sides can be added', (await page.locator('dialog [data-arm]').count()) === 4 && await page.isHidden('dialog #arm-add'));
  await page.locator('dialog [data-arm-remove]').nth(3).click();
  await page.locator('dialog [data-arm-remove]').nth(2).click();
  await page.selectOption('dialog #arm-ref-1', 'ad:120252672230740312');
  const weekAgo = await page.evaluate(() => { const d = new Date(Date.now() - 7 * 864e5); return d.toISOString().slice(0, 10); });
  await page.fill('dialog #f-start', weekAgo);
  await page.selectOption('dialog #f-metric', 'ctr');
  check('the target cost is only asked for cost metrics', await page.isHidden('dialog #target-field'));
  await page.selectOption('dialog #f-metric', 'cpl');
  await page.click('dialog button[type=submit]');
  await page.waitForSelector('.test .arms-table');
  const card = await page.textContent('.test');
  check('a new test compares its arms over its own days, with a verdict in words',
    /QA problem hook vs result hook/.test(card) && (await page.locator('.test .arms-table tbody tr').count()) === 2
    && /N1 - One simple system/.test(card) && /N3 - Same work twice/.test(card)
    && /(Too early to call|No clear difference|looks better|wins)/.test(await page.textContent('.test .verdict')), await page.textContent('.test .verdict'));
  await page.click('.test [data-finish]');
  await page.waitForSelector('dialog.test-dialog [name=verdict]');
  await page.check('dialog input[name=winner][value="A"]');
  await page.fill('dialog #f-verdict', 'A got cheaper leads; keep the problem hook.');
  await page.click('dialog button[type=submit]');
  await page.waitForFunction(() => document.querySelector('[data-n="finished"]')?.textContent === '1');
  check('finishing moves it to Finished and keeps it in view', (await page.textContent('[data-n="running"]')) === '0' && (await page.locator('.test').count()) === 1);
  check('a finished test shows the winner and what was learned', /Finished · A won/.test(await page.textContent('.test .pill')) && /keep the problem hook/.test(await page.textContent('.test .verdict')));
  // 9.4d: a winner gets a next step. Turn the others off and change the winner's budget through the usual
  // confirmations (cancelled here: nothing changes on Meta), or ask Claude for more like it.
  await page.waitForSelector('.test .test-next');
  const nextText = await page.textContent('.test .test-next');
  check('a test with a winner says the next step in words', /A \(N1 - One simple system\) won\. Turn the others off/.test(nextText.replace(/\s+/g, ' ')), nextText.replace(/\s+/g, ' ').slice(0, 120));
  const changesNow = () => sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(db.query('SELECT COUNT(*) AS n FROM meta_changes', one=True)['n'])"`).trim();
  const changesBefore = changesNow();
  await page.click('.test-next [data-off]');
  await page.waitForSelector('dialog.confirm #cd-cancel');
  check('Turn off from a test opens the usual on/off confirmation, starting on Cancel',
    /Turn off “N3 - Same work twice”\?/.test(await page.textContent('dialog.confirm h2')) && await page.evaluate(() => document.activeElement?.id === 'cd-cancel'));
  await page.click('dialog.confirm #cd-cancel');
  await page.click('.test-next [data-raise]');
  await page.waitForSelector('dialog.confirm #cd-input');
  check("the winner's budget opens the usual budget confirmation with today's amount", /Daily budget for/.test(await page.textContent('dialog.confirm h2'))
    && /Now \$[\d.,]+ a day/.test(await page.textContent('dialog.confirm .confirm-body')));
  await page.click('dialog.confirm #cd-cancel');
  await page.waitForTimeout(300);
  check('cancelling either one changes nothing on Meta', changesNow() === changesBefore);
  const moreHref = new URL(BASE + await page.getAttribute('.test-next a[href^="/desk.html"]', 'href'));
  check('Make more like this opens Claude with a new-ads request about the winning ad, ready to edit',
    moreHref.searchParams.get('kind') === 'creative' && /N1 - One simple system/.test(moreHref.searchParams.get('ask')) && /QA problem hook vs result hook/.test(moreHref.searchParams.get('ask')));
  await page.goto(moreHref.href);
  await page.waitForFunction(() => /N1 - One simple system/.test(document.getElementById('prompt')?.value || ''));
  check("Claude's box holds that request, not yet sent", /Write three new ads like/.test(await page.inputValue('#prompt')));
  await page.goto(BASE + `/experiments.html#${(await getJson('/api/experiments')).items[0].id}`);
  await page.waitForSelector('.test.flash [data-reopen]');
  await page.click('.test [data-reopen]');
  await page.waitForFunction(() => document.querySelector('[data-n="running"]')?.textContent === '1');
  check('Reopen puts it back to running without a winner', await page.evaluate(async () => (await (await fetch('/api/experiments')).json()).items[0].winner === null));
  check('each arm names its ad with a link to it', (await page.locator('.test .arm-names a.ent-link[href^="/ad.html?id="]').count()) === 2);
  await page.goto(BASE + '/ad.html?id=120252672229040312');
  await page.waitForSelector('#cr-main .facts');
  const testLink = page.locator('#cr-main .facts a.ent-link[href^="/experiments.html#"]');
  check("an ad's page links the tests it is in", (await testLink.count()) === 1 && /QA problem hook/.test(await testLink.textContent()));
  await Promise.all([page.waitForURL('**/experiments.html#*'), testLink.click()]);
  await page.waitForSelector('.test.flash');

  const propId = sh(`docker exec -w /app edgebourne-ads-backend python -c "
import db, json, desk_api
t = db.execute(\\"INSERT INTO desk_tasks (kind, prompt, status, summary) VALUES ('review', 'QA: suggest a test', 'done', 'One test to run') RETURNING id\\", returning=True)
p = desk_api.clean_proposal({'kind': 'experiment', 'title': 'Test the order portal against the weekly report', 'rationale': 'Both run to the same people; hook rate decides which story stops the scroll.',
  'payload': {'name': 'QA portal vs report', 'metric': 'hook', 'arms': [{'label': 'Portal', 'ad_ids': ['120252672229400312']}, {'label': 'Report', 'ad_ids': ['120252672232030312']}]}})
r = db.execute('INSERT INTO desk_proposals (task_id, kind, title, rationale, payload) VALUES (%s, %s, %s, %s, %s) RETURNING id', (t['id'], p['kind'], p['title'], p['rationale'], json.dumps(p['payload'])), returning=True)
print(r['id'])"`).trim();
  await page.goto(BASE + '/desk.html', { waitUntil: 'networkidle' });
  const sugg = page.locator(`#p-${propId}`);
  await sugg.waitFor();
  check('Claude can suggest a test: its arms and number show on the suggestion',
    /Portal.*N2 - Order portal.*Report.*N4 - Weekly report.*Hook rate/s.test(await sugg.textContent()) && /Tracks “QA portal vs report” on the Tests page/.test(await sugg.textContent()));
  await sugg.locator('[data-accept]').click();
  await page.waitForSelector('dialog.accept-sheet #cd-ok:not(:empty)');
  await page.click('dialog.accept-sheet #cd-ok');
  await page.waitForSelector('dialog.accept-sheet .sheet-result a');
  await Promise.all([page.waitForURL('**/experiments.html#*'), page.click('dialog.accept-sheet .sheet-result a')]);
  await page.waitForSelector('.test.flash');
  check('approving it starts tracking the test and opens it', /QA portal vs report/.test(await page.textContent('.test.flash')) && /suggested by Claude/.test(await page.textContent('.test.flash')));
  check('the suggestion is marked done', sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(db.query('SELECT status FROM desk_proposals WHERE id = ${propId}', one=True)['status'])"`).trim() === 'applied');
  await page.screenshot({ path: `${OUT}/flow-tests.png`, fullPage: true });
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute('DELETE FROM experiments')"`);

  // Meta A/B tests: off by default; once allowed in Settings, a test runs on Meta after its cost is confirmed.
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db,settings_store;db.execute('DELETE FROM experiments');settings_store.set('meta_ab_tests',None)"`);
  const fakeStudies = () => JSON.parse(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/fake/_studies').read().decode())"`));
  const studiesBefore = Object.keys(fakeStudies()).length;
  const mtId = await page.evaluate(async () => (await (await fetch('/api/experiments', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'QA on Meta', metric: 'cpl', start_day: new Date(Date.now() - 6 * 864e5).toISOString().slice(0, 10),
      arms: [{ label: 'A', ad_ids: ['120252672229040312'] }, { label: 'B', ad_ids: ['120252672230740312'] }] }) })).json()).id);
  await page.goto(BASE + '/experiments.html');
  await page.waitForSelector('.test');
  check('Meta A/B tests start switched off', /Run on Meta: off in Settings/.test(await page.textContent('.test')) && await page.locator('[data-meta]').count() === 0);
  const offSeen = errors.length;
  const refused = await page.evaluate(async (id) => (await fetch(`/api/experiments/${id}/meta`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start_day: '2030-01-02', end_day: '2030-01-09', daily_budget_cents: 1000, confirm_total_cents: 7000 }) })).status, mtId);
  errors.splice(offSeen);
  check('while off, the server refuses to create one', refused === 403 && Object.keys(fakeStudies()).length === studiesBefore);
  await openSettings('ab');
  await page.waitForSelector('#mt-state .pill');
  await page.check('#mt-on');
  await page.click('#mt-form button[type=submit]');
  await page.waitForSelector('dialog.confirm');
  check('turning them on asks first', /Allow A\/B tests on Meta/.test(await page.textContent('dialog.confirm')));
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => /On/.test(document.getElementById('mt-state').textContent));
  await page.goto(BASE + '/experiments.html');
  await page.click('.test [data-meta]');
  await page.waitForSelector('dialog.test-dialog #m-budget');
  const metaSeen = errors.length;
  await page.fill('#m-budget', '500');
  await page.waitForFunction(() => /twice the campaign's daily budget/.test(document.getElementById('m-plan').textContent));
  check('a test budget over twice the campaign budget is refused before anything is sent', await page.isDisabled('#m-go'));
  errors.splice(metaSeen); // the refused plan logs an expected 400
  await page.fill('#m-budget', '10');
  await page.waitForFunction(() => !document.getElementById('m-go').disabled);
  check('the dialog says what it does and what it costs', /up to \$70\.00 in total/.test(await page.textContent('#m-plan')) && /up to \$70/.test(await page.textContent('#m-go')));
  await page.click('#m-go');
  await page.waitForSelector('.test .on-meta');
  const studies = Object.values(fakeStudies()).slice(studiesBefore);
  check('Meta gets one ad-against-ad test with the budget in cents, starting tomorrow at the earliest',
    studies.length === 1 && studies[0].type === 'SPLIT_TEST_V2' && studies[0].cells.map((c) => c.ads[0]).join() === '120252672229040312,120252672230740312'
    && studies[0].start_time > Date.now() / 1000, JSON.stringify(studies[0] && studies[0].cells));
  check('the test shows it is booked on Meta', /Starts .*A\/B test on Meta.*test budget \$10\.00 a day, up to \$70/s.test(await page.textContent('.test .on-meta')));
  await page.click('.test [data-meta-refresh]');
  await page.waitForFunction(() => /high performer/.test(document.querySelector('.test .on-meta')?.textContent || ''));
  check("Meta's own result reads back in the arms' names", /Meta marks B as the high performer \(A 10%, B 90%\)/.test(await page.textContent('.test .on-meta')));
  check('a booked test cannot change its arms', await page.evaluate(async (id) => (await fetch(`/api/experiments/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ arms: [{ label: 'A', ad_ids: ['120252672229400312'] }, { label: 'B', ad_ids: ['120252672230740312'] }] }) })).status, mtId) === 409);
  errors.splice(metaSeen); // that refusal logs an expected 409
  sh(`docker exec -w /app edgebourne-ads-backend python -c "
import db, json, time
r = db.query('SELECT meta_study FROM experiments WHERE id = ${mtId}', one=True)['meta_study']
r['start_time'] = int(time.time()) - 3600
db.execute('UPDATE experiments SET meta_study = %s WHERE id = ${mtId}', (json.dumps(r),))"`);
  await page.reload();
  await page.waitForSelector('.test [data-meta-end]');
  await page.click('.test [data-meta-end]');
  await page.waitForSelector('dialog.confirm');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => /Ended early/.test(document.querySelector('.test .on-meta')?.textContent || ''));
  const ended = Object.values(fakeStudies()).slice(studiesBefore)[0];
  check('ending it early moves its end on Meta to now, deleting nothing', ended && ended.end_time <= Date.now() / 1000 + 120 && Object.keys(fakeStudies()).length === studiesBefore + 1);
  check('both writes are in the change log', sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(db.query(\\"SELECT string_agg(action, ',' ORDER BY id) AS a FROM meta_changes WHERE level = 'study' AND ok AND created_at > now() - interval '5 minutes'\\", one=True)['a'])"`).trim().endsWith('create,end'));
  await page.screenshot({ path: `${OUT}/flow-meta-test.png`, fullPage: true });

  // A booking Meta didn't answer (or one a restart cut off) is looked for on Meta, never booked twice blind.
  const lostId = await page.evaluate(async () => (await (await fetch('/api/experiments', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'QA lost booking', metric: 'cpl', start_day: new Date(Date.now() - 6 * 864e5).toISOString().slice(0, 10),
      arms: [{ label: 'A', ad_ids: ['120252672229040312'] }, { label: 'B', ad_ids: ['120252672230740312'] }] }) })).json()).id);
  const seedBooking = (study) => sh(`docker exec -w /app edgebourne-ads-backend python -c "import db,base64;db.execute('UPDATE experiments SET meta_study = %s WHERE id = ${lostId}', (base64.b64decode('${Buffer.from(JSON.stringify(study)).toString('base64')}').decode(),))"`);
  const lostStudy = () => JSON.parse(sh(`docker exec -w /app edgebourne-ads-backend python -c "import db,json;print(json.dumps(db.query('SELECT meta_study FROM experiments WHERE id = ${lostId}', one=True)['meta_study']))"`).trim());
  seedBooking({ creating: true, unknown: true, name: 'QA lost booking (nowhere on Meta)', at: new Date().toISOString(), start_day: '2030-01-02', end_day: '2030-01-09' });
  await page.reload();
  const lostCard = page.locator('.test', { hasText: 'QA lost booking' });
  await lostCard.locator('[data-meta-find]').waitFor();
  const lostSeen = errors.length;
  const rebook = await page.evaluate(async (id) => (await fetch(`/api/experiments/${id}/meta`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start_day: '2030-01-02', end_day: '2030-01-09', daily_budget_cents: 1000, confirm_total_cents: 7000 }) })).status, lostId);
  errors.splice(lostSeen); // the refusal logs an expected 409
  check('a test Meta may have booked says so and cannot be booked again', /May be on Meta/.test(await lostCard.locator('.pill.warn').textContent())
    && rebook === 409 && Object.keys(fakeStudies()).length === studiesBefore + 1);
  await lostCard.locator('[data-meta-find]').click();
  await page.waitForFunction(() => [...document.querySelectorAll('.test')].some((el) => /QA lost booking/.test(el.textContent) && !el.querySelector('[data-meta-find]')));
  check('looking finds nothing on Meta, so the test is free to book again', lostStudy() === null);
  // The booked test's own booking, as a claim a restart left behind twenty minutes ago (no answer recorded).
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db,json,datetime as d;r=db.query('SELECT meta_study FROM experiments WHERE id = ${mtId}', one=True)['meta_study'];r={k:v for k,v in r.items() if k not in ('id','results','created_at','ended_early_at','fetched_at')};r.update(creating=True,at=(d.datetime.now(d.timezone.utc)-d.timedelta(minutes=20)).isoformat());db.execute('UPDATE experiments SET meta_study = %s WHERE id = ${lostId}', (json.dumps(r),))"`);
  await page.reload();
  await lostCard.locator('[data-meta-find]').waitFor();
  check('a booking a restart left behind turns into "may be on Meta" after ten minutes', /May be on Meta/.test(await lostCard.textContent()));
  await lostCard.locator('[data-meta-find]').click();
  await page.waitForFunction(() => [...document.querySelectorAll('.test')].some((el) => /QA lost booking/.test(el.textContent) && !el.querySelector('[data-meta-find]')));
  const adopted = lostStudy();
  check('looking finds it on Meta by its exact name and links it', adopted && adopted.id === Object.keys(fakeStudies())[studiesBefore] && !adopted.creating,
    JSON.stringify(adopted));
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db,settings_store;db.execute('DELETE FROM experiments');settings_store.set('meta_ab_tests',None)"`);

  // Lead forms: build one with a live check and phone preview, create it on the Page, use it in a new ad.
  const fake = (p) => JSON.parse(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/fake/${p}').read().decode())"`));
  await page.goto(BASE + '/ads.html');
  await Promise.all([page.waitForURL('**/forms.html'), page.click('.subnav a[href="/forms.html"]')]);
  await page.waitForSelector('#list table');
  check('Lead forms lists the Page forms with their leads', /EB \| Free AI workflow review/.test(await page.textContent('#list')));
  // 9.4b: each form's leads (as stored here) link to Leads narrowed to that form; Meta's own count beside them.
  const formLeads = page.locator('[data-form-row="1132280359202136"] a.form-leads');
  const formHref = await formLeads.getAttribute('href');
  const formLeadsShown = Number((await formLeads.textContent()).replace(/\D/g, ''));
  const formApi = await page.evaluate(async () => (await (await fetch('/api/leads?form=1132280359202136&status=all')).json()));
  check('a form names its leads and links to Leads narrowed to that form, on every stage', formHref === '/leads.html?form=1132280359202136&status=all'
    && formLeadsShown === formApi.leads.length && formApi.leads.length > 0 && formApi.narrowed && formApi.narrowed.kind === 'form', `${formHref} ${formLeadsShown} ${formApi.leads.length}`);
  await Promise.all([page.waitForURL('**/leads.html?form=**'), formLeads.click()]);
  await page.waitForFunction(() => /^Lead form: /.test(document.querySelector('#source')?.selectedOptions[0]?.text || ''));
  check('Leads opened from a form says which form and offers Clear filters', await page.isVisible('#clear-filters'));
  await page.waitForFunction(() => document.querySelector('#filters [data-f="all"][aria-pressed="true"]'));
  const formOpened = await page.evaluate(() => ({ rows: document.querySelectorAll('#list .lead-row').length,
    all: Number(document.querySelector('#filters [data-f="all"] .n').textContent), open: Number(document.querySelector('#filters [data-f="open"] .n').textContent) }));
  check("the form's lead number is what the opened Leads page lists, and its stage counts are that form's", formOpened.rows === formLeadsShown && formOpened.all === formLeadsShown
    && formOpened.open <= formLeadsShown, `${formLeadsShown} ${JSON.stringify(formOpened)}`);
  await page.selectOption('#source', '');
  await page.waitForFunction(() => !/form=/.test(location.search));
  await page.click('#clear-filters');
  await page.waitForFunction(() => !/status=/.test(location.search) && document.querySelector('#filters [data-f="open"][aria-pressed="true"]'));
  check('picking "All campaigns and ads" drops the form', !/form=/.test(page.url()));
  await page.goto(BASE + '/forms.html');
  await page.waitForSelector('#list table');
  await page.click('#new-form');
  await page.waitForSelector('#form-edit');
  await page.fill('#f-name', 'QA intro call form');
  await page.fill('#f-intro', 'Get a free 20-minute intro call');
  await page.fill('#f-bullets', 'We look at how you work today\nYou leave with one thing to fix first');
  check('the phone preview shows the intro as it is typed', /Get a free 20-minute intro call/.test(await page.textContent('#phone')) && /one thing to fix first/.test(await page.textContent('#phone')));
  await page.click('#q-add');
  await page.fill('#q-label-0', 'What is your yearly income?');
  await page.fill('#q-opts-0', 'Under 50k\nOver 50k');
  await page.waitForFunction(() => /Meta would stop ads/.test(document.getElementById('f-check').textContent));
  await page.waitForSelector('#q-label-0[aria-invalid="true"]');
  const qErr = await page.evaluate(() => { const i = document.getElementById('q-label-0'); return i.getAttribute('aria-describedby').split(' ').map((id) => document.getElementById(id)?.textContent || '').join(' '); });
  check('a prohibited question is caught before creating, with the reason, at the question itself', /financial details/.test(await page.textContent('#f-check')) && /financial details/.test(qErr), qErr);
  await page.fill('#f-name', '');
  await page.click('#f-create');
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'f-name');
  check('Create with problems sends nothing: every problem field is marked and the first gets the focus',
    (await page.locator('dialog.confirm[open]').count()) === 0 && (await page.getAttribute('#f-name', 'aria-invalid')) === 'true' && (await page.getAttribute('#q-label-0', 'aria-invalid')) === 'true');
  await page.fill('#f-name', 'QA intro call form');
  await page.fill('#q-label-0', 'How many people work at your company?');
  await page.fill('#q-opts-0', '1-5\n6-20\n21 or more');
  await page.check('#form-edit input[name="type"][value="intent"]');
  await page.waitForFunction(() => /Ready/.test(document.getElementById('f-check').textContent));
  check('fixed fields lose their marks', (await page.locator('#form-edit [aria-invalid="true"]').count()) === 0);
  check('a serious-leads form adds the review step to the preview', await page.locator('#steps [data-show-step="review"]').count() === 1);
  await page.click('#steps [data-show-step="questions"]');
  check('the preview lists the prefilled fields and the answers to pick', /Contact information.*Maria Lopez.*How many people work at your company\?.*6-20/s.test(await page.textContent('#phone')));
  const formsBefore = Object.keys(fake('_forms')).length;
  await page.click('#f-create');
  await page.waitForSelector('dialog.confirm');
  check('creating says a form cannot change afterwards', /doesn't allow changes afterwards/.test(await page.textContent('dialog.confirm')));
  await page.click('dialog.confirm #cd-ok');
  await page.waitForSelector('#list tr.flash');
  const newForms = Object.values(fake('_forms')).slice(formsBefore);
  check('Meta gets the form: prefilled fields, the question with its answers, the review step, the privacy page',
    newForms.length === 1 && newForms[0].questions.map((q) => q.type).join() === 'FULL_NAME,EMAIL,PHONE,CUSTOM'
    && newForms[0].questions[3].options.map((o) => o.value).join('|') === '1-5|6-20|21 or more'
    && newForms[0].is_optimized_for_quality === true && newForms[0].privacy_policy_url === 'https://edgebourne.com/privacy', JSON.stringify(newForms[0] && newForms[0].questions));
  const formSeen = errors.length;
  const sneaky = await page.evaluate(async () => { const r = await fetch('/api/forms', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'x', intro_title: 'y', custom: [{ label: 'Have you ever been arrested?', options: [] }] }) }); return [r.status, (await r.json()).policy.length]; });
  errors.splice(formSeen);
  check('the server refuses a prohibited question too', sneaky[0] === 400 && sneaky[1] === 1 && Object.keys(fake('_forms')).length === formsBefore + 1);
  await page.locator('[data-copy="1132280359202136"]').click();
  await page.waitForSelector('#form-edit');
  await page.fill('#f-name', 'QA typed name');
  await page.click('#form-edit [data-close]');
  await page.waitForSelector('dialog.confirm[open]');
  check('closing a form with typed work asks first', /Throw away this form/.test(await page.textContent('dialog.confirm')));
  await page.click('dialog.confirm #cd-cancel');
  await page.waitForSelector('dialog.confirm', { state: 'detached' }).catch(() => {});
  check('Keep editing leaves the typed work', (await page.inputValue('#f-name')) === 'QA typed name');
  await page.locator('[data-copy="1132280359202136"]').click();
  await page.waitForSelector('dialog.confirm[open]');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => document.getElementById('f-name')?.value !== 'QA typed name');
  check('Copy into a new form starts from the old one', (await page.inputValue('#f-intro')) === 'Free AI workflow review' && (await page.inputValue('#q-label-0')) === 'What kind of business do you run?'
    && (await page.inputValue('#f-name')) === 'EB | Free AI workflow review (copy)');
  await page.goto(BASE + `/new-ad.html?form=${newForms[0].id}`);
  await page.waitForSelector('#form-pick:not([hidden])');
  check('New ad can use the new form', (await page.inputValue('#form')) === newForms[0].id);
  const creativesBefore = Object.keys(fake('_creatives')).length;
  const adMade = await page.evaluate(async (formId) => (await (await fetch('/api/ads/new', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ adset_id: '120252672227950312', template_ad_id: '120252672229040312', name: 'QA form ad', body: 'B', title: 'T', media: { kind: 'same' }, form_id: formId }) })).json()).id, newForms[0].id);
  const cr = Object.values(fake('_creatives')).slice(creativesBefore)[0];
  check("a new ad's button opens the chosen form", !!adMade && cr && cr.object_story_spec.video_data.call_to_action.value.lead_gen_form_id === newForms[0].id, JSON.stringify(cr && cr.object_story_spec.video_data.call_to_action));

  // New ad set: starts from the live one, places and ages change, the estimate follows, created paused.
  await page.goto(BASE + '/ads.html?level=campaign');
  await Promise.all([page.waitForURL('**/new-adset.html?campaign=**'), page.locator('.campaign-add').first().click()]);
  await page.waitForSelector('#pl-list li b');
  check('New ad set opened from the Campaigns list has Cancel back to that list', /^\/ads\.html\?.*level=campaign/.test(await page.getAttribute('#cancel', 'href')), await page.getAttribute('#cancel', 'href'));
  check('a new ad set starts from the live one: its places, ages and hints',
    (await page.locator('#pl-list li').count()) === 4 && /San Diego area/.test(await page.textContent('#pl-list'))
    && (await page.inputValue('#age_min')) === '25' && (await page.inputValue('#suggest_min')) === '30' && await page.isChecked('#keep_hints'));
  check('a campaign with its own budget asks for none on the ad set', await page.isHidden('#budget-field') && /shared by all its ad sets/.test(await page.textContent('#budget-note')));
  await page.waitForFunction(() => /M/.test(document.getElementById('estimate').textContent));
  check('the audience estimate shows', /1\.4M – 1\.6M/.test(await page.textContent('#estimate')), await page.textContent('#estimate'));
  for (let i = 0; i < 4; i++) await page.locator('#pl-list [data-remove]').first().click();
  await page.fill('#pl-q', 'fon');
  await page.waitForSelector('#pl-results li[data-pick]');
  await page.keyboard.press('Enter');
  check("a place is found with Meta's place search and added with a radius", /Fontana, California/.test(await page.textContent('#pl-list')) && (await page.inputValue('#pl-list select')) === '25');
  await page.selectOption('#pl-list select', '15');
  await page.fill('#name', 'QA Inland Empire');
  await page.fill('#age_min', '30');
  const asSeen = errors.length;
  const asetsAsked = Object.keys(fake('_adsets')).length;
  await page.click('#create');
  await page.waitForSelector('#as-form .field.error .err');
  check('Advantage+ audience refuses a minimum age over 25, saying why, before any confirmation and before Meta', /at most 25/.test(await page.textContent('#as-form .field.error'))
    && (await page.locator('dialog.confirm').count()) === 0 && Object.keys(fake('_adsets')).length === asetsAsked && (await page.getAttribute('#age_min', 'aria-invalid')) === 'true');
  check('its step says what to fix', (await page.getAttribute('#stepper li:nth-child(2)', 'data-state')) === 'fix' && /at most 25/.test(await page.textContent('#stepper li:nth-child(2)')));
  errors.splice(asSeen);
  await page.fill('#age_min', '25');
  const adsetsBefore = Object.keys(fake('_adsets')).length;
  await page.click('#create');
  await page.waitForSelector('dialog.confirm');
  check('creating says it is off and empty', /switched off and with no ads yet/.test(await page.textContent('dialog.confirm')));
  await Promise.all([page.waitForURL('**/new-ad.html?adset=**'), page.click('dialog.confirm #cd-ok')]);
  const newSets = Object.values(fake('_adsets')).slice(adsetsBefore);
  check('Meta gets a paused ad set: the city with its radius, the ages, the hints, no budget of its own',
    newSets.length === 1 && newSets[0].status === 'PAUSED' && newSets[0].targeting.geo_locations.cities.map((c) => `${c.key}:${c.radius}:${c.distance_unit}`).join() === '2420886:15:mile'
    && newSets[0].targeting.age_range.join() === '30,64' && newSets[0].targeting.flexible_spec[0].behaviors.length === 2 && newSets[0].destination_type === 'ON_AD',
    JSON.stringify(newSets[0] && newSets[0].targeting));
  await page.waitForFunction(() => document.querySelectorAll('#aset-pick option').length > 0);
  check('the next step is adding an ad to the new ad set', (await page.inputValue('#aset-pick')) === newSets[0].id);
  check('that page says the ad set was made, links to it, and Cancel still goes back to the list',
    (await page.getAttribute('#made-note a.ent-link', 'href')) === `/adset.html?id=${newSets[0].id}` && /^\/ads\.html\?.*level=campaign/.test(await page.getAttribute('#cancel', 'href')));
  // 9.4b: the new, empty ad set says who it reaches without learning data, and offers its first ad.
  {
    const p2 = await page.context().newPage();
    await p2.goto(BASE + `/adset.html?id=${newSets[0].id}`);
    await p2.waitForSelector('#who-sees');
    const emptyNew = await p2.getAttribute('#empty-new', 'href').catch(() => null);
    check('an ad set with no ads offers New ad in its empty state', (emptyNew || '').startsWith(`/new-ad.html?adset=${newSets[0].id}`), emptyNew);
    check('who sees it shows even before Meta reports learning', /Who sees it/.test(await p2.textContent('#who-sees')) && (await p2.locator('#who-sees .learn').count()) === 0,
      await p2.textContent('#who-sees'));
    check('an ad set page links to its leads', (await p2.getAttribute('#en-leads', 'href')) === `/leads.html?adset=${newSets[0].id}`);
    await p2.close();
  }
  await page.reload();
  await page.waitForFunction(() => document.querySelectorAll('#aset-pick option').length > 0);
  check('the "just created" note is said once: a reload keeps the ad set but drops the note', !/[?&]made=/.test(page.url())
    && (await page.locator('#made-note').count()) === 0 && (await page.inputValue('#aset-pick')) === newSets[0].id, page.url());

  // New campaign: one form for campaign, ad set, form and ads; created off; resumes after a refusal; publish needs the budget typed.
  await page.goto(BASE + '/ads.html');
  await page.waitForSelector('#new-menu:not([hidden]) summary');
  check('Ads has one primary New button (admins pick what to make from it)', (await page.locator('.page-head .btn-primary:visible').count()) === 1
    && /btn-primary/.test(await page.getAttribute('#new-menu summary', 'class')) && await page.isHidden('#new-ad'));
  await page.click('#new-menu summary');
  await Promise.all([page.waitForURL('**/new-campaign.html?from=**'), page.click('#campaign-link')]);
  check('New campaign opened from Ads has Cancel back to Ads', /^\/ads\.html/.test(await page.getAttribute('#cancel', 'href')), await page.getAttribute('#cancel', 'href'));
  await page.waitForSelector('#nc-list li b');
  await page.waitForFunction(() => /to finish first/.test(document.getElementById('ready').textContent));
  check('the wizard lists what is still missing, by step', /Goal.*Give the campaign a name.*Budget/s.test(await page.textContent('#stepper'))
    && (await page.locator('#stepper li[data-state="todo"]').count()) >= 3);
  let lastCheck = null;
  const keepCheck = (r) => { if (/\/api\/builds\/check$/.test(r.url())) lastCheck = r.postData(); };
  page.on('request', keepCheck);
  await page.fill('#c-name', 'QA Payroll - Leads');
  await page.fill('#c-budget', '90');
  await page.fill('#s-name', 'QA SoCal - Instant form');
  await page.fill('#a-name-0', 'QA N6 - Payroll');
  await page.fill('#a-title-0', 'Payroll in one click');
  await page.waitForFunction(() => /more than 3 times what runs now/.test(document.getElementById('review').textContent));
  page.off('request', keepCheck);
  const hugeBuildSeen = errors.length;
  const hugeBuild = await page.evaluate(async (b) => { const r = await fetch('/api/builds', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: b }); return { status: r.status, body: await r.json() }; }, lastCheck);
  await page.waitForTimeout(300);
  errors.splice(hugeBuildSeen); // the refusal logs an expected 400
  await page.click('#nc-create');
  await page.waitForSelector('#nc-form .field.error .err');
  const ncMarked = await page.$$eval('#nc-form [aria-invalid="true"]', (els) => els.map((e) => e.name));
  check('Create with problems marks each field (the budget, the form) and opens no confirmation', ncMarked[0] === 'budget'
    && (await page.locator('dialog.confirm').count()) === 0 && (await page.evaluate(() => document.activeElement.name)) === 'budget', ncMarked.join());
  check('a budget far above what runs now is refused (the check and the server)', /more than 3 times/.test(await page.textContent('[data-step="budget"]')) && hugeBuild.status === 400
    && (hugeBuild.body.problems || []).some((p) => p.step === 'budget' && /more than 3 times/.test(p.message)), `${hugeBuild.status} ${JSON.stringify(hugeBuild.body.problems)}`);
  await page.fill('#c-budget', '15');
  await page.click('#cr-add');
  await page.selectOption('#a-tpl-1', '120252672230740312');
  check('a second ad starts from the words of the ad it copies', /typing the same thing twice/i.test(await page.inputValue('#a-title-1')) || (await page.inputValue('#a-body-1')).length > 20);
  await page.fill('#a-name-1', 'QA N7 - Retyping');
  await page.selectOption('#f-form', '1132280359202136');
  await page.waitForFunction(() => /Ready to create/.test(document.getElementById('review').textContent));
  check('the review reads in dollars: the campaign, the ad set, the form, each ad',
    /\$15\.00 a day \(about \$456\.00 a month\).*San Diego area.*EB \| Free AI workflow review.*QA N6 - Payroll.*QA N7 - Retyping/s.test(await page.textContent('#review')));
  sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;urllib.request.urlopen('http://localhost:5001/fake/_refuse_next_ad')"`);
  const campsBefore = Object.keys(fake('_campaigns')).length;
  const ncSeen = errors.length;
  await page.click('#nc-create');
  await page.waitForSelector('dialog.confirm');
  check('creating says everything starts switched off', /All switched off: nothing spends until you publish/.test(await page.textContent('dialog.confirm')));
  await page.click('dialog.confirm #cd-ok');
  await page.waitForSelector('#resume');
  errors.splice(ncSeen); // Meta's refusal is logged by the server, not the page; keep the check honest anyway
  check('when Meta refuses an ad halfway, what was made stays off and the page says what stopped', /Meta refused ad 1/.test(await page.textContent('#build'))
    && Object.keys(fake('_campaigns')).length === campsBefore + 1 && Object.values(fake('_campaigns')).slice(-1)[0].status === 'PAUSED');
  await page.click('#resume');
  await page.waitForSelector('#pub-form');
  const builtCamps = Object.values(fake('_campaigns')).slice(campsBefore);
  const builtSets = Object.values(fake('_adsets')).filter((s) => s.campaign_id === builtCamps[0].id);
  check('finishing makes only what was missing: one campaign, one ad set, two ads, all off',
    builtCamps.length === 1 && builtSets.length === 1 && (await page.locator('.build-table tbody tr').count()) === 4
    && builtCamps[0].daily_budget === '1500' && builtSets[0].status === 'PAUSED' && !builtSets[0].daily_budget);
  check('each new ad links to its preview', (await page.locator('.build-table a[href^="/ad.html"]').count()) === 2);
  await page.fill('#pub-typed', '20');
  await page.click('#pub-form button[type=submit]');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForSelector('#pub-form .field.error .err');
  check('publishing needs the exact daily budget typed', /Type the daily budget, \$15\.00/.test(await page.textContent('#pub-form')) && Object.values(fake('_campaigns')).slice(-1)[0].status === 'PAUSED');
  errors.splice(ncSeen);
  await page.fill('#pub-typed', '15');
  await page.click('#pub-form button[type=submit]');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => /Published/.test(document.getElementById('build').textContent));
  check('a published campaign links to what was made: the campaign, its ad set and each ad',
    (await page.locator('#build .note.ok a.ent-link[href^="/campaign.html?id="]').count()) === 1 && (await page.locator('.build-table a.ent-link[href^="/campaign.html?id="]').count()) === 1
    && (await page.locator('.build-table a.ent-link[href^="/adset.html?id="]').count()) === 1);
  const order = sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(','.join(r['level'] for r in db.query(\\"SELECT level FROM meta_changes WHERE action = 'status' AND new_value = 'ACTIVE' ORDER BY id DESC LIMIT 4\\")[::-1]))"`).trim();
  check('publishing turns on the ads, then the ad set, then the campaign last', order === 'ad,ad,adset,campaign' && Object.values(fake('_campaigns')).slice(-1)[0].status === 'ACTIVE', order);
  await page.screenshot({ path: `${OUT}/flow-new-campaign.png`, fullPage: true });

  // 9.4e: New campaign has the same uploader, so an ad with nothing to start from gets its own picture here
  // (a new account no longer has to go to New ad first, which needs an ad set it doesn't have yet).
  await page.goto(BASE + '/new-campaign.html');
  await page.waitForSelector('#a-tpl-0 option', { state: 'attached' });
  await page.selectOption('#a-tpl-0', '');
  await page.waitForFunction(() => document.getElementById('a-media-0').value === '');
  // Someone types the words while the file goes up: the upload landing must not move the caret.
  await page.fill('#a-body-0', 'Typing while it uploads');
  await page.evaluate(() => { const t = document.getElementById('a-body-0'); t.focus(); t.setSelectionRange(6, 6); });
  await page.setInputFiles('#nc-file', { name: 'qa-campaign.png', mimeType: 'image/png', buffer: Buffer.alloc(30 * 1024, 5) });
  await page.waitForFunction(() => /^image:/.test(document.getElementById('a-media-0').value));
  check('New campaign uploads a picture and puts it on the ad that had none', /qa-campaign\.png/.test(await page.textContent('#a-media-0 option:checked')));
  const caret = await page.evaluate(() => ({ id: document.activeElement?.id, at: document.activeElement?.selectionStart, value: document.getElementById('a-body-0').value }));
  check('an upload landing leaves the words being typed and the caret where they were', caret.id === 'a-body-0' && caret.at === 6 && caret.value === 'Typing while it uploads', JSON.stringify(caret));
  await page.fill('#c-name', 'QA never made');
  await page.waitForFunction(() => /Goal/.test(document.querySelector('#stepper li[data-state="done"]')?.textContent || ''));
  check('a filled-in step is ticked with what it holds', /QA never made/.test(await page.textContent('#stepper li:nth-child(1)')));

  // A build whose campaign create Meta didn't answer: Finish creating adopts the campaign Meta made, never a second one.
  const lostBuild = sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(db.execute(\\"INSERT INTO campaign_builds (spec, made, status, created_by, account_id) SELECT spec || jsonb_build_object('name', 'QA lost campaign'), jsonb_build_object('unknown', 'campaign', 'ads', '{}'::jsonb), 'partial', created_by, account_id FROM campaign_builds ORDER BY id DESC LIMIT 1 RETURNING id\\", returning=True)['id'])"`).trim();
  const lostCamp = JSON.parse(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen(urllib.request.Request('http://localhost:5001/v24.0/act_1025971549903293/campaigns?access_token=x', data=b'name=QA+lost+campaign&status=PAUSED&objective=OUTCOME_LEADS&daily_budget=1500')).read().decode())"`)).id;
  const campsBeforeResume = Object.keys(fake('_campaigns')).length;
  const resumed = await page.evaluate(async (id) => (await (await fetch(`/api/builds/${id}/resume`, { method: 'POST' })).json()), lostBuild);
  const lostMade = JSON.parse(sh(`docker exec -w /app edgebourne-ads-backend python -c "import db,json;print(json.dumps(db.query('SELECT made FROM campaign_builds WHERE id = ${lostBuild}', one=True)['made']))"`).trim());
  check('finishing a build after Meta did not answer adopts the campaign Meta made instead of making a second one',
    lostMade.campaign_id === lostCamp && Object.keys(fake('_campaigns')).length === campsBeforeResume && !lostMade.unknown, `${lostCamp} ${JSON.stringify(lostMade)} ${JSON.stringify(resumed).slice(0, 200)}`);

  // Meta's automatic changes on an ad: read in plain words, warn on the rewriting ones, switch one with a new creative.
  await page.goto(BASE + '/ad.html?id=120252672230740312');
  await openFold('auto');
  await page.waitForSelector('.enh-list');
  check("the ad page lists Meta's automatic changes in plain words", /Image touch-ups.*Video filters.*Text improvements.*Relevant comments/s.test(await page.textContent('#enh')));
  check('features that change the words or pictures are flagged when on', /On, and they change your words or pictures: Video filters/.test(await page.textContent('#enh')));
  const crBefore = Object.keys(fake('_creatives')).length;
  const statusBefore = await page.textContent('#cr-status');
  await page.click('[data-enh="video_filtering"]');
  await page.waitForSelector('dialog.confirm');
  check('switching one asks first and says Meta reviews the ad again', /reviews the ad again/.test(await page.textContent('dialog.confirm')));
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => !/Video filters\. For brand/.test(document.getElementById('enh').textContent) && document.querySelector('[data-enh="video_filtering"]')?.getAttribute('aria-checked') === 'false');
  const newCr = Object.values(fake('_creatives')).slice(crBefore);
  const spec = newCr[0] && newCr[0].degrees_of_freedom_spec.creative_features_spec;
  check('a new creative carries the change and keeps every other setting', newCr.length === 1 && spec.video_filtering.enroll_status === 'OPT_OUT'
    && spec.image_touchups.enroll_status === 'OPT_IN' && spec.text_optimizations.enroll_status === 'OPT_OUT', JSON.stringify(spec));
  check("the ad's on/off state is untouched", (await page.textContent('#cr-status')) === statusBefore);

  // Ideas: tags on the ad page, results by idea on Results, Claude's tag suggestion applied on approval.
  await page.goto(BASE + '/ad.html?id=120252672232030312');
  await openFold('idea');
  await page.waitForSelector('#idea .idea-row');
  check('an ad shows its idea tags, hook first', (await page.inputValue('#tag-hook')) === 'Question'
    && (await page.locator('#idea .idea-row label').first().textContent()) === 'Hook' && (await page.inputValue('#tag-persona')) === 'Ops and office managers');
  await page.fill('#tag-angle', '  reports that build themselves  ');
  await page.fill('#tag-offer', '');
  await page.click('#idea button[type=submit]');
  await page.waitForFunction(() => document.getElementById('tag-angle')?.value === 'Reports that build themselves');
  check('saving tidies the words and an empty box removes the tag', (await page.inputValue('#tag-offer')) === ''
    && await page.evaluate(async () => !('offer' in (await (await fetch('/api/ads/ad/120252672232030312/tags')).json()).tags)));
  await page.fill('#tag-offer', 'Free intro call');
  await page.click('#idea button[type=submit]');
  await page.waitForFunction(() => document.getElementById('tag-offer')?.value === 'Free intro call');
  // 9.5 Creative › Ideas: the groups with their pictures, the same verdict rule, a way to the Gallery for each.
  await page.goto(BASE + '/ideas.html?range=30');
  await page.waitForSelector('.idea-grp');
  const hooks = await page.$$eval('.idea-grp .idea-name', (b) => b.map((x) => x.textContent));
  const outcome = page.locator('.idea-grp[data-idea-row="Outcome promise"]');
  check('Ideas groups ads by hook, with both outcome-promise ads in one group', hooks.includes('Outcome promise') && hooks.includes('Question')
    && /N2 - Order portal, N5 - Quote to invoice/.test(await outcome.textContent()), hooks.join(' | '));
  const ideaApi = await page.evaluate(async () => (await fetch('/api/concepts?by=hook&range=30')).json());
  const outGroup = ideaApi.groups.find((g) => g.value === 'Outcome promise');
  const pics = await outcome.locator('.idea-th img').evaluateAll((im) => im.map((i) => i.getAttribute('src')));
  check('each group shows the pictures of its ads, biggest spender first', pics.length === 2 && outGroup
    && pics.join() === [...outGroup.members].filter((m) => m.thumb).sort((a, b) => b.spend_cents - a.spend_cents).map((m) => m.thumb).join(), JSON.stringify(pics));
  check('the cheapest idea says how sure that is, and too-early groups are marked', /cheapest/i.test(await page.textContent('#ideas')) && /sure/.test(await page.textContent('#ideas .note'))
    && ideaApi.groups.filter((g) => !g.enough && g.value !== 'Not tagged').length === await page.locator('.idea-grp .pill:has-text("Too early")').count());
  const galHref = await outcome.locator('.idea-gal').getAttribute('href');
  check('a group links to the Gallery filtered on that idea, same dates', galHref === '/gallery.html?dim=hook&tag=Outcome+promise&range=30', galHref);
  await Promise.all([page.waitForURL('**/gallery.html?**'), outcome.locator('.idea-gal').click()]);
  await page.waitForSelector('.gal-card, #gal .empty');
  check('… and the Gallery opens on it', (await page.inputValue('#tag-pick')) === 'hook:Outcome promise' && (await page.inputValue('#range-pick')) === '30');
  await page.goto(BASE + '/ideas.html?range=30');
  await page.waitForSelector('.idea-grp');
  await page.click('#idea-by [data-idea="persona"]');
  await page.waitForFunction(() => /Ops and office managers/.test(document.getElementById('ideas').textContent));
  check('the grouping switches to who it is for, and the address keeps it', /Wholesale and distribution/.test(await page.textContent('#ideas')) && /by=persona/.test(page.url()));
  // Results keeps one line on the hooks with the way to Ideas; an older link to a tag on Results opens Ideas on it.
  await page.goto(BASE + '/performance.html?range=14');
  await page.waitForFunction(() => { const e = document.querySelector('#ideas-sum'); return e && e.querySelector('p') && !e.querySelector('.skeleton'); });
  check('Results says which hook is cheapest and links to Ideas on the same dates', /hook/.test(await page.textContent('#ideas-sum'))
    && (await page.getAttribute('#ideas-open', 'href')) === '/ideas.html?range=14' && (await page.locator('#ideas-panel table').count()) === 0);
  check('… and without a campaign picked it needs no note that it counts every campaign', (await page.locator('#ideas-all').count()) === 0);
  await page.goto(BASE + '/performance.html?campaign=120252638288040312&range=14');
  await page.waitForFunction(() => { const e = document.querySelector('#ideas-sum'); return e && e.querySelector('p') && !e.querySelector('.skeleton'); });
  check('with one campaign picked on Results, the hook line says it counts every campaign', (await page.inputValue('#campaign')) === '120252638288040312'
    && /Counts every campaign/.test(await page.textContent('#ideas-sum')), await page.textContent('#ideas-sum'));
  await page.goto(BASE + '/performance.html?campaign=');
  await page.goto(BASE + '/performance.html?idea=hook&tag=Question#ideas-panel');
  await page.waitForURL('**/ideas.html?**');
  await page.waitForSelector('.idea-grp.is-marked');
  check('an older Results link to a tag opens Ideas with that group marked', (await page.getAttribute('.idea-grp.is-marked', 'data-idea-row')) === 'Question', page.url());
  const tagProp = sh(`docker exec -w /app edgebourne-ads-backend python -c "
import db, json, desk_api
db.execute(\\"DELETE FROM ad_tags WHERE ad_id = '120252672233160312' AND dimension = 'hook'\\")
t = db.execute(\\"INSERT INTO desk_tasks (kind, prompt, status, summary) VALUES ('review', 'QA: tag the ads', 'done', 'Tags') RETURNING id\\", returning=True)
p = desk_api.clean_proposal({'kind': 'tags', 'title': 'Tag N5 - Quote to invoice', 'rationale': 'It promises an outcome in the first line.', 'payload': {'ad_id': '120252672233160312', 'tags': {'hook': 'outcome promise', 'bogus': 'x'}}})
r = db.execute('INSERT INTO desk_proposals (task_id, kind, title, rationale, payload) VALUES (%s, %s, %s, %s, %s) RETURNING id', (t['id'], p['kind'], p['title'], p['rationale'], json.dumps(p['payload'])), returning=True)
print(r['id'])"`).trim();
  await page.goto(BASE + '/desk.html', { waitUntil: 'networkidle' });
  const tp = page.locator(`#p-${tagProp}`);
  await tp.waitFor();
  check('Claude can suggest tags: the suggestion shows them', /Hook.*Outcome promise/s.test(await tp.textContent()) && !/bogus/.test(await tp.textContent()) && /Nothing changes on Meta/.test(await tp.textContent()));
  await tp.locator('[data-accept]').click();
  await page.waitForSelector('dialog.accept-sheet #cd-ok:not(:empty)');
  await page.click('dialog.accept-sheet #cd-ok');
  await page.waitForFunction(() => document.querySelector('dialog.accept-sheet #cd-ok')?.textContent === 'Done');
  await page.click('dialog.accept-sheet #cd-ok');
  await page.waitForFunction((id) => !document.getElementById(`p-${id}`), tagProp);
  check('approving applies them, marked as from Claude', sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;r=db.query(\\"SELECT value, source FROM ad_tags WHERE ad_id = '120252672233160312' AND dimension = 'hook'\\", one=True);print(r['value'], r['source'])"`).trim() === 'Outcome promise claude');

  // Swipe file: save a competitor ad, long runs flagged, watched Pages, Claude adds what it found.
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute('DELETE FROM swipes');db.execute('DELETE FROM watched_pages')"`);
  await page.goto(BASE + '/research.html');
  await page.waitForSelector('#swipes p');
  const parts = await page.$$eval('#rs-tabs [role="tab"]', (t) => t.map((x) => x.textContent.replace(/\s*\d+\s*$/, '').trim()));
  check('Research opens on the swipe file, in four parts: Swipe file, Search, Watched Pages, Past research', parts.join() === 'Swipe file,Search,Watched Pages,Past research'
    && await page.isVisible('#swipe-add') && await page.isHidden('#watch-form') && await page.isHidden('#ask-form'), parts.join());
  await page.click('#rs-tabs [data-part="watched"]');
  await page.waitForSelector('#watch-form', { state: 'visible' });
  check('a part is in the address', /#tab=watched$/.test(page.url()), page.url());
  await page.fill('#w-name', 'Acme Business Software');
  await page.fill('#w-terms', 'custom software Riverside');
  await page.click('#watch-form button[type=submit]');
  await page.waitForFunction(() => /Acme Business Software/.test(document.getElementById('watched').textContent));
  check('a competitor Page can be watched', /custom software Riverside · not checked yet/.test(await page.textContent('#watched'))
    && (await page.textContent('#n-watched')) === '1');
  await page.click('#rs-tabs [data-part="swipes"]');
  await page.click('#swipe-add');
  await page.fill('#sw-link', 'https://www.facebook.com/ads/library/?id=1234567890123');
  await page.fill('#sw-page', 'Acme Business Software');
  await page.fill('#sw-body', 'Still running your shop on spreadsheets? We build software around how you work.');
  const longAgo = await page.evaluate(() => new Date(Date.now() - 45 * 864e5).toISOString().slice(0, 10));
  await page.fill('#sw-start', longAgo);
  await page.click('#swipe-form button[type=submit]');
  await page.waitForSelector('.swipe');
  check('a saved ad shows how long it has run, and 30+ days reads as likely working', /Running 4[56] days: likely working/.test(await page.textContent('.swipe'))
    && (await page.getAttribute('.swipe a', 'href')) === 'https://www.facebook.com/ads/library/?id=1234567890123');
  await page.click('#swipe-add');
  await page.fill('#sw-link', '1234567890123');
  await page.fill('#sw-page', 'Acme Business Software');
  await page.click('#swipe-form button[type=submit]');
  await page.waitForTimeout(500);
  check('saving the same Library ad again updates it instead of adding a copy', (await page.locator('.swipe').count()) === 1);
  await page.fill('.swipe-note', 'Same promise as N1');
  await page.press('.swipe-note', 'Tab');
  await page.waitForTimeout(400);
  const ag = JSON.parse(sh('docker cp dev/qa_agent_swipes.py edgebourne-ads-backend:/app/qa_agent_swipes.py && docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python qa_agent_swipes.py; docker exec edgebourne-ads-backend rm -f /app/qa_agent_swipes.py').trim().split('\n').pop());
  check("Claude's side: the watched Pages, then new ads saved and a bad one skipped with the reason",
    ag.watched.join() === 'Acme Business Software' && ag.first.added === 2 && ag.first.skipped[0] === "Paste the Ad Library link, or the ad's text"
    && ag.again.added === 0 && ag.again.refreshed === 1 && ag.refused === 401, JSON.stringify(ag));
  await page.reload();
  await page.waitForSelector('.swipe');
  check('found ads show as from Claude, with their tags; a stopped one counts to the day it stopped',
    (await page.locator('.swipe').count()) === 3 && /Ran 97 days/.test(await page.textContent('#swipes')) && /Outcome promise/.test(await page.textContent('#swipes'))
    && /checked/.test(await page.evaluate(() => document.getElementById('watched').textContent)) && !/not checked yet/.test(await page.evaluate(() => document.getElementById('watched').textContent)));
  await page.click('#swipe-filter [data-sf="long"]');
  check('Running 30+ days shows only the long runs', (await page.locator('.swipe').count()) === 2);
  check('the note was kept', await page.evaluate(() => [...document.querySelectorAll('.swipe-note')].some((i) => i.value === 'Same promise as N1')));
  // Ask Claude to research: a double click while it sends starts one research run (audit A3-32).
  const researchCount = () => Number(sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(db.query(\\"SELECT COUNT(*) AS n FROM desk_tasks WHERE kind = 'research'\\", one=True)['n'])"`));
  const researchBefore = researchCount();
  await page.click('#rs-tabs [data-part="search"]');
  await page.fill('#prompt', 'QA: which offers repeat nearby?');
  await page.route('**/api/desk/tasks', async (route) => { await new Promise((r) => setTimeout(r, 900)); await route.continue(); });
  await page.dblclick('#ask-form button[type=submit]');
  await page.evaluate(() => document.getElementById('ask-form').requestSubmit());
  await page.waitForFunction(() => document.getElementById('prompt').value === '', null, { timeout: 10000 });
  await page.unroute('**/api/desk/tasks');
  check('a double click on Send to Claude starts one research run', researchCount() === researchBefore + 1, `${researchBefore} → ${researchCount()}`);
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute(\\"UPDATE desk_tasks SET status = 'cancelled' WHERE kind = 'research' AND status = 'queued' AND prompt = 'QA: which offers repeat nearby?'\\")"`);
  await page.click('#rs-tabs [data-part="past"]');
  await page.waitForFunction(() => /which offers repeat nearby/.test(document.getElementById('tasks').textContent));
  check('a research request shows under Past research', /#tab=past$/.test(page.url()));
  // 9.5 The loop: "Make something like this" on one saved ad, "Write a brief" on several → an editable draft → a Claude conversation.
  const creativeIds = () => sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(','.join(str(r['id']) for r in db.query(\\"SELECT id FROM desk_tasks WHERE kind = 'creative' ORDER BY id\\")))"`).trim().split(',').filter(Boolean);
  const creativeBefore = creativeIds();
  py(`import db
long = ' '.join(['Still running your shop on spreadsheets and retyping every order by hand?'] * 80)
db.execute(\\"UPDATE swipes SET body = %s WHERE library_id = '1234567890123'\\", (long,))`);
  await page.goto(BASE + '/research.html');
  await page.waitForSelector('.swipe [data-like]');
  const longCard = page.locator('.swipe:has(a[href$="?id=1234567890123"])');
  await longCard.locator('[data-like]').click();
  await page.waitForSelector('dialog.confirm.wide #cd-input');
  const likeDraft = await page.inputValue('#cd-input');
  check('Make something like this opens a draft with that ad, its note and its link, its long text trimmed to fit under 4,000 characters',
    /^Make a new ad for Edge Bourne like this competitor ad/.test(likeDraft) && /Acme Business Software · running 4[56] days, likely working/.test(likeDraft) && /Why we kept it: Same promise as N1/.test(likeDraft)
    && /ads\/library\/\?id=1234567890123/.test(likeDraft) && /Text: Still running.*…$/m.test(likeDraft) && likeDraft.length <= 3500
    && /of 4,000 characters/.test(await page.textContent('#cd-hint')) && (await page.evaluate(() => document.getElementById('cd-input').selectionEnd)) === 0, `${likeDraft.length} chars`);
  await page.fill('#cd-input', 'x'.repeat(4001));
  await page.click('#cd-ok');
  check('a draft over 4,000 characters is not sent and says why', /Keep it under 4,000 characters/.test(await page.textContent('#cd-err')) && await page.isVisible('dialog.confirm') && creativeIds().length === creativeBefore.length);
  await page.fill('#cd-input', likeDraft + '\nQA: keep it calm.');
  await Promise.all([page.waitForURL('**/desk.html#r/**'), page.click('#cd-ok')]);
  const likeId = page.url().split('#r/')[1];
  const likeTask = JSON.parse(py(`import db, json;r=db.query('SELECT kind, prompt, status FROM desk_tasks WHERE id = %s', (${Number(likeId)},), one=True);print(json.dumps(r))`));
  check('… Send to Claude starts a "creative" conversation with the edited words and opens it', likeTask.kind === 'creative' && likeTask.status === 'queued'
    && likeTask.prompt.endsWith('QA: keep it calm.') && /Acme Business Software/.test(likeTask.prompt), JSON.stringify({ id: likeId, kind: likeTask.kind }));
  await page.waitForSelector('.cv-you, #cv-col');
  // Several ticked: Write a brief from the tray, in page order; Cancel sends nothing; the tray caps at 10.
  await page.goto(BASE + '/research.html');
  await page.waitForSelector('.swipe [data-pick-swipe]');
  const swipeBoxes = page.locator('.swipe [data-pick-swipe]');
  await swipeBoxes.nth(1).check();
  await swipeBoxes.nth(0).check();
  await page.waitForSelector('#rs-tray [data-tray="brief"]');
  const swipePages = await page.$$eval('.swipe', (cs) => cs.slice(0, 2).map((c) => c.querySelector('header b').textContent));
  check('ticking saved ads shows the tray with Write a brief, and the page makes room for it', /2\s*selected/.test(await page.textContent('#rs-tray'))
    && await page.evaluate(() => document.body.classList.contains('has-bulk')));
  await page.click('#rs-tray [data-tray="brief"]');
  await page.waitForSelector('dialog.confirm.wide #cd-input');
  const briefText = await page.inputValue('#cd-input');
  const firstText = await page.locator('.swipe').nth(0).locator('.swipe-body, .swipe-title').first().textContent();
  check('Write a brief drafts from the picked ads in page order and asks for 3 concepts', /^Write a short creative brief for Edge Bourne from these 2 competitor ads/.test(briefText)
    && briefText.indexOf('1. ' + swipePages[0]) >= 0 && briefText.indexOf('2. ' + swipePages[1]) > briefText.indexOf('1. ' + swipePages[0]) && /3 genuinely different ad concepts/.test(briefText)
    && briefText.includes(firstText.trim().slice(0, 20)) && /Write a brief from 2 saved ads/.test(await page.textContent('dialog.confirm h2')), briefText.slice(0, 200));
  await page.click('#cd-cancel');
  await page.waitForSelector('dialog.confirm', { state: 'detached' });
  check('Cancel sends nothing and keeps the ticks', creativeIds().length === creativeBefore.length + 1 && (await page.locator('.swipe.is-picked').count()) === 2);
  const qaRivals = py(`import db
ids = []
for i in range(10):
    r = db.execute(\\"INSERT INTO swipes (page_name, body, source) VALUES (%s, %s, 'manual') RETURNING id\\", ('QA brief rival ' + str(i), 'Words ' + str(i)), returning=True)
    ids.append(str(r['id']))
print(','.join(ids))`).split(',');
  await page.reload();
  await page.waitForSelector('.swipe [data-pick-swipe]');
  const rivalBoxes = page.locator('.swipe [data-pick-swipe]');
  for (let i = 0; i < 11; i += 1) await rivalBoxes.nth(i).check();
  await page.waitForSelector('#rs-tray [data-tray="brief"][disabled]');
  check('more than 10 ticked: Write a brief waits and says why', /A brief takes 10 at most/.test(await page.textContent('#rs-tray')));
  await page.keyboard.press('Escape');
  check('Escape clears the ticks', (await page.locator('#rs-tray .bk').count()) === 0 && (await page.locator('.swipe.is-picked').count()) === 0);
  const seenErrs = errors.length;
  const otherAcct = await page.evaluate(async (id) => (await fetch(`/api/swipes/brief?ids=${id}`)).status, 999999999);
  await page.waitForTimeout(300);
  errors.splice(seenErrs);  // the refused request logs an expected 404
  check('a brief for a saved ad that is not in this account is refused', otherAcct === 404, String(otherAcct));
  py(`import db
db.execute('DELETE FROM swipes WHERE id = ANY(%s)', ([${qaRivals.map(Number).join(',')}],))
db.execute(\\"UPDATE desk_tasks SET status = 'cancelled' WHERE kind = 'creative' AND status = 'queued' AND id = %s\\", (${Number(likeId)},))`);
  await page.goto(BASE + '/desk.html#schedules');
  await page.waitForSelector('#view');
  await page.waitForTimeout(600);
  check('a weekly Competitor check schedule is offered, off', /Competitor check/.test(await page.textContent('#view')));

  // Meta's advice on Today: score, suggestions in plain words, apply one through the +20% warning, benchmarks from the Mac.
  sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;urllib.request.urlopen(urllib.request.Request('http://localhost:5001/v24.0/120252638288040312?access_token=x', data=b'daily_budget=2000'))"`);
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db,settings_store;settings_store.set('meta_advice',None);settings_store.set('meta_benchmarks',None);db.execute('UPDATE campaigns SET daily_budget_cents = 2000 WHERE id = %s', ('120252638288040312',))"`);
  ageBudget(); // earlier checks changed this budget today: the +20% warning is what this check is about, not the 3-day rule
  await page.goto(BASE + '/home.html');
  await page.waitForSelector('.advice-list');
  check("Today shows Meta's Opportunity Score and its suggestions, most points first",
    /87\/100/.test(await page.textContent('#advice')) && (await page.$$eval('.advice-list .ttl b', (b) => b.map((x) => x.textContent))).join('|') === "Spend more on a campaign that's doing well|Add a vertical 9:16 video for Reels");
  check('a suggestion that needs new media points to Ads Manager instead of an Apply button',
    (await page.locator('.advice-list li').nth(1).locator('[data-apply]').count()) === 0 && /Needs a 9:16 video with sound/.test(await page.textContent('.advice-list li:nth-child(2)')));
  check('a budget suggestion shows the step in dollars and flags more than +20%', /\$20\.00 → \$26\.00 a day \(\+30%\): more than \+20%/.test(await page.textContent('.advice-list li:first-child')));
  const budgetBefore = Object.values(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/v24.0/120252638288040312?access_token=x').read().decode())"`).match(/"daily_budget":"?(\d+)/).slice(1))[0];
  // Meta adds its amount to the live budget: a stored budget older than Meta's is refused, not applied (audit 3).
  sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;urllib.request.urlopen(urllib.request.Request('http://localhost:5001/v24.0/120252638288040312?access_token=x', data=b'daily_budget=2400'))"`);
  const adviceSig = await page.getAttribute('[data-apply]', 'data-apply');
  const advSeen = errors.length;
  const staleAdvice = await page.evaluate(async (sig) => { const r = await fetch('/api/advice/apply', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ signature: sig, accept_big: true, confirm_to: 2600 }) }); return { status: r.status, body: await r.json() }; }, adviceSig);
  const staleAdviceMeta = metaObj('120252638288040312').daily_budget; // read before the reset below: nothing may have been added
  sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;urllib.request.urlopen(urllib.request.Request('http://localhost:5001/v24.0/120252638288040312?access_token=x', data=b'daily_budget=2000'))"`);
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute('UPDATE campaigns SET daily_budget_cents = 2000 WHERE id = %s', ('120252638288040312',))"`);
  errors.splice(advSeen); // the refusal logs an expected 409
  ageBudget(); // the stale read above recorded Ads Manager's 2400 as a change just now
  check("Meta's budget advice is checked against the live budget, not the last sync's", staleAdvice.status === 409 && /24\.00 a day now/.test(staleAdvice.body.error)
    && staleAdviceMeta === '2400', `${staleAdviceMeta} ${JSON.stringify(staleAdvice.body)}`);
  // The 3-day rule on Meta's advice: a raise right after another change is refused without the knowing yes, and the
  // refusal sends the list back so the next Apply asks for it (Raise anyway, as a danger button).
  sh(`docker exec edgebourne-postgres psql -U edgebourne -d ebads -tAc "INSERT INTO meta_changes (level, entity_id, entity_name, campaign_id, action, old_value, new_value, ok, account_id) VALUES ('campaign', '120252638288040312', 'QA', '120252638288040312', 'budget', '1900', '2000', true, 1)"`);
  const advRecentSeen = errors.length;
  const advRecent = await page.evaluate(async (sig) => { const r = await fetch('/api/advice/apply', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ signature: sig, accept_big: true, confirm_to: 2600 }) }); return { status: r.status, body: await r.json() }; }, adviceSig);
  errors.splice(advRecentSeen); // the refusal logs an expected 409
  const advFresh = advRecent.body.fresh && advRecent.body.fresh.items.find((i) => i.signature === adviceSig);
  check("Meta's budget advice right after another change is refused without the knowing yes, and the list comes back saying so",
    advRecent.status === 409 && advRecent.body.code === 'recent_change' && advFresh && advFresh.budget.recent === true
    && metaObj('120252638288040312').daily_budget === '2000', `${advRecent.status} ${JSON.stringify(advFresh && advFresh.budget)}`);
  await page.reload();
  await page.waitForSelector('.advice-list [data-apply]');
  await page.click('[data-apply]');
  await page.waitForSelector('dialog.confirm');
  const advRecentDlg = (await page.textContent('dialog.confirm')).replace(/\s+/g, ' ');
  const advRecentOk = await page.$eval('dialog.confirm #cd-ok', (b) => [b.textContent, b.classList.contains('btn-danger')]);
  await page.click('dialog.confirm #cd-cancel');
  check('Apply then says the budget changed less than 3 days ago and asks Raise anyway, as a danger button',
    /Less than 3 days since the last change/.test(advRecentDlg) && advRecentOk[0] === 'Raise anyway' && advRecentOk[1], `${advRecentOk} ${advRecentDlg.slice(0, 160)}`);
  ageBudget();
  await page.reload();
  await page.waitForSelector('.advice-list [data-apply]');
  await page.click('[data-apply]');
  await page.waitForSelector('dialog.confirm');
  check('applying it asks first, with the +20% warning, and says "Apply anyway"', /More than \+20% in one step/.test(await page.textContent('dialog.confirm')) && /Apply anyway/.test(await page.textContent('dialog.confirm #cd-ok')));
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => /96\/100/.test(document.getElementById('advice').textContent));
  const budgetAfter = sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/v24.0/120252638288040312?access_token=x').read().decode())"`).match(/"daily_budget":"?(\d+)/)[1];
  check('Meta applies it: the budget moves by its step, the score rises, the suggestion goes', budgetBefore === '2000' && budgetAfter === '2600'
    && (await page.locator('.advice-list li').count()) === 1 && /▲ 9/.test(await page.textContent('#advice')), `${budgetBefore} → ${budgetAfter}`);
  const advLogged = sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;r=db.query('SELECT action, ok, accepted FROM meta_changes ORDER BY id DESC LIMIT 1', one=True);print(r['action'], r['ok'], r['accepted'])"`).trim();
  check('the change is logged like any other, with the +20% warning it was confirmed through', advLogged === "recommendation True ['big']", advLogged);
  check('without benchmarks yet it says where they come from', /come with Claude's Monday summary/.test(await page.textContent('#advice')));
  const bmk = JSON.parse(sh('docker cp dev/qa_agent_benchmarks.py edgebourne-ads-backend:/app/qa_agent_benchmarks.py && docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python qa_agent_benchmarks.py; docker exec edgebourne-ads-backend rm -f /app/qa_agent_benchmarks.py').trim().split('\n').pop());
  await page.reload();
  await page.waitForSelector('#advice .bench');
  check("the Monday summary's benchmarks show on Today", bmk.body.saved === 2 && /Cost per lead\s*\$4\.79\s*\$18–\$42/.test(await page.textContent('#advice .bench')) && /From Claude's Monday summary, 2026-11-09/.test(await page.textContent('#advice')));
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute(\\"UPDATE campaigns SET daily_budget_cents = 2000 WHERE id = '120252638288040312'\\")"`);

  // Fix with Claude: Meta's Reels advice goes to the Mac as a Desk run; its 9:16 proposals update the running ads.
  const reels = page.locator('.advice-list li', { hasText: 'vertical 9:16' });
  check('advice the console cannot apply offers "Fix with Claude"', (await reels.locator('[data-fix]').count()) === 1 && (await reels.locator('[data-apply]').count()) === 0);
  await reels.locator('[data-fix]').click();
  await page.waitForSelector('dialog.confirm');
  const fixWords = (await page.textContent('dialog.confirm')).replace(/\s+/g, ' ');
  check('the dialog says what Claude will do and that nothing changes until accepted, in the console\'s words (accept, not approve)',
    /9:16 version with sound of each running ad/.test(fixWords) && /Nothing changes on Meta until you accept/.test(fixWords)
    && /Accepting one updates that ad/.test(fixWords) && !/Approving|proposes/.test(fixWords), fixWords.slice(0, 240));
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => /Waiting for your Mac/.test(document.querySelector('.advice-list')?.textContent || ''));
  const fixTask = sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;r=db.query(\\"SELECT id FROM desk_tasks WHERE kind='advice' ORDER BY id DESC LIMIT 1\\", one=True);print(r['id'])"`).trim();
  const fixAgain = await page.evaluate(async (key) => (await fetch('/api/advice/fix', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key }) })).json(),
    'REELS_PC_RECOMMENDATION:120252672227950312');
  check('asking twice while it waits reuses the same run', String(fixAgain.task_id) === fixTask && fixAgain.already === true, JSON.stringify(fixAgain));
  const mac = JSON.parse(sh(`docker cp dev/qa_agent_advice.py edgebourne-ads-backend:/app/qa_agent_advice.py && docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python qa_agent_advice.py ${fixTask}; docker exec edgebourne-ads-backend rm -f /app/qa_agent_advice.py`).trim().split('\n').pop());
  check("the Mac gets Meta's advice and the ad set's running ads", mac.advice === 'REELS_PC_RECOMMENDATION' && mac.ads.length === 5 && mac.task.campaign_id === '120252638288040312'
    && /^Meta's advice: Add a vertical 9:16 video for Reels \(\+4 points\)/.test(mac.task.prompt) && mac.added.added === 2, JSON.stringify(mac).slice(0, 200));
  await page.reload();
  await page.waitForSelector('.advice-list');
  check('Today shows the fixes waiting for a yes, in the console\'s word', /2 suggestions/.test(await page.locator('.advice-list li', { hasText: 'vertical 9:16' }).textContent()));
  await page.goto(BASE + '/desk.html#waiting');
  const vcard = page.locator('#cv-col .sg', { hasText: `9:16 for Reels: N3` });
  await vcard.waitFor();
  check('the suggestion says the ad is updated, not copied, and previews it as Reels',
    /Update ad/.test(await vcard.locator('.sg-type').textContent()) && /updated, not copied/.test(await vcard.textContent())
    && (await vcard.locator('[data-preview]').getAttribute('data-format')) === 'INSTAGRAM_REELS');
  await vcard.locator('[data-preview] iframe').waitFor({ timeout: 15000 });
  check("Meta's Reels preview of the 9:16 version loads", /INSTAGRAM_REELS/.test(await vcard.locator('[data-preview] iframe').getAttribute('src')));
  const [n3id, n3vid] = mac.picks[0];
  const fakeAd = (id) => JSON.parse(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/v24.0/${id}?access_token=x').read().decode())"`));
  const fakeCreative = (cid) => JSON.parse(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/fake/_creative/${cid}').read().decode())"`));
  const n3before = fakeAd(n3id).creative_id;
  await vcard.locator('[data-accept]').click();
  await page.waitForSelector('dialog.accept-sheet #cd-ok:not(:empty)');
  check('accepting explains the update and the new review', /Reels and Stories get Claude's 9:16 video/.test(await page.textContent('dialog.accept-sheet')) && /Meta reviews the ad again/.test(await page.textContent('dialog.accept-sheet')));
  await page.click('dialog.accept-sheet #cd-ok');
  await page.waitForFunction(() => document.querySelector('dialog.accept-sheet #cd-ok')?.textContent === 'Done', null, { timeout: 30000 });
  await page.click('dialog.accept-sheet #cd-ok');
  await page.waitForFunction(() => ![...document.querySelectorAll('#cv-col .sg b')].some((h) => /N3/.test(h.textContent)));
  const n3after = fakeAd(n3id).creative_id;
  const n3made = fakeCreative(n3after);
  const feed = n3made.asset_feed_spec || {};
  check('the running ad now carries 4:5 for feeds and 9:16 for Reels and Stories, same form', n3after !== n3before
    && feed.videos.map((v) => v.video_id).includes(n3vid) && feed.asset_customization_rules[0].customization_spec.instagram_positions.join() === 'story,reels'
    && JSON.stringify(feed.call_to_actions).includes('lead_gen_form_id') && feed.titles[0].text === 'Stop typing the same thing twice', `${n3before} → ${n3after}`);
  check('the update is logged as a change', sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;r=db.query('SELECT action, ok, entity_id FROM meta_changes ORDER BY id DESC LIMIT 1', one=True);print(r['action'], r['ok'], r['entity_id'])"`).trim() === `placement_media True ${n3id}`);
  // A copy Meta stores without the lead form never reaches the running ad.
  sh('docker exec edgebourne-fake-meta python -c "import urllib.request;urllib.request.urlopen(\'http://localhost:5001/fake/_drop_form?on=1\')"');
  const [n4id] = mac.picks[1];
  const n4before = fakeAd(n4id).creative_id;
  const n4card = page.locator('#cv-col .sg', { hasText: '9:16 for Reels: N4' });
  const lostFormSeen = errors.length;
  await n4card.locator('[data-accept]').click();
  await page.waitForSelector('dialog.accept-sheet #cd-ok:not(:empty)');
  await page.click('dialog.accept-sheet #cd-ok');
  await page.waitForFunction(() => /lost the lead form/.test(document.querySelector('dialog.accept-sheet')?.textContent || ''), null, { timeout: 30000 });
  await page.waitForFunction(() => document.querySelector('dialog.accept-sheet #cd-ok')?.textContent === 'Done');
  await page.click('dialog.accept-sheet #cd-ok');
  errors.splice(lostFormSeen); // the refused update logs an expected 400
  check('a creative that lost the lead form is refused and the ad is left alone', fakeAd(n4id).creative_id === n4before);
  sh('docker exec edgebourne-fake-meta python -c "import urllib.request;urllib.request.urlopen(\'http://localhost:5001/fake/_drop_form?on=0\')"');
  await page.goto(BASE + '/home.html');
  await page.waitForSelector('.advice-list');
  check('after the run, Today offers to fix it again', /Fix again with Claude/.test(await page.locator('.advice-list li', { hasText: 'vertical 9:16' }).textContent()));

  // Polish and new versions update the ad itself: same ad, results kept, each version's numbers apart.
  const n5 = '120252672233160312';
  const dbq = (code) => sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;${code}"`).trim();
  const polished = await page.evaluate(async (id) => (await (await fetch(`/api/ads/ad/${id}/polish`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ passes: ['headline'], variants: true, direction: 'qa' }) })).json()), n5);
  const polishTask = polished.task_id;
  const macU = JSON.parse(sh(`docker cp dev/qa_agent_update.py edgebourne-ads-backend:/app/qa_agent_update.py && docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python qa_agent_update.py ${polishTask} ${mac.picks[0][0]}; docker exec edgebourne-ads-backend rm -f /app/qa_agent_update.py`));
  check('copy from a polish run is marked as an update of that ad', macU.proposals.A.update === true && macU.proposals.B.update === true && macU.added.added === 4, JSON.stringify(macU));
  const n5creative = fakeAd(n5).creative_id;
  const adsBefore = dbq("print(db.query('SELECT count(*) AS n FROM ads', one=True)['n'])");
  const seenB = errors.length; // the refusals below log expected errors, and so does the preview of the ad that can't be updated
  await page.goto(BASE + '/desk.html#waiting');
  const cardOf = (l) => page.locator('#cv-col .sg', { hasText: `New headline ${l}` });
  await cardOf('A').waitFor();
  check('the suggestion says the ad is updated, not copied', /Update ad/.test(await cardOf('A').locator('.sg-type').textContent()) && /updated, not copied/.test(await cardOf('A').textContent()) && /Make a new ad instead/.test(await cardOf('A').textContent()));
  await cardOf('A').locator('[data-preview] iframe').waitFor({ timeout: 15000 });
  check("Meta's preview of the update loads", /MOBILE_FEED_STANDARD/.test(await cardOf('A').locator('[data-preview] iframe').getAttribute('src')));
  await page.locator('[data-accept-all]').first().click();
  await page.waitForSelector('dialog.accept-sheet #cd-ok:not(:empty)');
  const ticked = await page.$$eval('dialog.accept-sheet [data-item]', (b) => b.filter((x) => x.checked).map((x) => x.getAttribute('aria-label')));
  check('variants of one ad are never ticked together', !ticked.some((t) => /New headline [ABC]/.test(t)) && /Tick one/.test(await page.textContent('dialog.accept-sheet')), ticked.join('|'));
  await page.click('dialog.accept-sheet #cd-cancel');
  await cardOf('A').locator('[data-accept]').click();
  await page.waitForSelector('dialog.accept-sheet #cd-ok:not(:empty)');
  check('accepting explains it stays the same ad', /same ad, results kept/.test(await page.textContent('dialog.accept-sheet')) && /Meta reviews the ad again/.test(await page.textContent('dialog.accept-sheet')));
  await page.click('dialog.accept-sheet #cd-ok');
  await page.waitForFunction(() => document.querySelector('dialog.accept-sheet #cd-ok')?.textContent === 'Done', null, { timeout: 30000 });
  await page.click('dialog.accept-sheet #cd-ok');
  await page.waitForFunction(() => ![...document.querySelectorAll('#cv-col .sg b')].some((h) => /New headline A/.test(h.textContent)));
  const n5v2 = fakeAd(n5).creative_id;
  const n5made = fakeCreative(n5v2).object_story_spec;
  check('the same ad now carries the new words, video and form', n5v2 !== n5creative && n5made.video_data.title === 'Headline A' && n5made.video_data.message === 'Primary text A.'
    && n5made.video_data.video_id === fakeCreative(n5creative).object_story_spec.video_data.video_id && JSON.stringify(n5made).includes('lead_gen_form_id'), `${n5creative} → ${n5v2}`);
  check('no new ad was made and the name did not change', dbq("print(db.query('SELECT count(*) AS n FROM ads', one=True)['n'])") === adsBefore && !/Variant/.test(fakeAd(n5).name), fakeAd(n5).name);
  check('the update is logged', dbq("r=db.query('SELECT action, ok, entity_id FROM meta_changes ORDER BY id DESC LIMIT 1', one=True);print(r['action'], r['ok'], r['entity_id'])") === `update_creative True ${n5}`);
  // A copy Meta stores without the form never reaches the ad, and the suggestion is marked failed.
  sh('docker exec edgebourne-fake-meta python -c "import urllib.request;urllib.request.urlopen(\'http://localhost:5001/fake/_drop_form?on=1\')"');
  const lostForm = await page.evaluate(async (id) => { const r = await fetch(`/api/proposals/${id}/approve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); return { status: r.status, body: await r.json() }; }, macU.proposals.B.id);
  sh('docker exec edgebourne-fake-meta python -c "import urllib.request;urllib.request.urlopen(\'http://localhost:5001/fake/_drop_form?on=0\')"');
  check('an update that lost the lead form leaves the ad alone', lostForm.status === 400 && /lost the lead form/.test(lostForm.body.error) && fakeAd(n5).creative_id === n5v2, JSON.stringify(lostForm));
  check("the change log keeps the plain reason, not Meta's raw keys", !/feed keys|Meta returned/.test(dbq(`r=db.query('SELECT error FROM meta_changes WHERE proposal_id = %s AND NOT ok ORDER BY id DESC LIMIT 1', (${macU.proposals.B.id},), one=True);print(r['error'])`)));
  const placedBefore = fakeAd(mac.picks[0][0]).creative_id;
  const placed = await page.evaluate(async (id) => { const r = await fetch(`/api/proposals/${id}/approve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); return { status: r.status, body: await r.json() }; }, macU.proposals.D.id);
  errors.splice(seenB); // both refusals log an expected error
  check('an ad with different media per placement is refused, not flattened', placed.status === 409 && /different media per placement/.test(placed.body.error) && fakeAd(mac.picks[0][0]).creative_id === placedBefore, JSON.stringify(placed));
  await page.evaluate(async (id) => fetch(`/api/proposals/${id}/decline`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }), macU.proposals.D.id);
  // Results per version: the switch happened 3 days ago, and Meta approved it the next day.
  dbq(`import account_info as a, datetime as d;t=a.today();s=t-d.timedelta(days=3);db.execute('UPDATE ad_versions SET started_on=%s, started_at=now()-interval \\'3 days\\' WHERE ad_id=%s AND number=2',(s,'${n5}'));db.execute(\\"INSERT INTO status_events (level, entity_id, field, old_value, new_value, source, at) VALUES ('ad', %s, 'effective_status', 'IN_PROCESS', 'ACTIVE', 'poll', now()-interval '2 days')\\",('${n5}',))`);
  await page.goto(BASE + `/ad.html?id=${n5}`);
  await openFold('versions');
  await page.waitForSelector('.ver-tbl');
  const verRows = await page.$$eval('.ver-tbl tbody tr', (rows) => rows.map((r) => [...r.cells].map((c) => c.textContent.trim())));
  const expected = JSON.parse(dbq(`import account_info as a, datetime as d, json;t=a.today();r=db.query('SELECT day, spend_cents FROM ad_daily WHERE ad_id=%s AND day<%s',('${n5}',t));tz=lambda n:t-d.timedelta(days=n);print(json.dumps({'old':sum(x['spend_cents'] for x in r if x['day']<tz(3)),'old_days':len([x for x in r if x['day']<tz(3)]),'new':sum(x['spend_cents'] for x in r if x['day']>tz(2)),'new_days':len([x for x in r if x['day']>tz(2)]),'mid_days':len([x for x in r if tz(3)<=x['day']<=tz(2)])}))`));
  const verDollars = (c) => (c / 100).toFixed(2);
  check('each version shows only its own days and spend', verRows.length === 2 && /Version 2/.test(verRows[0][0]) && Number(verRows[0][1]) === expected.new_days && verRows[0][2].includes(verDollars(expected.new))
    && /Version 1/.test(verRows[1][0]) && Number(verRows[1][1]) === expected.old_days && verRows[1][2].includes(verDollars(expected.old)), JSON.stringify([verRows, expected]));
  check('the versions table fits its panel, so Switch back is never scrolled out of sight', await page.$eval('.ver-tbl', (t) => t.parentElement.scrollWidth <= t.parentElement.clientWidth));
  check('the current version is marked and the days around the switch are explained', /On the ad now/.test(verRows[0][0]) && new RegExp(`${expected.mid_days} days around a switch`).test(await page.textContent('.ver-tbl >> xpath=ancestor::details')));
  await page.screenshot({ path: `${OUT}/flow-versions.png`, fullPage: true });
  // Switching back puts the old creative on the same ad.
  await page.click('[data-restore="1"]');
  await page.waitForSelector('dialog.confirm');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => document.querySelectorAll('.ver-tbl tbody tr').length === 3);
  check('switching back restores the original creative as a new version', fakeAd(n5).creative_id === n5creative && /Back to version 1/.test(await page.locator('.ver-tbl tbody tr').first().textContent()) && /On the ad now/.test(await page.locator('.ver-tbl tbody tr').first().textContent()));
  // The other way round stays possible: a separate new ad, the current one untouched.
  await page.goto(BASE + '/desk.html#waiting');
  await cardOf('C').waitFor();
  await cardOf('C').locator('[data-as="new"]').click();
  await page.waitForSelector('dialog.confirm');
  check('making a separate ad says the current one stays', /separate new ad/.test(await page.textContent('dialog.confirm')));
  await Promise.all([page.waitForURL('**created=1**'), page.click('dialog.confirm #cd-ok')]);
  // By name: the fake's ids restart each run, so a row count can't see a new ad reusing an old id.
  const variantAd = dbq(`r=db.query(\\"SELECT m.entity_id, a.status FROM meta_changes m JOIN ads a ON a.id = m.entity_id WHERE m.action = 'create' AND m.ok AND m.new_value = 'Variant C' ORDER BY m.id DESC LIMIT 1\\", one=True);print(r['entity_id'], r['status'])`).split(' ');
  check('it creates a new ad, off, and leaves the original alone', variantAd[0] !== n5 && variantAd[1] === 'PAUSED' && fakeAd(n5).creative_id === n5creative, variantAd.join(' '));

  // Comments: reply as the Page and hide / show, never delete; only comments on the ad's own post.
  await page.goto(BASE + '/ad.html?id=120252672229400312#tab=comments');
  await page.waitForSelector('.comment');
  check('comments show who, what, and whether the Page answered', (await page.locator('.comment').count()) === 2 && /2 not answered/.test(await page.textContent('.comments-panel .panel-head')));
  const first = page.locator('.comment').first();
  await first.locator('[data-reply-open]').click();
  await first.locator('textarea').fill('Thanks Daniel! It depends on what you need; we cover it on the free intro call.');
  await first.locator('.c-reply button[type=submit]').click();
  await page.waitForSelector('dialog.confirm');
  check('a reply is shown in full before it is posted publicly', /It appears publicly under the comment/.test(await page.textContent('dialog.confirm')) && /free intro call/.test(await page.textContent('dialog.confirm .quote')));
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => /You \(the Page\)/.test(document.querySelector('.comment')?.textContent || ''));
  const fc = fake('_comments');
  const post = Object.keys(fc).find((k) => fc[k][0].comments.data.some((r) => /free intro call/.test(r.message)));
  check('the reply reaches Facebook under that comment, and the comment reads answered',
    !!post && fc[post][0].comments.data.length === 1 && /Answered/.test(await page.textContent('.comment')));
  await page.locator('.comment').nth(1).locator('[data-hide="1"]').click();
  await page.waitForSelector('dialog.confirm');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => /Hidden/.test(document.querySelectorAll('.comment')[1]?.textContent || ''));
  check('hiding a comment hides it on Facebook, and it can be shown again', fake('_comments')[post][1].is_hidden === true);
  await page.locator('.comment').nth(1).locator('[data-hide="0"]').click();
  await page.waitForFunction(() => !/Hidden/.test(document.querySelectorAll('.comment')[1]?.textContent || 'Hidden'));
  check('shown again', fake('_comments')[post][1].is_hidden === false && (await page.locator('[data-delete], [data-remove-comment]').count()) === 0);
  const cSeen = errors.length;
  const foreign = await page.evaluate(async () => (await fetch('/api/insights/ad/120252672229400312/comments/999_1/reply', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: 'x' }) })).status);
  errors.splice(cSeen);
  check("a comment that isn't on this ad's post is refused", foreign === 404);
  check('replies and hiding are logged', sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(','.join(r['action'] for r in db.query('SELECT action FROM meta_changes ORDER BY id DESC LIMIT 3')[::-1]))"`).trim() === 'comment_reply,comment_hide,comment_show');

  // Tracking health: what Meta's dataset received (here: the lead stages sent earlier in this run), and what to do.
  await openSettings('tracking');
  await page.waitForSelector('#tr-body .tr-headline');
  await page.click('#tr-fresh');
  await page.waitForFunction(() => /Lead/.test(document.getElementById('tr-body').textContent) && /Healthy|Something to fix/.test(document.getElementById('tr-state').textContent));
  const tr = await page.textContent('#tr-body');
  check('Tracking health shows what Meta received, from a server, with match quality', /Healthy/.test(await page.textContent('#tr-state'))
    && /Lead \d/.test(tr) && /Contacted \d/.test(tr) && /100%/.test(tr) && /Lead 7\.4\/10/.test(tr), tr.replace(/\s+/g, ' ').slice(0, 300));
  check('it says sending is off when it is, and what to do', /sending is off/.test(tr) && /Turn on Settings → Lead stages to Meta/.test(tr));
  check('a silent dataset is one of the alert rules', /Lead stages stop reaching Meta's dataset/.test(await page.textContent('#al-form')));
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import settings_store,json;settings_store.set('tracking_snapshot', json.dumps({'dataset':'1','details':{'server_last_fired_time':'1969-12-31T16:00:00-0800'},'events':{},'sources':{'server':0,'browser':0},'match':[],'fetched_at':'2099-01-01T00:00:00+00:00'}))"`);
  await page.reload();
  await page.waitForSelector('#tr-body .tr-headline');
  check('a dataset that never received anything reads "Not set up" and explains it', /Not set up/.test(await page.textContent('#tr-state')) && /never received an event/.test(await page.textContent('#tr-body')));
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import settings_store;settings_store.set('tracking_snapshot', None)"`);

  // Installable app + push: manifest and offline page, a device turned on, messages encrypted end to end, channel order.
  const man = await page.evaluate(async () => { const r = await fetch('/manifest.webmanifest'); return { type: r.headers.get('content-type'), m: await r.json() }; });
  check('the app manifest is served with its icons and opens on Today', man.m.start_url === '/home.html' && man.m.display === 'standalone' && man.m.icons.some((i) => i.purpose === 'maskable'));
  check('the service worker is registered', await page.evaluate(async () => !!(await navigator.serviceWorker.getRegistration('/'))));
  const ecdh = require('crypto').generateKeyPairSync('ec', { namedCurve: 'prime256v1' });
  const jwk = ecdh.privateKey.export({ format: 'jwk' });
  const raw = Buffer.concat([Buffer.from([4]), Buffer.from(jwk.x, 'base64url'), Buffer.from(jwk.y, 'base64url')]).toString('base64url');
  const authKey = require('crypto').randomBytes(16).toString('base64url');
  const fakePost = (path, body) => sh(`docker exec edgebourne-fake-meta python -c "import urllib.request,json;urllib.request.urlopen(urllib.request.Request('http://localhost:5001${path}', data=json.dumps(${JSON.stringify(body).replace(/"/g, "'")}).encode(), headers={'Content-Type':'application/json'}))"`);
  fakePost('/push/_register', { id: 'qa1', private: jwk.d, auth: authKey });
  const sentBefore = JSON.parse(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/push/_sent').read().decode())"`)).length;
  const pushSeen = errors.length;
  const refusedEvil = await page.evaluate(async () => (await fetch('/api/me/push', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ subscription: { endpoint: 'https://evil.example/collect', keys: { p256dh: 'x', auth: 'y' } } }) })).status);
  errors.splice(pushSeen);
  check("the server only accepts the browsers' own push services", refusedEvil === 400);
  await page.evaluate(async ({ raw, authKey }) => fetch('/api/me/push', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ subscription: { endpoint: 'http://fake-meta:5001/push/qa1', keys: { p256dh: raw, auth: authKey } }, label: 'QA phone' }) }), { raw, authKey });
  await page.goto(BASE + '/account.html');
  await page.waitForSelector('.device-list');
  check('Your account lists the devices with notifications on', /QA phone/.test(await page.textContent('.device-list')));
  await page.evaluate(() => fetch('/api/me/push/test', { method: 'POST' }));
  const got = JSON.parse(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/push/_sent').read().decode())"`)).slice(sentBefore);
  check('a test message reaches the device, encrypted with its keys and readable only with them', got.length === 1 && got[0].payload.title === 'Test from Edge Bourne Ads' && got[0].id === 'qa1', JSON.stringify(got[0] || {}));
  const channels = sh(`docker exec -w /app edgebourne-ads-backend python -c "
import db, notify
uid = db.query(\\"SELECT id FROM users WHERE email = 'eugene@edgebourne.com'\\", one=True)['id']
tg = db.query('SELECT notify_telegram FROM users WHERE id = %s', (uid,), one=True)['notify_telegram']
a = notify.reach([uid], 'notify_new_leads')
db.execute('UPDATE users SET notify_telegram = FALSE WHERE id = %s', (uid,))
b = notify.reach([uid], 'notify_new_leads')
notify.queue(uid, 'push', 'lead', 'New lead: QA Push', ['Phone (555) 010-0000'], '/leads.html', dedupe_key='qa-push-lead-${Date.now()}')
notify.process_pending()
db.execute('UPDATE users SET notify_telegram = %s WHERE id = %s', (tg, uid))
print(a[0][1] if a else '-', b[0][1] if b else '-')"`).trim();
  const got2 = JSON.parse(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/push/_sent').read().decode())"`)).slice(sentBefore + 1);
  check('alerts go to Telegram first, then to push devices, then email; a lead alert arrives by push with its link',
    channels === 'telegram push' && got2.length === 1 && got2[0].payload.title === 'New lead: QA Push' && got2[0].payload.url === '/leads.html', `${channels} ${JSON.stringify(got2[0] || {})}`);
  const gSeen = errors.length;
  const badKeys = await page.evaluate(async () => (await fetch('/api/me/push', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ subscription: { endpoint: 'http://fake-meta:5001/push/x', keys: { p256dh: 'BFAKE', auth: 'AFAKE' } } }) })).status);
  await page.evaluate(async ({ raw, authKey }) => fetch('/api/me/push', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ subscription: { endpoint: 'http://fake-meta:5001/push/gone1', keys: { p256dh: raw, auth: authKey } }, label: 'Old laptop' }) }), { raw, authKey });
  await page.evaluate(() => fetch('/api/me/push/test', { method: 'POST' }));
  errors.splice(gSeen);
  errors.splice(gSeen);
  const left = await page.evaluate(async () => (await (await fetch('/api/me/push')).json()).devices.map((d) => d.label));
  check('a device the push service says is gone is removed by itself; unusable keys are refused up front', left.join() === 'QA phone' && badKeys === 400, `${left.join()} ${badKeys}`);
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute('DELETE FROM push_subscriptions')"`);

  // Agency mode: accounts never see each other's data (every GET route, three roles), switching, read-only clients.
  const leak = JSON.parse(sh('docker cp dev/qa_leaks.py edgebourne-ads-backend:/app/qa_leaks.py && docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python qa_leaks.py; docker exec edgebourne-ads-backend rm -f /app/qa_leaks.py').trim().split('\n').pop());
  check(`no account's data shows in another: ${leak.routes_checked.join(' + ')} route calls as admin on each account and as a client`, leak.leaks.length === 0 && leak.routes_checked.every((n) => n > 40), leak.leaks.slice(0, 3).join(' | '));
  check('no route of the leak walk fails with a server error', leak.routes_crashed.length === 0, leak.routes_crashed.slice(0, 4).join(' | '));
  check('a client can change nothing (every change refused) and cannot switch accounts', leak.client_writes_not_refused.length === 0 && leak.client_switch_status === 403 && leak.client_stays_on_own_account,
    leak.client_writes_not_refused.slice(0, 4).join(' | '));
  check('each account still sees its own data', leak.admin_sees_account2_on_account2 && leak.client_sees_own_leads);
  // The walk only finds a leak where the other account has a marked row: each screen must show its own account's marks.
  const markShown = { 'admin on account 1': ['/api/inbox', '/api/desk', '/api/views', '/api/builds/open', '/api/settings/activity'],
    'admin on account 2, own ids': ['/api/inbox', '/api/desk', '/api/views', '/api/builds/open', '/api/settings/activity', '/api/timeline/<level>/<entity_id>',
      '/api/proposals/<int:proposal_id>', '/api/leads/<int:lead_id>', '/api/ads/ad/<ad_id>/tags', '/api/experiments/<int:exp_id>', '/api/builds/<int:build_id>'] };
  const unmarked = Object.entries(markShown).flatMap(([who, routes]) => routes.filter((r) => !(leak.routes_showing_own_mark[who] || []).includes(r)).map((r) => `${who}: ${r}`));
  check('the leak walk has marked rows to find in Inbox, Claude, saved views, builds, History and the timeline', unmarked.length === 0, unmarked.join(' | '));
  check('every table that holds account data is limited to its account by the database (row-level security)',
    leak.tables_without_isolation.length === 0 && leak.app_role_bypasses_rls === false && leak.isolated_tables >= 28, `${leak.isolated_tables} tables; missing: ${leak.tables_without_isolation.join()}`);
  await page.goto(BASE + '/ads.html');
  await page.waitForSelector('#acct-rail');
  check('admins switch accounts from the sidebar', (await page.locator('#acct-rail option').count()) >= 3 && /Edge Bourne/.test(await page.textContent('#acct-rail option:checked')));
  await page.selectOption('#acct-rail', String(leak.account2));
  await page.waitForFunction(() => /ACCT2MARK/.test(document.getElementById('cr-all')?.textContent || ''), null, { timeout: 8000 }).catch(() => {});
  const acct2 = `${await page.textContent('#acct-rail option:checked')} | ${(await page.textContent('#cr-all')).replace(/\s+/g, ' ')}`;
  check('switched, the Ads page shows only that account', /ACCT2MARK ad/.test(acct2) && !/One simple system/.test(acct2), acct2.slice(0, 220));
  await page.selectOption('#acct-rail', '1');
  await page.waitForFunction(() => /One simple system/.test(document.getElementById('cr-all')?.textContent || ''));
  check('and back', /One simple system/.test(await page.textContent('#cr-all')) && !/ACCT2MARK/.test(await page.textContent('#cr-all')));
  await page.selectOption('#acct-rail', 'new');
  await page.waitForSelector('dialog.confirm');
  await page.fill('#cd-input', 'QA Studio');
  await Promise.all([page.waitForURL('**/settings.html**'), page.click('dialog.confirm #cd-ok')]);
  await page.waitForSelector('#acct-rail');
  check('adding an account opens Settings on it, ready to connect its Meta account', /QA Studio/.test(await page.textContent('#acct-rail option:checked')));
  await page.evaluate(() => fetch('/api/accounts/switch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: 1 }) }));
  sh(`docker exec -w /app edgebourne-ads-backend python -c "
from werkzeug.security import generate_password_hash
import db
db.execute(\\"UPDATE users SET password_hash = %s, must_change_password = FALSE WHERE email = 'client-qa@burdanova.test'\\", (generate_password_hash('client-pass-123'),))
db.execute(\\"UPDATE accounts SET archived_at = now() WHERE name = 'QA Studio'\\")
import account_ctx
with account_ctx.all_accounts():
    db.execute(\\"UPDATE leads SET created_time = now(), status = 'new', first_contacted_at = NULL, form_id = '777000111', form_name = 'QA client form' WHERE meta_lead_id = 'ACCT2MARKlead'\\")
    db.execute(\\"DELETE FROM inbox_reads WHERE user_id = (SELECT id FROM users WHERE email = 'client-qa@burdanova.test')\\")"`);
  const cctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
  const cp = await cctx.newPage();
  cp.on('pageerror', (e) => errors.push('client page: ' + e.message));
  await cp.goto(BASE + '/login.html');
  await cp.fill('#email', 'client-qa@burdanova.test');
  await cp.fill('#password', 'client-pass-123');
  await Promise.all([cp.waitForURL('**/home.html**'), cp.click('button[type=submit]')]);
  await cp.waitForSelector('.rail .nav a .label');
  const nav = await cp.$$eval('.rail .nav a .label', (a) => a.map((x) => x.textContent.trim()));
  check('a client signs in to their own account with the read-only menu', nav.join() === 'Today,Inbox,Leads,Ads,Creative,Insights' && /Burdanova QA/.test(await cp.textContent('.rail')), nav.join());
  const clientBulk = await cp.evaluate(async () => (await fetch('/api/ads/bulk/preview', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'ebads' },
    body: JSON.stringify({ action: 'status', level: 'ad', ids: ['x'], value: 'PAUSED' }) })).status);
  check('a client can\'t make bulk changes', clientBulk === 403, String(clientBulk));
  // Their own read marks and saved views are theirs to change (the screens offer them).
  const clientOwn = await cp.evaluate(async () => {
    const send = async (m, u, b) => (await fetch(u, { method: m, headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'ebads' }, body: b === undefined ? undefined : JSON.stringify(b) }));
    const before = await (await fetch('/api/inbox?filter=unread')).json();
    const read = before.items.length ? (await send('POST', '/api/inbox/read', { keys: [before.items[0].key] })).status : 0;
    const after = await (await fetch('/api/inbox?filter=unread')).json();
    const v = await send('POST', '/api/views', { page: 'ads', name: 'Client QA', query: 'view=all&range=30', shared: true });
    const vb = await v.json();
    const share = await (await send('PATCH', `/api/views/${vb.id}`, { name: 'Client QA 2', shared: true })).json();
    const del = (await send('DELETE', `/api/views/${vb.id}`)).status;
    return { unread: [before.counts.unread, after.counts.unread], read, view: v.status, shared: [vb.shared, share.shared], del };
  });
  check("a client marks Inbox items read and keeps their own saved views, never shared", clientOwn.read === 200 && clientOwn.unread[1] === clientOwn.unread[0] - 1
    && clientOwn.view === 201 && clientOwn.shared.join() === 'false,false' && clientOwn.del === 200, JSON.stringify(clientOwn));
  await cp.goto(BASE + '/ads.html');
  await cp.waitForSelector('#cr-all .cr-toolbar');
  check('a client gets no New button or menu on Ads', await cp.isHidden('#new-ad') && await cp.isHidden('#new-menu') && (await cp.locator('#empty-new').count()) === 0);
  {
    const CAD = '920000000000003';
    await cp.goto(BASE + `/ad.html?id=${CAD}`);
    await cp.waitForSelector('#cr-state');
    await openFold('idea', cp);
    await cp.waitForSelector('#idea .facts');
    const controls = await cp.evaluate(() => ['[data-toggle]', '#dup', '#cr-actions a[href*="new-ad.html"]', '#idea input', '#idea button[type=submit]', '#edit-budget',
      '[data-goto="polish"]', '[data-restore]', '#cr-tabs [data-tab="polish"]'].filter((x) => document.querySelector(x)));
    check('a client sees an ad with no switch, copy, new ad, tag editing, budget or Claude controls', controls.length === 0
      && (await cp.locator('#cr-actions a[href^="/compare.html"]').count()) === 1, controls.join());
    await cp.goto(BASE + `/ad.html?id=${CAD}#tab=comments`);
    await cp.reload();
    await cp.waitForSelector('.comments-panel, #cr-main .empty');
    check('a client reads the comments with no Reply or Hide', (await cp.locator('[data-reply-open], [data-hide], .c-reply').count()) === 0);
    await cp.goto(BASE + `/ad.html?id=${CAD}#tab=history`);
    await cp.reload();
    await cp.waitForSelector('#cr-main ol.tl, #cr-main .empty');
    const cd = await cp.evaluate(async (id) => (await fetch(`/api/ads/ad/${id}`)).json(), CAD);
    check("a client's ad History never says which change came from Claude", cd.changes.every((c) => !c.proposal_id) && cd.history.every((i) => !i.proposal_id && i.source !== 'claude')
      && !/Claude/.test(await cp.innerText('#cr-main')));
  }
  await cp.goto(BASE + '/leads.html');
  await cp.waitForSelector('.lead-row');
  await cp.click('.lead-row');
  await cp.waitForSelector('#stages');
  check("a client sees their leads but not the controls that change them", /ACCT2MARK Lead Person/.test(await cp.textContent('#list'))
    && !(await cp.isVisible('#note-form')) && (await cp.locator('#stages button:visible').count()) <= 1
    && !(await cp.isVisible('#log-call')) && (await cp.locator('#fu-box').count()) === 1 && (await cp.locator('.fu-actions:visible, [data-fu]:visible').count()) === 0);
  {
    // L1: a read-only client sees the Follow-up box and the history, and the server refuses a logged call.
    const clientLead = await cp.getAttribute('.lead-row', 'data-id');
    const callStatus = await cp.evaluate(async (id) => (await fetch(`/api/leads/${id}/calls`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ outcome: 'no_answer' }) })).status, clientLead);
    check('a read-only client cannot log a call (403)', callStatus === 403, String(callStatus));
    // Their Call link only dials (on the lead and on Today): no call dialog they could never save.
    const noTel = () => cp.evaluate(() => document.addEventListener('click', (e) => { if (e.target.closest('a[href^="tel:"]')) e.preventDefault(); }, true));
    await cp.reload();
    await cp.waitForSelector('#call-link');
    await noTel();
    await cp.click('#call-link');
    await cp.waitForTimeout(700);
    const leadDialog = await cp.locator('dialog.fu-dialog').count();
    await cp.goto(BASE + '/home.html');
    await cp.waitForSelector(`[data-dial="${clientLead}"]`);
    await noTel();
    await cp.click(`[data-dial="${clientLead}"]`);
    await cp.waitForTimeout(700);
    const todayDialog = await cp.locator('dialog.fu-dialog').count();
    check("a read-only client's Call buttons only dial: no call dialog on the lead or on Today", leadDialog === 0 && todayDialog === 0, `${leadDialog} ${todayDialog}`);
    // With Settings → Client access on, the client logs a call through the dialog (L1 flow 11b).
    py(`import settings_store, json;settings_store.set('client_lead_updates', 'on', account_id=${leak.account2})`);
    await cp.goto(BASE + `/leads.html#lead=${clientLead}`);
    await cp.reload();
    await cp.waitForSelector('#log-call:visible');
    await cp.click('#log-call');
    await cp.click('dialog.fu-dialog [data-outcome="no_answer"]');
    const [clientCall] = await Promise.all([cp.waitForResponse((r) => r.request().method() === 'POST' && /\/calls$/.test(r.url())), cp.click('dialog.fu-dialog #fu-save')]);
    await cp.waitForSelector('dialog.fu-dialog', { state: 'detached' });
    const clientLogged = await cp.evaluate(async (id) => (await fetch(`/api/leads/${id}`)).json(), clientLead);
    check('a client with lead updates on logs a call: No answer, Call back set', clientCall.status() === 200 && clientLogged.call_attempts === 1 && clientLogged.next_step_kind === 'call_back',
      JSON.stringify({ code: clientCall.status(), n: clientLogged.call_attempts, next: clientLogged.next_step_kind }));
    py(`import settings_store;settings_store.set('client_lead_updates', None, account_id=${leak.account2})`);
    py(`import db, account_ctx
with account_ctx.all_accounts():
    db.execute(\\"DELETE FROM lead_events WHERE lead_id = %s AND kind IN ('call', 'next_set', 'next_cleared', 'stage')\\", (${clientLead},))
    db.execute(\\"UPDATE leads SET status = 'new', first_contacted_at = NULL, call_attempts = 0, unanswered_streak = 0, ever_reached = FALSE, last_call_at = NULL, last_outcome = NULL, next_step_kind = NULL, next_step_text = NULL, next_step_at = NULL, next_step_by = NULL WHERE id = %s\\", (${clientLead},))`);
    await cp.goto(BASE + '/leads.html');
    await cp.waitForSelector('.lead-row');
    await cp.click('.lead-row');
    await cp.waitForSelector('#stages');
  }
  // Forms and tests are admin pages: a client reads their names but gets no link to them.
  await cp.waitForFunction(() => /QA client form/.test(document.getElementById('detail')?.textContent || ''));
  const clientPlain = await cp.evaluate(async () => {
    const ui = await import('/js/ui.js');
    return { formLinks: document.querySelectorAll('#detail a[href^="/forms.html"], #detail a[href^="/experiments.html"]').length,
      test: ui.entityLink('test', '42', 'QA test'), form: ui.entityLink('form', '42', 'QA form'), ad: ui.entityLink('ad', '42', 'QA ad') };
  });
  check("a client sees a lead's form by name with no link, and tests and forms never link for them", clientPlain.formLinks === 0
    && clientPlain.test === 'QA test' && clientPlain.form === 'QA form' && /^<a class="ent-link" href="\/ad\.html\?id=42">/.test(clientPlain.ad), JSON.stringify(clientPlain));
  // The command menu offers a client nothing that changes things: no Create, no Settings, no Refresh from Meta.
  await cp.keyboard.press(process.platform === 'darwin' ? 'Meta+k' : 'Control+k');
  await cp.waitForSelector('dialog.palette[open]');
  const clientMenu = {};
  for (const q of ['refresh', 'new', 'settings', 'claude', 'team']) {
    await cp.fill('dialog.palette input', q);
    await cp.waitForTimeout(450);
    clientMenu[q] = await cp.evaluate(() => [...document.querySelectorAll('dialog.palette .pal-item')].filter((li) => li.dataset.type !== 'lead' && li.dataset.type !== 'ad' && li.dataset.type !== 'adset' && li.dataset.type !== 'campaign')
      .map((li) => li.querySelector('.pal-t').textContent));
  }
  await cp.keyboard.press('Escape');
  const clientBad = Object.values(clientMenu).flat().filter((t) => /^(New |Refresh|Settings|Ask Claude|Claude|Team|Lead forms|Tests|Research)/.test(t));
  check('a client\'s command menu has no actions that change things, no Settings and no admin pages', clientBad.length === 0 && clientMenu.refresh.length === 0, JSON.stringify(clientMenu));
  await cp.goto(BASE + '/report.html');
  await cp.waitForSelector('.r-head');
  check("a client opens their own account's report, without the share button", /Burdanova QA/.test(await cp.textContent('.r-head')) && await cp.isHidden('#share'));
  await cp.goto(BASE + '/gallery.html');
  await cp.waitForSelector('.gal-card, #gal .empty');
  check('a client opens the Gallery to look only: no New ad, no Research tab', await cp.isHidden('#gal-new') && (await cp.locator('.subnav a[href="/research.html"]').count()) === 0
    && (await cp.locator('.rail .nav a[href="/gallery.html"]').count()) === 1);
  // 9.5 client pass: Ideas and the Gallery show no control that changes anything; Research is not theirs.
  await cp.goto(BASE + '/ideas.html');
  await cp.waitForSelector('.idea-grp, #ideas .empty');
  const clientActs = async () => cp.evaluate(() => [...document.querySelectorAll('.main button, .main a.btn, .main form, .main input:not([type=checkbox]), .main textarea, #gal-tray button')]
    .filter((el) => el.offsetParent !== null && !el.closest('#idea-by, .crumbs, .subnav, .topline, .views, .empty .row [data-clear-filters]') && !['range-pick', 'status-pick', 'tag-pick'].includes(el.id)
      && !el.matches('[data-gview], [data-tag], [data-pick], [data-tray="compare"], [data-tray="clear"], [data-retry]'))
    .map((el) => (el.id || el.className || el.tagName) + ':' + el.textContent.trim().slice(0, 20)));
  const ideasActs = await clientActs();
  check('a client sees Ideas with nothing to change: only the grouping, the dates and links', ideasActs.length === 0 && (await cp.locator('.subnav a[href="/ideas.html"]').count()) === 1
    && !/ask Claude|tag them/.test(await cp.textContent('#ideas')), ideasActs.join(' | '));
  await cp.goto(BASE + '/gallery.html');
  await cp.waitForSelector('.gal-card, #gal .empty');
  const galActs = await clientActs();
  check('a client sees the Gallery with nothing to change', galActs.length === 0, galActs.join(' | '));
  await cp.goto(BASE + '/research.html');
  await cp.waitForURL('**/home.html');
  const clientBrief = await cp.evaluate(async () => (await fetch('/api/swipes/brief?ids=1')).status);
  check('a client never reaches Research or a brief', /home\.html/.test(cp.url()) && clientBrief === 403, String(clientBrief));
  await cp.goto(BASE + '/report.html');
  await cp.waitForSelector('.r-head');
  check("a client's report links no form or test", (await cp.locator('#report a[href^="/forms.html"], #report a[href^="/experiments.html"]').count()) === 0);
  await cp.waitForSelector('#period option', { state: 'attached' });
  const clientWeeks = await cp.$$eval('#period option', (o) => o.map((x) => x.value));
  const clientKind = await cp.getAttribute('#kind [aria-pressed="true"]', 'data-kind');
  check("a client gets the report's period picker too: whole periods, newest first", clientWeeks.length >= 1
    && clientWeeks.every((d) => (clientKind === 'week' ? new Date(d + 'T12:00:00Z').getUTCDay() === 1 : d.endsWith('-01')))
    && clientWeeks.every((d, i) => i === 0 || d < clientWeeks[i - 1]), `${clientKind}: ${clientWeeks.join()}`);
  await cp.goto(BASE + '/performance.html?range=30');
  await cp.waitForSelector('#cr-note', { state: 'attached' });
  const clientNote = await cp.textContent('#cr-note');
  check('a client sees Results without being told to turn ads on or off or change budgets', !/turn ads on or off|change budgets/i.test(clientNote), clientNote);
  const clientToday = await cp.evaluate(async () => (await fetch('/api/home')).json());
  check("a client's Today lists only ad status and leads: no suggestions, money or upkeep", clientToday.queue.every((r) => ['status', 'leads'].includes(r.category) && !r.proposal_id),
    clientToday.queue.map((r) => r.category).join());
  await cctx.close();

  // Client reports: the five parts, a share link without sign-in, the print layout, the scheduled email.
  await page.goto(BASE + '/report.html');
  await page.waitForSelector('.r-head');
  const rep = await page.textContent('#report');
  check('the report reads in the five parts, business result first, with its footnotes',
    /1\. What happened.*Cost per (qualified )?lead.*2\. Why.*3\. What we did.*4\. What's next.*5\. What we need from you/s.test(rep) && /attribution setting/.test(rep), rep.slice(0, 160));
  check('the first sentence measures against the target per qualified lead', /against the \$60\.00 target/.test(await page.textContent('.r-headline')));
  check('the report funnel starts from the leads received, each rate naming its base; Meta\'s count only in the ads table',
    /^Leads received/.test((await page.textContent('.r-funnel tbody tr th')).trim()) && /^Leads/.test((await page.textContent('.r-figs div:nth-child(2) span')).trim())
    && !/Leads \(Meta\)/.test(await page.textContent('.r-figs')) && (await page.$$eval('.r-funnel tbody tr td:last-child', (t) => t.slice(1).every((c) => !c.textContent.trim() || / of (Leads received|Contacted|Qualified)$/.test(c.textContent.trim()))))
    && (await page.locator('.r-ads thead th', { hasText: 'Leads (Meta)' }).count()) === (await page.locator('.r-ads').count()));
  const repWeek = await page.evaluate(async () => (await fetch('/api/reports?kind=week')).json());
  check("each change in the report is dated by the account's day, inside the period",
    repWeek.changes.every((c) => c.day >= repWeek.start && c.day <= repWeek.end), repWeek.changes.map((c) => c.day).join(' '));
  check('signed in, the report links each ad to its page', (await page.locator('.r-ads a.ent-link[href^="/ad.html?id="]').count()) === (await page.locator('.r-ads tbody tr').count())
    && (await page.locator('.r-ads tbody tr').count()) > 0);
  await page.click('#kind [data-kind="month"]');
  await page.waitForFunction(() => /Month/.test(document.querySelector('.r-kicker')?.textContent || ''));
  check('a month report covers the last complete month', /Oct 1 – Oct 31, 2026/.test(await page.textContent('.r-head')));
  // 9.4d: earlier weeks or months, a confirmation before a share link, print in plain words and print-safe colours.
  check('the month picker starts on the last complete month', /October 2026 \(last month\)/.test(await page.textContent('#period option:checked')), await page.textContent('#period option:checked'));
  await page.click('#kind [data-kind="week"]');
  await page.waitForFunction(() => /Week/.test(document.querySelector('.r-kicker')?.textContent || ''));
  await page.waitForFunction(() => /last week/.test(document.querySelector('#period option:checked')?.textContent || ''));
  const weekOpts = await page.$$eval('#period option', (o) => o.map((x) => x.value));
  check('earlier weeks can be picked, newest first, each a Monday', weekOpts.length >= 2 && weekOpts.every((v, i) => !i || v < weekOpts[i - 1]) && weekOpts.every((v) => new Date(v + 'T12:00:00').getDay() === 1), weekOpts.join());
  const headNow = await page.textContent('.r-head');
  await page.selectOption('#period', weekOpts[1]);
  await page.waitForFunction((h) => document.querySelector('.r-head')?.textContent !== h, headNow);
  const earlier = await page.evaluate(async (s) => (await fetch(`/api/reports?kind=week&start=${s}`)).json(), weekOpts[1]);
  check('an earlier week opens that week, and the address keeps it', new URL(page.url()).searchParams.get('start') === weekOpts[1] && earlier.start === weekOpts[1]
    && (await page.textContent('.r-head')).includes(await page.evaluate((iso) => new Date(iso + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' }), weekOpts[1])));
  check('the print button says what it does', (await page.textContent('#pdf')).trim() === 'Print or save as PDF');
  const sharedCount = () => sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(db.query(\\"SELECT COUNT(*) AS n FROM activity WHERE action = 'report.shared'\\", one=True)['n'])"`).trim();
  const sharesBefore = sharedCount();
  await page.click('#share');
  await page.waitForSelector('dialog.confirm #cd-cancel');
  check('Share a link asks first and says who can open it, for how long', /without signing in, for 90 days/.test(await page.textContent('dialog.confirm .confirm-body'))
    && await page.evaluate(() => document.activeElement?.id === 'cd-cancel'));
  await page.click('dialog.confirm #cd-cancel');
  await page.waitForTimeout(300);
  check('cancelling makes no link', sharedCount() === sharesBefore);
  await page.click('#share');
  await page.waitForSelector('dialog.confirm #cd-ok');
  await page.click('dialog.confirm #cd-ok');
  let sharesAfter = sharesBefore;
  for (let i = 0; i < 20 && sharesAfter === sharesBefore; i++) { await page.waitForTimeout(250); sharesAfter = sharedCount(); }
  const lastShare = JSON.parse(sh(`docker exec -w /app edgebourne-ads-backend python -c "import db,json;print(json.dumps(db.query(\\"SELECT details FROM activity WHERE action = 'report.shared' ORDER BY id DESC LIMIT 1\\", one=True)['details']))"`).trim());
  check('confirming makes one link, for the week on screen', Number(sharesAfter) === Number(sharesBefore) + 1 && lastShare.start === weekOpts[1], JSON.stringify(lastShare));
  await page.selectOption('#period', weekOpts[0]);
  await page.waitForFunction(() => !new URL(location.href).searchParams.get('start'));
  await page.click('#kind [data-kind="month"]');
  await page.waitForFunction(() => /Month/.test(document.querySelector('.r-kicker')?.textContent || ''));
  const shareUrl = await page.evaluate(async () => (await (await fetch('/api/reports/share', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"kind":"week"}' })).json()).url);
  const anonCtx = await browser.newContext();
  const anon = await anonCtx.newPage();
  await anon.goto(BASE + '/report.html?' + shareUrl.split('?')[1]);
  await anon.waitForSelector('.r-head');
  check('a share link opens the report without signing in, with no menu', /Edge Bourne/.test(await anon.textContent('.r-head')) && (await anon.locator('.rail').count()) === 0 && /This link works until/.test(await anon.textContent('.r-foot')));
  const sharedRep = await anon.evaluate(async (q) => (await fetch('/api/reports/shared?' + q)).json(), shareUrl.split('?')[1]);
  check('a shared report links nothing and carries no ids', (await anon.locator('#report a.ent-link').count()) === 0 && sharedRep.ads.every((a) => !('id' in a))
    && sharedRep.changes.every((c) => !('entity_id' in c)), JSON.stringify(sharedRep.ads[0] || {}));
  const rSeen = errors.length;
  await anon.goto(BASE + '/report.html?' + shareUrl.split('?')[1].replace(/.$/, (c) => (c === 'a' ? 'b' : 'a')));
  await anon.waitForSelector('#report .note');
  errors.splice(rSeen);
  check('a changed link is refused', /isn't valid or has expired/.test(await anon.textContent('#report')));
  await anon.emulateMedia({ media: 'print' });
  await anonCtx.close();
  await page.emulateMedia({ media: 'print' });
  check('the PDF (print) layout hides the menu and buttons', await page.isHidden('#pdf') && await page.isHidden('.rail'));
  await page.emulateMedia({ media: 'print', colorScheme: 'dark' });
  const inkOf = (sel) => page.$eval(sel, (el) => { const m = getComputedStyle(el).color.match(/\d+/g).map(Number); return (m[0] + m[1] + m[2]) / 3; });
  const printInk = [await inkOf('.rp-doc'), await inkOf('.r-foot'), await inkOf('.r-figs span')];
  check('printed from dark mode the report is still dark ink on white paper', printInk.every((v) => v < 110)
    && await page.$eval('.rp-doc', (el) => getComputedStyle(el).backgroundColor === 'rgb(255, 255, 255)'), printInk.join());
  await page.emulateMedia({ media: 'screen', colorScheme: 'light' });
  // W2: one honest funnel, and an admin reviews a client report before it goes out (account Burdanova QA,
  // its client client-qa@burdanova.test). Python runs in that account; its last printed line is JSON.
  {
  const w2Seen = errors.length;
  const A2 = leak.account2;
  const CLIENT = 'client-qa@burdanova.test';
  const mailSent = () => JSON.parse(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/mail/_sent').read().decode())"`));
  const toClient = (from) => mailSent().slice(from).filter((m) => m.to.includes(CLIENT));
  const py2 = (code) => JSON.parse(sh(`docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -c "
import account_ctx, account_info, db, settings_store, reports_api, report_logic as rl, json
from datetime import datetime, date, time, timedelta, timezone
with account_ctx.use(${A2}):
    s, e = rl.period('week', reports_api.today())
    monday = datetime.combine(e + timedelta(days=1), time(17), timezone.utc)
${code.trim().split('\n').map((l) => '    ' + l).join('\n')}"`).trim().split('\n').pop());
  const post = (url, body, p = page) => p.evaluate(async ([u, b]) => {
    const r = await fetch(u, { method: u.endsWith('/note') ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) });
    let j = null; try { j = await r.json(); } catch (err) { /* not JSON */ }
    return { status: r.status, body: j };
  }, [url, body]);
  // Last week in account 2: Meta counted 6 leads on a tagged ad, 4 reached the console (one contacted, one
  // qualified); Meta also saw the ad switched off in Ads Manager.
  const seed = py2(`
db.execute('DELETE FROM client_reports')
db.execute('DELETE FROM alerts WHERE rule = ANY(%s)', (['report_review', 'report_sent'],))
settings_store.set('report_review', None)
for sql in ('DELETE FROM ad_daily WHERE ad_id = %s', 'DELETE FROM leads WHERE ad_id = %s', 'DELETE FROM ad_tags WHERE ad_id = %s'):
    db.execute(sql, ('W2QA-ad',))  # left over from a run that stopped half way
db.execute('DELETE FROM status_events WHERE entity_id = %s AND source = %s AND field = %s AND old_value = %s AND new_value = %s', ('920000000000003', 'poll', 'configured_status', 'ACTIVE', 'PAUSED'))
base = reports_api.totals(s, e)
mid = datetime.combine(s + timedelta(days=2), time(18), timezone.utc)
db.execute('INSERT INTO ad_daily (day, ad_id, ad_name, spend_cents, impressions, leads) VALUES (%s, %s, %s, %s, %s, %s)', (s + timedelta(days=2), 'W2QA-ad', 'W2QA ad', 4800, 3000, 6))
for i, st in enumerate(['new', 'contacted', 'qualified', 'new']):
    db.execute('INSERT INTO leads (meta_lead_id, created_time, status, max_stage, ad_id, ad_name, full_name) VALUES (%s, %s, %s, %s, %s, %s, %s)', ('W2QA-%d' % i, mid, st, st, 'W2QA-ad', 'W2QA ad', 'W2QA person %d' % i))
db.execute('INSERT INTO ad_tags (ad_id, dimension, value) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING', ('W2QA-ad', 'hook', 'W2 hook'))
db.execute('INSERT INTO status_events (level, entity_id, entity_name, field, old_value, new_value, source, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)', ('ad', '920000000000003', 'ACCT2MARK ad', 'configured_status', 'ACTIVE', 'PAUSED', 'poll', mid))
print(json.dumps({'start': s.isoformat(), 'prev': (s - timedelta(days=7)).isoformat(), 'base': base}))`);
  await page.goto(`${BASE}/report.html?kind=week&acct=${A2}`);
  await page.waitForSelector('.r-head');
  const w2 = await getJson('/api/reports?kind=week');
  const expReceived = seed.base.received + 4;
  const expMeta = seed.base.meta_leads + 6;
  const gapText = (await page.locator('.r-gap').count()) ? await page.textContent('.r-gap') : '';
  check('the report funnel counts the leads received (Meta\'s count beside it, in plain words); no rate passes 100%',
    w2.funnel[0].step === 'Leads received' && w2.funnel[0].n === expReceived && w2.funnel.every((f) => f.rate === null || f.rate <= 100)
    && (await page.textContent('.r-funnel tbody tr th')).trim() === 'Leads received'
    && new RegExp(`Meta counted ${expMeta} leads; ${expMeta - expReceived} of them didn't reach your leads list`).test(gapText)
    && new RegExp(`Meta counted ${expMeta}`).test(await page.textContent('.r-figs div:nth-child(2) small')),
    `${JSON.stringify(w2.funnel)} ${gapText}`);
  const hookGroup = (w2.ideas && w2.ideas.groups || []).find((g) => g.value === 'W2 hook');
  check('the ideas in the report count qualified leads of the leads received (not of Meta\'s count)',
    !!hookGroup && hookGroup.qualified === 1 && hookGroup.received === 4 && hookGroup.leads === 6 && hookGroup.qualified_rate === 0.25, JSON.stringify(hookGroup));
  check('What we did lists a switch made in Ads Manager, dated by the account\'s day',
    w2.changes.some((c) => c.where === 'outside' && c.text === 'Ad “ACCT2MARK ad”: turned off (in Ads Manager)' && c.day >= w2.start && c.day <= w2.end)
    && /ACCT2MARK ad.*turned off \(in Ads Manager\)/.test(await page.textContent('#report')), JSON.stringify(w2.changes.slice(-3)));

  // Wait for me (the default): nothing goes out at 8 AM; one open item for this account's admins.
  const mails0 = mailSent().length;
  const waited = py2(`
settings_store.set('report_email', 'weekly')
sent = [reports_api.send_due(monday), reports_api.send_due(monday)]
row = db.query('SELECT status FROM client_reports WHERE kind = %s AND start_day = %s', ('week', s), one=True)
alert = db.query('SELECT id, level, kind, resolved_at IS NULL AS open, title, href FROM alerts WHERE rule = %s', ('report_review',), one=True)
told = db.query('SELECT n.user_id, n.button, u.account_id FROM notifications n JOIN users u ON u.id = n.user_id WHERE n.ref = %s AND n.kind = %s', (str(alert['id']), 'alert')) if alert else []
print(json.dumps({'sent': sent, 'row': row, 'alert': alert, 'told': told}, default=str))`);
  const told = waited.told.map((t) => t.user_id);
  check('waiting for review: no email at 8 AM, the week waits, one open Needs-action item and a "Review it" message to this account\'s admins only',
    waited.sent.join() === '0,0' && toClient(mails0).length === 0 && waited.row && waited.row.status === 'waiting'
    && waited.alert && waited.alert.open && waited.alert.kind === 'event' && waited.alert.level === 'warn' && waited.alert.title === 'Weekly report for Burdanova QA is waiting for you'
    && told.includes(1) && waited.told.every((t) => t.button === 'Review it' && (t.account_id === null || t.account_id === A2)) && waited.told.some((t) => t.account_id === A2),
    JSON.stringify(waited));
  const w2Inbox = await getJson('/api/inbox?box=need');
  const w2Today = await getJson('/api/home');
  check('the waiting report is in the Inbox under Needs action and on Today with the decisions',
    w2Inbox.items.some((i) => i.rule === 'report_review' && i.need && i.title === 'Weekly report for Burdanova QA is waiting for you')
    && w2Today.queue.some((r) => r.rule === 'report_review' && r.group === 'decide'), JSON.stringify(w2Today.queue.map((r) => r.rule)));
  await page.goto(`${BASE}${waited.alert.href.replace('#', `&acct=${A2}#`)}`);
  await page.waitForSelector('#rv-bar:not([hidden]) #rv-state .pill');
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'rv-note');
  check('the item opens Reports at the review bar, on the note: "Waiting for you", nothing goes out until Send',
    (await page.textContent('#rv-state .pill')).trim() === 'Waiting for you' && /Nothing goes to client-qa@burdanova\.test until you press Send\./.test(await page.textContent('#rv-state'))
    && await page.isVisible('#rv-send') && await page.isVisible('#rv-later') && await page.isVisible('#rv-skip') && await page.isHidden('#rv-hold'));

  // The client meanwhile: still being prepared, no review bar, no writes.
  const wctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
  const wc = await wctx.newPage();
  wc.on('pageerror', (e) => errors.push('w2 client: ' + e.message));
  await wc.goto(BASE + '/login.html');
  await wc.fill('#email', CLIENT); await wc.fill('#password', 'client-pass-123');
  await Promise.all([wc.waitForURL('**/home.html**'), wc.click('button[type=submit]')]);
  await wc.goto(`${BASE}/report.html?kind=week&start=${seed.start}`);
  await wc.waitForSelector('.r-head');
  const clientW2Writes = [];
  for (const u of ['/api/reports/note', '/api/reports/send', '/api/reports/hold', '/api/reports/skip', '/api/reports/resend', '/api/reports/email-preview']) {
    clientW2Writes.push((await post(u, { kind: 'week', start: seed.start, note: 'x', when: 'now', expect_to: [CLIENT] }, wc)).status);
  }
  check('a client sees "still being prepared" until it goes out, with no review bar, and can change nothing',
    /This report is still being prepared\. It will reach you by email\./.test(await wc.textContent('#report')) && (await wc.locator('#rv-bar').count()) === 0
    && clientW2Writes.every((x) => x === 403), clientW2Writes.join());
  // A send that reached nobody (mail server down) leaves no copy: the client still waits and never sees the draft note.
  // send_at an hour ahead so the running worker leaves the row to this call.
  const failedSend = py2(`
from unittest import mock
import mailer
db.execute('UPDATE client_reports SET note = %s, status = %s, send_at = now() + make_interval(hours => 1) WHERE kind = %s AND start_day = %s', ('W2QA draft note', 'scheduled', 'week', s))
rid = db.query('SELECT id FROM client_reports WHERE kind = %s AND start_day = %s', ('week', s), one=True)['id']
with mock.patch.object(mailer, 'send', side_effect=mailer.MailError('server down')):
    n = reports_api.send_row(rid, datetime.now(timezone.utc))
row = db.query('SELECT status, snapshot IS NULL AS no_copy, last_error FROM client_reports WHERE id = %s', (rid,), one=True)
print(json.dumps({'n': n, 'row': row}))`);
  await wc.reload();
  await wc.waitForSelector('.r-head');
  const failedSeen = errors.length;
  const nothingSent = await page.evaluate(async (u) => (await fetch(u)).status, `/api/reports/sent?kind=week&start=${seed.start}`);
  await page.waitForTimeout(800);
  errors.splice(failedSeen); // the 404 asked for on purpose
  check('a send that reached nobody keeps no copy: the client still waits, sees no draft note, and there is nothing to see as sent',
    failedSend.n === 0 && failedSend.row.status === 'scheduled' && failedSend.row.no_copy && failedSend.row.last_error === 'server down'
    && /still being prepared/.test(await wc.textContent('#report')) && !/W2QA draft note/.test(await wc.textContent('#report')) && nothingSent === 404,
    `${JSON.stringify(failedSend)} ${nothingSent}`);
  py2(`
db.execute('UPDATE client_reports SET note = NULL, status = %s, send_at = NULL, last_error = NULL, attempts = 0 WHERE kind = %s AND start_day = %s', ('waiting', 'week', s))
print('{}')`);
  await page.reload();
  await page.waitForSelector('#rv-bar:not([hidden]) #rv-state .pill');

  // The note shows first as it is typed; the email preview carries it before the headline; Send now sends once.
  const NOTE = 'W2QA note: N3 was turned off on Wednesday.\nTwo new videos go live this week.';
  await page.fill('#rv-note', NOTE);
  check('the note shows first in the report as it is typed, line breaks kept',
    await page.isVisible('#r-note') && (await page.$eval('#report > section', (el) => el.id)) === 'r-note' && (await page.innerText('#r-note .rv-text')).includes('Wednesday.\nTwo new'));
  await page.click('#rv-preview summary');
  await page.waitForSelector('#rv-mailbox .rv-mail');
  const mailText = await page.textContent('#rv-mailbox .rv-mail');
  check('Preview the email: to the client, the note before the headline, the link',
    /^Hi \w+,\s+W2QA note/.test(mailText) && mailText.indexOf('W2QA note') < mailText.indexOf(w2.headline)
    && mailText.includes("[the report's own link, made when it goes out]") && !/report\.html\?t=/.test(mailText)
    && /client-qa@burdanova\.test/.test(await page.textContent('#rv-mailbox')) && /Week of /.test(await page.textContent('#rv-mailbox')), mailText.slice(0, 120));
  const mails1 = mailSent().length;
  await page.click('#rv-send');
  await page.waitForSelector('dialog.confirm #cd-ok');
  const sendWords = await page.textContent('dialog.confirm');
  await page.click('dialog.confirm #cd-ok');
  const wentOut = await page.waitForFunction(() => /^Sent /.test(document.querySelector('#rv-state .pill')?.textContent || ''), null, { timeout: 25000 }).then(() => true, () => false);
  const firstMail = toClient(mails1);
  const afterSend = py2(`
print(json.dumps({'open': db.query('SELECT COUNT(*) AS n FROM alerts WHERE rule = %s AND resolved_at IS NULL', ('report_review',), one=True)['n'], 'fyi': db.query('SELECT title, level, kind FROM alerts WHERE rule = %s', ('report_sent',)), 'row': db.query('SELECT status, sent_to, note FROM client_reports WHERE kind = %s AND start_day = %s', ('week', s), one=True)}, default=str))`);
  check('Send now asks first, the worker sends one email per client starting with the note, the item closes and an FYI says it went',
    /Send the report now\?/.test(sendWords) && /client-qa@burdanova\.test with a link that works for 90 days/.test(sendWords) && wentOut
    && firstMail.length === 1 && /^Hi \w+,\r?\n\r?\nW2QA note: N3 was turned off on Wednesday\.\r?\nTwo new videos/.test(firstMail[0].text) && /: your ads report, Week of /.test(firstMail[0].subject)
    && afterSend.open === 0 && afterSend.fyi.length === 1 && afterSend.fyi[0].title === 'Weekly report sent to 1 client' && afterSend.fyi[0].level === 'info'
    && afterSend.row.status === 'sent' && afterSend.row.note === NOTE, `${wentOut} ${JSON.stringify(firstMail.map((m) => m.text.slice(0, 60)))} ${JSON.stringify(afterSend)}`);
  const refusedSeen = errors.length;
  const sentAgain = await post('/api/reports/send', { kind: 'week', start: seed.start, when: 'now', expect_to: [CLIENT] });
  await page.waitForTimeout(1500);
  errors.splice(refusedSeen); // the 409 asked for on purpose
  check('a second Send now sends nothing', sentAgain.status === 409 && toClient(mails1).length === 1, `${sentAgain.status} ${toClient(mails1).length}`);

  // What the client got is what the client sees: the frozen copy, the note first, "Figures as sent on".
  await wc.reload();
  await wc.waitForSelector('.r-foot');
  const spentSent = await wc.textContent('.r-figs div:first-child b');
  check('the client sees the copy that went out: our note first and signed, "Figures as sent on", no links',
    (await wc.$eval('#report > section', (el) => el.id)) === 'r-note' && /W2QA note/.test(await wc.textContent('#r-note')) && /— \w+/.test(await wc.textContent('#r-note'))
    && /Figures as sent on /.test(await wc.textContent('.r-foot')) && (await wc.locator('#report a.ent-link').count()) === 0);
  py2(`
db.execute('UPDATE ad_daily SET spend_cents = spend_cents + 5000 WHERE ad_id = %s', ('W2QA-ad',))
print('{}')`);
  await wc.reload();
  await wc.waitForSelector('.r-foot');
  await page.reload();
  await page.waitForSelector('#rv-bar:not([hidden]) #rv-state .pill');
  const spentNow = await page.textContent('.r-figs div:first-child b');
  check("later changes don't reach the client's copy; the admin sees today's figures with See what was sent",
    (await wc.textContent('.r-figs div:first-child b')) === spentSent && spentNow !== spentSent && await page.isVisible('#rv-sent') && await page.isVisible('#rv-resend')
    && /^Sent /.test(await page.textContent('#rv-state .pill')), `${spentSent} ${spentNow}`);
  const w2Share = (await post('/api/reports/share', { kind: 'week', start: seed.start })).body.url;
  const w2anonCtx = await browser.newContext();
  const w2anon = await w2anonCtx.newPage();
  await w2anon.goto(BASE + '/report.html?' + w2Share.split('?')[1]);
  await w2anon.waitForSelector('.r-foot');
  check('a share link for a sent period shows the same frozen copy with the note',
    /W2QA note/.test(await w2anon.textContent('#r-note')) && (await w2anon.textContent('.r-figs div:first-child b')) === spentSent && /Figures as sent on /.test(await w2anon.textContent('.r-foot')));
  await w2anonCtx.close();
  await page.click('#rv-sent');
  await page.waitForSelector('#rv-asent:not([hidden])');
  await page.waitForSelector('.r-foot');
  check('See what was sent opens the frozen copy, with the way back', /^As sent on /.test(await page.textContent('#rv-asent')) && (await page.textContent('.r-figs div:first-child b')) === spentSent
    && await page.isHidden('#rv-bar') && (await page.locator('#rv-asent a', { hasText: "Back to today's figures" }).count()) === 1);
  await page.click('#rv-asent a');
  await page.waitForSelector('#rv-bar:not([hidden]) #rv-note');

  // A note edited after sending: the client's copy shows the new words, and no email goes.
  const mails2 = mailSent().length;
  await page.fill('#rv-note', 'W2QA note, reworded after sending.');
  await page.click('#rv-note-save');
  const editedToast = await page.waitForFunction(() => /no new email was sent/.test(document.querySelector('.toast')?.textContent || ''), null, { timeout: 8000 }).then(() => true, () => false);
  await wc.reload();
  await wc.waitForSelector('#r-note');
  await page.waitForTimeout(1000);
  check('editing the note after sending changes the client\'s copy and sends nothing', editedToast && /reworded after sending/.test(await wc.textContent('#r-note')) && toClient(mails2).length === 0);
  const refusedSeen2 = errors.length;
  const stale = await post('/api/reports/note', { kind: 'week', start: seed.start, note: 'from an old tab', note_at: '2020-01-01T00:00:00+00:00' });
  const listChanged = await post('/api/reports/send', { kind: 'week', start: seed.prev, when: 'now', expect_to: ['someone-else@example.com'] });
  errors.splice(refusedSeen2); // the two 409s asked for on purpose
  check('a note saved from an older copy and a send to a client list that changed are refused in plain words',
    stale.status === 409 && /Someone else changed this note/.test(stale.body.error) && listChanged.status === 409 && /The client list changed/.test(listChanged.body.error)
    && JSON.stringify(listChanged.body.to) === JSON.stringify([CLIENT]), `${stale.status} ${listChanged.status} ${JSON.stringify(listChanged.body)}`);

  // An older week no one decided on reads "Not sent" (nothing waits for it); one held back still waits.
  const olderState = (await getJson(`/api/reports?kind=week&start=${seed.prev}`)).review;
  check('an older week that was never emailed reads "Not sent", with Send now and no Don\'t send',
    olderState.status === 'not_sent' && olderState.pill[1] === 'Not sent' && olderState.actions.join() === 'send_now,send_later', JSON.stringify(olderState));
  py2(`
db.execute('INSERT INTO client_reports (kind, start_day, end_day, status) VALUES (%s, %s, %s, %s)', ('week', s - timedelta(days=7), s - timedelta(days=1), 'waiting'))
print('{}')`);
  // Don't send this one, with Undo (the week before, held back and waiting).
  await page.goto(`${BASE}/report.html?kind=week&start=${seed.prev}`);
  await page.waitForSelector('#rv-bar:not([hidden]) #rv-skip:not([hidden])');
  await page.click('#rv-skip');
  await page.waitForSelector('.toast .toast-act');
  const skipWords = `${await page.textContent('.toast')} | ${await page.textContent('#rv-state .pill')}`;
  await page.click('.toast .toast-act');
  const undone = await page.waitForFunction(() => /Waiting for you/.test(document.querySelector('#rv-state .pill')?.textContent || ''), null, { timeout: 8000 }).then(() => true, () => false);
  check("Don't send this one says so with Undo, and Undo puts it back to waiting", /This report won't be sent\..*\| Not sending/.test(skipWords) && undone, skipWords);

  // Phones: arriving from the Inbox item the bar's status is below the sticky header, not under it.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${BASE}/report.html?kind=week&start=${seed.prev}&acct=${A2}#review`);
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === 'rv-note');
  await page.waitForTimeout(300);
  const arrival = await page.evaluate(() => {
    const under = Math.max(0, ...[...document.querySelectorAll('.topbar, .subnav, .page-head')].filter((el) => {
      const cs = getComputedStyle(el);
      return (cs.position === 'sticky' || cs.position === 'fixed') && cs.display !== 'none';
    }).map((el) => el.getBoundingClientRect().bottom));
    return { under, state: document.getElementById('rv-state').getBoundingClientRect().top, scrolled: window.scrollY };
  });
  check('on a phone, opening the review item shows the status line below the header', arrival.state >= arrival.under, JSON.stringify(arrival));
  // Phones: the bar stacks, full-width 44px buttons, a 16px note field, nothing past the edge; never printed.
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await page.waitForTimeout(300);
    const phone = await page.evaluate(() => ({
      heights: ['rv-send', 'rv-later', 'rv-skip', 'rv-note-save'].map((id) => document.getElementById(id).getBoundingClientRect().height),
      full: ['rv-send', 'rv-later'].every((id) => Math.abs(document.getElementById(id).getBoundingClientRect().width - document.getElementById('rv-acts').getBoundingClientRect().width) < 2),
      font: getComputedStyle(document.getElementById('rv-note')).fontSize,
      over: document.documentElement.scrollWidth - window.innerWidth,
    }));
    check(`the review bar at ${width}px: buttons at least 44px tall and full width, a 16px note, nothing past the edge`,
      phone.heights.every((h) => h >= 44) && phone.full && phone.font === '16px' && phone.over <= 0, JSON.stringify(phone));
    if (width === 390) await page.screenshot({ path: `${OUT}/w2-review-390.png`, fullPage: false });
  }
  await page.setViewportSize({ width: 1360, height: 900 });
  await page.emulateMedia({ media: 'print' });
  check('the review bar is never printed', await page.isHidden('#rv-bar'));
  await page.emulateMedia({ media: 'screen' });

  // Settings: send without my review, kept after a reload.
  await openSettings('reports-panel');
  await page.check('#rep-review-auto');
  await page.click('#rep-form button[type=submit]');
  await page.waitForFunction(() => /Report settings saved/.test(document.querySelector('.toast')?.textContent || ''));
  await openSettings('reports-panel');
  await page.waitForFunction(() => /sent by itself/.test(document.getElementById('rep-state')?.textContent || ''));
  check('Settings: "Send it without my review" is kept, and the pill says "Weekly · sent by itself"',
    await page.isChecked('#rep-review-auto') && (await page.textContent('#rep-state')).trim() === 'Weekly · sent by itself');

  // Without review: before 8 AM it would go by itself at 8; Hold stops it; Send at 8 AM sends at the next 8 AM;
  // with no row it goes once (the behaviour before W2).
  // The week as the worker set it to go out by itself (an hour from now, so the running worker leaves it alone).
  const autoNow = py2(`
db.execute('DELETE FROM client_reports')
db.execute('INSERT INTO client_reports (kind, start_day, end_day, status, send_at) VALUES (%s, %s, %s, %s, now() + make_interval(hours => 1))', ('week', s, e, 'scheduled'))
at = reports_api.auto_at('week', s, e, None, datetime.combine(e + timedelta(days=1), time(7), account_info.tz()))
print(json.dumps({'at': at.isoformat() if at else None, 'day': (e + timedelta(days=1)).isoformat()}))`);
  const held = await post('/api/reports/hold', { kind: 'week', start: seed.start });
  const heldSent = py2(`print(json.dumps([reports_api.send_due(monday), db.query('SELECT COUNT(*) AS n FROM alerts WHERE dedupe_key = %s AND resolved_at IS NULL', ('report_review:week:' + s.isoformat(),), one=True)['n']]))`);
  // Send at 8 AM with a note typed, then edit the note again: it saves (no false "someone else changed it").
  await page.goto(`${BASE}/report.html?kind=week&start=${seed.start}&acct=${A2}`);
  await page.waitForSelector('#rv-bar:not([hidden]) #rv-later:not([hidden])');
  await page.fill('#rv-note', 'W2QA note for 8 AM.');
  await page.click('#rv-later');
  await page.waitForSelector('dialog.confirm #cd-ok');
  await page.click('dialog.confirm #cd-ok');
  await page.locator('.toast', { hasText: 'Set to go out on' }).first().waitFor({ timeout: 8000 });
  await page.fill('#rv-note', 'W2QA note for 8 AM, edited.');
  await page.click('#rv-note-save');
  const resaved = await page.locator('.toast', { hasText: 'Note saved' }).first().waitFor({ timeout: 8000 }).then(() => true, () => false);
  check('after Send at 8 AM the note can be edited and saved again', resaved && !(await page.locator('.toast', { hasText: 'Someone else changed' }).count()));
  const later = { body: await getJson(`/api/reports?kind=week&start=${seed.start}`) };
  const mails3 = mailSent().length;
  const laterSent = py2(`
row = db.query('SELECT send_at FROM client_reports WHERE kind = %s AND start_day = %s', ('week', s), one=True)
local = row['send_at'].astimezone(account_info.tz())
print(json.dumps({'early': reports_api.send_due(row['send_at'] - timedelta(minutes=1)), 'due': reports_api.send_due(row['send_at'] + timedelta(minutes=1)), 'hour': local.hour, 'minute': local.minute}))`);
  check('without review: at 8 AM by itself; Hold keeps it back; Send at 8 AM goes at the next 8 AM, once',
    autoNow.at && autoNow.at.startsWith(`${autoNow.day}T08:00`) && held.body.review.status === 'waiting' && heldSent.join() === '0,1'
    && later.body.review.status === 'scheduled' && laterSent.early === 0 && laterSent.due === 1 && laterSent.hour === 8 && laterSent.minute === 0 && toClient(mails3).length === 1,
    `${JSON.stringify(autoNow)} ${JSON.stringify(held.body && held.body.review && held.body.review.status)} ${heldSent} ${JSON.stringify(laterSent)}`);
  const mails4 = mailSent().length;
  const autoOnce = py2(`
db.execute('DELETE FROM client_reports')
print(json.dumps([reports_api.send_due(monday), reports_api.send_due(monday)]))`);
  const m = toClient(mails4)[0];
  check("without review and no row, Monday's email goes to the account's clients once, with a link that works",
    autoOnce.join() === '1,0' && !!m && /report\.html\?t=/.test(m.text) && /Burdanova QA/.test(m.subject), `${autoOnce} ${JSON.stringify(m || {}).slice(0, 160)}`);

  py2(`
for sql in ('DELETE FROM client_reports', 'DELETE FROM ad_daily WHERE ad_id = %s', 'DELETE FROM leads WHERE ad_id = %s', 'DELETE FROM ad_tags WHERE ad_id = %s'):
    db.execute(sql, ('W2QA-ad',) if '%s' in sql else None)
db.execute('DELETE FROM alerts WHERE rule = ANY(%s)', (['report_review', 'report_sent'],))
db.execute('DELETE FROM status_events WHERE entity_id = %s AND source = %s AND field = %s AND old_value = %s AND new_value = %s', ('920000000000003', 'poll', 'configured_status', 'ACTIVE', 'PAUSED'))
settings_store.set('report_email', None); settings_store.set('report_review', None)
print('{}')`);
  // An account that doesn't email reports (wait for me is the default): its client reads the report in the console.
  await wc.goto(`${BASE}/report.html?kind=week&start=${seed.start}`);
  await wc.waitForSelector('.r-head');
  check("a client of an account that doesn't email reports still reads the report (nothing would ever release it)",
    (await wc.locator('.r-foot').count()) === 1 && !/still being prepared/.test(await wc.textContent('#report')));
  await wctx.close();
  await page.evaluate(() => fetch('/api/accounts/switch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: 1 }) }));
  check('the report review pages log no console errors', errors.length === w2Seen, errors.slice(w2Seen).join(' | '));
  }


  // Ad blockers hide elements whose class or id looks like an ad (EasyList: .ad-cell, .adset, #ads-panel …).
  // An ads console is full of them, so no class or id may start with ad- / ads- / adset / advert / sponsor / banner / promo.
  const risky = [];
  const riskyFiles = [];
  for (const p of ['home.html', 'inbox.html', 'ads.html', 'ads.html?level=campaign', 'campaign.html?id=120252638288040312', 'adset.html?id=120252672227950312',
    'compare.html?ids=120252672232030312,120252672233160312', 'ad.html?id=120252672229400312', 'performance.html', 'new-campaign.html', 'new-ad.html', 'new-adset.html', 'desk.html']) {
    await page.goto(BASE + '/' + p);
    riskyFiles.push(...(await page.evaluate(() => performance.getEntriesByType('resource').map((r) => new URL(r.name).pathname)
      .filter((u) => /\/(ad|ads|adset|advert|banner|sponsor|promo)[-_.]|[-_](ad|ads)\.js/i.test(u)))).map((u) => `${p}: ${u}`));
    await page.waitForTimeout(1500);
    risky.push(...(await page.evaluate(() => [...document.querySelectorAll('[class], [id]')].flatMap((e) => [...(typeof e.className === 'string' ? e.className.split(/\s+/) : []), e.id])
      .filter((n) => /^(ad|ads|adset|adsets|advert|advertisement|sponsor|sponsored|banner|promo|promoted)([-_]|$)/i.test(n)))).map((n) => `${p}: ${n}`));
  }
  check('no class or id an ad blocker would hide', risky.length === 0, [...new Set(risky)].slice(0, 6).join(' | '));
  check('no script or stylesheet path an ad blocker would block', riskyFiles.length === 0, [...new Set(riskyFiles)].slice(0, 6).join(' | '));

  {
  const a2Seen = errors.length;
  // Audit 2 (2026-11-10): money checks on the server, one apply per click, accounts in links, closed
  // accounts and links, client access, console-wide settings, health, the cross-site guard, phonePage width.
  const call = (method, url, body, headers) => page.evaluate(async ([m, u, b, h]) => {
    const r = await fetch(u, { method: m, headers: { 'Content-Type': 'application/json', ...(h || {}) }, body: b === undefined ? undefined : JSON.stringify(b) });
    let j = null; try { j = await r.json(); } catch (e) { /* not JSON */ }
    return { status: r.status, body: j };
  }, [method, url, body, headers]);
  const CAMP = '120252638288040312';
  const seeded = JSON.parse(sh('docker cp dev/qa_audit2.py edgebourne-ads-backend:/app/qa_audit2.py && docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python qa_audit2.py; docker exec edgebourne-ads-backend rm -f /app/qa_audit2.py').trim().split('\n').pop());
  const want = Math.round(seeded.live * 1.2 / 100) * 100;
  const budgetPlan = await call('GET', `/api/proposals/${seeded.budget}/check`);
  check("a budget proposal is read for its new amount (not the first number) against Meta's live budget",
    budgetPlan.status === 200 && budgetPlan.body.from === seeded.live && budgetPlan.body.to === want, JSON.stringify(budgetPlan.body));
  await page.goto(BASE + '/desk.html#waiting');
  await page.waitForSelector(`[data-proposal="${seeded.budget}"] [data-accept]`);
  await page.click(`[data-proposal="${seeded.budget}"] [data-accept]`);
  await page.waitForSelector('dialog.accept-sheet #cd-ok:not(:empty)');
  const budgetRow = page.locator('dialog.accept-sheet .sheet-item', { hasText: await page.getAttribute(`[data-proposal="${seeded.budget}"]`, 'data-title') });
  const dlg = (await budgetRow.textContent()).replace(/\s+/g, ' ');
  check('accepting shows the live budget → the new one in dollars', dlg.includes(`$${(seeded.live / 100).toFixed(2)}`) && dlg.includes(`$${(want / 100).toFixed(2)}`), dlg);
  await budgetRow.locator('input').check();
  await page.click('dialog.accept-sheet #cd-ok');
  await page.waitForFunction(() => document.querySelector('dialog.accept-sheet #cd-ok')?.textContent === 'Done', null, { timeout: 30000 });
  await page.click('dialog.accept-sheet #cd-ok');
  const budgetAfter = Number(sh(`docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -c "import meta_client;print(meta_client.get('${CAMP}', fields='daily_budget')['daily_budget'])"`).trim());
  check('and Meta gets exactly that amount', budgetAfter === want, `${budgetAfter}`);
  const unclear = await call('POST', `/api/proposals/${seeded.unclear}/approve`, {});
  check("an unclear amount from Claude is refused, not guessed", unclear.status === 400 && /isn't one clear amount/.test(unclear.body.error), JSON.stringify(unclear.body));
  const twiceStatus = await page.evaluate(async (id) => (await Promise.all([1, 2].map(() => fetch(`/api/proposals/${id}/approve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })))).map((r) => r.status).sort(), seeded.double);
  check('approving twice at once applies once (the second is refused)', twiceStatus.join() === '200,409', twiceStatus.join());
  await call('POST', '/api/ads/ad/120252672229400312/status', { status: 'ACTIVE', confirm_daily_cents: (await call('GET', '/api/ads/ad/120252672229400312/spend')).body.daily_cents });
  const unconfirmed = await call('POST', '/api/ads/ad/120252672229400312/status', { status: 'ACTIVE' });
  const offFirst = await call('POST', '/api/ads/ad/120252672230740312/status', { status: 'PAUSED' });
  const onBlind = await call('POST', '/api/ads/ad/120252672230740312/status', { status: 'ACTIVE' });
  const spendCtx = await call('GET', '/api/ads/ad/120252672230740312/spend');
  const onSeen = await call('POST', '/api/ads/ad/120252672230740312/status', { status: 'ACTIVE', confirm_daily_cents: spendCtx.body.daily_cents });
  check('turning on needs the daily spend seen first (read fresh from Meta)', offFirst.status === 200 && onBlind.status === 409 && spendCtx.body.daily_cents > 0 && onSeen.status === 200,
    `${offFirst.status} ${onBlind.status} ${JSON.stringify(spendCtx.body)} ${onSeen.status} ${unconfirmed.status}`);
  // Audit 3: a pause Claude proposed is sent even when the stored status already says off (Meta is read first).
  const dbq3 = (py) => sh(`docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -c "import db;${py}"`).trim();
  const fakeSet = (id, body) => sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;urllib.request.urlopen(urllib.request.Request('http://localhost:5001/v24.0/${id}?access_token=x', data=b'${body}'))"`);
  const N3ID = '120252672230740312';
  dbq3(`db.execute('UPDATE ads SET status = %s WHERE id = %s', ('PAUSED', '${N3ID}'))`);
  const stalePlan = await call('GET', `/api/proposals/${seeded.stale}/check`);
  const stale = await call('POST', `/api/proposals/${seeded.stale}/approve`, {});
  const staleLogged = dbq3(`print(db.query('SELECT COUNT(*) AS n FROM meta_changes WHERE proposal_id = %s AND ok', (${seeded.stale},), one=True)['n'])`);
  check('approving a pause reads Meta first: a stale "off" in the console still turns it off on Meta', stalePlan.body.from === 'ACTIVE' && !stalePlan.body.already
    && stale.status === 200 && metaObj(N3ID).status === 'PAUSED' && staleLogged === '1', `${JSON.stringify(stalePlan.body)} ${stale.status} ${metaObj(N3ID).status} ${staleLogged}`);
  // Already off on Meta (read just now): the Accept sheet says nothing is sent, and approving sends nothing.
  const seedProp = (title, status) => Number(dbq3(`print(db.execute(\\"INSERT INTO desk_proposals (task_id, kind, title, entity_type, entity_id, entity_name, field, current_value, proposed_value, status) SELECT task_id, 'status', '${title}', 'ad', entity_id, entity_name, 'status', 'ACTIVE', 'PAUSED', '${status}' FROM desk_proposals WHERE id = ${seeded.stale} RETURNING id\\", returning=True)['id'])`));
  const alreadyId = seedProp('QA pause what Meta already has off', 'pending');
  const unknownId = seedProp('QA pause Meta did not answer', 'unknown');
  const a2Task = dbq3(`print(db.query('SELECT task_id FROM desk_proposals WHERE id = %s', (${seeded.stale},), one=True)['task_id'])`);
  await page.goto(BASE + '/desk.html#waiting');
  await page.waitForSelector(`[data-proposal="${alreadyId}"] [data-accept]`);
  await page.click(`[data-proposal="${alreadyId}"] [data-accept]`);
  const alreadySaid = await page.waitForFunction(() => /already off on Meta, so nothing is sent/.test(document.querySelector('dialog.accept-sheet')?.textContent || ''), null, { timeout: 15000 }).then(() => true, () => false);
  await page.click('dialog.accept-sheet #cd-cancel');
  const alreadyApprove = await call('POST', `/api/proposals/${alreadyId}/approve`, {});
  const alreadyWrites = dbq3(`print(db.query('SELECT COUNT(*) AS n FROM meta_changes WHERE proposal_id = %s', (${alreadyId},), one=True)['n'])`);
  check('a pause Meta already has says so in the Accept sheet, and approving it sends nothing', alreadySaid && alreadyApprove.status === 200
    && alreadyWrites === '0' && metaObj(N3ID).status === 'PAUSED', `${alreadySaid} ${alreadyApprove.status} ${alreadyWrites}`);
  // A write Meta didn't answer: shown as "check Ads Manager" and never approved again.
  await page.goto(BASE + `/desk.html#r/${a2Task}`);
  const unknownShown = await page.waitForFunction(() => [...document.querySelectorAll('.pill.warn')].some((el) => /Meta didn't answer: check Ads Manager/.test(el.textContent)), null, { timeout: 15000 }).then(() => true, () => false);
  const unknownAgain = await call('POST', `/api/proposals/${unknownId}/approve`, {});
  check('a proposal Meta did not answer shows "check Ads Manager" and cannot be approved again', unknownShown && unknownAgain.status === 409, `${unknownShown} ${unknownAgain.status}`);
  // A lifetime budget needs the same confirmation as a daily one, with the amount shown.
  fakeSet(CAMP, 'daily_budget=&lifetime_budget=150000&end_time=2030-01-01T00:00:00%2B0000');
  const lifeBlind = await call('POST', `/api/ads/ad/${N3ID}/status`, { status: 'ACTIVE' });
  const lifeDaily = await call('POST', `/api/ads/ad/${N3ID}/status`, { status: 'ACTIVE', confirm_daily_cents: 150000 });
  const lifeSpend = await call('GET', `/api/ads/ad/${N3ID}/spend`);
  const lifeOn = await call('POST', `/api/ads/ad/${N3ID}/status`, { status: 'ACTIVE', confirm_lifetime_cents: lifeSpend.body.lifetime_cents });
  fakeSet(CAMP, `daily_budget=${budgetAfter}&lifetime_budget=&end_time=`);
  check('turning on from a lifetime budget shows the total and needs it echoed', lifeBlind.status === 409 && lifeDaily.status === 409
    && lifeSpend.body.lifetime_cents === 150000 && !lifeSpend.body.daily_cents && lifeSpend.body.holder === CAMP && lifeOn.status === 200 && metaObj(N3ID).status === 'ACTIVE',
    `${lifeBlind.status} ${lifeDaily.status} ${JSON.stringify(lifeSpend.body)} ${lifeOn.status}`);
  // The budget dialog's "from" is checked against Meta's live budget even when the stored one is current.
  const staleFrom = await call('POST', `/api/ads/campaign/${CAMP}/budget`, { daily_budget_cents: budgetAfter + 100, from_cents: budgetAfter + 900 });
  const noFrom = await call('POST', `/api/ads/campaign/${CAMP}/budget`, { daily_budget_cents: budgetAfter + 100 });
  check('a budget change from an amount the page showed but Meta no longer has is refused', staleFrom.status === 409 && noFrom.status === 409
    && Number(metaObj(CAMP).daily_budget) === budgetAfter, `${staleFrom.status} ${noFrom.status} ${JSON.stringify(staleFrom.body)}`);
  const huge = await call('POST', `/api/ads/campaign/${CAMP}/budget`, { daily_budget_cents: 50000, from_cents: budgetAfter, accept_big: true });
  check("a budget above the account's ceiling is refused even when confirmed", huge.status === 400 && /ceiling/.test(huge.body.error), JSON.stringify(huge.body));
  const jump = await call('POST', `/api/ads/campaign/${CAMP}/budget`, { daily_budget_cents: budgetAfter * 2, from_cents: budgetAfter });
  check('more than +20% needs a knowing yes', jump.status === 409 && /\+20%/.test(jump.body.error), JSON.stringify(jump.body));
  const csrf = await call('POST', '/api/refresh', undefined, { 'Content-Type': 'text/plain', 'X-Requested-With': 'elsewhere' });
  check("a write that didn't come from the console is refused (cross-site guard)", csrf.status === 403, `${csrf.status}`);
  const health = await call('GET', '/api/health');
  check('health says the database and the worker are fine', health.status === 200 && health.body.status === 'ok', JSON.stringify(health.body));
  // Account 2: console-wide keys refused there; an alert link opens in its account.
  await page.goto(BASE + `/leads.html?acct=${leak.account2}`);
  await page.waitForSelector('#acct-rail');
  check('a link from an alert switches to the account it names', (await page.inputValue('#acct-rail')) === String(leak.account2) && !/acct=/.test(page.url()), page.url());
  const sharedKeys = await call('PUT', '/api/settings/meta', { meta_app_secret: 'x'.repeat(32) });
  check("Meta's app keys can't be changed from another account's Settings", sharedKeys.status === 403, JSON.stringify(sharedKeys.body));
  await openSettings('email');
  await page.waitForSelector('#console-note:not([hidden])');
  check('Settings marks the console-wide part and locks it outside Edge Bourne', await page.isDisabled('#smtp-form button[type=submit]'));
  // Client access: off by default, on in Settings, only the stage.
  const lead2 = seeded.lead2;
  const cl = await (await browser.newContext({ viewport: { width: 1360, height: 900 } })).newPage();
  await cl.goto(BASE + '/login.html');
  await cl.fill('#email', 'client-qa@burdanova.test'); await cl.fill('#password', 'client-pass-123');
  await Promise.all([cl.waitForURL('**/home.html**'), cl.click('button[type=submit]')]);
  const clientCall = (method, url, body) => cl.evaluate(async ([m, u, b]) => (await fetch(u, { method: m, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) })).status, [method, url, body]);
  const stageBefore = await clientCall('PATCH', `/api/leads/${lead2}`, { status: 'contacted' });
  await call('PUT', '/api/settings/client-access', { update_leads: true });
  const granted = await clientCall('PATCH', `/api/leads/${lead2}`, { status: 'contacted' });
  const ownerStatus = await clientCall('PATCH', `/api/leads/${lead2}`, { owner_id: 1 });
  await call('PUT', '/api/settings/client-access', { update_leads: false });
  check('clients move lead stages only when the account allows it, and nothing else', `${stageBefore} ${granted} ${ownerStatus}` === '403 200 403', `${stageBefore} ${granted} ${ownerStatus}`);
  // Share links stop on demand and when the account closes; the client loses access while it's closed.
  const link2 = (await call('POST', '/api/reports/share', { kind: 'week' })).body.url;
  const anon2 = await (await browser.newContext()).newPage();
  const openLink = async () => anon2.evaluate(async (u) => (await fetch('/api/reports/shared?' + u.split('?')[1])).status, link2);
  await anon2.goto(BASE + '/login.html');
  const okBefore = await openLink();
  await call('POST', '/api/reports/revoke', {});
  const okAfter = await openLink();
  check('"Stop all shared links" stops the old ones', okBefore === 200 && okAfter === 404, `${okBefore} ${okAfter}`);
  const link3 = (await call('POST', '/api/reports/share', { kind: 'week' })).body.url;
  await call('PATCH', `/api/accounts/${leak.account2}`, { archived: true });
  const closedLink = await anon2.evaluate(async (u) => (await fetch('/api/reports/shared?' + u.split('?')[1])).status, link3);
  const closedClient = await clientCall('GET', '/api/leads');
  await call('PATCH', `/api/accounts/${leak.account2}`, { archived: false });
  const reopened = await anon2.evaluate(async (u) => (await fetch('/api/reports/shared?' + u.split('?')[1])).status, link3);
  check('closing an account stops its links and its people, reopening brings them back', `${closedLink} ${closedClient} ${reopened}` === '404 403 200', `${closedLink} ${closedClient} ${reopened}`);
  await call('POST', '/api/accounts/switch', { id: 1 });
  check('admins of one account and members stay in their account (leak test)', leak.leaks_member_and_account_admin.length === 0
    && Object.values(leak.account_admin_limits).every((s) => s === 403) && leak.cross_account_writes.length === 0 && leak.cross_account_writes_changed_account1 === false,
    JSON.stringify(leak.account_admin_limits) + leak.cross_account_writes.join(' | ') + (leak.cross_account_writes_changed_account1 ? ' account 1 changed' : ''));
  check('background work started from one account stays in that account', leak.resync_thread_account.join() === String(leak.account2) && leak.account2_assignments_seen_from_1 === 0);
  check("an account's leads, alerts and Meta assets stay its own (recipients, Page routing, duplicate check, Claude's proposals, Telegram errors)",
    leak.tenant_problems.length === 0, leak.tenant_problems.join(' | '));
  // A new ad from nothing: the account's Page, the chosen form, an image from the library.
  const libItem = (await call('GET', '/api/media')).body.items.find((i) => i.kind === 'image' || (i.kind === 'video' && i.ready));
  const crBefore = Object.keys(fake('_creatives')).length;
  const scratch = await call('POST', '/api/ads/new', { adset_id: '120252672227950312', name: 'QA scratch ad', body: 'New words', title: 'New headline',
    media: libItem.kind === 'image' ? { kind: 'image', hash: libItem.hash } : { kind: 'video', video_id: libItem.video_id }, form_id: '1132280359202136' });
  const scr = Object.values(fake('_creatives')).slice(crBefore)[0];
  check('a new ad can start from nothing: the Page, the chosen form, its own image or video', scratch.status === 201 && scr && scr.object_story_spec.page_id
    && (scr.object_story_spec.link_data || scr.object_story_spec.video_data).call_to_action.value.lead_gen_form_id === '1132280359202136', JSON.stringify(scr && scr.object_story_spec).slice(0, 200));
  // 8.1 Status history: Meta's review of an ad (in review → rejected → fixed) lands on its History tab,
  // and the console's own on/off from flow 1 is marked as made here, by whom.
  const N3 = '120252672230740312';
  const pull = () => sh(`docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -c "import insights; insights.sync_structure()"`);
  for (const to of ['IN_PROCESS', 'DISAPPROVED', 'ACTIVE']) {
    sh(`docker exec edgebourne-ads-backend python -c "import requests;requests.get('http://fake-meta:5001/fake/_review?ad=${N3}&to=${to}')"`);
    pull();
    if (to === 'DISAPPROVED') {
      // 9.4c: the Overview leads with the status in words, Meta's reason and the way to fix it.
      await page.goto(BASE + `/ad.html?id=${N3}`);
      await page.waitForSelector('#cr-state');
      const st = (await page.textContent('#cr-state')).replace(/\s+/g, ' ');
      check("a rejected ad's Overview opens on Rejected with Meta's reason and a way to fix it", (await page.locator('#cr-state.tone-bad').count()) === 1
        && /Rejected/.test(st) && (await page.locator('#cr-state .cs-reasons li').count()) > 0 && (await page.locator('#cr-state [data-goto="polish"]').count()) === 1, st.slice(0, 200));
    }
  }
  await page.goto(BASE + `/ad.html?id=${N3}#tab=history`);
  await page.reload();  // the Overview was just open: a change of hash alone doesn't load the page again
  await page.waitForSelector('#cr-main ol.tl');
  const n3Timeline = await page.locator('#cr-main ol.tl').innerText();
  check('Meta review steps show on the ad\'s History tab in plain words', ['Sent to review', 'Rejected', 'Personal attributes', 'Fixed · delivering again'].every((w) => n3Timeline.includes(w))
    && !/Fixed · delivering again\s*\n\s*by /.test(n3Timeline), n3Timeline.replace(/\n+/g, ' | ').slice(0, 300));
  const fixedBy = await page.locator('#cr-main ol.tl li', { hasText: 'Fixed · delivering again' }).first().locator('small').last().textContent();
  check("Meta's own steps are credited to Meta", fixedBy.trim() === 'Meta', fixedBy);
  // Claude's decided suggestions: the line about the campaign links there, jumps to its card, and owners get the conversation.
  const jumps = page.locator('#cr-main ol.tl [data-jump]');
  if (await jumps.count()) {
    const target = await jumps.first().getAttribute('data-jump');
    await jumps.first().click();
    await page.waitForSelector(`#${target}.flash`);
    check("a suggestion's line in the History jumps to its card below", await page.evaluate((id) => document.activeElement?.id === id, target), target);
    check('a suggestion about the campaign links to it, and the owner gets its conversation with Claude',
      (await page.locator('#cr-main ol.tl li[data-source="claude"] a.ent-link[href^="/campaign.html?id="]').count()) > 0 && (await page.locator('#cr-main ol.tl a[href^="/desk.html#r/"]').count()) > 0);
  } else check("a suggestion's line in the History jumps to its card below", false, 'no decided suggestion on N3');
  {
    const n3 = (await call('GET', `/api/ads/ad/${N3}`)).body;
    const advice = n3.history.filter((i) => /Meta's advice/.test(i.title));
    check("Meta's advice in the History says what changed, money included, and names the campaign by its own name",
      advice.some((i) => /^Applied Meta's advice: .+\(\+\$6\.00 a day\)$/.test(i.title))
      && advice.every((i) => i.on && i.on.level === 'campaign' && i.on.name === n3.ad.campaign_name),
      advice.slice(0, 2).map((i) => `${i.title} / ${JSON.stringify(i.on)}`).join(' | '));
  }
  const again = (await call('GET', `/api/ads/ad/${N3}`)).body.timeline.length;
  pull();
  check('a repeat refresh records nothing new', (await call('GET', `/api/ads/ad/${N3}`)).body.timeline.length === again);
  // 8.2 Status alerts reach the Inbox: the rejection (with Meta's reason) and an approval; reading one lowers the count.
  sh(`docker exec edgebourne-ads-backend python -c "import requests;requests.get('http://fake-meta:5001/fake/_review?ad=120252672233160312&to=IN_PROCESS')"`);
  pull();
  sh(`docker exec edgebourne-ads-backend python -c "import requests;requests.get('http://fake-meta:5001/fake/_review?ad=120252672233160312&to=ACTIVE')"`);
  pull();
  const box = (await call('GET', '/api/inbox?filter=all&kind=status')).body;
  const rejected = box.items.find((i) => i.title.startsWith('Meta rejected') && i.entity_id === N3);
  const approved = box.items.find((i) => i.title.startsWith('Meta approved') && i.entity_id === '120252672233160312');
  check('a rejection reaches the Inbox with Meta\'s reason, an approval too', !!rejected && /Personal attributes/.test(rejected.lines[0]) && !!approved,
    box.items.slice(0, 4).map((i) => i.title).join(' | '));
  const unreadBefore = (await call('GET', '/api/refresh')).body.inbox_unread;
  await call('POST', '/api/inbox/read', { keys: [approved.key] });
  check('marking an Inbox item read lowers the unread count by one', (await call('GET', '/api/refresh')).body.inbox_unread === unreadBefore - 1);
  // 8.3 Instant status updates: the switch subscribes the app and the ad account; a signed webhook makes the
  // worker read the ad again within seconds (no poll), records it as from Meta and raises the alert.
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import settings_store as s; s.set('meta_app_id','1626330625641508'); s.set('meta_verify_token','qa-verify-token')"`);
  const hooksOn = await call('POST', '/api/settings/meta/status-updates', { on: true });
  const subs = fake('_subscriptions');
  check('turning on instant status updates subscribes the app (app token) and installs it on the ad account',
    hooksOn.status === 200 && subs.app.ad_account && subs.app.ad_account.app_token && subs.app.ad_account.fields.includes('with_issues_ad_objects') && subs.accounts.length === 1, JSON.stringify(subs));
  const N1 = '120252672229040312';
  sh(`docker exec edgebourne-ads-backend python -c "import requests;requests.get('http://fake-meta:5001/fake/_review?ad=${N1}&to=DISAPPROVED')"`);
  sh(`docker cp dev/status_webhook.py edgebourne-ads-backend:/tmp/status_webhook.py`);
  const hookResp = sh(`docker exec -w /app edgebourne-ads-backend python /tmp/status_webhook.py ${N1} with_issues_ad_objects`);
  let viaHook = null;
  for (let i = 0; i < 20 && !viaHook; i++) {
    await page.waitForTimeout(500);
    viaHook = (await call('GET', `/api/ads/ad/${N1}`)).body.timeline.find((r) => r.source === 'webhook' && r.new_value === 'DISAPPROVED');
  }
  check('a signed status webhook is read within seconds and recorded as from Meta', !!viaHook, hookResp.trim());
  const unsigned = await page.evaluate(async () => (await fetch('/webhooks/meta', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"object":"ad_account","entry":[]}' })).status);
  check('an unsigned status webhook is refused', unsigned === 403);
  const hooksOff = await call('POST', '/api/settings/meta/status-updates', { on: false });
  check('turning it off removes the ad account, keeps polling', hooksOff.status === 200 && fake('_subscriptions').accounts.length === 0);
  sh(`docker exec edgebourne-ads-backend python -c "import requests;requests.get('http://fake-meta:5001/fake/_review?ad=${N1}&to=ACTIVE')"`);
  pull();
  await page.goto(BASE + '/ad.html?id=120252672229400312#tab=history');
  await page.waitForSelector('#cr-main ol.tl');
  const n2Timeline = await page.locator('#cr-main ol.tl').innerText();
  check('an on/off made from the console is marked as made here, by whom', n2Timeline.includes('Eugene, from this console'), n2Timeline.replace(/\n+/g, ' | ').slice(0, 300));
  await page.click('#hist-show [data-show="console"]');
  const madeHere = await page.$$eval('#cr-main ol.tl li', (ls) => ls.map((l) => l.dataset.source));
  check("the ad's dashboard changes sit in the same timeline, and Made here shows only those", madeHere.length > 0 && madeHere.every((x) => x === 'console')
    && (await page.getAttribute('#hist-show [data-show="console"]', 'aria-pressed')) === 'true', madeHere.join());
  {
    const n2d = (await call('GET', '/api/ads/ad/120252672229400312')).body;
    const mine = n2d.timeline.filter((r) => r.source === 'console');
    const expected = new Set(mine.filter((r) => r.change_id).map((r) => r.change_id)).size + mine.filter((r) => !r.change_id).length;
    const lines = n2d.history.filter((i) => i.kind === 'status' && i.source === 'console');
    check('an on/off made here is one line in the History (what was asked, with what Meta did under it)',
      expected > 0 && lines.length === expected && lines.some((i) => i.sub), `${lines.length} lines for ${expected} switches`);
  }
  // 9.4c Ad Overview: status, results and Claude first; the rest folds and remembers; the preview stays through a
  // refresh and reads itself again once Meta's link is old.
  {
    const AD = '120252672229400312';
    await page.goto(BASE + `/ad.html?id=${AD}`);
    await page.evaluate(() => localStorage.removeItem('ebads-folds'));
    await page.reload();
    await page.waitForSelector('#cr-state');
    const order = await page.evaluate(() => {
      const els = ['#cr-state', '.cr-figs', '#cr-claude', '#fold-where', '#fold-words', '#fold-idea', '#fold-auto'].map((x) => document.querySelector(x));
      return els.map((el, i) => !!el && (i === 0 || !!(els[i - 1].compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)));
    });
    check('the ad Overview leads with its status, then results, then Claude, with the rest below', order.every(Boolean), JSON.stringify(order));
    check('the status card says what the ad is doing, with its 14 delivery days', /Delivering|Off|In review/.test(await page.textContent('#cr-state .cs-h'))
      && (await page.locator('#cr-state .trk i').count()) === 14 && (await page.textContent('#cr-state .cs-line')).trim().length > 10);
    const folds = await page.$$eval('details.fold', (ds) => Object.fromEntries(ds.map((d) => [d.dataset.fold, d.open])));
    check("Where it runs starts open; Words, The idea and Meta's automatic changes start folded", folds.where === true && folds.words === false && folds.idea === false && folds.auto === false, JSON.stringify(folds));
    const adRow = (await getJson(`/api/ads/ad/${AD}`)).ad;
    await page.waitForFunction(() => ['#fold-idea', '#fold-auto'].every((x) => !/Reading/.test(document.querySelector(`${x} .fold-s`)?.textContent || 'Reading')));
    check('a folded section says what is inside on its line', (await page.textContent('#fold-words .fold-s')).trim() === (adRow.title || '—')
      && /on|off|None listed/i.test(await page.textContent('#fold-auto .fold-s')), await page.textContent('#fold-auto .fold-s'));
    await page.click('#fold-words > summary');
    await page.waitForFunction(() => JSON.parse(localStorage.getItem('ebads-folds') || '{}').words === true);
    await page.reload();
    await page.waitForSelector('#fold-words');
    check('an opened fold stays open after a reload', await page.$eval('#fold-words', (d) => d.open) && await page.isVisible('#fold-words .facts'));
    await page.click('#fold-words > summary');
    await page.waitForSelector('#preview-frame iframe:not(.preview-loading)', { timeout: 15000 });
    await page.$eval('#preview-frame iframe', (f) => { f.dataset.qa = 'kept'; });
    const previews = [];
    const onPreview = (r) => { if (/\/preview\?format=/.test(r.url())) previews.push(r.url()); };
    page.on('request', onPreview);
    await openFold('idea');
    await page.waitForSelector('#idea input[name]');
    await page.fill('#idea input[name] >> nth=0', 'QA unsaved tag');
    await page.click('.topline [data-refresh]');
    await page.waitForFunction(() => !document.querySelector('.topline [data-refresh]').disabled, null, { timeout: 60000 });
    await page.waitForSelector('#cr-state');
    const keptTag = await page.waitForFunction(() => document.querySelector('#idea input[name]')?.value === 'QA unsaved tag', null, { timeout: 10000 }).then(() => true, () => false);
    check('a refresh keeps tags typed in The idea but not saved yet', keptTag);
    await page.$eval('#fold-idea', (d) => { d.open = false; });
    check('a refresh redraws the numbers but keeps the preview as it was', previews.length === 0 && (await page.locator('#preview-frame iframe[data-qa="kept"]').count()) === 1, `${previews.length} preview reads`);
    await page.$eval('#preview-frame', (b) => { b.dataset.loadedAt = String(Date.now() - 31 * 60 * 1000); });
    await Promise.all([page.waitForRequest((r) => /\/preview\?format=/.test(r.url())), page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')))]);
    await page.waitForSelector('#preview-frame iframe:not(.preview-loading)', { timeout: 15000 });
    check('a preview older than half an hour reads itself again when the page is back in view', (await page.locator('#preview-frame iframe[data-qa="kept"]').count()) === 0);
    page.off('request', onPreview);
    // The tabs say when Meta's answer didn't come, with Try again, and keep their own controls.
    const VID = '120252672230740312';
    for (const [name, route, done] of [['video', '**/api/insights/ad/*/diagnostics', '#funnel .bars'], ['audience', '**/api/insights/breakdown**', '#aud-spend .bars, #aud-body .empty'],
      ['comments', '**/api/insights/ad/*/comments', '.comments-panel'], ['polish', '**/api/ads/ad/*/polish-runs', '#polish-form']]) {
      const seenE = errors.length;
      await page.route(route, (r) => r.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ error: 'QA: Meta did not answer' }) }));
      await page.goto(BASE + `/ad.html?id=${VID}#tab=${name}`);
      await page.reload();  // the same ad with another tab: a change of hash alone doesn't load the page again
      await page.waitForSelector('#cr-main .empty[role="alert"] [data-retry]');
      const said = (await page.textContent('#cr-main .empty[role="alert"]')).replace(/\s+/g, ' ');
      const kept = name !== 'audience' || (await page.isVisible('#aud-range'));
      await page.unroute(route);
      await page.click('#cr-main [data-retry]');
      await page.waitForSelector(done);
      await page.waitForTimeout(300);
      errors.splice(seenE);
      check(`the ${name} tab says when its data didn't come, and Try again loads it`, /This didn't load/.test(said) && /QA: Meta did not answer/.test(said) && kept, said.slice(0, 120));
    }
    // The ad's own campaign name may say Edge Bourne; the checks themselves may not.
    const passesText = JSON.stringify(await getJson('/api/polish/passes'));
    const local = [...((await page.innerText('#cr-main')).match(/\bN1\b|AI chip|OPTIONAL|Southern California/g) || []),
      ...(passesText.match(/\bN1\b|AI chip|OPTIONAL|Southern California|Edge Bourne|intro call/g) || [])];
    check('the Polish tab and its checks use words that fit any business', local.length === 0, local.join());
  }
  // New ad: only ad sets an ad can go into (Meta refuses deleted and archived ones).
  const newOpts = (await call('GET', '/api/ads/new/options')).body;
  const goneSets = sh(`docker exec edgebourne-postgres psql -U edgebourne -d ebads -tAc "SELECT string_agg(id, ',') FROM adsets WHERE effective_status IN ('DELETED', 'ARCHIVED')"`).trim().split(',').filter(Boolean);
  check('New ad offers no deleted or archived ad set, delivering ones first', goneSets.length > 0 && newOpts.adsets.length > 0
    && !newOpts.adsets.some((s) => goneSets.includes(s.id)) && newOpts.adsets[0].effective_status === 'ACTIVE', `${goneSets.length} gone, offered ${newOpts.adsets.map((s) => s.effective_status).join()}`);
  // …and the server refuses one too, whatever the screen sent (a proposal or ?adset= naming a gone ad set).
  const goneSet = sh(`docker exec edgebourne-postgres psql -U edgebourne -d ebads -tAc "SELECT id FROM adsets WHERE account_id = 1 AND effective_status IN ('DELETED', 'ARCHIVED') LIMIT 1"`).trim();
  const intoGone = await call('POST', '/api/ads/new', { adset_id: goneSet, template_ad_id: N1, name: 'QA into a gone ad set', body: 'QA', title: 'QA', media: { kind: 'same' } });
  check('a new ad for a deleted or archived ad set is refused before anything reaches Meta', intoGone.status === 400 && /deleted or archived/.test((intoGone.body || {}).error), `${goneSet}: ${intoGone.status} ${JSON.stringify(intoGone.body)}`);
  await page.goto(`${BASE}/new-ad.html?adset=${goneSet}`);
  await page.waitForSelector('#aset-pick option', { state: 'attached' });
  await page.waitForTimeout(300);
  check('New ad says so when ?adset= names a deleted or archived ad set, and still picks a real one',
    /deleted or archived/.test(await page.textContent('body')) && (await page.$eval('#aset-pick', (s) => s.selectedIndex)) >= 0);
  // D2 Edits made in Ads Manager, the 3-day rule and change marks (all against the fake: /fake/_outside is Ads Manager).
  {
    // A refusal the check expects (409) logs a console error in the page: dropped only around that call.
    const expected = async (fn) => { const n = errors.length; const r = await fn(); errors.splice(n); return r; };
    const DC = '120252638288040312', DS = '120252672227950312';
    const usd = (c) => `$${(c / 100).toFixed(2)}`;
    const sql = (q) => sh(`docker exec edgebourne-postgres psql -U edgebourne -d ebads -tAc "${q}"`).trim();
    const SETUP_SQL = "field IN ('daily_budget','lifetime_budget','spend_cap','bid_strategy','bid_amount','start_time','end_time','targeting')";
    const setupEvents = () => Number(sql(`SELECT count(*) FROM status_events WHERE ${SETUP_SQL}`));
    const outsideAlerts = () => Number(sql("SELECT count(*) FROM alerts WHERE rule = 'outside_edit'"));
    const timelineOf = async (level, id) => (await getJson(`/api/${level === 'campaign' ? 'campaigns' : 'adsets'}/${id}?range=14`)).timeline;
    // 10. Seeding: the first read after the update stores budgets, dates and audiences quietly, even when a stored value was stale.
    pull();
    sql(`UPDATE campaigns SET setup_seen_at = NULL, daily_budget_cents = daily_budget_cents + 100 WHERE id = '${DC}'`);
    const beforeSeed = setupEvents();
    pull();
    check('the first read after the update records no change (budgets, dates and audiences are stored quietly)', setupEvents() === beforeSeed
      && sql(`SELECT setup_seen_at IS NOT NULL FROM campaigns WHERE id = '${DC}'`) === 't', String(setupEvents() - beforeSeed));
    // 1. A budget raised in Ads Manager: recorded once, by Ads Manager, and a warning to act on (it breaks +20%).
    ageBudget();
    const b0 = Number(metaObj(DC).daily_budget), b1 = Math.round(b0 * 1.5 / 100) * 100;
    outside(DC, `daily_budget=${b1}`);
    pull();
    const tl1 = await timelineOf('campaign', DC);
    const ev1 = tl1.find((i) => i.title === `Budget ${usd(b0)} → ${usd(b1)} a day`);
    check('a budget raised in Ads Manager is in the History, by Ads Manager', ev1 && ev1.by === 'Ads Manager' && ev1.cat === 'money', JSON.stringify(tl1.slice(0, 2)));
    const money1 = (await getJson('/api/inbox?box=all&kind=money')).items.find((i) => i.title === `Budget changed in Ads Manager: ${usd(b0)} → ${usd(b1)} a day`);
    check('it lands in the Inbox once as Money that needs action, saying it is more than +20%', money1 && money1.level === 'warn' && money1.need
      && money1.lines.some((l) => /That's \+\d+%, more than the \+20% step/.test(l)) && money1.href === `/campaign.html?id=${DC}&tab=history`, JSON.stringify(money1));
    const afterOne = setupEvents(), alertsOne = outsideAlerts();
    pull();
    check('reading Meta again records nothing new', setupEvents() === afterOne && outsideAlerts() === alertsOne);
    // Done closes it (admins), and it moves to For your information.
    await page.goto(`${BASE}/inbox.html?box=need&kind=money#item=${encodeURIComponent(money1.key)}`);
    await page.waitForSelector('#ib-detail [data-done]');
    check('the History link and Done are on the item', /Open the history/.test(await page.textContent('#ib-detail')));
    await page.click('#ib-detail [data-done]');
    await page.waitForFunction((k) => !document.querySelector(`#ib-list [data-key="${k}"]`), money1.key);
    const done1 = (await getJson('/api/inbox?box=all&kind=money')).items.find((i) => i.key === money1.key);
    check('Done moves it to For your information', done1 && !done1.need && !done1.actions.includes('done'), JSON.stringify(done1));
    // 3. The 3-day rule on the server: a raise right after that change needs the knowing yes; it is stored with the change.
    const r409 = await expected(() => call('POST', `/api/ads/campaign/${DC}/budget`, { daily_budget_cents: b1 + 200, from_cents: b1 }));
    check('a raise under 3 days after the last change is refused without the knowing yes', r409.status === 409 && r409.body.code === 'recent_change'
      && r409.body.last.to === b1 && r409.body.last.where === 'outside', JSON.stringify(r409.body));
    const r200 = await call('POST', `/api/ads/campaign/${DC}/budget`, { daily_budget_cents: b1 + 200, from_cents: b1, accept_recent: true });
    check('with the knowing yes it goes through, and the change says which warning was confirmed', r200.status === 200 && Number(metaObj(DC).daily_budget) === b1 + 200
      && sql(`SELECT accepted::text FROM meta_changes WHERE entity_id = '${DC}' AND action = 'budget' ORDER BY id DESC LIMIT 1`) === '{recent}', String(r200.status));
    const tl3 = await timelineOf('campaign', DC);
    check('History says it was confirmed knowingly', tl3.some((i) => i.sub === 'Confirmed knowingly: under 3 days since the last change'));
    // 4. Back to the exact previous amount, or a cut: never "recent".
    const back = await call('POST', `/api/ads/campaign/${DC}/budget`, { daily_budget_cents: b1, from_cents: b1 + 200 });
    const cut = await call('POST', `/api/ads/campaign/${DC}/budget`, { daily_budget_cents: b1 - 100, from_cents: b1 });
    check('going back to the previous budget and a cut need no extra yes', `${back.status} ${cut.status}` === '200 200', `${back.status} ${cut.status}`);
    // 5. The dialog reads the last change first and says Raise anyway / Back to.
    const alertsBefore5 = outsideAlerts();
    await page.goto(`${BASE}/campaign.html?id=${DC}`);
    await page.waitForSelector('#en-actions [data-budget]');
    await page.click('#en-actions [data-budget]');
    await page.waitForSelector('dialog.confirm #cd-last');
    const lastLine = await page.textContent('dialog.confirm .confirm-body');
    check('the budget dialog shows the last change, today, by you', /Last change: .*today/.test(lastLine) && /by you/.test(lastLine), lastLine.trim());
    await page.fill('#cd-input', String(((b1 - 100) / 100 + 2).toFixed(2)));
    const raiseLabel = await page.textContent('#cd-ok');
    const raiseHint = await page.textContent('#cd-hint');
    const raiseDanger = await page.$eval('#cd-ok', (b) => b.classList.contains('btn-danger'));
    await page.fill('#cd-input', String((b1 / 100).toFixed(2)));
    const backLabel = await page.textContent('#cd-ok');
    const backDanger = await page.$eval('#cd-ok', (b) => b.classList.contains('btn-danger'));
    check("Raise anyway is the danger button, like the same warning on Meta's advice; Change budget is not", raiseDanger && !backDanger, `${raiseDanger} ${backDanger}`);
    const backHint = await page.textContent('#cd-hint');
    check('a raise says Raise anyway with the 3-day words; the previous amount says Change budget and Back to', raiseLabel === 'Raise anyway'
      && /Less than 3 days since the last change/.test(raiseHint) && backLabel === 'Change budget' && /Back to/.test(backHint), `${raiseLabel} | ${backLabel} | ${backHint}`);
    await page.screenshot({ path: `${OUT}/flow-d2-budget-dialog.png` });
    await page.click('dialog.confirm #cd-ok');
    await page.waitForFunction((t) => (document.querySelector('#en-actions [data-budget]')?.textContent || '').includes(t), usd(b1));
    // 2. A change made here and read back from Meta is not an edit made in Ads Manager.
    pull();
    check('a budget changed here, then read from Meta, raises no Ads Manager note', outsideAlerts() === alertsBefore5, `${alertsBefore5} → ${outsideAlerts()}`);
    // 6. Bulk: the line says when it changed, the button says Apply anyway, the server wants the yes.
    await page.goto(`${BASE}/ads.html?level=campaign`);
    await page.waitForSelector(`.tbl [data-pick="${DC}"]`);
    await page.locator(`.tbl [data-pick="${DC}"]`).check();
    await page.click('.bk [data-bulk="budget"]');
    await page.waitForSelector('dialog.confirm #cd-input');
    await page.fill('#cd-input', '+5%');
    await page.click('dialog.confirm #cd-ok');
    await page.waitForSelector('dialog.confirm .bk-lines');
    const bkPill = await page.textContent('dialog.confirm .bk-lines');
    const bkOk = await page.textContent('dialog.confirm #cd-ok');
    await page.screenshot({ path: `${OUT}/flow-d2-bulk.png` });
    await page.click('dialog.confirm #cd-cancel');
    check('the bulk preview marks a budget changed today and says Apply anyway', /changed today/.test(bkPill) && bkOk === 'Apply anyway', `${bkPill} | ${bkOk}`);
    const pv6 = await call('POST', '/api/ads/bulk/preview', { action: 'budget_pct', level: 'campaign', ids: [DC], value: 5 });
    const ap6 = await expected(() => call('POST', '/api/ads/bulk/apply', { plan_token: pv6.body.plan_token }));
    check('bulk apply refuses a recent raise without the knowing yes', pv6.body.totals.recent === true && ap6.status === 409 && Number(metaObj(DC).daily_budget) === b1, `${ap6.status} ${JSON.stringify(ap6.body)}`);
    // 7. Claude's budget suggestion on this campaign is never ticked for you and says when it last changed.
    const want7 = b1 + 100;
    const pid = py(`import db, json
r = db.execute(\\"INSERT INTO desk_proposals (task_id, kind, title, status, entity_type, entity_id, entity_name, proposed_value, payload, account_id) SELECT id, 'budget', 'QA D2 raise', 'pending', 'campaign', '${DC}', 'Edge Bourne campaign', '\\$${(want7 / 100).toFixed(2)}/day', %s, 1 FROM desk_tasks WHERE account_id = 1 ORDER BY id DESC LIMIT 1 RETURNING id\\", (json.dumps({'proposed_cents': ${want7}}),), returning=True)
print(r['id'])`);
    await page.goto(`${BASE}/inbox.html?box=need&kind=claude#item=proposal%3A${pid}`);
    await page.waitForSelector('#ib-detail [data-accept]');
    await page.click('#ib-detail [data-accept]');
    await page.waitForSelector('dialog.accept-sheet #cd-ok:not(:empty)');
    const item7 = page.locator('dialog.accept-sheet .sheet-item', { hasText: 'QA D2 raise' });
    const why7 = await item7.textContent();
    check('the Accept sheet never ticks a budget changed under 3 days ago, and says why', !(await item7.locator('input').isChecked()) && /Budget last changed/.test(why7), why7.replace(/\s+/g, ' '));
    await page.click('dialog.accept-sheet #cd-cancel');
    await call('POST', `/api/proposals/${pid}/decline`, {});
    // 6b. Bulk right after an Ads Manager change the console hasn't read yet: the preview records it first, so the
    // line is flagged and apply wants the knowing yes.
    ageBudget();
    const live6 = Number(metaObj(DC).daily_budget), out6 = live6 + 300;
    outside(DC, `daily_budget=${out6}`);
    const pv6b = await call('POST', '/api/ads/bulk/preview', { action: 'budget_pct', level: 'campaign', ids: [DC], value: 5 });
    const ap6b = await expected(() => call('POST', '/api/ads/bulk/apply', { plan_token: pv6b.body.plan_token }));
    const tl6b = await timelineOf('campaign', DC);
    check('a bulk raise right after an unread Ads Manager change: recorded in History by Ads Manager, flagged, refused without the yes',
      pv6b.body.totals.recent === true && pv6b.body.lines[0].from === out6 && ap6b.status === 409 && ap6b.body.code === 'recent_change'
      && Number(metaObj(DC).daily_budget) === out6 && tl6b.some((i) => i.title === `Budget ${usd(live6)} → ${usd(out6)} a day` && i.by === 'Ads Manager'),
      `${JSON.stringify(pv6b.body.totals)} ${ap6b.status} ${JSON.stringify(tl6b.slice(0, 2))}`);
    // 6c. The yes covers only the lines the preview flagged: one that turned recent after the preview is skipped.
    ageBudget();
    const pv6c = await call('POST', '/api/ads/bulk/preview', { action: 'budget_pct', level: 'campaign', ids: [DC], value: 5 });
    sql(`INSERT INTO meta_changes (level, entity_id, entity_name, campaign_id, action, old_value, new_value, ok, account_id) VALUES ('campaign', '${DC}', 'QA', '${DC}', 'budget', '${out6 - 100}', '${out6}', true, 1)`);
    const ap6c = await call('POST', '/api/ads/bulk/apply', { plan_token: pv6c.body.plan_token, accept_recent: true });
    check('a line that changed less than 3 days ago since the preview is skipped, even with a yes sent',
      !pv6c.body.totals.recent && ap6c.status === 200 && ap6c.body.done === 0 && /less than 3 days/i.test(ap6c.body.results[0].error)
      && Number(metaObj(DC).daily_budget) === out6, `${ap6c.status} ${JSON.stringify(ap6c.body)}`);
    // 7b. Accepting Claude's raise right after an unread Ads Manager change: the fresh read records it, the server
    // wants the knowing yes, and the suggestion card asks Raise anyway (danger) and sends it.
    ageBudget();
    const live7b = Number(metaObj(DC).daily_budget), out7b = live7b + 200, want7b = out7b + 100;
    outside(DC, `daily_budget=${out7b}`);
    const pid7b = py(`import db, json
r = db.execute(\\"INSERT INTO desk_proposals (task_id, kind, title, status, entity_type, entity_id, entity_name, proposed_value, payload, account_id) SELECT id, 'budget', 'QA D2 raise after Ads Manager', 'pending', 'campaign', '${DC}', 'Edge Bourne campaign', '\\$${(want7b / 100).toFixed(2)}/day', %s, 1 FROM desk_tasks WHERE account_id = 1 ORDER BY id DESC LIMIT 1 RETURNING id\\", (json.dumps({'proposed_cents': ${want7b}}),), returning=True)
print(r['id'])`);
    const chk7b = await call('GET', `/api/proposals/${pid7b}/check`);
    const no7b = await expected(() => call('POST', `/api/proposals/${pid7b}/approve`, { from_cents: out7b, to_cents: want7b }));
    check('accepting a raise right after an unread Ads Manager change: the change is recorded and the server wants the knowing yes',
      chk7b.body.recent === true && chk7b.body.from === out7b && no7b.status === 409 && no7b.body.code === 'recent_change'
      && (await timelineOf('campaign', DC)).some((i) => i.title === `Budget ${usd(live7b)} → ${usd(out7b)} a day` && i.by === 'Ads Manager'),
      `${JSON.stringify(chk7b.body).slice(0, 200)} ${no7b.status}`);
    await page.goto(`${BASE}/ad.html?id=120252672230740312#tab=overview`);
    const card7b = page.locator(`#props [data-proposal="${pid7b}"]`);
    await card7b.waitFor();
    await card7b.locator('[data-approve]').click();
    await page.waitForSelector('dialog.confirm[open] #cd-ok');
    const ask7b = (await page.textContent('dialog.confirm[open]')).replace(/\s+/g, ' ');
    const ok7b = await page.$eval('dialog.confirm[open] #cd-ok', (b) => [b.textContent, b.classList.contains('btn-danger')]);
    await page.click('dialog.confirm[open] #cd-ok');
    for (let i = 0; i < 40 && sql(`SELECT status FROM desk_proposals WHERE id = ${pid7b}`) !== 'applied'; i++) await page.waitForTimeout(250);
    check('the suggestion card asks Raise anyway as a danger button with the last change, and that yes goes through',
      /Less than 3 days since the last change/.test(ask7b) && /in Ads Manager/.test(ask7b) && ok7b[0] === 'Raise anyway' && ok7b[1]
      && Number(metaObj(DC).daily_budget) === want7b
      && sql(`SELECT accepted::text FROM meta_changes WHERE proposal_id = ${pid7b} AND action = 'budget' ORDER BY id DESC LIMIT 1`) === '{recent}',
      `${ok7b} ${ask7b.slice(0, 200)}`);
    // Claude's snapshot (bridge desk 2.1) carries when each budget last changed, where, and when a raise is fine again.
    const snap = JSON.parse(py(`import desk_api, json, account_info, datetime
t = account_info.today()
s = desk_api.budget_snapshot({'start': (t - datetime.timedelta(days=14)).isoformat(), 'end': t.isoformat()})
b = next(x for x in s['budget_changes'] if x['id'] == '${DC}')
print(json.dumps({'last': b['last'], 'days': b['days_since'], 'ok_after': b['ok_after'], 'marks': len(s['recent_changes'])}))`).split('\n').pop());
    check("Claude's snapshot says when a budget last changed, where, and when a raise is fine again", snap.last && snap.last.from === out7b
      && snap.last.to === want7b && snap.last.where === 'console' && snap.days === 0 && !!snap.ok_after && snap.marks > 0, JSON.stringify(snap));
    // 8. Dates changed in Ads Manager.
    const endDay = py('import account_info, datetime;print((account_info.today() + datetime.timedelta(days=20)).isoformat())');
    outside(DS, `end_time=${endDay}T23:59:00-0800`);
    pull();
    const tl8 = await timelineOf('adset', DS);
    const endInbox = (await getJson('/api/inbox?box=all&kind=money')).items.some((i) => /^End date set in Ads Manager: /.test(i.title));
    check('an end date set in Ads Manager is in the History and the Inbox', tl8.some((i) => /^End date set: /.test(i.title) && i.by === 'Ads Manager') && endInbox);
    outside(DS, 'clear=end_time');
    pull();
    check('an end date taken off in Ads Manager reads “runs until turned off”', (await timelineOf('adset', DS)).some((i) => i.title === 'End date removed: runs until turned off'));
    // 9. Audience: a real change reads as before → after; Meta's own defaults are no change.
    const age0 = metaObj(DS).targeting.age_min;
    outside(DS, 'targeting_age_min=30');
    pull();
    const aud = (await timelineOf('adset', DS)).find((i) => /^Audience changed: /.test(i.title));
    check('an audience changed in Ads Manager says what changed', aud && new RegExp(`Ages ${age0}–.* → Ages 30–`).test(aud.title), aud && aud.title);
    const audBefore = Number(sql(`SELECT count(*) FROM status_events WHERE field = 'targeting'`));
    outside(DS, 'targeting_noise=1');
    pull();
    check("Meta's own audience defaults are not an audience change", Number(sql(`SELECT count(*) FROM status_events WHERE field = 'targeting'`)) === audBefore);
    // An outside warning still open after the 3-day window closes by itself.
    const stale = py(`import alerts, db
r = db.execute(\\"INSERT INTO alerts (rule, dedupe_key, level, title, lines, kind, entity_id, campaign_id, href, created_at) VALUES ('outside_edit', 'qa-d2-stale-' || md5(random()::text), 'warn', 'QA old outside edit', '[]', 'event', '${DC}', '${DC}', '/campaign.html?id=${DC}&tab=history', now() - interval '73 hours') RETURNING id\\", returning=True)
alerts.run()
print(db.query('SELECT resolved_at IS NOT NULL AS done FROM alerts WHERE id = %s', (r['id'],), one=True)['done'])`);
    check('an Ads Manager warning still open after 3 days closes by itself', stale === 'True', stale);
    // 12–14. Marks on the charts: the changes of the last days sit under their day (moved to yesterday: charts end there).
    ageBudget(1);
    sql(`UPDATE status_events SET at = at - interval '1 day', meta_time = meta_time - interval '1 day' WHERE field IN ('end_time','targeting','start_time')`);
    const cd = await getJson(`/api/campaigns/${DC}?range=14`);
    check('the campaign page carries budget marks for the day they happened', cd.marks.some((m) => m.day === cd.series[cd.series.length - 1].day && m.cats.includes('money'))
      && /\d+ changes? in this period/.test(cd.marks_summary), JSON.stringify(cd.marks.slice(-1)));
    await page.goto(`${BASE}/campaign.html?id=${DC}&range=14`);
    await page.waitForSelector('#c-spend svg .chg-mark');
    check('the campaign charts show the marks and a guide on budget days', (await page.locator('#c-spend svg .chg-guide').count()) > 0
      && /\d+ changes? in this period/.test(await page.textContent('#chg-panel .chg-fold summary')));
    await page.locator('#c-spend .hit').last().hover();
    await page.waitForSelector('#c-spend .tip:not([hidden]) .tip-chg');
    check('hovering a marked day lists its changes in the tooltip', /budget/i.test(await page.textContent('#c-spend .tip .tip-chg')));
    await page.screenshot({ path: `${OUT}/flow-d2-marks.png` });
    // 13. Show on charts: off hides the marks and stays off after a reload; on brings them back.
    await page.$eval('#chg-panel .chg-fold', (d) => { d.open = true; });
    await page.click('#chg-panel [data-chg-toggle]');
    const hidden = await page.$eval('#c-spend .chg-mark', (m) => getComputedStyle(m).display === 'none');
    await page.reload();
    await page.waitForSelector('#c-spend svg .chg-mark', { state: 'attached' });
    const stillHidden = await page.$eval('#c-spend .chg-mark', (m) => getComputedStyle(m).display === 'none');
    await page.$eval('#chg-panel .chg-fold', (d) => { d.open = true; });
    await page.click('#chg-panel [data-chg-toggle]');
    const back13 = await page.$eval('#c-spend .chg-mark', (m) => getComputedStyle(m).display !== 'none');
    check('Show on charts turns the marks off, remembered after a reload, and back on', hidden && stillHidden && back13, `${hidden} ${stillHidden} ${back13}`);
    // 14. The same marks on the ad, Results and Compare.
    const N1d2 = '120252672229040312', N2d2 = '120252672229400312';
    for (const [url, sel] of [[`/ad.html?id=${N1d2}&range=14`, '#c-spend'], ['/performance.html?range=14', '#c-spend'], [`/compare.html?ids=${N1d2},${N2d2}&range=14&chart=spend`, '#cmp-chart']]) {
      await page.goto(BASE + url);
      const got = await page.waitForSelector(`${sel} svg .chg-mark`, { timeout: 15000 }).then(() => true).catch(() => false);
      check(`change marks on ${url.split('?')[0]}`, got && (await page.locator('#chg-panel .chg-fold').count()) === 1);
    }
    // 15. A client sees marks without people's names and gets no budget history; 16. a teammate off this campaign gets a 404.
    py(`import db
from werkzeug.security import generate_password_hash as h
for email, role in (('qa-d2-client@example.com', 'client'), ('qa-d2-mate@example.com', 'member')):
    db.execute(\\"INSERT INTO users (email, name, password_hash, role, account_id) VALUES (%s, %s, %s, %s, 1) ON CONFLICT (email) DO UPDATE SET is_active = TRUE, password_hash = EXCLUDED.password_hash, role = EXCLUDED.role, account_id = 1, must_change_password = FALSE\\", (email, 'QA D2 ' + role, h('d2-pass-12345'), role))
db.execute(\\"DELETE FROM campaign_members WHERE user_id = (SELECT id FROM users WHERE email = 'qa-d2-mate@example.com')\\")`);
    for (const [email, label] of [['qa-d2-client@example.com', 'client'], ['qa-d2-mate@example.com', 'mate']]) {
      const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
      const p = await ctx.newPage();
      await p.goto(BASE + '/login.html');
      await p.fill('#email', email); await p.fill('#password', 'd2-pass-12345');
      await Promise.all([p.waitForURL('**/home.html**'), p.click('button[type=submit]')]);
      const res = await p.evaluate(async ([c]) => {
        const last = (await fetch(`/api/ads/campaign/${c}/budget/last`)).status;
        const r = await fetch(`/api/campaigns/${c}?range=14`);
        return { last, page: r.status, marks: r.ok ? (await r.json()).marks : null };
      }, [DC]);
      if (label === 'client') {
        const bys = [...new Set(res.marks.flatMap((m) => m.items.map((i) => i.by)))];
        check('a client sees the marks with no person named and no budget history', res.last === 403 && bys.length > 0 && bys.every((b) => ['Team', 'Meta', 'Ads Manager'].includes(b))
          && !res.marks.some((m) => m.items.some((i) => /Claude/.test(i.title))), `${res.last} ${bys.join()}`);
      } else {
        check("a teammate who isn't on the campaign can't read its budget history", res.last === 404 && res.page === 404, `${res.last} ${res.page}`);
      }
      await ctx.close();
    }
    py(`import db
db.execute(\\"UPDATE users SET is_active = FALSE WHERE email IN ('qa-d2-client@example.com', 'qa-d2-mate@example.com')\\")`);
    // 17. Phones: a tap on a marked day opens the same tooltip; the changes row is 44px; nothing past the edge.
    {
      const pctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
      await pctx.addCookies(await page.context().cookies());
      const pp = await pctx.newPage();
      pp.on('pageerror', (e) => errors.push('d2 phone: ' + e.message));
      await pp.goto(`${BASE}/campaign.html?id=${DC}&range=14`);
      await pp.waitForSelector('#c-spend svg .chg-mark');
      // The chart can sit under the fold (more figures above it): scroll it to the middle so the tap lands on it.
      await pp.$eval('#c-spend', (el) => el.scrollIntoView({ block: 'center' }));
      const box = await pp.locator('#c-spend .hit').last().boundingBox();
      await pp.touchscreen.tap(box.x + box.width / 2, box.y + box.height / 2);
      const tapped = await pp.waitForSelector('#c-spend .tip:not([hidden]) .tip-chg', { timeout: 3000 }).then(() => true).catch(() => false);
      const sumH = (await pp.locator('#chg-panel .chg-fold summary').boundingBox()).height;
      const over = await pp.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      await pp.screenshot({ path: `${OUT}/flow-d2-phone.png`, fullPage: true });
      check('on a phone a tap on a marked day shows its changes; the changes row is 44px; nothing past the edge', tapped && sumH >= 44 && over <= 0, `${tapped} ${sumH} ${over}`);
      await pctx.close();
    }
    // Put the ad set's audience back as the later checks expect it.
    outside(DS, `targeting_age_min=${age0}`);
    pull();
  }

  // 8.4 APIs for the new screens: ranges with the window before, campaign/ad set pages, compare, search, saved views, bulk.
  const C1 = '120252638288040312';
  const t14 = (await call('GET', '/api/ads?range=14&vs=prev')).body;
  check('the Ads tree takes a range and adds the window before', t14.range.days === 14 && !!t14.prev_range && !!t14.campaigns[0].prev);
  const camp = await call('GET', `/api/campaigns/${C1}?range=mtd`);
  check('a campaign has its own page data: breadcrumbs, ad sets, timeline, daily series', camp.status === 200 && camp.body.crumbs.length === 1
    && camp.body.entity.adsets.length >= 1 && Array.isArray(camp.body.timeline) && camp.body.series.length >= 1);
  const cmp = await call('GET', '/api/compare?ids=120252672232030312,120252672233160312,120252672230740312&range=14&vs=prev');
  check('compare lines up 3 ads metric by metric and won\'t name a winner too early', cmp.status === 200 && cmp.body.items.length === 3
    && cmp.body.rows.some((r) => r.key === 'cpl_cents') && cmp.body.verdict.ready === false && cmp.body.verdict.need_spend_cents > 0);
  check('compare needs at least 2 ads', (await call('GET', '/api/compare?ids=120252672232030312')).status === 400);
  const found = (await call('GET', '/api/search?q=weekly')).body.items;
  check('search finds ads by name and links to them', found.some((i) => i.type === 'ad' && i.href.startsWith('/ad.html?id=')));
  const view = await call('POST', '/api/views', { page: 'ads', name: 'QA live', query: '?view=on&range=14' });
  const views = (await call('GET', '/api/views?page=ads')).body.views;
  check('a saved view keeps its filter and comes back in the list', view.status === 201 && views.some((v) => v.id === view.body.id && v.query === 'view=on&range=14'));
  await call('DELETE', `/api/views/${view.body.id}`);
  const bp = await call('POST', '/api/ads/bulk/preview', { action: 'budget_pct', level: 'campaign', ids: [C1], value: 30 });
  const bpNo = await call('POST', '/api/ads/bulk/apply', { plan_token: bp.body.plan_token });
  check('a bulk budget step over +20% is refused until confirmed knowingly', bp.status === 200 && bp.body.totals.big && bpNo.status === 409);
  const bad = await call('POST', '/api/ads/bulk/apply', { plan_token: bp.body.plan_token.replace(/.$/, 'x'), accept_big: true });
  check('a changed or forged bulk plan is refused', bad.status === 409);
  const offIds = ['120252672232030312', '120252672233160312'];
  const offPrev = await call('POST', '/api/ads/bulk/preview', { action: 'status', level: 'ad', ids: offIds, value: 'PAUSED' });
  const offDone = await call('POST', '/api/ads/bulk/apply', { plan_token: offPrev.body.plan_token });
  metaHits(true);
  const onPrev = await call('POST', '/api/ads/bulk/preview', { action: 'status', level: 'ad', ids: offIds, value: 'ACTIVE' });
  const onPrevHits = metaHits(true);
  const budgetPaths = onPrevHits.filter((h) => /fields=daily_budget%2Clifetime_budget%2Cend_time/.test(h)).map((h) => h.split('?')[0]);
  const oneByOne = onPrevHits.filter((h) => offIds.some((i) => h.startsWith(`/v24.0/${i}?`))).length;
  const together = onPrevHits.filter((h) => new RegExp(`ids=${offIds[0]}%2C${offIds[1]}`).test(h)).length;
  check('a bulk preview reads the selection in one call and each shared budget once (A3-126)',
    budgetPaths.length > 0 && budgetPaths.length === new Set(budgetPaths).size && oneByOne === 0 && together === 1,
    `budget reads ${budgetPaths.join(' ')}, one by one ${oneByOne}, together ${together}`);
  const onNo = await call('POST', '/api/ads/bulk/apply', { plan_token: onPrev.body.plan_token });
  // A raise on Meta between the preview and the apply is seen before anything goes on (audit 3).
  const bulkBudget = Number(metaObj('120252638288040312').daily_budget);
  sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;urllib.request.urlopen(urllib.request.Request('http://localhost:5001/v24.0/120252638288040312?access_token=x', data=b'daily_budget=${bulkBudget + 500}'))"`);
  const onMoved = await call('POST', '/api/ads/bulk/apply', { plan_token: onPrev.body.plan_token, confirm_total_cents: onPrev.body.totals.daily_cents });
  sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;urllib.request.urlopen(urllib.request.Request('http://localhost:5001/v24.0/120252638288040312?access_token=x', data=b'daily_budget=${bulkBudget}'))"`);
  check('bulk turn-on is refused when a budget changed on Meta since the preview', onMoved.status === 409 && /changed on Meta since the preview/.test(onMoved.body.error)
    && metaObj(offIds[0]).status === 'PAUSED', JSON.stringify(onMoved.body));
  metaHits(true);
  const onDone = await call('POST', '/api/ads/bulk/apply', { plan_token: onPrev.body.plan_token, confirm_total_cents: onPrev.body.totals.daily_cents });
  const onDoneHits = metaHits(true);
  const refreshedEach = onDoneHits.filter((h) => /fields=id%2Cname%2Cstatus%2Cconfigured_status%2Ceffective_status/.test(h) && !/ids=/.test(h)).length;
  const refreshedTogether = onDoneHits.filter((h) => /ids=.*fields=id%2Cname%2Cstatus%2Cconfigured_status%2Ceffective_status/.test(h)).length;
  const stored = sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(sorted(r['status'] for r in db.query('SELECT status FROM ads WHERE id = ANY(%s)', (${JSON.stringify(offIds).replace(/"/g, "'")},))))"`).trim();
  check('after a bulk turn-on the items are read back together and stored as on (A3-126)', refreshedEach === 0 && refreshedTogether === 1 && stored === "['ACTIVE', 'ACTIVE']",
    `one by one ${refreshedEach}, together ${refreshedTogether}, stored ${stored}`);
  check('bulk off, then on only after the daily total is echoed (each budget counted once)', offDone.body.done === 2 && onPrev.body.totals.budgets.length === 1
    && onNo.status === 409 && onDone.body.done === 2);
  const tagged = sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(db.query('SELECT COUNT(DISTINCT bulk_id) AS n, COUNT(*) AS c FROM meta_changes WHERE bulk_id IN (%s, %s)', ('${offDone.body.bulk_id}', '${onDone.body.bulk_id}'), one=True))"`);
  check('every bulk write is logged in meta_changes under its bulk id', /'n': 2, 'c': 4/.test(tagged), tagged.trim());
  // Audit 3 performance (A3-46, A3-123): reach is read from Meta together and briefly, a Meta that didn't
  // answer isn't waited on again at the next load, and the ad page paints without Meta's rankings.
  const reachHits = (hits) => hits.filter((h) => /\/insights\?/.test(h) && /reach/.test(h) && !/spend/.test(h)).length;
  await call('GET', '/api/ads?range=14&vs=prev');
  metaHits(true);
  const warm = await call('GET', '/api/ads?range=14&vs=prev');
  const warmReads = reachHits(metaHits(true));
  check('a second Ads load inside the cache window asks Meta for no reach', warm.status === 200 && warmReads === 0, `${warmReads} reads`);
  const setSlow = (s) => sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;urllib.request.urlopen('http://localhost:5001/fake/_slow?reach=${s}')"`);
  setSlow(12);
  let slowT0 = Date.now();
  const slow1 = await call('GET', '/api/ads?range=custom&from=2026-08-03&to=2026-08-05');
  const slowMs = Date.now() - slowT0;
  metaHits(true);
  slowT0 = Date.now();
  const slow2 = await call('GET', '/api/ads?range=custom&from=2026-08-03&to=2026-08-05');
  const againMs = Date.now() - slowT0;
  const againReads = reachHits(metaHits(true));
  setSlow(0);
  check('with Meta hanging, Ads answers after one short wait with the daily reach marked as such', slow1.status === 200 && slowMs < 11000
    && slow1.body.campaigns.length > 0 && slow1.body.campaigns.every((c) => c.m.reach_summed), `${slowMs} ms`);
  check('the next load doesn\'t wait on the Meta that just failed', slow2.status === 200 && againMs < 3000 && againReads === 0, `${againMs} ms, ${againReads} reads`);
  const adBody = await call('GET', '/api/ads/ad/120252672230740312');
  const asked = [];
  const onAsk = (r) => { if (/\/diagnostics/.test(r.url())) asked.push(r.url()); };
  page.on('request', onAsk);
  metaHits(true);
  await page.goto(BASE + '/ad.html?id=120252672230740312');
  await page.waitForSelector('#cr-main .cr-layout');
  await page.waitForFunction(() => !/Reading from Meta/.test(document.querySelector('#enh')?.textContent || 'Reading from Meta'));
  await page.reload();
  await page.waitForSelector('#cr-main .cr-layout');
  await page.waitForFunction(() => !/Reading from Meta/.test(document.querySelector('#enh')?.textContent || 'Reading from Meta'));
  page.off('request', onAsk);
  const creativeReads = metaHits(true).filter((h) => /fields=name%2Cobject_story_spec%2Cdegrees_of_freedom_spec/.test(h)).length;
  check('the ad page brings its watch funnel and paints without asking for Meta\'s rankings (A3-123)', typeof adBody.body.funnel?.impressions === 'number' && asked.length === 0,
    asked.join(' '));
  check('the creative behind "Meta\'s automatic changes" is read from Meta once, not on every visit (A3-123)', creativeReads <= 1, `${creativeReads} reads`);
  // A3-131: the daily prune drops read marks whose alert or lead has left the Inbox, never a pending proposal's.
  const pruneLeft = require('child_process').execSync('docker exec -i -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -', { input: `
import account_ctx, db, jobs
keys = ['alert:qa-prune-old', 'proposal:qa-prune-old', 'alert:qa-prune-new']
with account_ctx.use(1):
    uid = db.query('SELECT id FROM users ORDER BY id LIMIT 1', one=True)['id']
    db.execute('DELETE FROM inbox_reads WHERE item_key = ANY(%s)', (keys,))
    for k, days in zip(keys, (40, 400, 2)):
        db.execute('INSERT INTO inbox_reads (user_id, item_key, read_at) VALUES (%s, %s, now() - make_interval(days => %s))', (uid, k, days))
with account_ctx.all_accounts():
    db.execute('DELETE FROM inbox_reads WHERE ' + dict(jobs.PRUNE)['inbox_reads'])
with account_ctx.use(1):
    left = sorted(r['item_key'] for r in db.query('SELECT item_key FROM inbox_reads WHERE item_key = ANY(%s)', (keys,)))
    db.execute('DELETE FROM inbox_reads WHERE item_key = ANY(%s)', (keys,))
print(','.join(left))
` }).toString().trim();
  check('the prune drops old read marks but keeps recent ones and a pending proposal\'s (A3-131)', pruneLeft === 'alert:qa-prune-new,proposal:qa-prune-old', pruneLeft);
  // 8.5 Signal shell: every page sits in the right section, has breadcrumbs, and ⌘K finds an ad.
  const sections = { 'home': 'Today', 'inbox': 'Inbox', 'leads': 'Leads', 'ads': 'Ads', 'ad.html?id=120252672230740312': 'Ads', 'new-ad': 'Ads',
    'forms': 'Ads', 'new-campaign': 'Ads', 'performance': 'Insights', 'report': 'Insights', 'experiments': 'Insights', 'desk': 'Claude', 'gallery': 'Creative', 'ideas': 'Creative', 'research': 'Creative' };
  const wrongNav = [];
  for (const [p, want] of Object.entries(sections)) {
    await page.goto(p.includes('.html') ? `${BASE}/${p}` : `${BASE}/${p}.html`);
    await page.waitForSelector('.crumbs *');
    const got = await page.evaluate(() => document.querySelector('.rail .nav a[aria-current="page"] .label')?.textContent);
    if (got !== want) wrongNav.push(`${p}: ${got}`);
  }
  check('every page highlights its own section in the sidebar', wrongNav.length === 0, wrongNav.join(' | '));
  await page.goto(BASE + '/ad.html?id=120252672230740312');
  await page.waitForFunction(() => document.querySelectorAll('.crumbs a').length >= 2);
  const crumbText = await page.textContent('.crumbs');
  check('the ad page shows Ads › campaign › ad set › ad', /Ads.*Free intro call.*SoCal.*N3/.test(crumbText), crumbText);
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+k' : 'Control+k');
  await page.waitForSelector('dialog.palette[open]');
  await page.keyboard.type('weekly');
  await page.waitForSelector('dialog.palette .pal-item:has-text("N4 - Weekly report")');
  await page.keyboard.press('ArrowDown');
  const target = await page.evaluate(() => document.querySelector('dialog.palette .pal-item[aria-selected="true"] .pal-t')?.textContent);
  await page.keyboard.press('ArrowUp');
  const fromAd = page.url();  // already an ad page: wait for the palette's own navigation, not this URL
  await Promise.all([page.waitForURL((u) => /ad\.html\?id=/.test(u.href) && u.href.split('#')[0] !== fromAd.split('#')[0]), page.keyboard.press('Enter')]);
  check('⌘K finds an ad by name and Enter opens it', /ad\.html\?id=/.test(page.url()), `${target} → ${page.url()}`);
  // 9.3b: the command menu reaches every page, tab, Settings section, saved view and action, by the words people use.
  const palette = async (q) => {
    if (!(await page.isVisible('dialog.palette[open]'))) {
      await page.waitForSelector('.crumbs *');  // the frame is up, so the shortcut is listening
      await page.keyboard.press(process.platform === 'darwin' ? 'Meta+k' : 'Control+k');
      await page.waitForSelector('dialog.palette[open]');
    }
    await page.fill('dialog.palette input', q);
    await page.waitForTimeout(450);  // the server's matches arrive after a short pause
    return page.evaluate(() => [...document.querySelectorAll('dialog.palette .pal-item')].map((li) => ({ t: li.querySelector('.pal-t').textContent, type: li.dataset.type, sub: li.querySelector('small').textContent })));
  };
  const firstFor = {};
  for (const [q, want] of [['results', 'Results'], ['home', 'Today'], ['performance', 'Results'], ['targets', 'Settings: Targets'], ['schedules', 'Claude: Schedules'],
    ['swipe file', 'Research'], ['gallery', 'Gallery'], ['by idea', 'Ideas'], ['hooks', 'Ideas'], ['watched pages', 'Research: Watched Pages'], ['creative', 'Gallery'], ['tired', 'Gallery: Tired'], ['experiments', 'Tests'], ['dark mode', 'Switch theme'], ['needs attention', 'Ads that need attention'], ['ads review', 'Ads in review']]) {
    const got = await palette(q);
    firstFor[q] = got[0]?.t;
    if (got[0]?.t !== want) firstFor[q] = `${got[0]?.t} (wanted ${want})`;
  }
  check('⌘K finds pages, tabs, Settings sections and actions by their own name and by the words people use (Home, Results, Performance…)',
    Object.entries(firstFor).every(([, t]) => !/wanted/.test(t)), JSON.stringify(firstFor));
  await palette('targets');
  await Promise.all([page.waitForURL('**/settings.html#targets'), page.keyboard.press('Enter')]);
  await page.waitForSelector('#targets[data-section]:not([hidden])');
  await page.waitForTimeout(300);
  const targetsOpen = await page.evaluate(() => ({ top: Math.round(document.getElementById('targets').getBoundingClientRect().top),
    shown: [...document.querySelectorAll('[data-section]')].filter((x) => !x.hidden).map((x) => x.id).join() }));
  check('⌘K → "Settings: Targets" opens Settings on that section alone', targetsOpen.shown === 'targets' && targetsOpen.top >= 0 && targetsOpen.top < 300, JSON.stringify(targetsOpen));
  // Every address the long page had (and the links alerts stored) opens its section; a deep one opens its fold too.
  const anchors = {};
  for (const [hash, want] of [['meta-form', 'meta'], ['mt-form', 'ab'], ['tracking', 'tracking'], ['meta', 'meta'], ['tg-targets', 'targets'], ['reports-panel', 'reports-panel'],
    ['crm-code', 'crm'], ['smtp-form', 'email'], ['activity', 'activity-panel'], ['nonsense', 'meta'], ['', 'meta']]) {
    await page.goto(`${BASE}/settings.html${hash ? '#' + hash : ''}`);
    await page.reload();
    await page.waitForSelector('[data-section]:not([hidden])');
    const got = await page.evaluate((h) => ({ shown: [...document.querySelectorAll('[data-section]')].filter((x) => !x.hidden).map((x) => x.id).join(),
      fold: h === 'crm-code' ? document.getElementById('crm-adv').open : true }), hash);
    if (got.shown !== want || !got.fold) anchors[hash || '(none)'] = `${got.shown}${got.fold ? '' : ' (fold shut)'}`;
  }
  check('every old Settings address (#meta-form, #mt-form, #tracking, #meta…) opens its section, a field inside a fold opens the fold', Object.keys(anchors).length === 0, JSON.stringify(anchors));
  // A Meta test code is never saved, so typing one doesn't mark Lead stages as unsaved (nor warn on leaving).
  await page.goto(`${BASE}/settings.html#crm-code`);
  await page.reload();
  await page.waitForSelector('#crm-code');
  await page.fill('#crm-code', 'TEST1');
  await page.click('.settings-nav [data-set="meta"]');
  await page.waitForSelector('#meta[data-section]:not([hidden])');
  check('typing a Meta test code leaves no "not saved yet" mark', (await page.locator('.settings-nav .set-dirty').count()) === 0);
  // The Settings links the server writes into alerts and Today (from the alert rules themselves), plus any stored ones.
  const storedLinks = py(`
from datetime import timedelta
import alerts, db, account_ctx
from tests.test_alerts_logic import snap, TODAY, RULES
y, d2 = TODAY - timedelta(days=1), TODAY - timedelta(days=2)
found = alerts.evaluate(snap(meta_leads={y: 2, d2: 1}, inbox_leads={}, last_pull_age_h=4, tracking={'state': 'quiet', 'headline': 'x'}), RULES, TODAY)
links = {a['href'] for a in found if (a['href'] or '').startswith('/settings.html')}
with account_ctx.all_accounts():
    links |= {r['href'] for r in db.query('SELECT DISTINCT href FROM alerts WHERE left(href, 14) = \\'/settings.html\\'')}
print(' '.join(sorted(links)))`).split(' ').filter(Boolean);
  const unresolved = [];
  for (const href of storedLinks) {
    await page.goto(BASE + href);
    await page.reload();
    await page.waitForSelector('[data-section]:not([hidden])');
    const shown = await page.evaluate(() => [...document.querySelectorAll('[data-section]')].filter((x) => !x.hidden).map((x) => x.id).join());
    const hash = href.split('#')[1];
    if (hash && !(await page.evaluate(([h, id]) => { const el = document.getElementById(h); return !!el && el.closest('[data-section]').id === id; }, [hash, shown]))) unresolved.push(`${href} → ${shown}`);
  }
  check('the Settings links alerts carry (Meta connection, Tracking health) open their section', unresolved.length === 0
    && ['/settings.html#meta', '/settings.html#tracking'].every((h) => storedLinks.includes(h)), `${storedLinks.join(' ')} ${unresolved.join(' | ')}`);
  // A saved view is one Enter away.
  const qaView = await page.evaluate(async () => (await (await fetch('/api/views', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ page: 'ads', name: 'QA menu view', query: 'view=off&level=adset' }) })).json()).id);
  await page.goto(BASE + '/home.html');
  await page.waitForSelector('.crumbs *');
  const viewHit = (await palette('QA menu view'))[0];
  await Promise.all([page.waitForURL('**/ads.html?**'), page.keyboard.press('Enter')]);
  const viewUrl = new URL(page.url());
  check('⌘K lists saved views and opens one as it was saved', viewHit?.type === 'view' && /Saved view/.test(viewHit.sub) && viewUrl.searchParams.get('view') === 'off' && viewUrl.searchParams.get('level') === 'adset',
    `${JSON.stringify(viewHit)} → ${page.url()}`);
  await page.evaluate((id) => fetch(`/api/views/${id}`, { method: 'DELETE' }), qaView);
  // Results of every kind keep a place: many campaigns, ad sets and ads never push the leads out.
  const leadsWithE = Number(py(`import db;print(db.query(\\"SELECT COUNT(*) AS n FROM leads WHERE NOT is_test AND (full_name ILIKE '%in%' OR email ILIKE '%in%' OR phone ILIKE '%in%')\\", one=True)['n'])`));
  const wide = await getJson('/api/search?q=in');
  const kinds = wide.items.reduce((o, i) => ({ ...o, [i.type]: (o[i.type] || 0) + 1 }), {});
  check('a wide search keeps leads in the results however many ads match too', leadsWithE > 0 && kinds.ad >= 3 && kinds.lead === Math.min(leadsWithE, 8) && wide.items.length <= 24, `${leadsWithE} leads match · ${JSON.stringify(kinds)}`);
  const pctSearch = await getJson('/api/search?q=' + encodeURIComponent('%%'));
  check('a % typed in search means a %, not "anything"', pctSearch.items.length === 0, String(pctSearch.items.length));
  // A saved competitor ad and a test are found by their words, and open where they live.
  const qaSwipe = await page.evaluate(async () => (await (await fetch('/api/swipes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ page_name: 'QA Menu Rivals', body: 'Quotes to invoices without retyping a thing' }) })).json()).id);
  const swipeHit = (await palette('without retyping'))[0];
  await Promise.all([page.waitForURL('**/research.html#swipe=**'), page.keyboard.press('Enter')]);
  await page.waitForSelector(`#swipes [data-swipe="${qaSwipe}"].flash`);
  check('⌘K finds a saved competitor ad by its words and Research shows it marked', swipeHit?.type === 'swipe' && /^QA Menu Rivals: Quotes to invoices/.test(swipeHit.t), JSON.stringify(swipeHit));
  await page.evaluate((id) => fetch(`/api/swipes/${id}`, { method: 'DELETE' }), qaSwipe);
  const qaTest = await getJson('/api/experiments').then((r) => r.items[0]);
  if (qaTest) {
    const testHit = (await palette(qaTest.name.slice(0, 12))).find((i) => i.type === 'test');
    check('⌘K finds a test by name', testHit && testHit.t === qaTest.name, JSON.stringify(testHit));
  }
  await page.keyboard.press('Escape');
  // This page's own tabs: an ad's Polish tab from the menu.
  await page.goto(BASE + '/ad.html?id=120252672230740312');
  await page.waitForSelector('#cr-tabs [role="tab"]');
  const tabHit = (await palette('polish')).find((i) => i.sub === 'This page');
  await page.locator('dialog.palette .pal-item', { hasText: 'This page' }).filter({ hasText: 'Polish' }).click();
  await page.waitForSelector('#cr-tabs [data-tab="polish"][aria-selected="true"]');
  check('⌘K offers this page\'s own tabs (an ad\'s Polish) and opens them', /: Polish$/.test(tabHit?.t || '') && /tab=polish/.test(page.url()), `${JSON.stringify(tabHit)} ${page.url()}`);
  // "?" shows every shortcut; an action runs from the menu.
  await page.locator('body').click({ position: { x: 5, y: 300 } });
  await page.keyboard.press('Shift+Slash');
  await page.waitForSelector('dialog.confirm .keys-list');
  const keysText = await page.textContent('dialog.confirm');
  check('"?" opens the keyboard shortcuts', /Keyboard shortcuts/.test(keysText) && /Search or jump to anything/.test(keysText) && /Settings/.test(keysText), keysText.slice(0, 120));
  await page.keyboard.press('Escape');
  await page.waitForSelector('dialog.confirm', { state: 'detached' });
  const themeBefore = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
  await palette('switch theme');
  await page.keyboard.press('Enter');
  const themeAfter = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
  check('⌘K runs an action (Switch theme) right where you are', themeAfter !== themeBefore && !(await page.isVisible('dialog.palette[open]')), `${themeBefore} → ${themeAfter}`);
  await page.evaluate(() => { localStorage.removeItem('ebads-theme'); document.documentElement.removeAttribute('data-theme'); });
  // Tabs from the menu land on what they name: Ideas, a Research part, a Claude view, an Inbox filter.
  await page.goto(BASE + '/home.html');
  await palette('by idea');
  await Promise.all([page.waitForURL('**/ideas.html'), page.keyboard.press('Enter')]);
  await page.waitForSelector('.idea-grp, #ideas .empty');
  check('⌘K → "Ideas" (also found as "by idea") opens Creative › Ideas', /Creative\s*\/\s*Ideas/.test(await page.textContent('.crumbs')));
  await palette('Research: Watched Pages');
  await Promise.all([page.waitForURL('**/research.html#tab=watched'), page.keyboard.press('Enter')]);
  await page.waitForSelector('#watch-form', { state: 'visible' });
  check('⌘K → "Research: Watched Pages" opens Research on that part', (await page.getAttribute('#rs-tabs [aria-selected="true"]', 'data-part')) === 'watched');
  // An older link to Results' By idea panel still lands on its summary.
  await page.goto(BASE + '/performance.html#ideas-panel');
  await page.waitForSelector('#ideas-sum p');
  await page.waitForTimeout(800);
  // The line is short now, so near the end of the page it can sit lower once the page is scrolled to its end.
  const ideasAt = await page.evaluate(() => ({ top: Math.round(document.getElementById('ideas-panel').getBoundingClientRect().top),
    end: Math.ceil(scrollY + innerHeight) >= document.documentElement.scrollHeight - 2, scrolled: scrollY > 0 }));
  check('an older "Results: By idea" link opens Results scrolled to its By idea line', ideasAt.scrolled && ideasAt.top >= 0 && (ideasAt.top < 200 || ideasAt.end) && ideasAt.top < 700, JSON.stringify(ideasAt));
  await palette('Claude: Schedules');
  await Promise.all([page.waitForURL('**/desk.html#schedules'), page.keyboard.press('Enter')]);
  await page.waitForSelector('[data-sub="schedules"][aria-current="page"]');
  check('⌘K → "Claude: Schedules" opens Claude on its Schedules view', /#schedules$/.test(page.url()));
  await palette('Inbox: Money');
  await Promise.all([page.waitForURL('**/inbox.html?box=all&kind=money'), page.keyboard.press('Enter')]);
  await page.waitForSelector('#ib-filters [data-f="money"][aria-pressed="true"]');
  check('⌘K → "Inbox: Money" opens the Inbox on the Money filter', /kind=money/.test(page.url()) && (await page.getAttribute('#ib-box [aria-selected="true"]', 'data-box')) === 'all');
  await page.goto(BASE + '/inbox.html?show=money');
  await page.waitForSelector('#ib-filters [data-f="money"][aria-pressed="true"]');
  check('an older Inbox link (?show=money) still lands on Money', (await page.getAttribute('#ib-box [aria-selected="true"]', 'data-box')) === 'all');
  // 9.5 Creative › Gallery: every ad as people see it, copies of one ad as one card, numbers from stored days.
  {
    const N2 = '120252672229400312', N1 = '120252672229040312';
    const gal = (q = '') => getJson(`/api/gallery?range=7${q}`);
    const cardOf = (d, adId) => d.groups.find((x) => x.ads.some((a) => a.id === adId));
    const before = cardOf(await gal(), N2);
    // The same video and words (spacing and capitals aside) on a new creative in the same ad set, and a picture ad.
    py(`import db, account_info
from datetime import timedelta
y = account_info.today() - timedelta(days=1)
db.execute('DELETE FROM ad_daily WHERE ad_id IN (%s, %s)', ('qa-gal-copy', 'qa-gal-pic'))
db.execute('DELETE FROM ads WHERE id IN (%s, %s)', ('qa-gal-copy', 'qa-gal-pic'))
db.execute('''INSERT INTO ads (id, name, campaign_id, adset_id, status, effective_status, creative_id, object_type, title, body, cta_type, video_id, image_url, created_time)
  SELECT 'qa-gal-copy', 'QA gallery copy', campaign_id, adset_id, 'PAUSED', 'PAUSED', 'qa-gal-creative', object_type, '  ' || upper(title), body, cta_type, video_id, image_url, created_time
  FROM ads WHERE id = %s''', ('${N2}',))
db.execute('''INSERT INTO ads (id, name, campaign_id, adset_id, status, effective_status, creative_id, object_type, title, body, cta_type, video_id, image_url, created_time)
  SELECT 'qa-gal-pic', 'QA gallery picture', campaign_id, adset_id, 'PAUSED', 'PAUSED', 'qa-gal-pic-creative', 'SHARE', 'A picture', 'Words', cta_type, NULL, image_url, created_time
  FROM ads WHERE id = %s''', ('${N2}',))
for ad, spend, leads in (('qa-gal-copy', 500, 1), ('qa-gal-pic', 300, 1)):
    db.execute('INSERT INTO ad_daily (day, ad_id, spend_cents, impressions, leads, video_3s) VALUES (%s, %s, %s, 1000, %s, 0)', (y, ad, spend, leads))`);
    const after = await gal();
    const merged = cardOf(after, N2);
    const pic = cardOf(after, 'qa-gal-pic');
    check('Gallery: the same video with the same words on a new creative is one card, its numbers added once',
      merged && merged.ads.map((a) => a.id).sort().join() === [N2, 'qa-gal-copy'].sort().join() && merged.top_ad_id === N2
      && merged.spend_cents === before.spend_cents + 500 && merged.leads === before.leads + 1 && cardOf(after, 'qa-gal-copy') === merged,
      JSON.stringify({ before: before && [before.spend_cents, before.leads], after: merged && [merged.spend_cents, merged.leads, merged.ads.length] }));
    check('Gallery: a picture ad is its own card with no hook rate (not 0)', pic && pic.ads.length === 1 && pic.kind === 'image' && pic.hook_rate === null, JSON.stringify(pic && [pic.kind, pic.hook_rate]));
    await page.goto(BASE + '/gallery.html?range=7');
    await page.waitForSelector('.gal-card');
    const shown = await page.evaluate(([mk, pk]) => {
      const m = document.querySelector(`.gal-card[data-key="${mk}"]`), p = document.querySelector(`.gal-card[data-key="${pk}"]`);
      return { copies: m?.querySelector('.gal-copies')?.textContent || '', hook: !!m && /Hook rate/.test(m.textContent), picHook: !!p && /Hook rate/.test(p.textContent),
        crumbs: document.querySelector('.crumbs')?.textContent, tabs: [...document.querySelectorAll('.subnav a')].map((a) => a.textContent), nav: document.querySelector('.rail .nav a[aria-current="page"]')?.textContent.trim() };
    }, [merged?.key, pic?.key]);
    check('Gallery page: the merged card says it runs as 2 ads, video cards show a hook rate, the picture card none; it sits under Creative with Gallery · Ideas · Research',
      /Runs as 2 ads/.test(shown.copies) && shown.hook && !shown.picHook && /Creative\s*\/\s*Gallery/.test(shown.crumbs) && shown.tabs.join() === 'Gallery,Ideas,Research' && shown.nav === 'Creative', JSON.stringify(shown));
    // A card whose copy Meta rejected shows under "Rejected or has a problem" even when another copy delivers, and says so.
    py(`import db
db.execute('UPDATE ads SET effective_status = %s WHERE id = %s', ('DISAPPROVED', 'qa-gal-copy'))`);
    const bad = await gal('&status=problem');
    const badCard = bad.groups.find((x) => x.key === merged?.key);
    await page.goto(BASE + '/gallery.html?range=7&status=problem');
    await page.waitForSelector('.gal-card, #gal .empty');
    const badShown = merged ? await page.evaluate((k) => document.querySelector(`.gal-card[data-key="${k}"]`)?.textContent || '', merged.key) : '';
    check('Gallery: a card with one rejected copy shows under "Rejected or has a problem", saying which part of it is',
      !!badCard && badCard.buckets.includes('problem') && (badCard.bucket === 'problem' || /1 copy is rejected/.test(badShown)), JSON.stringify(badCard && [badCard.bucket, badCard.buckets, badCard.problems]));
    py(`import db
db.execute('DELETE FROM ad_daily WHERE ad_id IN (%s, %s)', ('qa-gal-copy', 'qa-gal-pic'))
db.execute('DELETE FROM ads WHERE id IN (%s, %s)', ('qa-gal-copy', 'qa-gal-pic'))`);
    // Top: the judged cards cheapest first, then the rest by spend.
    const top = (await gal()).groups;
    const judged = top.filter((x) => x.enough);
    check('Gallery Top: judged cards first, cheapest cost per lead first; deleted cards only under Deleted',
      judged.length > 0 && top.slice(0, judged.length).every((x) => x.enough)
      && judged.every((x, i) => i === 0 || judged[i - 1].cpl_cents <= x.cpl_cents) && top.every((x) => x.bucket !== 'deleted'), top.map((x) => `${x.name}:${x.enough}:${x.cpl_cents}`).join(' | '));
    const launched = await gal('&view=launched');
    const weekAgo = new Date(Date.now() - 8 * 86400000).toISOString().slice(0, 10);
    check('Gallery Just launched: only cards that started in the last 7 days, newest first, and its chip counts them',
      launched.groups.every((x) => x.just_launched && x.launched_on >= weekAgo) && launched.groups.every((x, i) => i === 0 || launched.groups[i - 1].launched_on >= x.launched_on)
      && launched.counts.launched === launched.groups.length, launched.groups.map((x) => `${x.name}:${x.launched_on}`).join(' | '));
    if (launched.groups.length) {
      await page.goto(BASE + '/gallery.html?range=7&view=launched');
      await page.waitForSelector('.gal-card');
      const started = await page.$$eval('.gal-card', (cs) => cs.map((c) => c.querySelector('.gal-started')?.textContent || ''));
      check('Gallery Just launched: every card says the day it started', started.length === launched.groups.length && started.every((t) => /^Started \w{3} \d{1,2}$/.test(t.trim())), started.join(' | '));
    }
    // A card whose ad changed what it shows counts only the days of what it shows now, and says so with a link to its versions.
    const changedCard = (await gal()).groups.find((x) => x.version_since);
    check('Gallery: an ad that changed what it shows is marked with the day it changed (dev N3 / N5 have new versions)', !!changedCard);
    if (changedCard) {
      await page.goto(BASE + '/gallery.html?range=7');
      await page.waitForSelector('.gal-card');
      const since = await page.evaluate((k) => { const c = document.querySelector(`.gal-card[data-key="${k}"] .gal-since`); return c ? { text: c.textContent, href: c.querySelector('a')?.getAttribute('href') } : null; }, changedCard.key);
      check('Gallery: a changed ad\'s card says its numbers and bars count only the days it showed this version, linking its versions; the bars have their legend',
        !!since && /Changed on .*count only the days it showed this version/.test(since.text) && since.href === `/ad.html?id=${changedCard.version_ad}#fold=versions`
        && (await page.locator('#gal .trk-key').count()) === 1, JSON.stringify(since));
      await Promise.all([page.waitForURL('**/ad.html?id=**'), page.click(`.gal-card[data-key="${changedCard.key}"] .gal-since a`)]);
      await page.waitForSelector('#fold-versions');
      check('"See versions" opens the ad on its Versions panel', await page.evaluate(() => document.getElementById('fold-versions').open));
      await page.evaluate(() => { document.getElementById('fold-versions').open = false; });
    }
    // Tired comes from the fatigue alert; with that rule off the view says so.
    py(`import db, uuid, settings_store
settings_store.set('qa_rules_backup', settings_store.get('alert_rules') or '')
db.execute('INSERT INTO alerts (rule, dedupe_key, level, title, lines, entity_id, kind) VALUES (%s, %s, %s, %s, %s, %s, %s)', ('fatigue', 'qa-tired-' + uuid.uuid4().hex, 'warn', 'QA looks tired', '[]', '${N1}', 'condition'))`);
    try {
    await page.goto(BASE + '/gallery.html?view=tired&range=7');
    await page.waitForSelector('.gal-card, .empty');
    const tiredCards = await page.evaluate(() => [...document.querySelectorAll('.gal-card')].map((c) => ({ name: c.querySelector('.cr-name')?.textContent, tired: /Tired/.test(c.querySelector('.gal-status')?.textContent || '') })));
    check('Gallery Tired: the ads with an open "looks tired" alert, marked Tired', tiredCards.some((c) => /^N1/.test(c.name)) && tiredCards.every((c) => c.tired)
      && (await page.getAttribute('[data-gview="tired"]', 'aria-pressed')) === 'true', JSON.stringify(tiredCards));
    py(`import json, settings_store, alerts
r = alerts.saved_rules(); r['fatigue']['on'] = False
settings_store.set('alert_rules', json.dumps(r))`);
    await page.reload();
    await page.waitForSelector('.note');
    check('Gallery Tired says when the tired check is switched off in Settings › Alerts', /switched off/.test(await page.textContent('#gal .note'))
      && (await page.getAttribute('#gal .note a', 'href')) === '/settings.html#alerts');
    } finally {
      py(`import db, settings_store
db.execute('DELETE FROM alerts WHERE rule = %s AND title = %s', ('fatigue', 'QA looks tired'))
settings_store.set('alert_rules', settings_store.get('qa_rules_backup') or '')
db.execute('DELETE FROM settings WHERE key = %s', (settings_store.stored_key('qa_rules_backup'),))`);
    }
    // Filters: a tag on a card narrows to that idea (any copy), the status picker keeps one status; both in the URL.
    await page.goto(BASE + '/gallery.html?range=7');
    await page.waitForSelector('.gal-card .gal-tag');
    const tagBtn = page.locator(`.gal-card[data-key="${before.key}"] .gal-tag`).first();
    const tagWord = (await tagBtn.textContent()).trim();
    await tagBtn.click();
    await page.waitForFunction((t) => new URL(location.href).searchParams.get('tag') === t && document.querySelector('.gal-tag[aria-pressed="true"]'), tagWord);
    const tagged = await gal(`&dim=hook&tag=${encodeURIComponent(tagWord)}`);
    check('Gallery: a card\'s idea tag filters to the cards with that idea, and the URL keeps it',
      tagged.groups.length >= 1 && tagged.groups.every((x) => x.tags_all.some(([d, v]) => d === 'hook' && v === tagWord))
      && (await page.locator('.gal-card').count()) === tagged.groups.length && (await page.inputValue('#tag-pick')) === `hook:${tagWord}`, `${tagWord}: ${tagged.groups.length}`);
    await page.selectOption('#tag-pick', '');
    await page.selectOption('#status-pick', 'deleted');
    await page.waitForFunction(() => new URL(location.href).searchParams.get('status') === 'deleted');
    await page.waitForTimeout(300);
    const del = await gal('&status=deleted');
    check('Gallery: the status picker shows only that status (Deleted here)', del.groups.length > 0 && del.groups.every((x) => x.bucket === 'deleted')
      && (await page.locator('.gal-card').count()) === del.groups.length);
    // Compare from two cards: each card's top-spending ad, on the same dates.
    await page.goto(BASE + '/gallery.html?range=14');
    await page.waitForSelector('.gal-card [data-pick]');
    const keys = await page.$$eval('.gal-card', (cs) => cs.slice(0, 2).map((c) => c.dataset.key));
    const tops = (await gal('').then(() => getJson('/api/gallery?range=14'))).groups.filter((x) => keys.includes(x.key)).sort((a, b) => keys.indexOf(a.key) - keys.indexOf(b.key)).map((x) => x.top_ad_id);
    await page.locator(`.gal-card[data-key="${keys[0]}"] [data-pick]`).check();
    await page.waitForSelector('#gal-tray [data-tray="compare"][disabled]');
    check('Gallery: with one card picked, the tray says in words why Compare waits', /Pick 2 to 6 to compare/.test(await page.textContent('#gal-tray')) && await page.isVisible('#gal-why'));
    await page.locator(`.gal-card[data-key="${keys[1]}"] [data-pick]`).check();
    await page.waitForSelector('#gal-tray [data-tray="compare"]:not([disabled])');
    await Promise.all([page.waitForURL('**/compare.html?**'), page.click('#gal-tray [data-tray="compare"]')]);
    const cmpUrl = new URL(page.url());
    check('Gallery: Compare from two picked cards opens Compare on their top-spending ads with the same dates',
      cmpUrl.searchParams.get('ids') === tops.join(',') && cmpUrl.searchParams.get('range') === '14' && cmpUrl.searchParams.get('vs') === '1', page.url());
    // On a phone the tray never covers the last row: the page makes room below it.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(BASE + '/gallery.html?range=30');
    await page.waitForSelector('.gal-card [data-pick]');
    for (const box of (await page.$$('.gal-card [data-pick]')).slice(0, 2)) await box.check();
    await page.waitForSelector('#gal-tray .bk');
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await page.waitForTimeout(200);
    const room = await page.evaluate(() => { const cs = document.querySelectorAll('.gal-card'); return { last: cs[cs.length - 1].getBoundingClientRect().bottom, tray: document.querySelector('#gal-tray .bk').getBoundingClientRect().top }; });
    check('Gallery on a phone: with cards picked, the last card ends above the tray', room.last <= room.tray, JSON.stringify(room));
    await page.keyboard.press('Escape');
    check('Gallery: Escape clears the picks and gives the room back', !(await page.evaluate(() => document.body.classList.contains('has-bulk'))) && (await page.locator('#gal-tray .bk').count()) === 0);
    await page.setViewportSize({ width: 1360, height: 900 });
    // ⌘K and the Claude section: Research lives under Creative now, at the same address.
    await page.goto(BASE + '/research.html');
    await page.waitForSelector('.crumbs a');
    const research = await page.evaluate(() => ({ crumbs: document.querySelector('.crumbs').textContent, tabs: [...document.querySelectorAll('.subnav a')].map((a) => a.textContent) }));
    await page.goto(BASE + '/desk.html');
    await page.waitForSelector('.crumbs *');
    await page.waitForSelector('nav.subnav [data-sub="schedules"]');
    const deskTabs = await page.evaluate(() => [...document.querySelectorAll('nav.subnav a')].map((a) => a.textContent));
    check('Research sits under Creative (same address), and Claude no longer has a Research tab',
      /Creative\s*\/\s*Research/.test(research.crumbs) && research.tabs.join() === 'Gallery,Ideas,Research' && deskTabs.join() === 'Conversations,By ad,Schedules', JSON.stringify({ research, deskTabs }));
  }
  // 9.4 Inbox triage: Needs action first, FYI for the rest; the badge counts what needs you and is new.
  await page.goto(BASE + '/inbox.html');
  await page.waitForSelector('.ib-item, .ib-none');
  check('the Inbox opens on Needs action, with For your information and All beside it, and filters by kind',
    (await page.locator('#ib-box [role="tab"]').count()) === 3 && (await page.getAttribute('#ib-box [aria-selected="true"]', 'data-box')) === 'need'
    && (await page.locator('#ib-filters [data-f]').count()) === 6 && (await page.locator('#ib-filters [data-unread]').count()) === 1 && (await page.locator('.ib-item').count()) > 0);
  // Raised straight into the table: no message goes out for these two.
  const triage = ['qa-triage-ad', 'qa-triage-ad2'].map((ent, i) => py(`import db,uuid;r=db.execute(\\"INSERT INTO alerts (rule, dedupe_key, level, title, lines, entity_id, campaign_id, href, kind, resolved_at) VALUES ('ad_rejected', %s, 'bad', %s, '[]', %s, '120252638288040312', '/ads.html', 'condition', ${i ? 'NULL' : 'now()'}) RETURNING id\\", ('qa-'+uuid.uuid4().hex, '${i ? 'QA still rejected' : 'QA fixed since'}', '${ent}'), returning=True);print(r['id'])`));
  const needList = await getJson('/api/inbox?box=need');
  const fyiList = await getJson('/api/inbox?box=fyi');
  const frame = await getJson('/api/refresh');
  check('a problem fixed since sits in For your information and leaves the needs-action count; an open one needs action',
    needList.items.some((i) => i.key === `alert:${triage[1]}`) && !needList.items.some((i) => i.key === `alert:${triage[0]}`) && fyiList.items.some((i) => i.key === `alert:${triage[0]}`)
    && needList.items.every((i) => i.need) && fyiList.items.every((i) => !i.need), triage.join());
  await page.reload();
  await page.waitForSelector('.ib-item');
  await page.waitForTimeout(600);
  check('the Inbox badge and the Needs action tab count the same: what needs you and is new, not every unread note', frame.inbox_need === needList.counts.need_unread
    && frame.inbox_unread === needList.counts.unread && (await page.textContent('.rail [data-inbox-count]')).trim() === String(frame.inbox_need || '')
    && ((await page.locator('#ib-box [data-box="need"] .n').count()) ? (await page.textContent('#ib-box [data-box="need"] .n')).trim() : '') === String(frame.inbox_need || ''),
    `${frame.inbox_need} / ${frame.inbox_unread} / ${await page.textContent('.rail [data-inbox-count]')}`);
  // E only marks read: the item under the keyboard loses its dot, nothing opens, nothing is decided.
  const unreadRows = page.locator('#ib-list .ib-item.unread');
  const firstOpen = (await page.textContent('#ib-detail h2')).trim();
  const urlBefore = page.url();
  const eKey = await unreadRows.nth(1).getAttribute('data-key');
  await unreadRows.nth(1).focus();
  await page.keyboard.press('e');
  await page.waitForFunction((k) => !document.querySelector(`#ib-list [data-key="${k}"]`)?.classList.contains('unread'), eKey);
  const eRead = (await getJson('/api/inbox?box=need')).items.find((i) => i.key === eKey);
  check('E marks the item read and does nothing else', eRead && !eRead.unread && page.url() === urlBefore
    && (await page.textContent('#ib-detail h2')).trim() === firstOpen, `${eKey} ${firstOpen}`);
  // A suggestion in the Inbox is accepted through the Accept sheet only.
  let claudeItems = (await getJson('/api/inbox?box=need&kind=claude')).items;
  if (!claudeItems.length) {
    py(`import db;db.execute(\\"INSERT INTO desk_proposals (task_id, kind, title, status) SELECT id, 'other', 'QA inbox suggestion', 'pending' FROM desk_tasks ORDER BY id DESC LIMIT 1\\")`);
    claudeItems = (await getJson('/api/inbox?box=need&kind=claude')).items;
  }
  await page.goto(BASE + `/inbox.html?box=need&kind=claude#item=${encodeURIComponent(claudeItems[0].key)}`);
  await page.waitForSelector('#ib-detail [data-accept]');
  check('a suggestion in the Inbox has no bare accept button, only Review and accept', (await page.locator('#ib-detail button', { hasText: /^Accept$/ }).count()) === 0
    && /Review and accept/.test(await page.textContent('#ib-detail [data-accept]')));
  await page.click('#ib-detail [data-accept]');
  await page.waitForSelector('dialog.accept-sheet #cd-ok:not(:empty)');
  check('Review and accept opens the Accept sheet on Cancel', (await page.evaluate(() => document.activeElement.id)) === 'cd-cancel');
  await page.click('dialog.accept-sheet #cd-cancel');
  await page.waitForSelector('dialog.accept-sheet', { state: 'detached' });
  check('cancelling the sheet leaves the suggestion waiting', (await getJson('/api/inbox?box=need&kind=claude')).items.some((i) => i.key === claudeItems[0].key));
  // 9.3a: an item about a campaign, ad set or ad names it with a link, and the open item is in the URL.
  const navAlert = py(`import alerts;r=alerts.raise_found([{'rule':'changed_outside','key':'qa-nav-subject-'+__import__('uuid').uuid4().hex,'level':'info','title':'QA changed outside','lines':['Budget changed in Ads Manager'],'entity_id':'120252638288040312','campaign_id':'120252638288040312','href':'/campaign.html?id=120252638288040312','kind':'event'}]);print(r[0][0])`);
  await page.goto(BASE + `/inbox.html#item=alert%3A${navAlert}`);
  await page.waitForSelector('#ib-detail .ib-about a.ent-link');
  check('an Inbox item opened by its address names its campaign with a link to it, even when it is for your information', (await page.getAttribute('#ib-detail .ib-about a.ent-link', 'href')) === '/campaign.html?id=120252638288040312'
    && /QA changed outside/.test(await page.textContent('#ib-detail h2')) && /For your information/.test(await page.textContent('#ib-detail .ib-kicker')), navAlert);
  // The item named by the address only counts on arrival: picking a filter, opening an item and refreshing keep the filter.
  await page.click('#ib-filters [data-unread]');
  await page.waitForSelector('#ib-filters [data-unread][aria-pressed="true"]');
  await page.waitForSelector('.ib-item, .ib-none');
  const ibPicked = (await page.locator('.ib-item').count()) ? await page.locator('.ib-item').first().getAttribute('data-key') : null;
  if (ibPicked) { await page.locator('.ib-item').first().click(); await page.waitForFunction(() => /item=/.test(location.hash)); }
  const ibTitle = ibPicked ? (await page.textContent('#ib-detail h2')).trim() : '';
  await Promise.all([page.waitForResponse((r) => /\/api\/inbox\?/.test(r.url())), page.click('.topline [data-refresh]')]);
  await page.waitForTimeout(400);
  const ibAfter = await page.evaluate(() => ({ on: document.querySelector('#ib-filters [data-unread]')?.getAttribute('aria-pressed'), unread: new URLSearchParams(location.search).get('unread'),
    title: document.querySelector('#ib-detail h2')?.textContent.trim() || '' }));
  check('with Unread only, opening an item and refreshing keep Unread only and the item on screen', ibPicked && ibAfter.on === 'true' && ibAfter.unread === '1' && ibAfter.title === ibTitle,
    JSON.stringify({ ibPicked, ibTitle, ...ibAfter }));
  await page.click('#ib-filters [data-f="leads"]');
  await page.waitForTimeout(400);
  const ibLeads = await page.evaluate(() => ({ sel: document.querySelector('#ib-filters [data-f][aria-pressed="true"]')?.dataset.f, kind: new URLSearchParams(location.search).get('kind'), hash: location.hash }));
  check('picking another filter after an item was open keeps that filter and drops the item from the address', ibLeads.sel === 'leads' && ibLeads.kind === 'leads' && !/item=/.test(ibLeads.hash), JSON.stringify(ibLeads));
  py(`import db;db.execute(\\"DELETE FROM alerts WHERE entity_id IN ('qa-triage-ad', 'qa-triage-ad2')\\")`);
  // 8.6 Ads manager: select → bulk bar (Cancel changes nothing, confirm turns off), peek with the timeline, level in the URL,
  // a saved view from the toolbar, campaign and ad set pages with breadcrumbs.
  await page.goto(BASE + '/ads.html?view=delivering');
  await page.waitForSelector('.tbl [data-pick]');
  const picks = page.locator('.tbl [data-pick]');
  const pickedIds = [await picks.nth(0).getAttribute('data-pick'), await picks.nth(1).getAttribute('data-pick')];
  await picks.nth(0).check(); await picks.nth(1).check();
  await page.waitForSelector('.bk');
  check('selecting ads shows the bulk bar with the count', /2\s*selected/.test(await page.textContent('.bk')));
  await page.click('.bk [data-bulk="off"]');
  await page.waitForSelector('dialog.confirm');
  const offDialog = await page.textContent('dialog.confirm');
  await page.click('dialog.confirm #cd-cancel');
  await page.waitForTimeout(400);
  const stillOn = await page.evaluate((ids) => Promise.all(ids.map((i) => fetch(`/api/ads/ad/${i}`).then((r) => r.json()).then((d) => d.ad.status))), pickedIds);
  check('bulk off lists every ad first, and Cancel changes nothing', /Turn off 2 ads/.test(offDialog) && stillOn.every((x) => x === 'ACTIVE'), offDialog.replace(/\s+/g, ' ').slice(0, 160));
  await page.click('.bk [data-bulk="off"]');
  await page.waitForSelector('dialog.confirm');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => !document.querySelector('.bk'));
  const nowOff = await page.evaluate((ids) => Promise.all(ids.map((i) => fetch(`/api/ads/ad/${i}`).then((r) => r.json()).then((d) => d.ad.status))), pickedIds);
  check('confirmed, bulk off turns both off', nowOff.every((x) => x === 'PAUSED'), nowOff.join());
  for (const i of pickedIds) {  // back on, one by one through the console's own switch rules
    const sp = await call('GET', `/api/ads/ad/${i}/spend`);
    await call('POST', `/api/ads/ad/${i}/status`, { status: 'ACTIVE', confirm_daily_cents: sp.body.daily_cents });
  }
  await page.goto(BASE + '/ads.html');
  await page.waitForSelector('.tbl tbody tr');
  await page.locator('.tbl tbody tr').first().locator('td.num').first().click();
  await page.waitForSelector('.pk.open .pk-tl li');
  check('clicking a row opens a quick look with its history, and the URL remembers it', /peek=ad/.test(page.url()) && (await page.locator('.pk.open .pk-tl li').count()) > 0);
  await page.keyboard.press('Escape');
  await page.click('#level [data-level="adset"]');
  await page.waitForSelector('.tbl tr[data-row^="adset:"]');
  check('the level switch shows ad sets and keeps it in the URL', /level=adset/.test(page.url()));
  await page.click('.view-chip#save-view');
  await page.waitForSelector('dialog.confirm #cd-input');
  await page.fill('#cd-input', 'QA ad sets');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForSelector('[data-saved]');
  await page.goto(BASE + '/ads.html');
  await page.waitForSelector('[data-saved]');
  await page.click('[data-saved]');
  await page.waitForSelector('.tbl tr[data-row^="adset:"]');
  check('a saved view from the toolbar brings back its level', /level=adset/.test(page.url()));
  await page.click('[data-unsave]');
  await page.goto(BASE + '/campaign.html?id=' + C1);
  await page.waitForSelector('.tbl tr[data-row^="adset:"]');
  check('a campaign page lists its ad sets under Ads › campaign', (await page.textContent('.crumbs')).includes('Free intro call') && await page.isVisible('#c-spend svg'));
  await page.goto(BASE + '/adset.html?id=120252672227950312');
  await page.waitForSelector('.tbl tr[data-row^="ad:"]');
  check('an ad set page shows its ads, learning and who sees it', /Learning/.test(await page.textContent('.learn')) && (await page.textContent('.crumbs')).split('/').length === 3);
  // 8.7 Compare page, Leads by source, Today's Inbox card.
  await page.goto(BASE + '/compare.html?ids=120252672232030312,120252672233160312,120252672230740312&range=14');
  await page.waitForSelector('#cmp-chart svg .ln');
  const cmpText = await page.textContent('#cmp');
  const cmpWords = await page.evaluate(() => { const svg = document.querySelector('#cmp-chart svg'); const d = document.getElementById(svg.getAttribute('aria-describedby')); return d ? d.textContent : ''; });
  check('the Compare chart says in words, per ad, its highest day and its last value', (cmpWords.match(/: (highest .+? on .+?, last [^;.]+|no data)/g) || []).length === 3, cmpWords);
  const cmpBox = await page.evaluate(() => { const w = document.querySelector('#cmp .tbl-wrap') || document.querySelector('.tbl-wrap'); return { max: getComputedStyle(w).maxHeight, cut: w.scrollHeight - w.clientHeight }; });
  check('the Compare table is shown at its full height (only the manager table scrolls in a box)', cmpBox.max === 'none' && cmpBox.cut <= 1, JSON.stringify(cmpBox));
  check('the Compare page lines up 3 ads with a verdict and a line per ad', (await page.locator('.cmp thead .cmp-th').count()) === 3
    && (await page.locator('#cmp-chart .ln').count()) === 3 && /Too early to name a winner|leads on cost per/.test(cmpText));
  // 9.4d: the metric names stay put while the ads scroll sideways; each ad's number is on its column, its line end and the legend.
  check('Compare keeps the metric column in view when the ads scroll sideways', await page.evaluate(() => getComputedStyle(document.querySelector('.cmp tbody th')).position === 'sticky'
    && getComputedStyle(document.querySelector('.cmp .cmp-corner')).position === 'sticky'));
  const cmpKeys = await page.evaluate(() => ({
    heads: [...document.querySelectorAll('.cmp thead .cmp-n b')].map((b) => b.textContent),
    ends: [...document.querySelectorAll('#cmp-chart .ln-key text')].map((t) => t.textContent).sort(),
    legend: [...document.querySelectorAll('.cmp-legend .cmp-n b')].map((b) => b.textContent),
    dashes: new Set([...document.querySelectorAll('#cmp-chart polyline.ln')].map((l) => l.getAttribute('stroke-dasharray') || 'solid')).size,
    visible: (() => { const b = document.querySelector('.cmp thead .cmp-n b'); const cs = getComputedStyle(b); return cs.color !== cs.backgroundColor; })(),
  }));
  check('each line is told apart without colour: a number on its column, at its end and in the legend, and its own dash',
    cmpKeys.heads.join() === '1,2,3' && cmpKeys.ends.join() === '1,2,3' && cmpKeys.legend.join() === '1,2,3' && cmpKeys.dashes === 3 && cmpKeys.visible, JSON.stringify(cmpKeys));
  await page.click('[data-drop]');
  await page.waitForFunction(() => document.querySelectorAll('.cmp thead .cmp-th').length === 2);
  check('removing an ad from the comparison keeps the rest', (new URL(page.url())).searchParams.get('ids').split(',').length === 2);
  // 9.3a Navigation: names link to their pages, reverse links, one date range, breadcrumbs back to the filtered list,
  // Cancel back to where a New page was opened from, and Back closes the quick look.
  const NAV_AD = '120252672229400312';
  await page.goto(BASE + `/ad.html?id=${NAV_AD}`);
  await page.waitForSelector('#cr-main .facts a.ent-link[href^="/campaign.html?id="]');
  check('the ad page links its campaign and ad set', (await page.locator('#cr-main .facts a.ent-link[href^="/adset.html?id="]').count()) === 1);
  await Promise.all([page.waitForURL('**/compare.html?ids=**'), page.click('#cr-actions a[href^="/compare.html"]')]);
  await page.waitForSelector('#cmp-pick');
  check('Compare from an ad opens the picker with that ad already ticked', await page.isChecked(`#cmp-pick input[value="${NAV_AD}"]`));
  const pickCards = await page.evaluate(() => [...document.querySelectorAll('.cmp-opt')].slice(0, 3).map((c) => ({ img: !!c.querySelector('img.cmp-opt-img'), m: c.querySelector('.cmp-opt-m')?.textContent || '' })));
  check('the picker shows each ad with its picture and its numbers for the dates', pickCards.length === 3 && pickCards.every((c) => c.img && /spent/.test(c.m) && /lead/.test(c.m)), JSON.stringify(pickCards));
  check('Compare waits for a second ad', await page.isDisabled('#cmp-go') && /pick 1 more/.test(await page.textContent('#cmp-count')));
  const boxes = page.locator('#cmp-pick input[type=checkbox]:not(:checked)');
  const second = await boxes.nth(0).getAttribute('value');
  await boxes.nth(0).check();
  // Ticks survive a change of campaign, so ads from two campaigns can be compared.
  await page.waitForSelector('#cmp-camp');
  const otherCamp = await page.$eval('#cmp-camp', (s) => [...s.options].map((o) => o.value).find((v) => v && v !== s.value && v !== '120252638288040312'));
  await page.selectOption('#cmp-camp', otherCamp);
  await page.waitForFunction((c) => document.getElementById('cmp-camp')?.value === c, otherCamp);
  check('ticked ads stay ticked, shown and counted when the campaign changes', await page.isChecked(`#cmp-pick input[value="${NAV_AD}"]`)
    && await page.isChecked(`#cmp-pick input[value="${second}"]`) && /2 of 6 picked/.test(await page.textContent('#cmp-count')) && !(await page.isDisabled('#cmp-go')),
    await page.textContent('#cmp-count'));
  await page.selectOption('#cmp-camp', '');
  await page.waitForFunction(() => document.querySelectorAll('#cmp-pick input:checked').length === 2);
  for (let i = 0; i < 4; i++) await boxes.nth(0).check();
  check('six is the most: the other ads can no longer be ticked', /6 of 6 picked/.test(await page.textContent('#cmp-count'))
    && (await page.locator('#cmp-pick input:not(:checked)').count()) > 0 && (await page.locator('#cmp-pick input:not(:checked):not(:disabled)').count()) === 0);
  // The campaign picked on Results is the one Insights' tabs come back to; the dates stay the shared ones.
  await page.goto(BASE + `/performance.html?campaign=${C1}&range=7`);
  await page.waitForSelector('.results-table tbody tr');
  await page.goto(BASE + '/experiments.html');
  await page.waitForSelector('.subnav a[href^="/performance.html"]');
  const resTab = await page.getAttribute('.subnav a[href^="/performance.html"]', 'href');
  check('the Results tab reopens Results on the campaign picked there, without old dates', resTab.includes(`campaign=${C1}`) && !/range=/.test(resTab), resTab);
  await Promise.all([page.waitForURL('**/performance.html?**'), page.click('.subnav a[href^="/performance.html"]')]);
  await page.waitForFunction((c) => document.getElementById('campaign')?.value === c, C1);
  check('…and Results opens filtered to it', (await page.inputValue('#campaign')) === C1);
  await page.goto(BASE + '/performance.html?campaign=');
  await page.waitForSelector('.results-table tbody tr');
  await call('PUT', '/api/ads/ad/120252672232030312/tags', { tags: { hook: 'Question' } });
  await page.goto(BASE + '/compare.html?ids=120252672232030312,120252672229040312&range=30');
  await page.waitForSelector('.cmp thead');
  const tagLink = page.locator('.cmp-tag a.ent-link[href^="/ideas.html?by="]').first();
  check('Compare names each tag with a link to that idea on Ideas', (await tagLink.count()) === 1);
  const tagWord = (await tagLink.textContent()).trim();
  await Promise.all([page.waitForURL('**/ideas.html?by=**'), tagLink.click()]);
  await page.waitForSelector('.idea-grp.is-marked');
  check('the idea opens on Ideas with its group marked and its ads linked', (await page.textContent('.idea-grp.is-marked .idea-name')).trim() === tagWord
    && (await page.locator('.idea-grp.is-marked .idea-ads a.ent-link[href^="/ad.html?id="]').count()) > 0, tagWord);
  await page.goto(BASE + `/campaign.html?id=${C1}`);
  await page.waitForSelector('#en-leads');
  check('a campaign page links to its leads and its results', (await page.getAttribute('#en-leads', 'href')) === `/leads.html?campaign=${C1}`
    && (await page.getAttribute('#en-results', 'href')).startsWith(`/performance.html?campaign=${C1}`));
  await Promise.all([page.waitForURL('**/leads.html?campaign=**'), page.click('#en-leads')]);
  await page.waitForFunction((c) => document.getElementById('source')?.value === `c:${c}`, C1).catch(() => {});
  check("its leads open filtered to that campaign", (await page.inputValue('#source')) === `c:${C1}`, await page.inputValue('#source'));
  await page.waitForSelector('.lead-row');
  await page.locator('.lead-row').first().click();
  await page.waitForSelector('#detail .facts');
  check("a lead's detail links its ad and its campaign", (await page.locator('#detail .facts a.ent-link[href^="/campaign.html?id="]').count()) === 1);
  // One date range: picked on Ads, it is what a campaign, Compare and Results open on.
  await page.goto(BASE + '/ads.html?view=delivering&range=7');
  await page.waitForSelector('#range-pick');
  await page.selectOption('#range-pick', '30');
  await page.waitForFunction(() => /range=30/.test(location.search));
  const rangeOn = async (url, sel) => { await page.goto(BASE + url); await page.waitForSelector(sel); return page.inputValue(sel); };
  const shared = [await rangeOn(`/campaign.html?id=${C1}`, '#range-pick'), await rangeOn('/adset.html?id=120252672227950312', '#range-pick'),
    await rangeOn('/compare.html?ids=120252672232030312,120252672233160312', '#cmp-range'), await rangeOn('/performance.html', '#range-pick')];
  check('the dates picked on Ads carry to Campaign, Ad set, Compare and Results', shared.every((r) => r === '30'), shared.join());
  await page.selectOption('#range-pick', '14');
  await page.waitForFunction(() => /range=14/.test(location.search));
  check('dates picked on Results carry back to Ads', (await rangeOn('/ads.html', '#range-pick')) === '14');
  const [adReq] = await Promise.all([page.waitForRequest((r) => new RegExp(`/api/ads/ad/${NAV_AD}\\?`).test(r.url())), page.goto(BASE + `/ad.html?id=${NAV_AD}`)]);
  await page.waitForSelector('#chart-range');
  check("the ad's daily charts open on the shared dates", (await page.inputValue('#chart-range')) === '14' && new URL(adReq.url()).searchParams.get('range') === '14', adReq.url());
  const [seriesRes] = await Promise.all([page.waitForResponse((r) => /\/series\?range=30/.test(r.url())), page.selectOption('#chart-range', '30')]);
  const days30 = (await seriesRes.json()).series.length;
  await page.waitForFunction(() => /range=30/.test(location.search));
  check('dates picked on the ad redraw its charts for 30 days and carry to the rest', days30 === 30 && new URL(page.url()).searchParams.get('id') === NAV_AD
    && (await page.evaluate(() => localStorage.getItem('ebads-range'))) === '30', `${days30} ${page.url()}`);
  await page.goto(BASE + `/campaign.html?id=${C1}`);
  await page.waitForSelector('#range-pick');
  await page.selectOption('#range-pick', '7');
  await page.waitForFunction(() => /range=7/.test(location.search) || document.querySelector('#range-pick').value === '7');
  await page.waitForTimeout(300);
  check('changing the dates on a campaign keeps the campaign in the address', new URL(page.url()).searchParams.get('id') === C1, page.url());
  // Breadcrumbs: back to the list as it was filtered.
  await page.goto(BASE + '/ads.html?view=delivering&q=N');
  await page.waitForSelector('.tbl tbody tr');
  await page.goto(BASE + `/ad.html?id=${NAV_AD}`);
  await page.waitForSelector('.crumbs a');
  const adsCrumb = await page.getAttribute('.crumbs a', 'href');
  check('the Ads breadcrumb goes back to the list as it was filtered', /view=delivering/.test(adsCrumb) && /q=N/.test(adsCrumb), adsCrumb);
  // ?from= on New pages: Cancel and the breadcrumb go back to the page it was opened from.
  await page.goto(BASE + `/campaign.html?id=${C1}`);
  await page.waitForSelector('#en-actions a[href^="/new-adset.html"]');
  await Promise.all([page.waitForURL('**/new-adset.html?**'), page.click('#en-actions a[href^="/new-adset.html"]')]);
  await page.waitForSelector('#cancel');
  const cancelTo = await page.getAttribute('#cancel', 'href');
  const midCrumb = await page.$$eval('.crumbs a', (as) => as.map((a) => `${a.textContent}=${a.getAttribute('href')}`));
  check('New ad set opened from a campaign has Cancel back to that campaign, and says so in the breadcrumbs',
    cancelTo === `/campaign.html?id=${C1}` && midCrumb.some((c) => c === `Campaign=/campaign.html?id=${C1}`), `${cancelTo} ${midCrumb.join(' | ')}`);
  await Promise.all([page.waitForURL(`**/campaign.html?id=${C1}`), page.click('#cancel')]);
  check('Cancel goes back to the campaign', page.url().endsWith(`/campaign.html?id=${C1}`));
  await page.goto(BASE + `/new-ad.html?from=${encodeURIComponent('//example.com/x.html')}`);
  await page.waitForSelector('#cancel');
  check('a ?from= pointing at another site is ignored', !/example\.com/.test(await page.getAttribute('#cancel', 'href')), await page.getAttribute('#cancel', 'href'));
  await page.goto(BASE + `/ad.html?id=${NAV_AD}`);
  await page.waitForSelector('#cr-actions a[href^="/new-ad.html"]');
  await Promise.all([page.waitForURL('**/new-ad.html?template=**'), page.click('#cr-actions a[href^="/new-ad.html"]')]);
  await page.waitForFunction((id) => document.getElementById('template')?.value === id, NAV_AD);
  check('New ad from this starts from the ad and Cancel goes back to it', (await page.getAttribute('#cancel', 'href')) === `/ad.html?id=${NAV_AD}`
    && await page.evaluate(() => document.getElementById('mt-same').getAttribute('aria-selected') === 'true'));
  await page.goto(BASE + `/new-ad.html?from=${NAV_AD}`);
  await page.waitForSelector('#template option', { state: 'attached' });
  await page.waitForTimeout(300);
  check('an older New ad link (?from=<ad>) still starts from that ad', (await page.inputValue('#template')) === NAV_AD, await page.inputValue('#template'));
  await page.goto(BASE + '/home.html');
  await page.waitForSelector('.today-changes');
  const viaAll = await page.locator('.tq-lead .tq-b p', { hasText: ' · from ' }).count();
  check('Today links the ad each lead came from and the things changed from the console',
    (await page.locator('.today-changes a.ent-link').count()) > 0 && viaAll > 0 && (await page.locator('.tq-lead .tq-b p a.ent-link[href^="/ad.html?id="]').count()) === viaAll, String(viaAll));
  // Back closes the quick look and stays on Ads.
  await page.goto(BASE + '/ads.html?range=7');
  await page.evaluate(() => localStorage.setItem('ebads-range', '7'));
  await page.waitForSelector('.tbl tbody tr');
  const listUrl = page.url();
  await page.locator('.tbl tbody tr').first().locator('td.num').first().click();
  await page.waitForSelector('.pk.open');
  await page.goBack();
  await page.waitForSelector('.pk:not(.open)');
  check('Back closes the quick look and stays on the list', page.url() === listUrl && !/peek=/.test(page.url()), page.url());
  await page.locator('.tbl tbody tr').first().locator('td.num').first().click();
  await page.waitForSelector('.pk.open');
  await page.keyboard.press('Escape');
  await page.waitForSelector('.pk:not(.open)');
  await page.waitForTimeout(200);
  check('closing the quick look leaves no extra step behind', !/peek=/.test(page.url()) && await page.evaluate(() => !(history.state && history.state.layer)), page.url());
  // The same number everywhere (cluster 6): labels, totals, tracks and dead campaigns.
  check('Compare calls ThruPlays ÷ 3-second views "Hold rate", as the Video tab does', /Hold rate/.test(cmpText) && !/Watched to the end/.test(cmpText));
  const deadCamp = sh(`docker exec -w /app edgebourne-ads-backend python -c "
import db
r = db.query(\\"SELECT id FROM campaigns WHERE effective_status = 'DELETED' AND daily_budget_cents IS NOT NULL ORDER BY id LIMIT 1\\", one=True)
print(r['id'] if r else '')"`).trim();
  await page.goto(BASE + '/ads.html?level=campaign');
  await page.waitForSelector('tr[data-row^="campaign:"]');
  check('deleted campaigns are left out of the Campaigns view, so none offers a budget or a new ad set',
    !deadCamp || ((await page.locator(`tr[data-row="campaign:${deadCamp}"]`).count()) === 0 && !/Deleted/.test(await page.textContent('.tbl tbody'))), deadCamp);
  if (deadCamp) {
    const deadBudget = await page.evaluate(async (id) => (await fetch(`/api/ads/campaign/${id}/budget`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ daily_budget_cents: 1600, from_cents: 1500 }) })).status, deadCamp);
    check("a deleted campaign's budget can't be changed", deadBudget === 409, String(deadBudget));
    const deadSeen = errors.length;
    await page.goto(BASE + '/new-adset.html?campaign=' + deadCamp);
    await page.waitForSelector('#campaign option', { state: 'attached' });
    await page.waitForTimeout(400);
    errors.splice(deadSeen);
    check('a new ad set for a deleted campaign is not quietly put in another one',
      (await page.inputValue('#campaign')) === '' && /deleted or archived/.test(await page.textContent('#budget-note')));
  }
  // A campaign archived in Ads Manager whose ads are not: hidden, but "Show archived" is offered to bring it back.
  const [archCamp, archWas] = sh(`docker exec -w /app edgebourne-ads-backend python -c "
import db
r = db.query(\\"SELECT id, effective_status FROM campaigns WHERE effective_status IN ('ACTIVE','PAUSED') ORDER BY id LIMIT 1\\", one=True)
print(r['id'] + ' ' + r['effective_status'] if r else '')"`).trim().split(' ');
  if (archCamp) {
    const setCampStatus = (st) => sh(`docker exec -w /app edgebourne-ads-backend python -c "
import db
db.execute(\\"UPDATE campaigns SET effective_status = '${st}' WHERE id = '${archCamp}'\\")"`);
    const before = await page.evaluate(async () => (await (await fetch('/api/ads?range=7')).json()).archived);
    setCampStatus('ARCHIVED');
    try {
      await page.goto(BASE + '/ads.html?level=campaign&range=7');
      await page.waitForSelector('tr[data-row^="campaign:"]');
      const hiddenNow = (await page.locator(`tr[data-row="campaign:${archCamp}"]`).count()) === 0;
      const offered = await page.isVisible('#archived');
      let back = false;
      if (offered) {
        await page.click('#archived');
        await page.waitForFunction(() => /Hide archived/.test(document.querySelector('#archived')?.textContent || ''));
        back = (await page.locator(`tr[data-row="campaign:${archCamp}"]`).count()) === 1;
        await page.click('#archived');
        await page.waitForFunction(() => /Show archived/.test(document.querySelector('#archived')?.textContent || ''));
      }
      const after = await page.evaluate(async () => (await (await fetch('/api/ads?range=7')).json()).archived);
      check('a campaign archived on its own is hidden, counted and brought back by "Show archived"',
        hiddenNow && offered && back && after === before + 1, `${hiddenNow} ${offered} ${back} ${before}→${after}`);
    } finally { setCampStatus(archWas); }
  }
  await page.goto(BASE + '/ads.html?range=7');
  await page.waitForSelector('tr[data-row^="ad:"] .trk');
  check('the Delivery track shows the last 14 days whatever the range', (await page.locator('tr[data-row^="ad:"] .trk').first().locator('i').count()) === 14);
  // 9.4b: the track says what it shows, a legend explains the bars, the On switch sits next to the name,
  // and the header and name column stay in view while the table scrolls.
  const trkWords = await page.getAttribute('tr[data-row^="ad:"] .trk', 'aria-label');
  check('each delivery track says in words how many days it spent', /^Spent on \d+ of the last 14 days$/.test(trkWords || ''), trkWords);
  check('a legend under the table explains the delivery bars', /spent that day/.test(await page.textContent('.trk-key')) && /in review/.test(await page.textContent('.trk-key')));
  const heads = await page.$$eval('.tbl thead th', (ths) => ths.map((t) => t.className.trim().split(/\s+/).pop()));
  check('the On switch is the column right after the name', heads.indexOf('c-on') === heads.indexOf('c-name') + 1, heads.join());
  const sticky = await page.evaluate(async () => {
    const wrap = document.querySelector('.tbl-wrap');
    wrap.scrollTop = 300; wrap.scrollLeft = 400;
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    const w = wrap.getBoundingClientRect(), th = document.querySelector('.tbl thead th').getBoundingClientRect();
    const name = document.querySelector('.tbl tbody tr:nth-child(8) td.c-name').getBoundingClientRect();
    const cb = document.querySelector('.tbl thead th.c-cb').getBoundingClientRect();
    const hit = document.elementFromPoint(cb.left + cb.width / 2, cb.top + cb.height / 2);
    const out = { scrolled: wrap.scrollTop > 0 && wrap.scrollLeft > 0, headTop: Math.round(th.top - w.top), nameLeft: Math.round(name.left - w.left),
      selectAll: Boolean(hit && hit.closest('thead th.c-cb')) };
    wrap.scrollTop = 0; wrap.scrollLeft = 0;
    return out;
  });
  check('scrolled down and across, the header stays on top and the name column stays at the left', sticky.scrolled && sticky.headTop <= 1 && sticky.nameLeft <= 40, JSON.stringify(sticky));
  check('scrolled down, the Select all box stays on top of the rows and can be clicked', sticky.selectAll, JSON.stringify(sticky));
  await page.locator('.tbl tbody tr').nth(1).locator('.c-cb input').check();
  await page.mouse.move(1, 1);
  const selBg = await page.evaluate(() => { const tr = document.querySelector('.tbl tbody tr.is-sel'); const bg = (sel) => getComputedStyle(tr.querySelector(sel)).backgroundColor; return [bg('td.c-cb'), bg('td.c-name'), bg('td.num')]; });
  check('a selected row is coloured from its tick box to the last column', selBg[0] === selBg[1] && selBg[1] === selBg[2] && selBg[0] !== 'rgb(255, 255, 255)', selBg.join(' | '));
  await page.locator('.tbl tbody tr').nth(1).locator('.c-cb input').uncheck();
  await page.goto(BASE + '/ads.html?level=adset');
  await page.waitForSelector('.tbl tr[data-row^="adset:"]');
  check('ad sets have no delivery bars, so no legend for them', (await page.locator('.trk-key').count()) === 0 && (await page.locator('.trk').count()) === 0);
  await page.locator('.tbl tr[data-row^="adset:"]').first().locator('td.num').first().click();
  await page.waitForSelector('.pk.open');
  const peekLeads = await page.getAttribute('.pk.open a[href^="/leads.html?adset="]', 'href').catch(() => null);
  check("an ad set's quick look links to its leads", /^\/leads\.html\?adset=\d+$/.test(peekLeads || ''), peekLeads);
  await page.keyboard.press('Escape');
  await page.goto(BASE + '/ads.html?view=off&q=zzzz-nothing');
  await page.waitForSelector('[data-clear-filters]');
  check('a filtered-out list says which filters and offers Clear filters', /“Off”/.test(await page.textContent('#cr-all .empty')) && /zzzz-nothing/.test(await page.textContent('#cr-all .empty')));
  await page.click('[data-clear-filters]');
  await page.waitForSelector('.tbl tr[data-row^="ad:"]');
  check('Clear filters brings every ad back and drops the filters from the address', !/view=|q=/.test(page.url()) && (await page.inputValue('#cr-search')) === '', page.url());
  const vsHead = async () => page.getAttribute('th:has(button[data-sort="vs"])', 'title');
  const vsDays = await vsHead();
  await page.goto(BASE + '/ads.html?range=mtd');
  await page.waitForSelector('th:has(button[data-sort="vs"])');
  const vsMonth = await vsHead();
  check('the "vs before" column says which period it compares with', /days just before/.test(vsDays) && /same days of the month before/.test(vsMonth), `${vsDays} | ${vsMonth}`);
  await page.goto(BASE + '/ads.html?range=7');
  await page.waitForSelector('tr[data-row^="ad:"] .trk');
  const tree7 = await page.evaluate(async () => (await fetch('/api/ads?range=7')).json());
  const listedSpend = tree7.campaigns.flatMap((c) => c.adsets.flatMap((s) => s.ads)).reduce((n, a) => n + (a.m.spend_cents || 0), 0);
  check('the header totals count every ad, and the footer names what no listed ad shows',
    tree7.totals.m.spend_cents >= listedSpend && (tree7.totals.m.spend_cents > listedSpend) === /from ads no longer listed/.test(await page.textContent('.cr-foot')),
    `${tree7.totals.m.spend_cents} vs ${listedSpend}`);
  await page.goto(BASE + '/leads.html');
  await page.waitForSelector('#source option[value^="a:"]', { state: 'attached' });
  const adOpt = await page.$eval('#source option[value^="a:"]', (o) => o.value);
  await page.selectOption('#source', adOpt);
  await page.waitForFunction(() => /[?&]ad=/.test(location.search));
  await page.waitForTimeout(600);
  const leadAds = await page.evaluate(async (a) => (await (await fetch(`/api/leads?ad=${a}`)).json()).leads.map((l) => l.ad_name), adOpt.slice(2));
  check('Leads filter to one ad and keep it in the URL', leadAds.length > 0 && new Set(leadAds).size === 1);
  check('a filtered Leads list offers Clear filters', await page.isVisible('#clear-filters'));
  await page.click('#clear-filters');
  await page.waitForFunction(() => !/[?&](ad|campaign)=/.test(location.search) && document.getElementById('clear-filters').hidden);
  check('Clear filters goes back to every open lead', (await page.inputValue('#source')) === '' && (await page.getAttribute('#filters [data-f="open"]', 'aria-pressed')) === 'true');
  await page.fill('#q', 'zz-nobody-by-this-name');
  await page.waitForSelector('#list [data-clear-filters]');
  check('a search that finds nobody says so and offers Clear filters', /Nothing matches/.test(await page.textContent('#list')));
  await page.click('#list [data-clear-filters]');
  await page.waitForSelector('#list .lead-row');
  check('…which brings the leads back and empties the search', (await page.inputValue('#q')) === '' && (await page.locator('#list .lead-row').count()) > 0);
  // 9.4 Today: one ranked queue made of the Inbox's Needs action, leads first, never its FYI.
  await page.goto(BASE + '/home.html');
  await page.waitForSelector('.tq-group, .tq-clear');
  const homeData = await getJson('/api/home');
  const ORDER = ['call', 'problems', 'follow', 'decide', 'money', 'system', 'later'];
  const drawn = await page.$$eval('.tq-group', (g) => g.map((x) => x.getAttribute('aria-labelledby').replace('tq-', '')));
  check('Today is one queue in a fixed order (call, fix, decide, money, keep it running) with no Inbox list of its own',
    drawn.length > 1 && drawn.every((g, i) => i === 0 || ORDER.indexOf(g) > ORDER.indexOf(drawn[i - 1])) && (await page.locator('#today-inbox, .attention').count()) === 0, drawn.join());
  const needKeys = (await getJson('/api/inbox?box=need')).items.map((i) => i.key);
  const fyiKeys = (await getJson('/api/inbox?box=fyi')).items.map((i) => i.key);
  const fromInbox = homeData.queue.filter((r) => /^(alert|proposal):/.test(r.key));
  check('Today lists what needs action and nothing that is only for your information', fromInbox.length > 0 && fromInbox.every((r) => needKeys.includes(r.key))
    && homeData.queue.every((r) => !fyiKeys.includes(r.key)) && new Set(homeData.queue.map((r) => r.key)).size === homeData.queue.length, fromInbox.map((r) => r.key).join());
  const openLeads = (await getJson('/api/leads?status=open')).leads;
  const callRows = homeData.queue.filter((r) => r.group === 'call');
  check('Today and Leads use one urgency rule for every waiting lead', callRows.length > 0
    && callRows.every((r) => openLeads.find((l) => `lead:${l.id}` === r.key)?.urgency === r.level)
    && (await page.$$eval('.tq-lead .clock', (c) => c.map((x) => x.className))).every((c, i) => c === `clock ${callRows[i].level}`), callRows.map((r) => r.level).join());
  check('the first hour comes first, then the longest wait', callRows.every((r, i) => i === 0 || (callRows[i - 1].bucket < r.bucket)
    || (callRows[i - 1].bucket === r.bucket && new Date(callRows[i - 1].at) <= new Date(r.at))), callRows.map((r) => `${r.bucket}`).join());
  if (!(await page.locator('.tq-group[aria-labelledby="tq-decide"] [data-accept]').count())) {
    py(`import db;db.execute(\\"INSERT INTO desk_proposals (task_id, kind, title, status) SELECT id, 'other', 'QA today suggestion', 'pending' FROM desk_tasks ORDER BY id DESC LIMIT 1\\")`);
    await page.reload();
    await page.waitForSelector('.tq-group[aria-labelledby="tq-decide"] [data-accept]');
  }
  const decideId = await page.getAttribute('.tq-group[aria-labelledby="tq-decide"] [data-accept]', 'data-accept');
  await page.click('.tq-group[aria-labelledby="tq-decide"] [data-accept]');
  await page.waitForSelector('dialog.accept-sheet #cd-ok:not(:empty)');
  check('a decision on Today opens the Accept sheet, starting on Cancel', (await page.evaluate(() => document.activeElement.id)) === 'cd-cancel');
  await page.click('dialog.accept-sheet #cd-cancel');
  await page.waitForSelector('dialog.accept-sheet', { state: 'detached' });
  check('cancelling it decides nothing', (await getJson('/api/home')).queue.some((r) => String(r.proposal_id) === decideId), decideId);
  check('Today ends with a way to the Inbox for the rest', /\/inbox\.html\?box=fyi/.test(await page.getAttribute('.tq-foot:last-child a', 'href')));
  check('L1: Today\'s footer counts the open leads with no next step and links to them', !homeData.follow.no_next
    || (await page.getAttribute('#fu-nonext a', 'href')) === '/leads.html?due=none' && new RegExp(`^${homeData.follow.no_next} open leads? ha(s|ve) no next step`).test(await page.textContent('#fu-nonext')), JSON.stringify(homeData.follow));
  // W1a: Got it (snooze) and Diagnose with Claude on alerts: Inbox, Today, the ad page, Settings, teammates, clients, phones.
  {
    const C = '120252638288040312';
    const CAMP = 'Edge Bourne - Free intro call - Leads';
    const reset = () => py(`import db;db.execute(\\"UPDATE alert_snoozes SET ended_at = now(), end_reason = 'by_hand' WHERE ended_at IS NULL\\");db.execute(\\"UPDATE desk_tasks SET status = 'cancelled' WHERE kind = 'diagnose' AND status IN ('queued', 'claimed', 'running')\\")`);
    // Raised the way the hourly check raises them (alerts.raise_found), each with a key of its own.
    const raise = (rule, level, measure, entity, title, kind = 'condition') => Number(py(`import alerts, uuid
r = alerts.raise_found([{'rule': '${rule}', 'key': '${rule}:${entity}:qa-w1-' + uuid.uuid4().hex, 'level': '${level}', 'title': '${title}', 'lines': ['QA line.'],
  'entity_id': '${entity}', 'campaign_id': ${entity === 'account' ? 'None' : `'${C}'`}, 'href': '/performance.html', 'measure': ${measure === null ? 'None' : measure},
  'kind': '${kind}', 'resolved': ${kind === 'event' ? 'True' : 'False'}}])
print(r[0][0] if r else 0)`));
    const sent = (id) => Number(py(`import db;print(db.query('SELECT COUNT(*) AS n FROM notifications WHERE kind = %s AND ref = %s', ('alert', '${id}'), one=True)['n'])`));
    const live = () => JSON.parse(py(`import db, json;print(json.dumps(db.query('SELECT id, rule, mode, end_reason, baseline::float8 AS b FROM alert_snoozes ORDER BY id DESC LIMIT 1', one=True)))`));
    const openItem = async (id, box = 'all') => {
      await page.goto(`${BASE}/inbox.html?box=${box}#item=${encodeURIComponent(`alert:${id}`)}`);
      await page.reload();
      await page.waitForFunction((k) => document.querySelector('#ib-detail h2') && document.querySelector(`#ib-list [data-key="${k}"][aria-current="true"]`), `alert:${id}`);
    };
    reset();
    const cap = raise('spend_cap', 'warn', 82, 'account', '82% of the account spending limit is used');
    await openItem(cap, 'need');
    check('an open alert offers Got it and Diagnose with Claude beside Open (admins)', await page.isVisible('#ib-detail [data-al-snooze]') && await page.isVisible('#ib-detail [data-al-diag]')
      && /Got it…/.test(await page.textContent('#ib-detail [data-al-snooze]')), String(cap));
    await page.click('#ib-detail [data-al-snooze]');
    await page.waitForSelector('dialog.al-choice .cd-choice');
    const gotIt = (await page.textContent('dialog.al-choice')).replace(/\s+/g, ' ');
    check('Got it asks when it should come back: in 3 days, or only if it gets worse, and says what that means',
      (await page.locator('dialog.al-choice .cd-choice').count()) === 2 && /Got it\. When should this come back\?/.test(gotIt) && /In 3 days/.test(gotIt)
      && /Only if it gets worse/.test(gotIt) && /You'll hear again at 95% of the limit\./.test(gotIt) && /Stays in the Inbox without messages until \w{3}, \w{3} \d+\./.test(gotIt)
      && (await page.evaluate(() => document.activeElement.id)) === 'cd-cancel', gotIt.slice(0, 260));
    await page.click('dialog.al-choice .cd-choice[data-value="worse"]');
    await page.waitForFunction(() => /Snoozed until it gets worse · Eugene/.test(document.querySelector('#ib-detail .al-snoozed')?.textContent || ''));
    const needNow = await getJson('/api/inbox?box=need');
    check('snoozed: the chip says until it gets worse and who, and it leaves Needs action', !needNow.items.some((i) => i.key === `alert:${cap}`)
      && (await getJson('/api/inbox?box=fyi')).items.some((i) => i.key === `alert:${cap}` && i.snooze && i.snooze.mode === 'worse') && (await page.locator('#ib-detail [data-al-wake]').count()) === 1);
    await page.click('.toast .toast-act');
    await page.waitForFunction((k) => (document.querySelector('#ib-detail .al-snoozed') === null), `alert:${cap}`);
    check('Undo in the toast wakes it: back in Needs action', (await getJson('/api/inbox?box=need')).items.some((i) => i.key === `alert:${cap}` && !i.snooze)
      && live().end_reason === 'by_hand');
    await openItem(cap, 'need');
    await page.click('#ib-detail [data-al-snooze]');
    await page.click('dialog.al-choice .cd-choice[data-value="worse"]');
    await page.waitForSelector('#ib-detail .al-snoozed');
    await page.goto(BASE + '/home.html');
    await page.waitForSelector('.tq-group, .tq-clear');
    const homeW1 = await getJson('/api/home');
    check('Today leaves a snoozed alert out and says so in one quiet line', !homeW1.queue.some((r) => r.key === `alert:${cap}`) && homeW1.snoozed === 1
      && /1 snoozed alert\. See them/.test(await page.textContent('.al-snoozed-line')) && /box=fyi/.test(await page.getAttribute('.al-snoozed-line a', 'href')), String(homeW1.snoozed));
    // The hourly check while snoozed: the same figure (85%) is stored quietly; 96% is clearly worse and goes out once.
    const quiet = raise('spend_cap', 'warn', 85, 'account', '85% of the account spending limit is used');
    const quietRow = JSON.parse(py(`import db, json;print(json.dumps(db.query('SELECT quiet FROM alerts WHERE id = %s', (${quiet},), one=True)))`));
    check('still snoozed at 85%: stored quietly, no message', quiet > 0 && quietRow.quiet === true && sent(quiet) === 0 && !live().end_reason, `${quiet} ${JSON.stringify(quietRow)}`);
    const worse = raise('spend_cap', 'warn', 96, 'account', '96% of the account spending limit is used');
    const worseRow = JSON.parse(py(`import db, json;print(json.dumps(db.query('SELECT title, lines, quiet FROM alerts WHERE id = %s', (${worse},), one=True)))`));
    check('at 96% it is clearly worse: one message titled "Worse:", saying where it was snoozed, and the snooze ends', worse > 0 && sent(worse) >= 1
      && /^Worse: 96%/.test(worseRow.title) && /^You snoozed this at 82% on \w{3} \d+\.$/.test(worseRow.lines[0]) && !worseRow.quiet && live().end_reason === 'worse', JSON.stringify(worseRow));
    // A link to an older row of the same problem (a diagnosis's "From an alert" names the row it was asked from)
    // opens the item that stands for the problem now, and the address follows it.
    await page.goto(`${BASE}/inbox.html?box=need#item=${encodeURIComponent(`alert:${cap}`)}`);
    await page.reload();
    await page.waitForFunction((k) => document.querySelector(`#ib-list [data-key="${k}"][aria-current="true"]`), `alert:${worse}`);
    const epi = (await getJson('/api/inbox?box=need')).items.find((i) => i.key === `alert:${worse}`);
    check('a link to an older row of a problem opens the item that stands for it now', /^Worse: 96%/.test(await page.textContent('#ib-detail h2'))
      && decodeURIComponent(new URL(page.url()).hash) === `#item=alert:${worse}` && epi && [cap, quiet].every((id) => epi.ids.includes(id))
      && !(await getJson('/api/inbox?box=all')).items.some((i) => i.key === `alert:${cap}`), `${page.url()} ${epi && epi.ids}`);
    // In 3 days, from the newest row; Settings lists it and wakes it.
    await openItem(worse, 'need');
    await page.click('#ib-detail [data-al-snooze]');
    await page.click('dialog.al-choice .cd-choice[data-value="days:3"]');
    await page.waitForFunction(() => /Snoozed until \w{3}, \w{3} \d+ · Eugene/.test(document.querySelector('#ib-detail .al-snoozed')?.textContent || ''));
    check('In 3 days: the chip names the day, and the snooze keeps 96% as where it started', live().mode === 'days' && live().b === 96);
    // Its own address (#snoozed) opens Settings → Alerts on the list.
    await page.goto(BASE + '/settings.html#snoozed');
    await page.reload();
    await page.waitForSelector('#alerts[data-section]:not([hidden]) #snoozed [data-al-wake]');
    check('Settings → Alerts lists what is snoozed, who did it and until when', /96% of the account spending limit is used/.test(await page.textContent('#snoozed'))
      && /Snoozed until \w{3}, \w{3} \d+ · Eugene/.test(await page.textContent('#snoozed')));
    await page.click('#snoozed [data-al-wake]');
    await page.waitForFunction(() => /Nothing is snoozed/.test(document.querySelector('#snoozed')?.textContent || ''));
    check('Wake it now in Settings ends it by hand', live().end_reason === 'by_hand');
    // What can't be snoozed for long, or at all.
    const track = raise('tracking', 'bad', 4, 'account', 'Leads are not reaching the inbox');
    await openItem(track, 'need');
    await page.click('#ib-detail [data-al-snooze]');
    await page.waitForSelector('dialog.al-choice .cd-choice');
    check('lost leads (tracking) wait a day at most: only Remind me tomorrow', (await page.$$eval('dialog.al-choice .cd-choice b', (b) => b.map((x) => x.textContent))).join() === 'Remind me tomorrow'
      && /can only wait a day/.test(await page.textContent('dialog.al-choice')));
    await page.click('dialog.al-choice #cd-cancel');
    const ev = raise('learning_limited', 'warn', null, '120252672227950312', 'Ad set “QA” is learning limited', 'event');
    const info = raise('day_overspend', 'info', 4000, C, 'QA spent a lot today');
    const fyi = (await getJson('/api/inbox?box=all')).items;
    check('an event and an info note offer no Got it', [ev, info].every((id) => { const i = fyi.find((x) => x.key === `alert:${id}`); return i && !i.actions.includes('snooze'); }), `${ev} ${info}`);
    await openItem(info);
    check('…and none shows on the screen', (await page.locator('#ib-detail [data-al-snooze]').count()) === 0);
    // Diagnose with Claude on "no leads": the request names the alert, the ids and the playbook; one run per problem.
    const dry = raise('no_leads', 'bad', 5, C, `No leads for 5 days in “${CAMP}”`);
    await openItem(dry, 'need');
    await page.click('#ib-detail [data-al-diag]');
    await page.waitForSelector('dialog.dg-form #cd-input');
    const draft = await page.inputValue('dialog.dg-form #cd-input');
    const dgText = (await page.textContent('dialog.dg-form')).replace(/\s+/g, ' ');
    check('the Diagnose request names the alert, the campaign id and the checklist, read only', draft.includes(C) && /Read only: change nothing on Meta\./.test(draft)
      && /Uses the “spending without leads” checklist\./.test(dgText) && /It changes nothing on Meta/.test(dgText) && /\d[\d,]* \/ 4,000/.test(dgText), draft.slice(0, 160));
    await page.fill('dialog.dg-form #cd-input', draft + '\nQA: look at the form first.');
    await page.click('dialog.dg-form #cd-ok');
    await page.waitForFunction(() => /Waiting for your Mac/.test(document.querySelector('#ib-detail .al-chip')?.textContent || ''));
    const dTask = JSON.parse(py(`import db, json;print(json.dumps(db.query(\\"SELECT id, kind, prompt, options->>'alert_key' AS k, options->>'playbook' AS pb FROM desk_tasks WHERE kind = 'diagnose' ORDER BY id DESC LIMIT 1\\", one=True)))`));
    check('Send to Claude files one diagnose run with the edited request and the problem as its key', dTask.kind === 'diagnose' && dTask.k === `no_leads:${C}`
      && /QA: look at the form first\./.test(dTask.prompt) && dTask.pb === 'meta-ads-doctor', JSON.stringify(dTask).slice(0, 200));
    const twice = await page.evaluate(async ([id]) => (await fetch('/api/diagnose', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ alert_id: id, prompt: 'again' }) })).json(), [dry]);
    check('asking again while it waits reuses the run', twice.already === true && twice.task_id === dTask.id, JSON.stringify(twice));
    check('the chip says Waiting for your Mac and opens the conversation', (await page.getAttribute('#ib-detail .al-chip', 'href')) === `/desk.html#r/${dTask.id}`);
    // The Mac's side: read-only tools only, then one suggestion; the chip and the Inbox follow, and accepting still asks first.
    sh(`docker exec edgebourne-ads-backend mkdir -p /tmp/qa_bridge && docker cp bridge/bridge.py edgebourne-ads-backend:/tmp/qa_bridge/bridge.py && docker cp bridge/desk edgebourne-ads-backend:/tmp/qa_bridge/desk && docker cp dev/qa_agent_diagnose.py edgebourne-ads-backend:/app/qa_agent_diagnose.py`);
    const macD = JSON.parse(sh(`docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python qa_agent_diagnose.py ${dTask.id} /tmp/qa_bridge; docker exec edgebourne-ads-backend rm -rf /app/qa_agent_diagnose.py /tmp/qa_bridge`).trim().split('\n').pop());
    check('the Mac runs a diagnosis as a read-only kind: no web, no shell but desk, no write tools', macD.read_only_kind === true && macD.writes.length === 0
      && macD.rule === 'no_leads' && macD.playbook === 'meta-ads-doctor' && macD.alert_key === `no_leads:${C}` && macD.added.added === 1 && macD.done === 200, JSON.stringify(macD).slice(0, 240));
    await openItem(dry);
    await page.waitForSelector('#ib-detail .al-chip.btn-claude');
    check('after the run the chip reads 1 suggestion and leads to the Accept sheet on the Claude page, with Diagnose again beside it',
      (await page.textContent('#ib-detail .al-chip')).trim() === '1 suggestion' && (await page.getAttribute('#ib-detail .al-chip', 'href')) === '/desk.html#waiting'
      && /Diagnose again/.test(await page.textContent('#ib-detail [data-al-diag]')));
    const dProp = (await getJson('/api/inbox?box=need&kind=claude')).items.find((i) => i.lines[0] === `From: No leads for 5 days in “${CAMP}”`);
    check('the suggestion in the Inbox says which alert it answers', Boolean(dProp), JSON.stringify((await getJson('/api/inbox?box=need&kind=claude')).items.map((i) => i.lines)).slice(0, 200));
    const adBefore = metaObj(macD.ad).status;
    await page.goto(`${BASE}/inbox.html?box=need&kind=claude#item=${encodeURIComponent(dProp.key)}`);
    await page.waitForSelector('#ib-detail [data-accept]');
    await page.click('#ib-detail [data-accept]');
    await page.waitForSelector('dialog.accept-sheet #cd-ok:not(:empty)');
    await page.click('dialog.accept-sheet #cd-cancel');
    await page.waitForSelector('dialog.accept-sheet', { state: 'detached' });
    check("accepting Claude's suggestion still goes through the Accept sheet; cancelled, nothing changes on Meta", metaObj(macD.ad).status === adBefore, adBefore);
    py(`import db;db.execute(\\"UPDATE desk_proposals SET status = 'declined' WHERE id = ${dProp.proposal_id}\\")`);
    // The ad page: a rejected ad offers Diagnose, and its run is the same problem as the alert's.
    const N4 = '120252672232030312';
    sh(`docker exec edgebourne-ads-backend python -c "import requests;requests.get('http://fake-meta:5001/fake/_review?ad=${N4}&to=WITH_ISSUES')"`);
    pull();
    await page.goto(`${BASE}/ad.html?id=${N4}`);
    await page.waitForSelector('#cs-diag [data-al-diag-ad]');
    await page.click('#cs-diag [data-al-diag-ad]');
    await page.waitForSelector('dialog.dg-form #cd-input');
    check("the ad page's request names the ad and uses Meta's ad rules", (await page.inputValue('dialog.dg-form #cd-input')).includes(N4) && /“Meta's ad rules” checklist/.test(await page.textContent('dialog.dg-form')));
    await page.click('dialog.dg-form #cd-ok');
    await page.waitForSelector('#cs-diag .al-chip');
    const adTask = JSON.parse(py(`import db, json;print(json.dumps(db.query(\\"SELECT id, options->>'alert_key' AS k FROM desk_tasks WHERE kind = 'diagnose' ORDER BY id DESC LIMIT 1\\", one=True)))`));
    const n4Alert = (await getJson('/api/inbox?box=all')).items.find((i) => i.rule === 'ad_rejected' && i.entity_id === N4);
    check("the ad's run and its Inbox alert share one problem key, so they show the same run", adTask.k === `ad_rejected:${N4}` && n4Alert && n4Alert.diagnose && n4Alert.diagnose.id === adTask.id,
      JSON.stringify([adTask, n4Alert && n4Alert.diagnose]));
    sh(`docker exec edgebourne-ads-backend python -c "import requests;requests.get('http://fake-meta:5001/fake/_review?ad=${N4}&to=ACTIVE')"`);
    pull();
    reset();
    // Teammates see the chip and no buttons, and are refused; clients see none of it.
    const cpl = raise('cpl_high', 'warn', 8000, C, 'QA leads cost too much');
    await page.evaluate(async ([id]) => fetch(`/api/alerts/${id}/snooze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: 'worse' }) }), [cpl]);
    const rej = raise('ad_rejected', 'bad', 2, N4, 'QA Meta rejected N4');
    py(`import db
from werkzeug.security import generate_password_hash as h
for email, role in (('qa-w1-client@example.com', 'client'), ('qa-w1-mate@example.com', 'member')):
    db.execute(\\"INSERT INTO users (email, name, password_hash, role, account_id) VALUES (%s, %s, %s, %s, 1) ON CONFLICT (email) DO UPDATE SET is_active = TRUE, password_hash = EXCLUDED.password_hash, role = EXCLUDED.role, account_id = 1, must_change_password = FALSE\\", (email, 'QA W1 ' + role, h('w1-pass-12345'), role))
db.execute(\\"INSERT INTO campaign_members (campaign_id, user_id, account_id) SELECT '${C}', id, 1 FROM users WHERE email = 'qa-w1-mate@example.com' ON CONFLICT DO NOTHING\\")`);
    for (const [email, who] of [['qa-w1-mate@example.com', 'mate'], ['qa-w1-client@example.com', 'client']]) {
      const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
      const p = await ctx.newPage();
      p.on('pageerror', (e) => errors.push(`${who} page: ${e.message}`));
      await p.goto(BASE + '/login.html');
      await p.fill('#email', email); await p.fill('#password', 'w1-pass-12345');
      await Promise.all([p.waitForURL('**/home.html**'), p.click('button[type=submit]')]);
      const res = await p.evaluate(async ([a, d]) => {
        const post = (u, b) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }).then((r) => r.status);
        const items = (await (await fetch('/api/inbox?box=all')).json()).items;
        return { snooze: await post(`/api/alerts/${a}/snooze`, { mode: 'worse' }), diagnose: await post('/api/diagnose', { alert_id: d, prompt: 'x' }),
          draft: (await fetch(`/api/diagnose/draft?alert_id=${d}`)).status, items: items.filter((i) => /^alert:/.test(i.key)).map((i) => ({ key: i.key, snooze: i.snooze, diagnose: i.diagnose, actions: i.actions, has: ['snooze', 'diagnose', 'actions', 'choices'].filter((k) => k in i) })) };
      }, [cpl, dry]);
      check(`a ${who === 'mate' ? 'teammate' : 'client'} can't snooze or diagnose`, res.snooze === 403 && res.diagnose === 403 && res.draft === 403, JSON.stringify([res.snooze, res.diagnose, res.draft]));
      if (who === 'mate') {
        const mine = res.items.find((i) => i.key === `alert:${cpl}`);
        await p.goto(`${BASE}/inbox.html?box=all#item=${encodeURIComponent(`alert:${cpl}`)}`);
        await p.waitForSelector('#ib-detail .al-snoozed');
        check('a teammate sees the snooze chip with who set it, and no buttons', mine && mine.snooze && mine.actions.length === 0 && !mine.diagnose
          && (await p.locator('#ib-detail [data-al-snooze], #ib-detail [data-al-wake], #ib-detail [data-al-diag], #ib-detail .al-acts').count()) === 0
          && /Snoozed until it gets worse · Eugene/.test(await p.textContent('#ib-detail .al-snoozed')), JSON.stringify(mine));
      } else {
        await p.goto(`${BASE}/inbox.html?box=all#item=${encodeURIComponent(`alert:${rej}`)}`);
        await p.waitForSelector('#ib-detail h2');
        check('a client sees no snooze, diagnosis or buttons on an alert', res.items.length > 0 && res.items.every((i) => i.has.length === 0)
          && (await p.locator('#ib-detail .al-acts, #ib-detail .al-snoozed').count()) === 0, JSON.stringify(res.items.slice(0, 2)));
      }
      await ctx.close();
    }
    py(`import db
db.execute(\\"UPDATE users SET is_active = FALSE WHERE email IN ('qa-w1-client@example.com', 'qa-w1-mate@example.com')\\")
db.execute(\\"DELETE FROM campaign_members WHERE user_id = (SELECT id FROM users WHERE email = 'qa-w1-mate@example.com')\\")`);
    reset();
    // Phones: a tap opens the item and Back closes it; Today rows keep one button plus ⋯; 44px buttons; a 16px request
    // field with Send to Claude in view; nothing past the edge at 320px.
    {
      // A fresh problem Claude hasn't looked into yet, on the ad set (signed in with the desktop session: no extra sign-ins).
      const dry = raise('no_leads', 'bad', 4, '120252672227950312', 'No leads for 4 days in “QA phone”');
      const signedIn = await page.context().storageState();
      const pctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, storageState: signedIn });
      const pp = await pctx.newPage();
      pp.on('pageerror', (e) => errors.push('phone page: ' + e.message));
      await pp.goto(BASE + '/inbox.html?box=need');
      await pp.waitForSelector(`#ib-list [data-key="alert:${dry}"]`);
      await pp.tap(`#ib-list [data-key="alert:${dry}"]`);
      await pp.waitForSelector('#ib-detail [data-al-diag]', { state: 'visible' });
      const sizes = await pp.$$eval('#ib-detail .ib-acts .btn', (b) => b.map((x) => Math.round(x.getBoundingClientRect().height)));
      check('on a phone a tap opens the alert with its buttons, each at least 44px tall', sizes.length >= 3 && sizes.every((h) => h >= 44), sizes.join());
      await pp.goBack();
      await pp.waitForFunction(() => !document.querySelector('#ib-panel').classList.contains('showing-detail'));
      check("the phone's Back closes it", await pp.isVisible(`#ib-list [data-key="alert:${dry}"]`));
      await pp.tap(`#ib-list [data-key="alert:${dry}"]`);
      await pp.waitForSelector('#ib-detail [data-al-diag]', { state: 'visible' });
      await pp.tap('#ib-detail [data-al-diag]');
      await pp.waitForSelector('dialog.dg-form #cd-input');
      await pp.tap('dialog.dg-form #cd-input');
      const dgFit = await pp.evaluate(() => { const ok = document.querySelector('dialog.dg-form #cd-ok').getBoundingClientRect();
        return { font: getComputedStyle(document.querySelector('dialog.dg-form #cd-input')).fontSize, okBottom: Math.round(ok.bottom), okH: Math.round(ok.height), vh: innerHeight }; });
      check('on a phone the request field is 16px and Send to Claude stays in view', dgFit.font === '16px' && dgFit.okBottom <= dgFit.vh && dgFit.okH >= 44, JSON.stringify(dgFit));
      await pp.tap('dialog.dg-form #cd-cancel');
      await pp.goto(BASE + '/home.html');
      await pp.waitForSelector(`.tq-row[data-key="alert:${dry}"] .al-more`);
      const rowW1 = await pp.evaluate((k) => { const r = document.querySelector(`.tq-row[data-key="${k}"]`); const more = r.querySelector('.al-more').getBoundingClientRect();
        return { inline: getComputedStyle(r.querySelector('.al-inline')).display, more: [Math.round(more.width), Math.round(more.height)] }; }, `alert:${dry}`);
      check('Today on a phone: Open plus one 44px ⋯ that holds Diagnose and Got it', rowW1.inline === 'none' && rowW1.more.every((n) => n >= 44), JSON.stringify(rowW1));
      await pp.tap(`.tq-row[data-key="alert:${dry}"] .al-more`);
      await pp.waitForSelector('dialog.al-choice .cd-choice');
      const menu = await pp.$$eval('dialog.al-choice .cd-choice', (b) => b.map((x) => [x.querySelector('b').textContent, Math.round(x.getBoundingClientRect().height)]));
      check('the ⋯ menu offers Diagnose with Claude and Got it… as 44px choices', menu.map((m) => m[0]).join() === 'Diagnose with Claude,Got it…' && menu.every((m) => m[1] >= 44), JSON.stringify(menu));
      await pp.tap('dialog.al-choice .cd-choice[data-value="snooze"]');
      await pp.waitForSelector('dialog.al-choice .cd-choice[data-value="days:1"]');
      const sheet = await pp.evaluate(() => { const r = document.querySelector('dialog.al-choice').getBoundingClientRect(); return { bottom: Math.round(r.bottom), vh: innerHeight, w: Math.round(r.width), vw: innerWidth }; });
      check('Got it on a phone is a sheet at the bottom; a red money alert can only wait a day', sheet.bottom === sheet.vh && sheet.w === sheet.vw
        && (await pp.$$eval('dialog.al-choice .cd-choice b', (b) => b.map((x) => x.textContent))).join() === 'Remind me tomorrow', JSON.stringify(sheet));
      await pp.tap('dialog.al-choice #cd-cancel');
      // An Ads Manager edit that broke a money rule waits for Done: on a phone Done is in the ⋯ too.
      const oe = Number(py(`import db;print(db.execute(\\"INSERT INTO alerts (rule, dedupe_key, level, title, lines, kind, entity_id, campaign_id, href) VALUES ('outside_edit', 'qa-w1-oe-' || md5(random()::text), 'warn', 'QA phone outside edit', '[]', 'event', '${C}', '${C}', '/campaign.html?id=${C}&tab=history') RETURNING id\\", returning=True)['id'])`));
      await pp.goto(BASE + '/home.html');
      await pp.waitForSelector(`.tq-row[data-key="alert:${oe}"] .al-more`);
      await pp.tap(`.tq-row[data-key="alert:${oe}"] .al-more`);
      await pp.waitForSelector('dialog.al-choice .cd-choice[data-value="done"]');
      const oeMenu = await pp.$$eval('dialog.al-choice .cd-choice b', (b) => b.map((x) => x.textContent));
      await pp.tap('dialog.al-choice .cd-choice[data-value="done"]');
      await pp.waitForSelector(`.tq-row[data-key="alert:${oe}"]`, { state: 'detached' });
      const oeShut = py(`import db;print(db.query('SELECT resolved_at IS NOT NULL AS d FROM alerts WHERE id = %s', (${oe},), one=True)['d'])`);
      check('on a phone the ⋯ also holds Done for an Ads Manager edit that waits for a person, and Done closes it',
        oeMenu.join() === 'Diagnose with Claude,Done' && oeShut === 'True', `${oeMenu.join()} ${oeShut}`);
      await pctx.close();
      const nctx = await browser.newContext({ viewport: { width: 320, height: 700 }, isMobile: true, hasTouch: true, storageState: signedIn });
      const np = await nctx.newPage();
      await np.goto(BASE + '/home.html');
      await np.waitForSelector(`.tq-row[data-key="alert:${dry}"]`);
      const over = async () => np.evaluate(() => [...document.querySelectorAll('.tq-row *, #ib-detail *, dialog *')].filter((e) => e.getBoundingClientRect().right > innerWidth + 1 && e.getBoundingClientRect().width > 0).map((e) => e.className || e.tagName).slice(0, 4));
      const homeOver = await over();
      await np.goto(`${BASE}/inbox.html?box=need#item=${encodeURIComponent(`alert:${dry}`)}`);
      await np.waitForSelector('#ib-detail [data-al-diag]', { state: 'visible' });
      const inboxOver = await over();
      await np.tap('#ib-detail [data-al-snooze]');
      await np.waitForSelector('dialog.al-choice .cd-choice');
      const dlgOver = await over();
      check('at 320px nothing of Today, the alert or Got it runs past the edge', !homeOver.length && !inboxOver.length && !dlgOver.length, JSON.stringify([homeOver, inboxOver, dlgOver]));
      await nctx.close();
    }
    // The QA alerts close, so later checks see the usual Inbox.
    py(`import db;db.execute(\\"UPDATE alerts SET resolved_at = now() WHERE (dedupe_key LIKE '%qa-w1-%' OR (rule = 'ad_rejected' AND entity_id = '${N4}')) AND resolved_at IS NULL\\")`);
    reset();
  }
  // W1b: lead-quality alerts. Of the leads the team worked (14 days ending 2 days ago) few qualify, or many look like junk:
  // one alert per campaign in the Inbox's Leads and on Today, with Got it and Diagnose; it closes once that's no longer true.
  {
    const C = '120252638288040312';
    const CAMP = 'Edge Bourne - Free intro call - Leads';
    const N3 = '120252672230740312';
    const PAUSED = 'qa-w1b-paused';
    const runAlerts = () => sh(`docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -c "import alerts;print(alerts.run())"`);
    // 24 worked leads on N3 (3 qualified, 17 contacted, 4 lost: no response) and 24 that look fake and nobody contacted, 5-13 days old.
    // The share stays between 10% and 20% whichever demo leads are still in the window (they age out day by day).
    // Leads that must not count, each worked and junk so it would move both figures: 1 day old, 17 days old, a test lead,
    // a repeat; and 12 worked, unqualified leads on a paused campaign (it would raise its own alert if paused ones counted).
    py(`import db
db.execute(\\"DELETE FROM leads WHERE meta_lead_id LIKE 'qa-w1b-%'\\")
db.execute(\\"INSERT INTO campaigns (id, name, status, effective_status) VALUES ('${PAUSED}', 'QA W1b paused', 'PAUSED', 'PAUSED') ON CONFLICT (id) DO UPDATE SET effective_status = 'PAUSED'\\")
rows = [('qualified', 'qualified', None, [])] * 3 + [('contacted', 'contacted', None, [])] * 17 + [('new', 'lost', 'no_response', [])] * 4 + [('new', 'new', None, ['fake_phone'])] * 24
ins = \\"INSERT INTO leads (meta_lead_id, created_time, full_name, campaign_id, campaign_name, ad_id, ad_name, status, max_stage, lost_reason, junk_flags, quality_checked, is_test, repeat_of) VALUES (%s, now() - make_interval(days => %s), %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s) RETURNING id\\"
first = None
for n, (stage, status, why, flags) in enumerate(rows):
    lid = db.execute(ins, ('qa-w1b-%d' % n, 5 + n % 9, 'QA quality %d' % n, '${C}', '${CAMP}', '${N3}', 'N3 - Same work twice', status, stage, why, flags, False, None), returning=True)['id']
    first = first or lid
for name, days, test, rep in (('d-new', 1, False, None), ('d-old', 17, False, None), ('d-test', 8, True, None), ('d-repeat', 8, False, first)):
    db.execute(ins, ('qa-w1b-' + name, days, 'QA quality ' + name, '${C}', '${CAMP}', '${N3}', 'N3 - Same work twice', 'lost', 'new', 'spam', [], False if not test else True, rep), returning=True)
for n in range(12):
    db.execute(ins, ('qa-w1b-p%d' % n, 6 + n % 5, 'QA paused %d' % n, '${PAUSED}', 'QA W1b paused', None, None, 'contacted', 'contacted', None, [], False, None), returning=True)`);
    // The same figures counted another way: SQL over the account's calendar, not the alert's Python.
    const want = JSON.parse(py(`import db, json, account_info
r = db.query(\\"SELECT COUNT(*) AS leads, COUNT(*) FILTER (WHERE l.max_stage <> 'new' OR l.status = 'lost') AS worked, COUNT(*) FILTER (WHERE l.max_stage IN ('qualified', 'won')) AS qualified, COUNT(*) FILTER (WHERE l.lost_reason = 'spam' OR (cardinality(l.junk_flags) > 0 AND NOT l.junk_dismissed AND l.max_stage = 'new' AND (l.lost_reason IS NULL OR l.lost_reason NOT IN ('not_fit', 'too_small', 'price', 'went_elsewhere')))) AS junk FROM leads l WHERE NOT l.is_test AND l.repeat_of IS NULL AND l.campaign_id = %s AND (l.created_time AT TIME ZONE %s)::date BETWEEN (now() AT TIME ZONE %s)::date - 16 AND (now() AT TIME ZONE %s)::date - 3\\", ('${C}',) + (account_info.tz_name(),) * 3, one=True)
print(json.dumps({k: int(v) for k, v in r.items()}))`));
    const decoys = Number(py(`import db;print(db.query(\\"SELECT COUNT(*) AS n FROM leads WHERE meta_lead_id LIKE 'qa-w1b-d-%%'\\", one=True)['n'])`));
    runAlerts();
    const lqItems = (await getJson('/api/inbox?box=need&kind=leads')).items.filter((i) => ['qualified_low', 'junk_high'].includes(i.rule) && i.entity_id === C);
    const ql = lqItems.find((i) => i.rule === 'qualified_low');
    const jh = lqItems.find((i) => i.rule === 'junk_high');
    const qPct = Math.round(want.qualified / want.worked * 1000) / 10;
    const jPct = Math.round(want.junk / want.leads * 1000) / 10;
    check('W1b: few qualified leads raise one alert on the campaign, in the Inbox under Leads, counted from the leads the team worked',
      Boolean(ql) && ql.title === `Only ${Math.round(want.qualified / want.worked * 100)}% of leads from “${CAMP}” qualify`
      && ql.lines[0] === `${want.qualified} of ${want.worked} leads the team worked in the last 14 days ${want.qualified === 1 ? 'was' : 'were'} qualified. You're alerted below 20%.`
      && ql.lines[ql.lines.length - 1] === "Cheap leads that don't qualify cost more than they look." && ql.need && ql.href === `/leads.html?campaign=${C}`,
      JSON.stringify([want, ql && ql.title, ql && ql.lines]));
    check('W1b: many junk-looking leads raise "look like junk", counted over every counted lead (flagged junk is never worked)',
      Boolean(jh) && jh.title === `${Math.round(want.junk / want.leads * 100)}% of leads from “${CAMP}” look like junk`
      && jh.lines[0] === `${want.junk} of ${want.leads} leads in the last 14 days look like junk (marked spam or fake, or fake-looking details and never contacted).`
      && jh.href === `/leads.html?campaign=${C}&status=all&junk=1`,
      JSON.stringify([want, jh && jh.title, jh && jh.lines, jh && jh.href]));
    const pausedAlerts = Number(py(`import db;print(db.query(\\"SELECT COUNT(*) AS n FROM alerts WHERE entity_id = '${PAUSED}' AND resolved_at IS NULL\\", one=True)['n'])`));
    check('leads newer than 2 days, older than 16 days, test leads, repeats and paused campaigns are left out of both figures',
      decoys === 4 && pausedAlerts === 0, JSON.stringify([decoys, pausedAlerts, want]));
    const stored = JSON.parse(py(`import db, json;print(json.dumps([float(r['measure']) for r in db.query(\\"SELECT measure FROM alerts WHERE id = ANY(%s) ORDER BY rule DESC\\", ([${ql ? ql.alert_id : 0}, ${jh ? jh.alert_id : 0}],))]))`));
    check('each keeps its share as the figure a snooze watches', JSON.stringify(stored) === JSON.stringify([qPct, jPct]), JSON.stringify([stored, qPct, jPct]));
    await page.goto(`${BASE}/inbox.html?box=need&kind=leads#item=${encodeURIComponent(`alert:${ql.alert_id}`)}`);
    await page.reload();
    await page.waitForSelector('#ib-detail [data-al-snooze]');
    check('the alert opens the campaign\'s leads, with Got it and Diagnose with Claude beside it',
      (await page.textContent('#ib-detail a.btn-primary')).trim() === 'See the leads' && (await page.getAttribute('#ib-detail a.btn-primary', 'href')) === `/leads.html?campaign=${C}`
      && await page.isVisible('#ib-detail [data-al-diag]'));
    await page.click('#ib-detail [data-al-snooze]');
    await page.waitForSelector('dialog.al-choice .cd-choice');
    const lqGotIt = (await page.textContent('dialog.al-choice')).replace(/\s+/g, ' ');
    // The server's rule: ten points lower, or "none of them" once that would be 0% or less.
    const lqHint = qPct <= 10 ? "You'll hear again if none of them qualify." : `You'll hear again if it drops to ${Math.round((qPct - 10) * 10) / 10}%.`;
    check('Got it on a lead-quality alert offers 3 days or until it gets worse, ten points lower',
      (await page.locator('dialog.al-choice .cd-choice').count()) === 2 && lqGotIt.includes(lqHint), `${lqHint} | ${lqGotIt.slice(0, 260)}`);
    await page.click('dialog.al-choice #cd-cancel');
    const lqDraft = await getJson(`/api/diagnose/draft?alert_id=${ql.alert_id}`);
    check('Diagnose uses the lead-quality checklist and names the campaign', lqDraft.playbook && lqDraft.playbook.label === 'lead quality' && lqDraft.prompt.includes(C),
      JSON.stringify(lqDraft.playbook));
    const lqHome = await getJson('/api/home');
    await page.goto(BASE + '/home.html');
    await page.waitForSelector(`.tq-row[data-key="alert:${ql.alert_id}"]`);
    check('Today lists them with the problems to fix, not with the leads to call',
      [ql, jh].every((i) => lqHome.queue.some((r) => r.key === `alert:${i.alert_id}` && r.group === 'problems'))
      && /See the leads/.test(await page.textContent(`.tq-row[data-key="alert:${ql.alert_id}"] .tq-acts`)), JSON.stringify(lqHome.queue.map((r) => [r.key, r.group])).slice(0, 300));
    await page.screenshot({ path: `${OUT}/flow-lead-quality-alerts.png` });
    // "See the leads" on the junk alert: the campaign's leads that look like junk, at every stage (spam is Lost).
    await page.goto(BASE + jh.href);
    await page.waitForSelector('#junk-wrap:not([hidden]) #junk-only:checked');
    await page.waitForSelector('#list .lead-row');
    const camp = await getJson(`/api/leads?status=all&campaign=${C}`);
    const junkOnly = await getJson(`/api/leads?status=all&junk=1&campaign=${C}`);
    const junkIds = camp.leads.filter((l) => l.junk && !l.repeat_of).map((l) => l.id).sort((a, b) => a - b);
    const shownRows = await page.locator('#list .lead-row').count();
    const shownJunk = await page.locator('#list .lead-row .pill.warn', { hasText: 'Looks like junk' }).count();
    check('the junk filter lists exactly the leads the junk rule marks (any stage, no repeats), with its count beside the box',
      JSON.stringify(junkOnly.leads.map((l) => l.id).sort((a, b) => a - b)) === JSON.stringify(junkIds) && junkOnly.junk === junkIds.length
      && junkIds.length >= 24 && shownRows === junkIds.length && shownJunk === junkIds.length
      && (await page.textContent('#junk-label')).trim() === `Only junk (${junkIds.length})` && !(await page.isHidden('#clear-filters')),
      JSON.stringify([junkIds.length, junkOnly.leads.length, junkOnly.junk, shownRows, shownJunk]));
    await page.click('#junk-only');
    const backToAll = await page.waitForFunction((n) => document.querySelectorAll('#list .lead-row').length > n, junkIds.length, { timeout: 8000 }).then(() => true, () => false);
    check('unticking it shows the campaign\'s other leads again and drops junk from the address',
      backToAll && !new URL(page.url()).searchParams.get('junk') && !(await page.isChecked('#junk-only')));
    // Who sees them: a teammate on the campaign sees both, with no buttons and is refused; a client sees neither.
    py(`import db
from werkzeug.security import generate_password_hash as h
for email, role in (('qa-w1-client@example.com', 'client'), ('qa-w1-mate@example.com', 'member')):
    db.execute(\\"INSERT INTO users (email, name, password_hash, role, account_id) VALUES (%s, %s, %s, %s, 1) ON CONFLICT (email) DO UPDATE SET is_active = TRUE, password_hash = EXCLUDED.password_hash, role = EXCLUDED.role, account_id = 1, must_change_password = FALSE\\", (email, 'QA W1 ' + role, h('w1-pass-12345'), role))
db.execute(\\"INSERT INTO campaign_members (campaign_id, user_id, account_id) SELECT '${C}', id, 1 FROM users WHERE email = 'qa-w1-mate@example.com' ON CONFLICT DO NOTHING\\")`);
    for (const [email, who] of [['qa-w1-mate@example.com', 'mate'], ['qa-w1-client@example.com', 'client']]) {
      const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
      const p = await ctx.newPage();
      p.on('pageerror', (e) => errors.push(`${who} page: ${e.message}`));
      await p.goto(BASE + '/login.html');
      await p.fill('#email', email); await p.fill('#password', 'w1-pass-12345');
      await Promise.all([p.waitForURL('**/home.html**'), p.click('button[type=submit]')]);
      const res = await p.evaluate(async ([a]) => {
        const lq = (items) => items.filter((i) => ['qualified_low', 'junk_high'].includes(i.rule)).map((i) => ({ key: i.key, actions: i.actions, diagnose: i.diagnose, group: i.group }));
        return { inbox: lq((await (await fetch('/api/inbox?box=all')).json()).items), home: lq((await (await fetch('/api/home')).json()).queue || []),
          snooze: (await fetch(`/api/alerts/${a}/snooze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: 'worse' }) })).status };
      }, [ql.alert_id]);
      if (who === 'mate') {
        await p.goto(`${BASE}/inbox.html?box=all#item=${encodeURIComponent(`alert:${ql.alert_id}`)}`);
        await p.waitForSelector('#ib-detail h2');
        check('a teammate on the campaign sees both lead-quality alerts, on Today too, with no Got it or Diagnose, and is refused',
          res.inbox.length === 2 && res.inbox.every((i) => (i.actions || []).length === 0 && !i.diagnose) && res.home.length === 2 && res.snooze === 403
          && (await p.locator('#ib-detail [data-al-snooze], #ib-detail [data-al-diag]').count()) === 0
          && (await p.textContent('#ib-detail a.btn-primary')).trim() === 'See the leads', JSON.stringify(res));
      } else {
        await p.goto(`${BASE}/inbox.html?box=all`);
        await p.waitForSelector('#ib-list');
        check('a client sees no lead-quality alert in the Inbox or on Today', res.inbox.length === 0 && res.home.length === 0 && res.snooze === 403
          && (await p.locator('#ib-list [data-key="alert:' + ql.alert_id + '"], #ib-list [data-key="alert:' + jh.alert_id + '"]').count()) === 0, JSON.stringify(res));
      }
      await ctx.close();
    }
    py(`import db
db.execute(\\"UPDATE users SET is_active = FALSE WHERE email IN ('qa-w1-client@example.com', 'qa-w1-mate@example.com')\\")
db.execute(\\"DELETE FROM campaign_members WHERE user_id = (SELECT id FROM users WHERE email = 'qa-w1-mate@example.com')\\")`);
    // Settings → Alerts on a phone: every rule's box is the same size, however long its label.
    {
      const sp = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, storageState: await page.context().storageState() })).newPage();
      sp.on('pageerror', (e) => errors.push('settings phone: ' + e.message));
      await sp.goto(BASE + '/settings.html#alerts');
      await sp.waitForSelector('#al-rules input[data-key="on"]');
      const widths = await sp.evaluate(() => [...document.querySelectorAll('#al-rules input[data-key="on"]')].map((i) => Math.round(i.getBoundingClientRect().width)));
      check('Settings → Alerts on a phone: every rule\'s tick box is 18px wide', widths.length === 19 && widths.every((w) => w === 18), JSON.stringify(widths));
      await sp.context().close();
    }
    // Gone again: without those leads both alerts close by themselves at the next check.
    py(`import db
db.execute(\\"DELETE FROM leads WHERE meta_lead_id LIKE 'qa-w1b-%'\\")
db.execute(\\"DELETE FROM campaigns WHERE id = '${PAUSED}'\\")`);
    runAlerts();
    const closed = JSON.parse(py(`import db, json;print(json.dumps([r['open'] for r in db.query('SELECT resolved_at IS NULL AS open FROM alerts WHERE id = ANY(%s)', ([${ql.alert_id}, ${jh.alert_id}],))]))`));
    check('once the leads are better the lead-quality alerts close by themselves', closed.length === 2 && closed.every((o) => o === false)
      && !(await getJson('/api/inbox?box=need&kind=leads')).items.some((i) => ['qualified_low', 'junk_high'].includes(i.rule)), JSON.stringify(closed));
  }
  // Phase 9.1: what used to break.
  const seen91 = errors.length;
  await page.goto(BASE + '/ads.html');
  await page.waitForSelector('tr[data-row^="ad:"] input[type=checkbox]');
  await page.locator('tr[data-row^="ad:"] input[type=checkbox]').nth(0).check();
  await page.locator('tr[data-row^="ad:"] input[type=checkbox]').nth(1).check();
  await Promise.all([page.waitForURL('**/compare.html**'), page.click('[data-bulk="compare"]')]);
  check('Compare from the Ads bar keeps "vs before" on', /[?&]vs=1/.test(page.url()), page.url());
  await page.evaluate(() => localStorage.setItem('ebads-range', 'mtd'));
  const perfRange = async () => {
    const [req] = await Promise.all([page.waitForRequest((r) => /\/api\/performance\?/.test(r.url())), page.goto(BASE + '/performance.html')]);
    return new URL(req.url()).searchParams.get('range');
  };
  const mtdAsked = await perfRange();
  await page.waitForFunction(() => document.querySelector('#range-pick')?.value === 'mtd');
  check('Results honours a month range picked on Ads', mtdAsked === 'mtd', mtdAsked);
  await page.evaluate(() => localStorage.setItem('ebads-range', 'nonsense'));
  const unknownAsked = await perfRange();
  await page.waitForFunction(() => document.querySelector('#range-pick')?.value === '7');
  check('Results ignores a range it does not know', unknownAsked === '7', unknownAsked);
  await page.evaluate(() => localStorage.removeItem('ebads-range'));
  await page.goto(BASE + '/leads.html');
  await page.waitForSelector('.lead-row');
  const leadIds = await page.$$eval('.lead-row', (r) => r.map((x) => x.dataset.id));
  await Promise.all([page.waitForResponse((r) => r.url().endsWith(`/api/leads/${leadIds[1]}`)), page.evaluate((id) => { location.hash = `lead=${id}`; }, leadIds[1])]);
  await page.waitForFunction((id) => document.querySelector(`.lead-row[data-id="${id}"]`)?.getAttribute('aria-current') === 'true', leadIds[1]);
  const jumpedName = (await getJson(`/api/leads/${leadIds[1]}`)).full_name || 'No name given';
  check('jumping to a lead while on Leads opens it', (await page.textContent('#detail .detail-top h2')) === jumpedName, jumpedName);
  await page.waitForTimeout(200);
  await page.fill('#note', 'half a thought');
  await Promise.all([page.waitForResponse((r) => r.request().method() === 'PATCH' && /api\/leads\//.test(r.url())), page.click('#stages [aria-pressed="true"]')]);
  await page.waitForTimeout(250);
  check('moving a lead keeps the note being typed', (await page.inputValue('#note')) === 'half a thought');
  // 9.4 Leads: a stage move can be put back from the toast, and the history says what happened in sentences.
  const undoLead = leadIds[1];
  const undoFrom = (await getJson(`/api/leads/${undoLead}`)).status;
  const undoTo = undoFrom === 'won' ? 'lost' : 'won';
  const [undoMoveRes] = await Promise.all([page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().endsWith(`/api/leads/${undoLead}`)), page.click(`#stages [data-stage="${undoTo}"]`)]);
  const undoMoved = await undoMoveRes.json();
  await page.waitForSelector('.toast .toast-act');
  check('a stage move says so with an Undo', /Moved to (Won|Lost)/.test(await page.textContent('.toast')) && undoMoved.undo && undoMoved.undo.minutes === 10, JSON.stringify(undoMoved.undo));
  // The toast waits while the keyboard is on its Undo (8 s otherwise), so it can be reached in time.
  await page.focus('.toast .toast-act');
  await page.waitForTimeout(8600);
  check('the Undo toast stays while the keyboard is on it', await page.isVisible('.toast .toast-act'));
  const [undoPost] = await Promise.all([page.waitForResponse((r) => /\/events\/\d+\/undo$/.test(r.url())), page.click('.toast .toast-act')]);
  await page.waitForFunction((b) => document.querySelector(`#stages [data-stage="${b}"]`)?.getAttribute('aria-pressed') === 'true', undoFrom);
  const undoBody = await undoPost.json();
  const undoLabel = { won: 'Won', lost: 'Lost' }[undoTo];
  check('Undo puts the stage back', undoPost.status() === 200 && undoBody.status === undoFrom, `${undoPost.status()} ${undoBody.status}`);
  check('the history reads newest first, in sentences, and marks the move undone', new RegExp(`^Eugene undid the move to ${undoLabel}$`).test(undoBody.history[0].text)
    && new RegExp(`moved it from \\w+ to ${undoLabel} \\(undone\\)$`).test(undoBody.history[1].text) && /undid the move/.test(await page.textContent('#detail ol.history li:first-child')),
    undoBody.history.slice(0, 2).map((h) => h.text).join(' | '));
  const undoCrmLeft = Number(py(`import db;print(db.query(\\"SELECT COUNT(*) AS n FROM crm_events WHERE lead_id = %s AND stage = %s\\", (${undoLead}, '${undoTo}'), one=True)['n'])`));
  check('Undo takes back a stage still waiting to go to Meta (one already sent stays, and the toast says so)', undoCrmLeft === 0 || (undoBody.undone.meta_has || []).includes(undoTo), `${undoCrmLeft} ${JSON.stringify(undoBody.undone)}`);
  const undoTwice = await page.evaluate(async ([id, ev]) => (await fetch(`/api/leads/${id}/events/${ev}/undo`, { method: 'POST', headers: { 'X-Requested-With': 'ebads' } })).status, [undoLead, undoMoved.undo.event_id]);
  check('the same move cannot be undone twice', undoTwice === 409, String(undoTwice));
  // Moved out of New, then emailed: Undo puts the stage back but the lead stays reached (not waiting again).
  {
    const before = JSON.parse(py(`import db,json;r=db.query(\\"SELECT status, first_contacted_at FROM leads WHERE id = %s\\", (${undoLead},), one=True);print(json.dumps({'status': r['status'], 'fc': r['first_contacted_at'].isoformat() if r['first_contacted_at'] else None}))`));
    py(`import db;db.execute(\\"UPDATE leads SET status = 'new', first_contacted_at = NULL WHERE id = %s\\", (${undoLead},))`);
    const moved = await page.evaluate(async (id) => (await (await fetch(`/api/leads/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'ebads' }, body: JSON.stringify({ status: 'contacted' }) })).json()), undoLead);
    const reply = py(`import db;r=db.execute(\\"INSERT INTO lead_replies (lead_id, to_email, subject, body, status, sent_at) VALUES (%s, 'qa@example.com', 'QA reply', 'x', 'sent', now()) RETURNING id\\", (${undoLead},), returning=True);print(r['id'])`);
    const back = await page.evaluate(async ([id, ev]) => { const r = await fetch(`/api/leads/${id}/events/${ev}/undo`, { method: 'POST', headers: { 'X-Requested-With': 'ebads' } }); return { code: r.status, body: await r.json() }; }, [undoLead, moved.undo && moved.undo.event_id]);
    const listed = (await getJson('/api/leads')).leads?.find((l) => String(l.id) === String(undoLead));
    check('Undo after an email sent since keeps the lead reached: back in New but not waiting for a call', back.code === 200 && back.body.status === 'new' && Boolean(back.body.first_contacted_at)
      && back.body.urgency === 'done' && (!listed || listed.urgency === 'done'), JSON.stringify({ code: back.code, status: back.body.status, fc: back.body.first_contacted_at, u: back.body.urgency, lu: listed && listed.urgency }));
    py(`import db;db.execute(\\"DELETE FROM lead_replies WHERE id = %s\\", (${reply},));db.execute(\\"UPDATE leads SET status = %s, first_contacted_at = %s WHERE id = %s\\", ('${before.status}', ${before.fc ? `'${before.fc}'` : 'None'}, ${undoLead}))`);
  }
  // L1 Follow-ups and booked calls: call outcomes, the next step, Undo, Lost after three tries, Today's rows,
  // a booked call with cost per booked call, did the call happen, the follow-up reminder and a history never pruned.
  {
    const C1 = "'120252638288040312', 'Edge Bourne - Free intro call - Leads'";
    const newLead = (key, name, mins) => Number(py(`import db
db.execute(\\"DELETE FROM leads WHERE meta_lead_id = '${key}'\\")
r = db.execute(\\"INSERT INTO leads (meta_lead_id, created_time, full_name, phone, campaign_id, campaign_name) VALUES ('${key}', now() - interval '${mins} minutes', '${name}', '+16195557788', ${C1}) RETURNING id\\", returning=True)
print(r['id'])`));
    const leadJson = (id) => getJson(`/api/leads/${id}`);
    const post = (url, body, method = 'POST') => page.evaluate(async ([u, b, m]) => { const r = await fetch(u, { method: m, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }); return { code: r.status, body: await r.json() }; }, [url, body, method]);
    const fuId = newLead('qa-follow-1', 'QA Follow Lead', 200);
    await page.goto(`${BASE}/leads.html#lead=${fuId}`);
    await page.reload();
    await page.waitForSelector('#fu-box');
    check('L1: a new lead\'s Follow-up box says No calls yet, with Log a call beside Call', /No calls yet\./.test(await page.textContent('#fu-box'))
      && await page.isVisible('#log-call') && await page.isVisible('#call-link'));
    // 1. No answer → Call back, later today (preselected) → Save.
    await page.click('#log-call');
    await page.waitForSelector('dialog.fu-dialog [data-outcome="no_answer"]');
    check('L1: Log a call asks how the call went, by first name', /How did the call with QA go\?/.test(await page.textContent('dialog.fu-dialog h2'))
      && (await page.locator('dialog.fu-dialog [data-outcome]').count()) === 5);
    await page.screenshot({ path: `${OUT}/flow-fu-outcome.png` });
    await page.click('[data-outcome="no_answer"]');
    await page.waitForSelector('dialog.fu-dialog [data-kind="call_back"][aria-pressed="true"]');
    check('L1: No answer suggests Call back, later today', await page.isVisible('dialog.fu-dialog [data-when="later_today"][aria-pressed="true"]')
      && /^Later today \(/.test(await page.textContent('[data-when="later_today"]')));
    const [callRes] = await Promise.all([page.waitForResponse((r) => /\/calls$/.test(r.url())), page.click('dialog.fu-dialog #fu-save')]);
    const called = await callRes.json();
    await page.waitForSelector('dialog.fu-dialog', { state: 'detached' });
    await page.waitForFunction((id) => /Call back/.test(document.querySelector(`.lead-row[data-id="${id}"] .fu-chip`)?.textContent || ''), fuId);
    check('L1: the call counts as a first try, the row says Call back, History and the toast say what happened', Boolean(called.first_contacted_at) && called.call_attempts === 1
      && called.urgency === 'done' && /Eugene called: no answer/.test(await page.textContent('#detail ol.history')) && /Logged: no answer\. Next: Call back/.test(await page.textContent('.toast'))
      && /Next: Call back/.test(await page.textContent('#fu-box')), `${called.call_attempts} ${await page.textContent('.toast')}`);
    // 2. Undo from the toast.
    const [undoRes] = await Promise.all([page.waitForResponse((r) => /\/undo$/.test(r.url())), page.click('.toast .toast-act')]);
    const undone = await undoRes.json();
    await page.waitForFunction(() => /\(undone\)/.test(document.querySelector('#detail ol.history')?.textContent || ''));
    check('L1: Undo takes the call back: no tries, waiting again, the next step it set gone, History says so', undoRes.status() === 200 && undone.call_attempts === 0
      && !undone.first_contacted_at && !undone.next_step_at && undone.history[0].text === 'Eugene took back the call'
      && undone.history.some((h) => h.text === 'Eugene called: no answer (undone)'), JSON.stringify(undone.history.slice(0, 3).map((h) => h.text)));
    const again = await post(`/api/leads/${fuId}/events/${called.undo.event_id}/undo`, {});
    check('L1: the same call cannot be taken back twice', again.code === 409, String(again.code));
    // A note alone is not a call: still waiting.
    await post(`/api/leads/${fuId}/notes`, { body: 'QA note, not a call' });
    check('L1: a note alone does not stop the first-call reminders', (await leadJson(fuId)).urgency !== 'done');
    // 3. Three calls nobody answered → one tap: Lost, couldn't reach (the next step closes).
    await post(`/api/leads/${fuId}`, { next_step: { kind: 'call_back', preset: 'tomorrow_9' } }, 'PATCH');
    for (let i = 0; i < 3; i++) await post(`/api/leads/${fuId}/calls`, { outcome: 'no_answer' });
    await page.reload();
    await page.waitForSelector('#fu-lost');
    check('L1: after three tries nobody answered, the box offers Lost: couldn\'t reach', (await page.textContent('#fu-lost')).trim() === "Lost: couldn't reach"
      && /3 tries, no answer\./.test(await page.textContent('#fu-suggest')));
    const badLost = await post(`/api/leads/${fuId}`, { status: 'lost', lost_reason: 'made up' }, 'PATCH');
    check('L1: a Lost reason outside the list is refused (400) and the lead stays put', badLost.code === 400 && (await leadJson(fuId)).status !== 'lost', String(badLost.code));
    const [lostResp] = await Promise.all([page.waitForResponse((r) => r.request().method() === 'PATCH'), page.click('#fu-lost')]);
    const lostUndo = ((await lostResp.json()).undo || {}).event_id;
    await page.waitForFunction(() => document.querySelector('#stages [data-stage="lost"]')?.getAttribute('aria-pressed') === 'true');
    const lostLead = await leadJson(fuId);
    check('L1: Lost: couldn\'t reach moves it to Lost with the reason and closes the next step', lostLead.status === 'lost' && !lostLead.next_step_at
      && lostLead.history.some((h) => h.text === 'Next step closed: lead is Lost') && lostLead.history.some((h) => /to Lost \(No response\): Couldn't reach after 3 tries$/.test(h.text)),
      JSON.stringify(lostLead.history.slice(0, 3).map((h) => h.text)));
    // Undo of the Lost move brings the next step back and takes back the "Next step closed" line with it.
    const unLost = await post(`/api/leads/${fuId}/events/${lostUndo}/undo`, {});
    check('L1: Undo of Lost brings the next step back and marks "Next step closed" undone', unLost.code === 200 && Boolean(unLost.body.next_step_at)
      && unLost.body.history.some((h) => h.text === 'Next step closed: lead is Lost (undone)') && !unLost.body.history.some((h) => h.text === 'Next step closed: lead is Lost'),
      JSON.stringify({ code: unLost.code, next: unLost.body.next_step_at, h: (unLost.body.history || []).slice(0, 4).map((h) => h.text) }));
    // 4. A stage move by hand asks what's next.
    await post(`/api/leads/${fuId}`, { status: 'contacted' }, 'PATCH');
    await page.reload();
    await page.waitForSelector('#stages [data-stage="qualified"]');
    await page.click('#stages [data-stage="qualified"]');
    await page.waitForSelector('dialog.fu-dialog [data-kind]');
    check('L1: moving a lead to Qualified asks what\'s next for them', /What's next for QA\?/.test(await page.textContent('dialog.fu-dialog h2')));
    await page.click('dialog.fu-dialog [data-kind="proposal"]');
    await page.click('dialog.fu-dialog [data-when="tomorrow_9"]');
    await page.click('dialog.fu-dialog #fu-save');
    await page.waitForSelector('dialog.fu-dialog', { state: 'detached' });
    const nextShown = await page.waitForFunction(() => /Next: Send a quote · tomorrow 9:00 AM/.test(document.querySelector('#fu-box')?.textContent || ''), null, { timeout: 8000 }).then(() => true).catch(() => false);
    check('L1: the box shows the next step and when', nextShown, await page.textContent('#fu-box'));
    // 5. Overdue: on Leads (?due=overdue) and on Today, where Done closes it.
    py(`import db;db.execute(\\"UPDATE leads SET next_step_at = now() - interval '2 hours' WHERE id = %s\\", (${fuId},))`);
    await page.goto(`${BASE}/leads.html?due=overdue`);
    await page.waitForSelector(`.lead-row[data-id="${fuId}"]`);
    check('L1: Overdue lists the lead with an Overdue chip, and the filter says so', /^Overdue: Send a quote/.test(await page.textContent(`.lead-row[data-id="${fuId}"] .fu-chip`))
      && (await page.inputValue('#follow')) === 'overdue' && await page.isVisible('#clear-filters'));
    await page.goto(`${BASE}/home.html`);
    const row = `.tq-row[data-key="lead:${fuId}"]`;
    await page.waitForSelector(`${row} [data-fu-done]`);
    check('L1: Today lists the overdue follow-up in Follow up, with Call and Done', /Overdue: Send a quote QA Follow Lead/.test(await page.textContent(row))
      && (await page.$eval(row, (r) => r.closest('.tq-group').getAttribute('aria-labelledby'))) === 'tq-follow' && await page.isVisible(`${row} [data-dial]`));
    await page.click(`${row} [data-fu-done]`);
    await page.waitForSelector(row, { state: 'detached' });
    check('L1: Done takes it off Today and History says so', (await leadJson(fuId)).history.some((h) => h.text === 'Done: Send a quote'));
    // 6. A call booked on a New lead: Contacted, the chip, booked figures on Results and the Ads manager.
    const bkId = newLead('qa-follow-2', 'QA Booked Lead', 30);
    await page.goto(`${BASE}/leads.html#lead=${bkId}`);
    await page.reload();
    await page.waitForSelector('#log-call');
    await page.click('#log-call');
    await page.click('dialog.fu-dialog [data-outcome="booked"]');
    await page.waitForSelector('dialog.fu-dialog [data-day="tomorrow"]');
    const bookDefault = await page.evaluate(() => {
      const day = document.querySelector('dialog.fu-dialog [data-day][aria-pressed="true"]')?.dataset.day;
      const [h, m] = document.querySelector('dialog.fu-dialog #fu-time').value.split(':').map(Number);
      const at = new Date(); at.setHours(h, m, 0, 0);
      if (day === 'tomorrow') at.setDate(at.getDate() + 1);
      return { day, time: document.querySelector('dialog.fu-dialog #fu-time').value, future: (day === 'today' || day === 'tomorrow') && at > new Date() };
    });
    check('L1: When is the call? starts on a time still ahead (Save straight away is never refused as past)', bookDefault.future, JSON.stringify(bookDefault));
    await page.click('dialog.fu-dialog [data-day="tomorrow"]');
    await page.fill('dialog.fu-dialog #fu-time', '14:00');
    await page.click('dialog.fu-dialog #fu-save');
    await page.waitForSelector('dialog.fu-dialog', { state: 'detached' });
    await page.waitForFunction((id) => /^Call on \w{3} 2 PM$/.test(document.querySelector(`.lead-row[data-id="${id}"] .fu-chip`)?.textContent || ''), bkId);
    const booked = await leadJson(bkId);
    check('L1: Booked a call on a New lead books it, moves it to Contacted and says so', Boolean(booked.booked_at) && booked.meeting_status === 'scheduled'
      && booked.status === 'contacted' && /Call booked for \w{3} 2 PM\. Moved to Contacted\./.test(await page.textContent('.toast'))
      && /Call booked for .*2:00 PM \(booked by phone\)/.test(await page.textContent('#fu-box')), await page.textContent('.toast'));
    py(`import db;db.execute(\\"UPDATE leads SET created_time = now() - interval '2 days', booked_at = now() - interval '2 days' WHERE id = %s\\", (${bkId},))`);
    await page.goto(`${BASE}/performance.html`);
    await page.waitForSelector('#fig-booked');
    check('L1: Results shows Calls booked and Cost per booked call (from your leads)', /Calls booked/.test(await page.textContent('#fig-booked'))
      && /Cost per booked call/.test(await page.textContent('#fig-cpb')) && /from your leads/.test(await page.textContent('#fig-cpb')));
    await page.goto(`${BASE}/ads.html`);
    await page.waitForSelector('.mgr-wrap thead');
    check('L1: the Ads manager\'s Results columns include Booked and Per booked call', /Booked/.test(await page.textContent('.mgr-wrap thead')) && /Per booked call/.test(await page.textContent('.mgr-wrap thead')));
    const rep = await getJson('/api/reports?kind=week');
    check('L1: the report funnel has Booked a call as a share of the leads received', rep.funnel.some((f) => f.step === 'Booked a call' && f.of === 'Leads received')
      && rep.footnotes.includes('Booked calls come from your leads list, by the day the lead arrived.'), JSON.stringify(rep.funnel));
    // A No answer counts as a first try, so the report says first call or email, never "heard back".
    await page.goto(`${BASE}/report.html?kind=week`);
    await page.waitForSelector('.r-head');
    const repText = await page.textContent('#report');
    check('L1: the report says how fast leads got a first call or email (not "heard back")', rep.now.median_minutes != null && /Half of the leads got a first call or email within \d+ (minutes|hours)\./.test(repText)
      && !/heard back/.test(repText), String(rep.now.median_minutes));
    // 7. Did the call happen? No-show → Call back, later today.
    py(`import db;db.execute(\\"UPDATE leads SET meeting_at = now() - interval '2 hours' WHERE id = %s\\", (${bkId},))`);
    await page.goto(`${BASE}/home.html`);
    const brow = `.tq-row[data-key="lead:${bkId}"]`;
    await page.waitForSelector(`${brow} [data-fu-meeting="no_show"]`);
    check('L1: Today asks whether the booked call happened', /Did the call with QA Booked Lead happen\?/.test(await page.textContent(brow)));
    await page.click(`${brow} [data-fu-meeting="no_show"]`);
    await page.waitForSelector('dialog.fu-dialog [data-kind="call_back"][aria-pressed="true"]');
    check('L1: a No-show asks for the next step, Call back later today preselected', await page.isVisible('dialog.fu-dialog [data-when="later_today"][aria-pressed="true"]'));
    await page.click('dialog.fu-dialog #fu-save');
    await page.waitForSelector('dialog.fu-dialog', { state: 'detached' });
    const noShow = await leadJson(bkId);
    check('L1: History says No-show and the call back is set', noShow.meeting_status === 'no_show' && noShow.history.some((h) => h.text === 'No-show') && noShow.next_step_kind === 'call_back');
    // 8. A due follow-up reminds once (a second pass sends nothing more).
    py(`import db;db.execute(\\"UPDATE leads SET next_step_kind = 'call_back', next_step_at = now() - interval '1 minute' WHERE id = %s\\", (${fuId},))`);
    const remind = () => JSON.parse(py(`import reminders, db, json
from datetime import datetime, timezone
reminders.followups(datetime.now(timezone.utc))
print(json.dumps([r['title'] for r in db.query(\\"SELECT title FROM notifications WHERE kind = 'followup' AND ref = %s\\", ('${fuId}',))]))`));
    const firstPass = remind();
    const secondPass = remind();
    check('L1: a follow-up that came due reminds once (to whoever set it), in plain words', firstPass.length >= 1 && secondPass.length === firstPass.length
      && firstPass.every((t) => /^Call back QA Follow Lead: due \d{1,2}:\d{2} [AP]M$/.test(t)), JSON.stringify([firstPass, secondPass]));
    // 9. History is never pruned (activity is, after 180 days).
    const pruned = JSON.parse(py(`import db, jobs, json
e = db.execute(\\"INSERT INTO lead_events (lead_id, kind, at, details) VALUES (%s, 'note', now() - interval '400 days', '{}') RETURNING id\\", (${fuId},), returning=True)['id']
a = db.execute(\\"INSERT INTO activity (actor, action, subject, at) VALUES ('qa', 'qa.old', 'qa-old', now() - interval '400 days') RETURNING id\\", returning=True)['id']
jobs.prune()
print(json.dumps([bool(db.query('SELECT 1 FROM lead_events WHERE id = %s', (e,), one=True)), bool(db.query('SELECT 1 FROM activity WHERE id = %s', (a,), one=True))]))`));
    check('L1: a lead\'s history is kept when old activity is pruned', pruned[0] === true && pruned[1] === false, JSON.stringify(pruned));
    // 12. Phone: the dialog's answers are thumb-sized, its fields 16px.
    const phone = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, storageState: await page.context().storageState() })).newPage();
    phone.on('pageerror', (e) => errors.push(e.message));
    await phone.goto(`${BASE}/leads.html#lead=${fuId}`);
    await phone.waitForSelector('#log-call');
    await phone.click('#log-call');
    await phone.waitForSelector('dialog.fu-dialog [data-outcome]');
    const fit = await phone.evaluate(() => ({ small: [...document.querySelectorAll('dialog.fu-dialog button')].filter((b) => b.getBoundingClientRect().height < 44).map((b) => b.textContent),
      font: getComputedStyle(document.querySelector('#fu-note')).fontSize, wide: document.documentElement.scrollWidth <= innerWidth,
      bottom: Math.round(document.querySelector('dialog.fu-dialog').getBoundingClientRect().bottom) === innerHeight }));
    await phone.screenshot({ path: `${OUT}/flow-fu-phone.png` });
    check('L1 phone: the call dialog sits at the bottom, every button is 44px or more, the note is 16px', fit.small.length === 0 && fit.font === '16px' && fit.wide && fit.bottom, JSON.stringify(fit));
    await phone.context().close();
    // 320px: the row's Overdue chip is whole (no clipped text), small and amber, inside the row.
    const narrowFu = await (await browser.newContext({ viewport: { width: 320, height: 700 }, isMobile: true, hasTouch: true, storageState: await page.context().storageState() })).newPage();
    narrowFu.on('pageerror', (e) => errors.push(e.message));
    await narrowFu.goto(`${BASE}/leads.html?due=overdue`);
    const chipSel = `.lead-row[data-id="${fuId}"] .fu-chip`;
    await narrowFu.waitForSelector(chipSel);
    const chipFit = await narrowFu.$eval(chipSel, (c) => {
      const row = c.closest('.lead-row').getBoundingClientRect(), r = c.getBoundingClientRect(), cs = getComputedStyle(c);
      const kind = getComputedStyle(c.closest('.who').querySelector(':scope > span:not(.fu-chip)'));
      return { text: c.textContent, whole: c.scrollWidth <= c.clientWidth + 1 && cs.whiteSpace !== 'nowrap' && cs.overflow === 'visible', inside: r.right <= row.right + 0.5,
        notFull: r.width < row.width - 40, small: parseFloat(cs.fontSize) < parseFloat(kind.fontSize), amber: cs.color !== kind.color, page: document.documentElement.scrollWidth <= innerWidth };
    });
    check('L1 320px: the row chip shows its whole text, small and amber, inside the row', /^Overdue: Call back \(/.test(chipFit.text) && chipFit.whole && chipFit.inside
      && chipFit.notFull && chipFit.small && chipFit.amber && chipFit.page, JSON.stringify(chipFit));
    await narrowFu.context().close();
    // The booked call's box line reads 'Did the call at 9 AM happen?' today, never 'on 9 AM'.
    py(`import db;db.execute(\\"UPDATE leads SET meeting_status = 'scheduled', meeting_at = now() - interval '2 hours' WHERE id = %s\\", (${bkId},))`);
    await page.goto(`${BASE}/leads.html#lead=${bkId}`);
    await page.reload();
    await page.waitForSelector('#fu-meeting');
    const mLine = await page.textContent('#fu-meeting');
    check("L1: the box asks 'Did the call at 4 PM happen?' (never 'on' before a bare time)", /Did the call (at|on \w{3}) \d{1,2}(:\d{2})? [AP]M happen\?/.test(mLine) && !/\bon \d/.test(mLine), mLine);
    // A lead older than the history kept (180 days before migration 039) says so under History.
    py(`import db;db.execute(\\"UPDATE leads SET created_time = now() - interval '400 days' WHERE id = %s\\", (${bkId},))`);
    await page.reload();
    await page.waitForSelector('#history-gap');
    const gapText = await page.textContent('#history-gap');
    const recentGap = (await leadJson(fuId)).history_gap;
    check('L1: a lead older than the kept history says "History before <date> was not kept." and a recent one says nothing', /^History before \w{3} \d{1,2}, \d{4} was not kept\.$/.test(gapText) && recentGap === null, `${gapText} | ${recentGap}`);
    // Booked figures show only for accounts that booked a call: these QA leads go, so later checks see the account as before.
    py(`import db;db.execute(\\"DELETE FROM leads WHERE meta_lead_id IN ('qa-follow-1', 'qa-follow-2')\\")`);
  }
  // L2 Lead quality: why a lead was lost, the highest stage reached, repeats, junk, Results → Lead quality, and
  // the snapshot without people. Every check reads the server's state too, never the page alone.
  {
    const C1 = "'120252638288040312', 'Edge Bourne - Free intro call - Leads'";
    const post = (url, body, method = 'POST') => page.evaluate(async ([u, b, m]) => { const r = await fetch(u, { method: m, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }); return { code: r.status, body: await r.json() }; }, [url, body, method]);
    const leadJson = (id) => getJson(`/api/leads/${id}`);
    const hook = (id) => sh(`docker exec edgebourne-ads-backend python -c "
import json, hmac, hashlib, requests, settings_store
body = json.dumps({'entry': [{'changes': [{'field': 'leadgen', 'value': {'leadgen_id': '${id}'}}]}]}).encode()
sig = 'sha256=' + hmac.new(settings_store.get('meta_app_secret').encode(), body, hashlib.sha256).hexdigest()
requests.post('http://localhost:5000/webhooks/meta', data=body, headers={'X-Hub-Signature-256': sig, 'Content-Type': 'application/json'})"`);
    const storedRow = async (metaId) => {
      for (let i = 0; i < 40; i++) {
        const r = py(`import db, json;r=db.query(\\"SELECT id, repeat_of, earlier_lead_id, repeat_checked, junk_flags, alerted_at IS NOT NULL AS told FROM leads WHERE meta_lead_id = '${metaId}'\\", one=True);print(json.dumps(r) if r else '')`);
        if (r && JSON.parse(r).told) return JSON.parse(r);
        await page.waitForTimeout(1000);
      }
      return null;
    };
    py(`import db
db.execute(\\"DELETE FROM leads WHERE meta_lead_id LIKE 'qa-l2-%%' OR meta_lead_id LIKE '7713%%' OR full_name IN ('Repeat QA', 'Late QA')\\")`);
    const insert = (key, name, days, status, maxStage) => Number(py(`import db, json
answers = json.dumps([{'name': 'what_kind_of_business_do_you_run?', 'values': ['QA shop']}])
r = db.execute(\\"INSERT INTO leads (meta_lead_id, created_time, full_name, phone, ad_id, ad_name, campaign_id, campaign_name, status, max_stage, quality_checked, answers) VALUES ('${key}', now() - interval '${days} days', '${name}', '+16195557789', '120252672229400312', 'N2 - Order portal', ${C1}, '${status}', '${maxStage}', TRUE, %s) RETURNING id\\", (answers,), returning=True)
print(r['id'])`));
    const lqId = insert('qa-l2-1', 'QA Quality Lead', 2, 'contacted', 'contacted');
    const moved = await post(`/api/leads/${lqId}`, { status: 'qualified' }, 'PATCH');
    check('L2: a move to Qualified raises the highest stage reached', moved.code === 200 && moved.body.max_stage === 'qualified', JSON.stringify([moved.code, moved.body.max_stage]));
    const qBefore = (await getJson('/api/performance?range=7')).totals.qualified;
    await page.goto(`${BASE}/leads.html#lead=${lqId}`);
    await page.reload();
    await page.waitForSelector('#stages [data-stage="lost"]');
    // 1. Lost asks why; Cancel changes nothing.
    await page.click('#stages [data-stage="lost"]');
    await page.waitForSelector('dialog.lost-dialog .cd-choice');
    const dlg = await page.evaluate(() => ({ title: document.querySelector('dialog.lost-dialog h2').textContent, n: document.querySelectorAll('dialog.lost-dialog .cd-choice').length,
      label: document.querySelector('dialog.lost-dialog label[for="cd-input"]').textContent, ok: document.querySelector('dialog.lost-dialog #cd-ok').textContent }));
    await page.screenshot({ path: `${OUT}/flow-l2-lost-dialog.png` });
    await page.click('dialog.lost-dialog #cd-cancel');
    await page.waitForSelector('dialog.lost-dialog', { state: 'detached' });
    check('L2: Lost opens "Why was this lead lost?" with 8 reasons and a note; Cancel leaves the stage', dlg.title === 'Why was this lead lost?' && dlg.n === 8
      && dlg.label === 'Anything to add? (optional)' && dlg.ok === 'Mark as lost' && (await leadJson(lqId)).status === 'qualified', JSON.stringify(dlg));
    // 2. No reason picked: "Pick a reason", and nothing is sent.
    let patches = 0;
    const countPatch = (r) => { if (r.method() === 'PATCH' && /\/api\/leads\/\d+$/.test(r.url())) patches += 1; };
    page.on('request', countPatch);
    await page.click('#stages [data-stage="lost"]');
    await page.waitForSelector('dialog.lost-dialog .cd-choice');
    await page.click('dialog.lost-dialog #cd-ok');
    await page.waitForSelector('dialog.lost-dialog #cd-perr:not([hidden])');
    check('L2: Mark as lost without a reason says "Pick a reason" and sends nothing', (await page.textContent('#cd-perr')) === 'Pick a reason' && patches === 0, String(patches));
    // 3. Price with a note: stored, and the facts say so.
    await page.click('dialog.lost-dialog .cd-choice[data-value="price"]');
    await page.fill('dialog.lost-dialog #cd-input', 'went with a cheaper quote');
    const [lostRes] = await Promise.all([page.waitForResponse((r) => r.request().method() === 'PATCH'), page.click('dialog.lost-dialog #cd-ok')]);
    page.off('request', countPatch);
    const lostBody = await lostRes.json();
    await page.waitForSelector('#lost-why');
    const lost = await leadJson(lqId);
    check('L2: Price with a note is stored, the facts say "Lost because: Price" and "Got as far as: Qualified"', lost.status === 'lost' && lost.lost_reason === 'price'
      && lost.lost_note === 'went with a cheaper quote' && lost.max_stage === 'qualified' && /^Price — “went with a cheaper quote”/.test((await page.textContent('#lost-why')).trim())
      && /^Qualified/.test((await page.textContent('#max-stage')).trim()) && /Moved to Lost/.test(await page.textContent('.toast')), JSON.stringify([lost.status, lost.lost_reason, lost.max_stage]));
    // 4. Qualified then lost still counts as qualified.
    const qAfter = (await getJson('/api/performance?range=7')).totals.qualified;
    check('L2: a qualified lead later lost still counts in Qualified on Results', qBefore >= 1 && qAfter === qBefore, `${qBefore} → ${qAfter}`);
    // 5. Undo: the stage, the highest stage and the reason come back; a Lost stage still waiting for Meta is taken back.
    const pendingLost = () => Number(py(`import db;print(db.query(\\"SELECT COUNT(*) AS n FROM crm_events WHERE lead_id = %s AND stage = 'lost' AND status = 'pending'\\", (${lqId},), one=True)['n'])`));
    const undo = await post(`/api/leads/${lqId}/events/${lostBody.undo.event_id}/undo`, {});
    check('L2: Undo puts back Qualified, takes the reason away and leaves no Lost waiting for Meta', undo.code === 200 && undo.body.status === 'qualified'
      && undo.body.lost_reason === null && undo.body.max_stage === 'qualified' && pendingLost() === 0, JSON.stringify([undo.code, undo.body.status, undo.body.lost_reason]));
    // Change the reason later: the dialog opens on the current one.
    await post(`/api/leads/${lqId}`, { status: 'lost', lost_reason: 'no_response' }, 'PATCH');
    await page.reload();
    await page.waitForSelector('#lost-change');
    await page.click('#lost-change');
    await page.waitForSelector('dialog.lost-dialog .cd-choice[data-value="no_response"][aria-pressed="true"]');
    const changeTitle = await page.textContent('dialog.lost-dialog h2');
    await page.click('dialog.lost-dialog .cd-choice[data-value="went_elsewhere"]');
    await Promise.all([page.waitForResponse((r) => r.request().method() === 'PATCH'), page.click('dialog.lost-dialog #cd-ok')]);
    await page.waitForFunction(() => /Went with someone else/.test(document.querySelector('#lost-why')?.textContent || ''));
    const changed = await leadJson(lqId);
    check('L2: Change opens "Change why it was lost" on the current reason and saves the new one, with a history line', changeTitle === 'Change why it was lost'
      && changed.lost_reason === 'went_elsewhere' && changed.history.some((h) => h.text === 'Eugene changed why it was lost: Went with someone else'), changed.lost_reason);
    // 6. The Why filter on Lost.
    await page.goto(`${BASE}/leads.html?status=lost&why=went_elsewhere`);
    await page.waitForSelector('#why:not([hidden])');
    await page.waitForSelector(`.lead-row[data-id="${lqId}"]`);
    const why = await getJson('/api/leads?status=lost&why=went_elsewhere');
    check('L2: Leads → Lost → Why lists only that reason, and the select counts it', why.leads.length >= 1 && why.leads.every((l) => l.lost_reason === 'went_elsewhere')
      && /^Went with someone else \(\d+\)$/.test(await page.$eval('#why', (s) => s.selectedOptions[0].textContent)) && await page.isVisible('#clear-filters'), String(why.leads.length));
    // Correct how far it got (admins): back to Contacted.
    await page.goto(`${BASE}/leads.html#lead=${lqId}`);
    await page.reload();
    await page.waitForSelector('#max-correct');
    await page.click('#max-correct');
    await page.waitForSelector('dialog.lost-dialog .cd-choice[data-value="qualified"][aria-pressed="true"]');
    await page.click('dialog.lost-dialog .cd-choice[data-value="contacted"]');
    await Promise.all([page.waitForResponse((r) => r.request().method() === 'PATCH'), page.click('dialog.lost-dialog #cd-ok')]);
    await page.waitForFunction(() => /^Contacted/.test((document.querySelector('#max-stage')?.textContent || '').trim()));
    check('L2: an admin corrects how far a lead got, and History says so', (await leadJson(lqId)).max_stage === 'contacted'
      && (await leadJson(lqId)).history.some((h) => h.text === 'Eugene corrected how far it got: Qualified → Contacted'));
    // Same person by hand: the newer lead got further, so the first lead's highest stage rises to it.
    const spId = insert('qa-l2-2', 'QA Same Person', 1, 'won', 'won');
    await page.click('#same-person');
    await page.waitForSelector('dialog.family-dialog #cd-input');
    await page.fill('dialog.family-dialog #cd-input', 'QA Same Person');
    await page.waitForSelector(`dialog.family-dialog .family-row[data-id="${spId}"]`);
    await page.click(`dialog.family-dialog .family-row[data-id="${spId}"]`);
    await Promise.all([page.waitForResponse((r) => /same-person$/.test(r.url())), page.click('dialog.family-dialog #cd-ok')]);
    await page.waitForSelector('#family-list');
    const sp = await leadJson(spId), root = await leadJson(lqId);
    check('L2: Same person as… links the newer lead to the older one, whose highest stage rises to Won', sp.repeat_of === lqId && root.max_stage === 'won'
      && /Linked to QA Quality Lead's first lead/.test(await page.textContent('.toast')) && /QA|N2/.test(await page.textContent('#family-list')), JSON.stringify([sp.repeat_of, root.max_stage]));
    // 7. The same person fills the form twice: a repeat, one automatic reply, "Asked again", the Open count unchanged.
    await page.evaluate(() => fetch('/api/settings/replies', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ auto: true }) }));
    const sfx = String(Date.now()).slice(-11);
    const firstId = `7711${sfx}0`, secondId = `7711${sfx}1`;
    const mailsBefore = mailSent().length;
    hook(firstId);
    const first = await storedRow(firstId);
    const openBefore = (await getJson('/api/leads?status=open')).counts;
    hook(secondId);
    const second = await storedRow(secondId);
    await page.waitForTimeout(4000); // one more worker pass: a second reply or alert would show up here
    const openAfter = (await getJson('/api/leads?status=open')).counts;
    const mails = mailSent().slice(mailsBefore);
    const replies = mails.filter((m) => m.to.includes('repeat-qa@qa.edgebourne.com'));
    const askedAgain = mails.filter((m) => /^Asked again: Repeat QA/.test(m.subject || ''));
    check('L2: a second fill from the same person is a repeat of the first, with one automatic reply in all', Boolean(first) && Boolean(second) && second.repeat_of === first.id
      && replies.length === 1, JSON.stringify({ first, second, replies: replies.length }));
    check('L2: the team hears "Asked again", and the Open count stays the same', askedAgain.length >= 1 && askedAgain.every((m) => /asked again \(from N3 - Same work twice\)/.test(m.text))
      && JSON.stringify(openBefore) === JSON.stringify(openAfter), JSON.stringify({ subjects: askedAgain.map((m) => m.subject), openBefore, openAfter }));
    await page.goto(`${BASE}/leads.html`);
    await page.waitForSelector(`.lead-row[data-id="${first.id}"]`);
    check('L2: the first lead\'s row says "Asked 2×" and the repeat is not listed under Open', /Asked 2×/.test(await page.textContent(`.lead-row[data-id="${first.id}"]`))
      && !(await page.$(`.lead-row[data-id="${second.id}"]`)));
    // 8. The repeat's page: a note instead of the stage; Not the same person makes it a lead of its own.
    await page.goto(`${BASE}/leads.html?status=all#lead=${second.id}`);
    await page.reload();
    await page.waitForSelector('#repeat-note');
    const repeatPage = { stages: await page.$('#stages'), text: await page.textContent('#repeat-note'), open: await page.getAttribute('#repeat-open', 'href'),
      muted: await page.$eval(`.lead-row[data-id="${second.id}"]`, (r) => r.classList.contains('is-repeat') && /Repeat/.test(r.textContent)) };
    await page.screenshot({ path: `${OUT}/flow-l2-repeat.png`, fullPage: true });
    check('L2: a repeat shows "asked again" with Open the first lead instead of the stage, muted in All', !repeatPage.stages && /Repeat QA asked again on .* from N3 - Same work twice\./.test(repeatPage.text)
      && repeatPage.open === `#lead=${first.id}` && repeatPage.muted, JSON.stringify({ ...repeatPage, stages: Boolean(repeatPage.stages) }));
    const refused = await post(`/api/leads/${second.id}`, { status: 'contacted' }, 'PATCH');
    check('L2: a repeat\'s stage can\'t be moved (409)', refused.code === 409, String(refused.code));
    // Nor worked on its own: no call, next step or booked call on a lead that doesn't count; no Log a call button.
    const callRefused = await post(`/api/leads/${second.id}/calls`, { outcome: 'reached' });
    const nextRefused = await post(`/api/leads/${second.id}`, { next_step: { kind: 'call_back', preset: 'tomorrow_9' } }, 'PATCH');
    const meetRefused = await post(`/api/leads/${second.id}`, { meeting: { unscheduled: true } }, 'PATCH');
    const stillNew = await leadJson(second.id);
    check('L2: a repeat refuses Log a call, a next step and a booked call (409), stays New, and shows no Log a call', callRefused.code === 409 && nextRefused.code === 409
      && meetRefused.code === 409 && stillNew.status === 'new' && stillNew.max_stage === 'new' && !stillNew.next_step_at && !stillNew.booked_at && !(await page.$('#log-call')),
      JSON.stringify([callRefused.code, nextRefused.code, meetRefused.code, stillNew.status, stillNew.max_stage]));
    const firstLead = await leadJson(first.id);
    check('L2: the first lead\'s history says they asked again', firstLead.history.some((h) => h.text === 'They asked again: the new request is linked here'),
      JSON.stringify(firstLead.history.map((h) => h.text)));
    const fyi = (await getJson('/api/inbox?kind=leads')).items.find((i) => i.key === `lead:${second.id}`);
    check('L2: the Inbox lists "Repeat QA asked again" for your information, pointing at the first lead', Boolean(fyi) && fyi.title === 'Repeat QA asked again'
      && fyi.rule === 'lead_repeat' && fyi.level === 'info' && fyi.need === false && fyi.href === `/leads.html#lead=${first.id}`, JSON.stringify(fyi));
    await page.click('#repeat-unlink');
    await page.waitForSelector('#stages');
    const unlinked = await leadJson(second.id);
    const openUnlinked = (await getJson('/api/leads?status=open')).counts;
    check('L2: Not the same person makes it a lead of its own, never linked again, and the Open count rises by 1', unlinked.repeat_of === null && unlinked.repeat_checked === true
      && openUnlinked.new === (openAfter.new || 0) + 1 && /Unlinked: counted as a separate lead/.test(await page.textContent('.toast'))
      && await page.isVisible('#no-auto-reply'), JSON.stringify({ r: unlinked.repeat_of, c: unlinked.repeat_checked, before: openAfter.new, after: openUnlinked.new }));
    // 9. A lead that looks like junk: flagged, no automatic reply to a test address, one tap to Lost: spam or fake.
    const junkId = `7713${sfx}0`, junk2Id = `7713${sfx}1`;
    const mailsJunk = mailSent().length;
    hook(junkId);
    const junk = await storedRow(junkId);
    await page.waitForTimeout(3000);
    const junkMails = mailSent().slice(mailsJunk);
    check('L2: a junk lead is flagged, still alerts (saying so), and gets no automatic reply', junk && ['fake_phone', 'test_email', 'short_name'].every((f) => junk.junk_flags.includes(f))
      && !junkMails.some((m) => m.to.includes('test@test.com')) && junkMails.some((m) => /^New lead \(looks like junk\): a,/.test(m.subject || '')), JSON.stringify({ flags: junk && junk.junk_flags, subjects: junkMails.map((m) => m.subject) }));
    await page.goto(`${BASE}/leads.html#lead=${junk.id}`);
    await page.reload();
    await page.waitForSelector('#junk-note');
    check('L2: the junk lead\'s row and page say "Looks like junk", with the reasons', /Looks like junk/.test(await page.textContent(`.lead-row[data-id="${junk.id}"]`))
      && /This looks like junk\. The phone number looks made up/.test(await page.textContent('#junk-note')));
    await page.click('#junk-lost');
    await page.waitForFunction(() => document.querySelector('#stages [data-stage="lost"]')?.getAttribute('aria-pressed') === 'true');
    check('L2: Mark as lost: spam or fake is one tap, with Undo', (await leadJson(junk.id)).lost_reason === 'spam' && await page.isVisible('.toast .toast-act'));
    // 10. It's real: the chip goes.
    hook(junk2Id);
    const junk2 = await storedRow(junk2Id);
    await page.goto(`${BASE}/leads.html#lead=${junk2.id}`);
    await page.reload();
    await page.waitForSelector('#junk-real');
    await page.click('#junk-real');
    await page.waitForSelector('#junk-note', { state: 'detached' });
    await page.waitForFunction((id) => !/Looks like junk/.test(document.querySelector(`.lead-row[data-id="${id}"]`)?.textContent || 'Looks like junk'), junk2.id);
    check("L2: It's real takes the chip away and the lead isn't junk any more", (await leadJson(junk2.id)).junk_dismissed === true && /Marked as real/.test(await page.textContent('.toast')));
    await page.evaluate(() => fetch('/api/settings/replies', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ auto: false }) }));
    // A catch-up that stores an older fill late links the newer one to it, with no second alert.
    const late = JSON.parse(py(`import leads, db, json
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc)
def data(i, mins):
    return {'id': i, 'created_time': (now - timedelta(minutes=mins)).strftime('%Y-%m-%dT%H:%M:%S+0000'), 'ad_id': '120252672229400312', 'ad_name': 'N2 - Order portal',
            'campaign_id': '120252638288040312', 'campaign_name': 'Edge Bourne - Free intro call - Leads', 'form_id': '1132280359202136',
            'field_data': [{'name': 'full_name', 'values': ['Late QA']}, {'name': 'email', 'values': ['late-qa@qa.edgebourne.com']}]}
newer, _ = leads.store_lead(data('qa-l2-late-new', 30))
older, _ = leads.store_lead(data('qa-l2-late-old', 90))
db.execute('UPDATE leads SET alerted_at = now() WHERE id IN (%s, %s)', (newer, older))
r = db.query('SELECT repeat_of FROM leads WHERE id = %s', (newer,), one=True)
print(json.dumps({'older': older, 'newer': newer, 'newer_repeat_of': r['repeat_of']}))`));
    check('L2: an older fill stored late becomes the first lead, and the newer one folds into it', late.newer_repeat_of === late.older, JSON.stringify(late));
    // A won client asks again: a returning lead of its own, pointing at the earlier one ("Already a client").
    const lqData = (i, mins, name, email) => `{'id': '${i}', 'created_time': (now - timedelta(minutes=${mins})).strftime('%Y-%m-%dT%H:%M:%S+0000'), 'ad_id': '120252672229400312', 'ad_name': 'N2 - Order portal',
            'campaign_id': '120252638288040312', 'campaign_name': 'Edge Bourne - Free intro call - Leads', 'form_id': '1132280359202136',
            'field_data': [{'name': 'full_name', 'values': ['${name}']}, {'name': 'email', 'values': ['${email}']}]}`;
    const back = JSON.parse(py(`import leads, db, json
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc)
old, _ = leads.store_lead(${lqData('qa-l2-back-old', 600, 'Back QA', 'back-qa@qa.edgebourne.com')})
db.execute(\\"UPDATE leads SET status = 'won', max_stage = 'won', status_changed_at = now() - interval '5 hours' WHERE id = %s\\", (old,))
new, _ = leads.store_lead(${lqData('qa-l2-back-new', 20, 'Back QA', 'back-qa@qa.edgebourne.com')})
db.execute('UPDATE leads SET alerted_at = now() WHERE id IN (%s, %s)', (old, new))
r = db.query('SELECT repeat_of, earlier_lead_id FROM leads WHERE id = %s', (new,), one=True)
print(json.dumps({'old': old, 'new': new, 'repeat_of': r['repeat_of'], 'earlier': r['earlier_lead_id']}))`));
    await page.goto(`${BASE}/leads.html#lead=${back.new}`);
    await page.reload();
    await page.waitForSelector('#repeat-before');
    check('L2: a client who asks again is a lead of its own that says "Already a client", with the "Asked before" chip', back.repeat_of === null && back.earlier === back.old
      && /Already a client: Won on/.test(await page.textContent('#repeat-before')) && (await page.getAttribute('#repeat-before a', 'href')) === `#lead=${back.old}`
      && /Asked before/.test(await page.textContent(`.lead-row[data-id="${back.new}"]`)) && Boolean(await page.$('#stages')), JSON.stringify(back));
    // Settings → Lead quality: Spot repeats off links nothing new (links already made stay); on again links again.
    const saveLq = async (on) => {
      await page.goto(`${BASE}/settings.html#lead-quality`);
      await page.waitForSelector('#lq-form #lq-repeats');
      await page.setChecked('#lq-repeats', on);
      await Promise.all([page.waitForResponse((r) => /\/api\/settings\/lead-quality$/.test(r.url()) && r.request().method() === 'PUT'), page.click('#lq-form button[type=submit]')]);
      await page.waitForFunction((want) => document.getElementById('lq-repeats').checked === want, on);
    };
    await saveLq(false);
    const offHint = await page.isVisible('#lq-repeats-off');
    const off = JSON.parse(py(`import leads, db, json
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc)
a, _ = leads.store_lead(${lqData('qa-l2-off-1', 50, 'Off QA', 'off-qa@qa.edgebourne.com')})
b, _ = leads.store_lead(${lqData('qa-l2-off-2', 40, 'Off QA', 'off-qa@qa.edgebourne.com')})
db.execute('UPDATE leads SET alerted_at = now() WHERE id IN (%s, %s)', (a, b))
print(json.dumps({'repeat_of': db.query('SELECT repeat_of FROM leads WHERE id = %s', (b,), one=True)['repeat_of'],
                  'kept': db.query('SELECT repeat_of FROM leads WHERE id = %s', (${late.newer},), one=True)['repeat_of']}))`));
    await saveLq(true);
    const on = JSON.parse(py(`import leads, db, json
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc)
c, _ = leads.store_lead(${lqData('qa-l2-off-3', 30, 'Off QA', 'off-qa@qa.edgebourne.com')})
db.execute('UPDATE leads SET alerted_at = now() WHERE id = %s', (c,))
print(json.dumps({'repeat_of': db.query('SELECT repeat_of FROM leads WHERE id = %s', (c,), one=True)['repeat_of']}))`));
    check('L2: Settings → Spot repeats off links no new fill, keeps links already made; on again links the next one', off.repeat_of === null && off.kept === late.older
      && offHint && on.repeat_of !== null && (await getJson('/api/settings')).lead_quality.repeats === true, JSON.stringify({ off, on, offHint }));
    // Lost with no reason: the Lost view nudges, and the report's Lost line counts it.
    const rep = await getJson('/api/reports?kind=week');
    const noWhy = Number(py(`import db, account_info
r = db.execute(\\"INSERT INTO leads (meta_lead_id, created_time, full_name, ad_id, ad_name, campaign_id, campaign_name, status, max_stage, quality_checked) VALUES ('qa-l2-nowhy', (%s::date + time '12:00') AT TIME ZONE %s, 'QA No Reason', '120252672229400312', 'N2 - Order portal', ${C1}, 'lost', 'contacted', TRUE) RETURNING id\\", ('${rep.start}', account_info.tz_name()), returning=True)
print(r['id'])`));
    await page.goto(`${BASE}/leads.html?status=lost`);
    await page.waitForSelector('#why-note:not([hidden])');
    const whyNote = await page.textContent('#why-note');
    await page.goto(`${BASE}/report.html?kind=week&start=${rep.start}`);
    await page.waitForSelector('#r-lost');
    const lostText = await page.textContent('#r-lost');
    const repAfter = await getJson(`/api/reports?kind=week&start=${rep.start}`);
    check('L2: Lost says how many lost leads have no reason yet, and the report has a "Lost:" line counting them', /\d+ lost leads? (has|have) no reason yet\. Open one and tap Change to add it\./.test(whyNote)
      && /^Lost: \d+/.test(lostText.trim()) && /no reason given/.test(lostText) && lostText.trim() === repAfter.lost_line && noWhy > 0, JSON.stringify({ whyNote, lostText, line: repAfter.lost_line }));
    // 11. Results → Lead quality: by ad, form and answer; cards on a phone.
    await page.goto(`${BASE}/performance.html?range=7`);
    await page.waitForSelector('#quality-body .quality-verdict');
    const byAd = await page.textContent('#quality-panel');
    await page.click('#quality-by [data-qby="form"]');
    await page.waitForFunction(() => document.querySelector('#quality-body thead th')?.textContent === 'Form' && /lq_by=form/.test(location.search));
    await page.click('#quality-by [data-qby="answer"]');
    await page.waitForSelector('#quality-question:not([hidden])');
    await page.waitForFunction(() => /lq_by=answer/.test(location.search) && /lq_q=/.test(location.search));
    const q = await getJson('/api/performance/quality?range=7&by=ad');
    check('L2: Results → Lead quality shows By ad, By form and By answer, kept in the address', /Lead quality/.test(byAd) && /What happened to the leads from each ad, same period/.test(byAd)
      && q.rows.length >= 1 && q.rows.every((r) => r.leads >= 0 && r.fills >= r.leads) && typeof q.junk_note === 'string', JSON.stringify(q.totals));
    await page.screenshot({ path: `${OUT}/flow-l2-results.png`, fullPage: true });
    const lqPhone = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, storageState: await page.context().storageState() })).newPage();
    lqPhone.on('pageerror', (e) => errors.push(e.message));
    await lqPhone.goto(`${BASE}/performance.html?range=7`);
    await lqPhone.waitForSelector('#quality-body .quality-verdict');
    await lqPhone.$eval('#quality-panel', (el) => el.scrollIntoView());
    const fitQ = await lqPhone.evaluate(() => ({ wide: document.documentElement.scrollWidth <= innerWidth, small: [...document.querySelectorAll('#quality-by button')].filter((b) => b.getBoundingClientRect().height < 44).length,
      cards: getComputedStyle(document.querySelector('#quality-cards') || document.body).display, table: document.querySelector('.quality-wide') ? getComputedStyle(document.querySelector('.quality-wide')).display : 'none' }));
    await lqPhone.screenshot({ path: `${OUT}/flow-l2-results-phone.png` });
    check('L2 phone: Lead quality is cards, no sideways scroll, 44px By buttons', fitQ.wide && fitQ.small === 0 && (fitQ.cards === 'grid' || !q.rows.length) && fitQ.table === 'none', JSON.stringify(fitQ));
    // The Lost dialog on a phone: at the bottom, the reasons thumb-sized, the note 16px.
    await lqPhone.goto(`${BASE}/leads.html#lead=${lqId}`);
    await lqPhone.waitForSelector('#lost-change');
    await lqPhone.click('#lost-change');
    await lqPhone.waitForSelector('dialog.lost-dialog .cd-choice');
    const fitL = await lqPhone.evaluate(() => ({ small: [...document.querySelectorAll('dialog.lost-dialog button')].filter((b) => b.getBoundingClientRect().height < 44).map((b) => b.textContent),
      font: getComputedStyle(document.querySelector('dialog.lost-dialog #cd-input')).fontSize, wide: document.documentElement.scrollWidth <= innerWidth,
      okInView: document.querySelector('dialog.lost-dialog #cd-ok').getBoundingClientRect().bottom <= innerHeight }));
    await lqPhone.screenshot({ path: `${OUT}/flow-l2-lost-phone.png` });
    check('L2 phone: the Lost dialog has 44px reasons, a 16px note and its buttons in view', fitL.small.length === 0 && fitL.font === '16px' && fitL.wide && fitL.okInView, JSON.stringify(fitL));
    await lqPhone.context().close();
    // 12–13. A client sees Lead quality but can't link or correct; a teammate can't correct.
    py(`import db
from werkzeug.security import generate_password_hash as h
for email, role in (('qa-l2-client@example.com', 'client'), ('qa-l2-mate@example.com', 'member')):
    db.execute(\\"INSERT INTO users (email, name, password_hash, role, account_id) VALUES (%s, %s, %s, %s, 1) ON CONFLICT (email) DO UPDATE SET is_active = TRUE, password_hash = EXCLUDED.password_hash, role = EXCLUDED.role, account_id = 1, must_change_password = FALSE\\", (email, 'QA L2 ' + role, h('l2-pass-12345'), role))
db.execute(\\"INSERT INTO campaign_members (campaign_id, user_id, account_id) SELECT '120252638288040312', id, 1 FROM users WHERE email = 'qa-l2-mate@example.com' ON CONFLICT DO NOTHING\\")`);
    // A repeat the teammate can see whose first lead sits in a campaign they can't see.
    const hidden = JSON.parse(py(`import db, json
root = db.execute(\\"INSERT INTO leads (meta_lead_id, created_time, full_name, campaign_id, campaign_name, ad_id, status, quality_checked) VALUES ('qa-l2-hidden-root', now() - interval '12 hours', 'QA Hidden Root', 'qa-l2-hidden-camp', 'QA hidden', 'qa-l2-hidden-ad', 'new', TRUE) RETURNING id\\", returning=True)['id']
rep = db.execute(\\"INSERT INTO leads (meta_lead_id, created_time, full_name, campaign_id, campaign_name, ad_id, ad_name, status, repeat_of, earlier_lead_id, repeat_source, quality_checked) VALUES ('qa-l2-hidden-rep', now() - interval '1 hour', 'QA Hidden Root', ${C1}, '120252672229400312', 'N2 - Order portal', 'new', %s, %s, 'auto', TRUE) RETURNING id\\", (root, root), returning=True)['id']
print(json.dumps({'root': root, 'rep': rep}))`));
    for (const [email, who] of [['qa-l2-client@example.com', 'client'], ['qa-l2-mate@example.com', 'mate']]) {
      const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
      const p = await ctx.newPage();
      p.on('pageerror', (e) => errors.push(e.message));
      await p.goto(BASE + '/login.html');
      await p.fill('#email', email); await p.fill('#password', 'l2-pass-12345');
      await Promise.all([p.waitForURL('**/home.html**'), p.click('button[type=submit]')]);
      const res = await p.evaluate(async ([id, other, h]) => {
        const send = (u, m, b) => fetch(u, { method: m, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }).then((r) => r.status);
        return { link: await send(`/api/leads/${id}/same-person`, 'POST', { other_id: other }), correct: await send(`/api/leads/${id}`, 'PATCH', { max_stage: 'new' }),
          quality: (await fetch('/api/performance/quality?range=7')).status, canCorrect: (await (await fetch(`/api/leads/${id}`)).json()).can_correct,
          seesRep: (await fetch(`/api/leads/${h.rep}`)).status, hiddenLink: await send(`/api/leads/${h.rep}/same-person`, 'POST', { other_id: id }) };
      }, [lqId, who === 'client' ? first.id : lqId, hidden]);
      if (who === 'client') {
        await p.goto(`${BASE}/performance.html?range=7`);
        await p.waitForSelector('#quality-body .quality-verdict');
        await p.goto(`${BASE}/leads.html#lead=${lqId}`);
        await p.waitForSelector('#detail h2');
        check('L2: a client reads Lead quality but can\'t link leads or correct a stage', res.quality === 200 && res.link === 403 && res.correct === 403 && res.canCorrect === false
          && !(await p.$('#max-correct')) && !(await p.isVisible('#same-person').catch(() => false)), JSON.stringify(res));
      } else {
        check('L2: a teammate can\'t correct how far a lead got (403), and linking a lead to itself is refused (400)', res.correct === 403 && res.canCorrect === false
          && res.quality === 200 && res.link === 400, JSON.stringify(res));
        const rootAfter = JSON.parse(py(`import db, json;print(json.dumps(db.query('SELECT repeat_of FROM leads WHERE id = %s', (${hidden.root},), one=True)))`));
        check('L2: a teammate can\'t link through a first lead in a campaign they don\'t see (404), and that lead is left alone', res.seesRep === 200 && res.hiddenLink === 404
          && rootAfter.repeat_of === null, JSON.stringify({ seesRep: res.seesRep, hiddenLink: res.hiddenLink, rootAfter }));
      }
      await ctx.close();
    }
    py(`import db
db.execute(\\"UPDATE users SET is_active = FALSE WHERE email IN ('qa-l2-client@example.com', 'qa-l2-mate@example.com')\\")
db.execute(\\"DELETE FROM campaign_members WHERE user_id = (SELECT id FROM users WHERE email = 'qa-l2-mate@example.com')\\")`);
    // 14. Claude's snapshot: lead quality per ad, never a person's name, email, phone or note.
    const snap = JSON.parse(py(`import json, account_ctx, desk_api
from app import create_app
app = create_app(run_migrations=False)
with app.test_request_context('/api/agent/snapshot?range=30'), account_ctx.use(1):
    body = desk_api.snapshot.__wrapped__().get_data(as_text=True)
d = json.loads(body)
print(json.dumps({'by_ad': 'lead_quality_by_ad' in d, 'totals': d.get('lead_quality_totals'), 'pii': [w for w in ('QA Quality Lead', 'Repeat QA', 'repeat-qa@qa', '5557701', '1234567890', 'test@test.com', 'went with a cheaper quote') if w in body]}))`));
    check('L2: the snapshot carries lead quality per ad and no names, emails, phones, answers or notes', snap.by_ad && snap.totals && snap.pii.length === 0, JSON.stringify(snap));
    py(`import db
db.execute(\\"DELETE FROM leads WHERE meta_lead_id LIKE 'qa-l2-%%' OR meta_lead_id LIKE '7713%%' OR full_name IN ('Repeat QA', 'Late QA')\\")`);
  }
  await page.goto(BASE + '/desk.html#list');
  await page.waitForSelector('#cv[data-state]');
  await page.waitForTimeout(400);
  check('the Claude list link shows a conversation on desktop', (await page.getAttribute('#cv', 'data-state')) !== 'none');
  await page.goto(BASE + '/team.html');
  await page.waitForSelector('#team-table tbody tr');
  {
    // Team's temporary password is the one notice dialog: shown once, one Done button, focused.
    const QA_MATE = 'qa-teammate@example.com';
    const mate = (await getJson('/api/team')).members.find((m) => m.email === QA_MATE);
    let pwResponse;
    if (mate) {
      await page.click(`[data-reset="${mate.id}"]`);
      await page.waitForSelector('dialog.confirm[open]');
      [pwResponse] = await Promise.all([page.waitForResponse((r) => r.request().method() === 'PATCH' && /api\/team\//.test(r.url())), page.click('dialog.confirm[open] #cd-ok')]);
    } else {
      await page.click('#add-btn');
      await page.fill('#m-name', 'QA Teammate');
      await page.fill('#m-email', QA_MATE);
      [pwResponse] = await Promise.all([page.waitForResponse((r) => r.request().method() === 'POST' && /api\/team$/.test(r.url())), page.click('#m-save')]);
    }
    const temp = (await pwResponse.json()).temporary_password;
    await page.waitForSelector('dialog.confirm[open] #pw-value');
    const pwNotice = await page.evaluate(() => ({ pw: document.querySelector('dialog.confirm[open] #pw-value').textContent, cancel: !!document.querySelector('dialog.confirm[open] #cd-cancel'), focus: document.activeElement.id }));
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: BASE });
    await page.click('dialog.confirm[open] #pw-copy');
    await page.waitForFunction(() => document.querySelector('dialog.confirm[open] #pw-copy')?.textContent === 'Copied');
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    check("Copy beside the teammate's temporary password puts exactly that password on the clipboard, and says so", copied === temp
      && /Password copied/.test(await page.textContent('dialog.confirm[open]')), copied === temp ? 'same' : 'differs');
    await page.click('dialog.confirm[open] #cd-ok');
    await page.waitForSelector('dialog.confirm[open]', { state: 'detached' }).catch(() => {});
    check("Team shows a teammate's temporary password once, in the one notice dialog with a single Done button",
      Boolean(temp) && pwNotice.pw === temp && !pwNotice.cancel && pwNotice.focus === 'cd-ok', JSON.stringify({ ...pwNotice, pw: pwNotice.pw === temp ? 'matches' : 'differs' }));
    const added = (await getJson('/api/team')).members.find((m) => m.email === QA_MATE);
    if (added && added.is_active) await page.evaluate(async (id) => { await fetch(`/api/team/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ is_active: false }) }); }, added.id);
    await page.reload();
    await page.waitForSelector('#team-table tbody tr');
    // 9.3a: a teammate's campaigns link to their pages (assigned for this check, then taken off again).
    const mateNow = (await getJson('/api/team')).members.find((m) => m.email === QA_MATE);
    if (mateNow) {
      const setCamps = (ids) => page.evaluate(async ([id, c]) => (await fetch(`/api/team/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ campaign_ids: c }) })).status, [mateNow.id, ids]);
      await setCamps(['120252638288040312']);
      await page.reload();
      await page.waitForSelector('#team-table tbody tr');
      const teamLinks = await page.$$eval('#team-table a.ent-link', (as) => as.map((a) => a.getAttribute('href')));
      await setCamps([]);
      check("Team links each teammate's campaign to its page", teamLinks.includes('/campaign.html?id=120252638288040312'), teamLinks.join());
      await page.reload();
      await page.waitForSelector('#team-table tbody tr');
    }
  }
  {
    // A teammate sees suggestions about their campaigns in the Inbox, with Review and accept but no link to the Claude page (admins only).
    const mateProp = py(`
from werkzeug.security import generate_password_hash
import db, account_ctx
with account_ctx.all_accounts():
    u = db.query(\\"SELECT id FROM users WHERE email = 'qa-teammate@example.com'\\", one=True)['id']
    db.execute(\\"UPDATE users SET is_active = TRUE, must_change_password = FALSE, password_hash = %s WHERE id = %s\\", (generate_password_hash('mate-pass-123'), u))
    db.execute(\\"INSERT INTO campaign_members (campaign_id, user_id, account_id) VALUES ('120252638288040312', %s, 1) ON CONFLICT DO NOTHING\\", (u,))
    r = db.execute(\\"INSERT INTO desk_proposals (task_id, kind, title, status, entity_type, entity_id, entity_name, account_id) SELECT id, 'other', 'QA teammate suggestion', 'pending', 'campaign', '120252638288040312', 'Edge Bourne campaign', 1 FROM desk_tasks WHERE account_id = 1 ORDER BY id DESC LIMIT 1 RETURNING id\\", returning=True)
    print(r['id'])`);
    const mctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
    const mp = await mctx.newPage();
    mp.on('pageerror', (e) => errors.push('teammate page: ' + e.message));
    await mp.goto(BASE + '/login.html');
    await mp.fill('#email', 'qa-teammate@example.com'); await mp.fill('#password', 'mate-pass-123');
    await Promise.all([mp.waitForURL('**/home.html**'), mp.click('button[type=submit]')]);
    await mp.goto(BASE + `/inbox.html?box=need&kind=claude#item=proposal%3A${mateProp}`);
    await mp.waitForSelector('#ib-detail [data-accept]');
    check("a teammate's suggestion in the Inbox offers Review and accept and no link to the Claude page", /Review and accept/.test(await mp.textContent('#ib-detail [data-accept]'))
      && (await mp.locator('#ib-detail a[href^="/desk.html"]').count()) === 0, mateProp);
    await mp.goto(BASE + '/ads.html');
    await mp.waitForSelector('#cr-all .cr-toolbar');
    check('a teammate gets one primary New ad and no New menu', await mp.isVisible('#new-ad') && await mp.isHidden('#new-menu')
      && /btn-primary/.test(await mp.getAttribute('#new-ad', 'class')) && (await mp.locator('.page-head .btn-primary:visible').count()) === 1);
    // The Gallery shows a teammate only the ads of the campaigns they're on; no Research tab, but New ad.
    await mp.goto(BASE + '/gallery.html?range=30');
    await mp.waitForSelector('.gal-card, #gal .empty');
    const mateCamps = await mp.evaluate(async () => { const out = []; for (const st of ['', 'deleted']) { const d = await (await fetch(`/api/gallery?range=30&status=${st}`)).json(); for (const g of d.groups) for (const a of g.ads) out.push(a.campaign_id); } return out; });
    const allCamps = new Set((await getJson('/api/gallery?range=30&status=deleted')).groups.concat((await getJson('/api/gallery?range=30')).groups).flatMap((g) => g.ads.map((a) => a.campaign_id)));
    check("a teammate's Gallery holds only their campaigns' ads, with New ad and no Research tab",
      mateCamps.length > 0 && mateCamps.every((c) => c === '120252638288040312') && allCamps.size > 1 && await mp.isVisible('#gal-new')
      && (await mp.locator('.subnav a[href="/research.html"]').count()) === 0, `${new Set(mateCamps).size} of ${allCamps.size} campaigns`);
    // L1: a call on a lead from a campaign they're not on is not found (404), and nothing is logged.
    const otherLead = Number(py(`import db
db.execute(\\"DELETE FROM leads WHERE meta_lead_id = 'qa-mate-other'\\")
print(db.execute(\\"INSERT INTO leads (meta_lead_id, created_time, full_name, phone, campaign_id, campaign_name) VALUES ('qa-mate-other', now(), 'QA Other Campaign Lead', '+16195550199', 'qa-other-campaign', 'QA other campaign') RETURNING id\\", returning=True)['id'])`));
    const mateCall = await mp.evaluate(async (id) => (await fetch(`/api/leads/${id}/calls`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'ebads' }, body: JSON.stringify({ outcome: 'no_answer' }) })).status, otherLead);
    const otherCalls = py(`import db;print(db.query(\\"SELECT call_attempts FROM leads WHERE id = %s\\", (${otherLead},), one=True)['call_attempts'])`);
    check("a teammate can't log a call on a lead from a campaign they're not on (404, nothing logged)", mateCall === 404 && otherCalls === '0', `${mateCall} ${otherCalls}`);
    py(`import db;db.execute(\\"DELETE FROM leads WHERE meta_lead_id = 'qa-mate-other'\\")`);
    await mctx.close();
    py(`
import db, account_ctx
with account_ctx.all_accounts():
    db.execute(\\"UPDATE desk_proposals SET status = 'declined' WHERE id = %s\\", (${mateProp},))
    db.execute(\\"DELETE FROM campaign_members WHERE user_id = (SELECT id FROM users WHERE email = 'qa-teammate@example.com')\\")
    db.execute(\\"UPDATE users SET is_active = FALSE WHERE email = 'qa-teammate@example.com'\\")`);
  }
  await page.evaluate(() => { const b = document.createElement('button'); b.id = 'qa-danger'; b.className = 'btn btn-danger'; b.textContent = 'Delete'; document.querySelector('.content').prepend(b); });
  await page.hover('#qa-danger');
  const dangerHover = await page.$eval('#qa-danger', (b) => { const c = getComputedStyle(b); return [c.color, c.backgroundColor]; });
  check('a danger button stays readable on hover', dangerHover[0] === 'rgb(255, 255, 255)' && dangerHover[1] !== 'rgb(238, 238, 235)', dangerHover.join(' on '));
  await page.goto(BASE + '/new-campaign.html');
  await page.waitForSelector('#c-budget');
  await page.fill('#c-budget', '17');
  await Promise.all([page.waitForResponse((r) => r.request().method() === 'POST' && /api\/refresh/.test(r.url())), page.click('.topline [data-refresh]')]);
  await page.waitForTimeout(700);
  check('Refresh on a half-filled form keeps what was typed', (await page.inputValue('#c-budget')) === '17');
  check('unfinished builds can be listed', await page.evaluate(async () => (await fetch('/api/builds/open')).ok));
  await page.route('**/api/home', (r) => r.abort());
  await page.goto(BASE + '/home.html', { waitUntil: 'load' });
  await page.waitForSelector('#home [data-retry]');
  check('a page that fails to load says so and offers Try again', /didn't load/i.test(await page.textContent('#home')));
  await page.unroute('**/api/home');
  await page.click('#home [data-retry]');
  await page.waitForSelector('.tq-group, .tq-clear');
  check('Try again loads the page', !/didn't load/i.test(await page.textContent('#home')) && (await page.locator('#home [data-retry]').count()) === 0);
  // L1: with nothing to do, Today says no follow-ups are due and how they get there.
  const homeBody = await getJson('/api/home');  // read in the page: Node can't resolve ads.localhost for route.fetch
  await page.route('**/api/home', (route) => route.fulfill({ json: { ...homeBody, queue: [], waiting_calls: 0, snoozed: 0, follow: { ...(homeBody.follow || {}), no_next: 0 } } }));
  await page.reload();
  await page.waitForSelector('.tq-clear');
  check('L1: an empty Today says "No follow-ups due" with how a follow-up gets there', (await page.textContent('#fu-none-due')) === 'No follow-ups due. Set a next step after each call and it shows up here on the day.');
  await page.unroute('**/api/home');
  // Today's minute timer and the frame's catch-up with Meta fire on the same tick: one /api/home, not two.
  const clockCtx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
  await clockCtx.addCookies(await page.context().cookies());
  const clockPage = await clockCtx.newPage();
  clockPage.on('pageerror', (e) => errors.push(e.message));
  await clockPage.clock.install();
  const pulledAt = Math.floor(Date.now() / 1000) - 600;
  let pulledAgain = false;
  const status = await getJson('/api/refresh');
  // The newer pull answers 1.5 s late, as a real /api/refresh can: Today's own timer fires before it does.
  await clockPage.route('**/api/refresh', async (route) => {
    if (route.request().method() !== 'GET') return route.continue();
    if (pulledAgain) await new Promise((r) => setTimeout(r, 1500));
    return route.fulfill({ json: { ...status, updated_at: pulledAgain ? pulledAt + 300 : pulledAt } });
  });
  await Promise.all([clockPage.waitForResponse((r) => /\/api\/refresh$/.test(r.url())), clockPage.goto(BASE + '/home.html')]);
  await clockPage.waitForSelector('.tq-group, .tq-clear');
  let homeLoads = 0;
  clockPage.on('request', (r) => { if (/\/api\/home$/.test(r.url())) homeLoads += 1; });
  pulledAgain = true;
  await clockPage.clock.runFor(61000);
  await clockPage.waitForTimeout(4000);
  check('Today loads once when its minute timer and a catch-up with Meta land together', homeLoads === 1, `${homeLoads} loads of /api/home`);
  await clockCtx.close();
  errors.splice(seen91, errors.length - seen91, ...errors.slice(seen91).filter((e) => !/ERR_FAILED/.test(e)));
  {
  // 9.2 Design system: token contrast in both themes, no retired token names, and keyboard / screen reader basics.
  await page.goto(BASE + '/home.html');
  await page.waitForSelector('.rail .nav a');
  const lowContrast = await guards.tokenContrast(page);
  check('every text colour token pair reads at 4.5:1 (marks 3:1) in light and dark', lowContrast.length === 0, lowContrast.join(' | '));
  const retired = await guards.retiredTokens(page);
  check('no stylesheet uses a retired token (--seal, --rust, --pine, --fog, --lift)', retired.length === 0, retired.join(' | '));
  // 9.2 part 2: one component of each kind and one vocabulary on every main screen.
  const drift = [], leaks = [];
  for (const p of guards.VOCAB_PAGES) {
    await page.goto(BASE + p);
    if (p.includes('#')) await page.reload();
    await page.waitForTimeout(1300);
    drift.push(...(await guards.componentDrift(page)).map((x) => `${p}: ${x}`));
    leaks.push(...(await guards.vocabularyLeaks(page)).map((x) => `${p}: ${x}`));
  }
  check('one Tabs, Filter, Status, Table, Empty state, Skeleton, Suggestion card and Dialog: no retired builds, each styled once', drift.length === 0, [...new Set(drift)].slice(0, 8).join(' | '));
  check('one vocabulary on every screen (Views, Cost per lead, Hook rate, Suggestion, Accept, Conversation)', leaks.length === 0, [...new Set(leaks)].slice(0, 8).join(' | '));
  const rangeWords = async (url, sel) => { await page.goto(BASE + url); await page.waitForSelector(sel); return page.$$eval(`${sel} option`, (o) => o.map((x) => `${x.value}:${x.textContent}`).join(',')); };
  const ranges = [await rangeWords('/ads.html', '#range-pick'), await rangeWords('/performance.html', '#range-pick'),
    await rangeWords('/campaign.html?id=120252638288040312', '#range-pick'), await rangeWords('/compare.html?ids=120252672232030312,120252672233160312', '#cmp-range')];
  check('one date range picker: Ads, Results, Campaign and Compare offer the same periods in the same words', new Set(ranges).size === 1 && /mtd:This month/.test(ranges[0]) && /^7:Last 7 days/.test(ranges[0]), ranges.join(' / '));
  const chipsOk = async (url, sel) => { await page.goto(BASE + url); await page.waitForSelector(`${sel} button`); return page.$$eval(`${sel} button`, (bs) => bs.length > 1 && bs.every((b) => b.classList.contains('view-chip'))); };
  check('list filters are the one Filter chip (Leads, Tests, Research, Results)', await chipsOk('/leads.html', '#filters') && await chipsOk('/experiments.html', '#show')
    && await chipsOk('/research.html', '#swipe-filter') && await chipsOk('/performance.html', '#cr-filter'));
  await page.goto(BASE + '/new-adset.html?campaign=120252638288040312');
  await page.waitForFunction(() => document.querySelector('[data-explain="advantage_audience"]')?.textContent);
  const advWords = await page.textContent('[data-explain="advantage_audience"]');
  const placeWords = await page.textContent('[data-explain="advantage_placements"]');
  await page.goto(BASE + '/research.html');
  await page.waitForFunction(() => document.querySelector('[data-explain="swipe_file"]')?.textContent);
  const swipeWords = await page.textContent('[data-explain="swipe_file"]');
  check('Advantage+ and the swipe file are explained in plain words, from the one vocabulary', /Advantage\+ audience lets Meta/.test(advWords) && /wherever it costs least/.test(placeWords) && /competitor ads you saved/i.test(swipeWords), `${advWords} | ${placeWords} | ${swipeWords}`);
  await page.goto(BASE + '/adset.html?id=120252672227950312');
  await page.waitForSelector('#cr-all .tabs [role="tab"]');
  check('the ad set page switches its lists with the one Tabs component', (await page.locator('#cr-all .tabs [role="tab"][aria-selected="true"]').count()) === 1 && (await page.locator('#cr-all .view-chip[role="tab"]').count()) === 0);
  await page.route(/\/api\/ads\?/, async (r) => { await new Promise((ok) => setTimeout(ok, 1500)); await r.continue(); });
  await page.goto(BASE + '/ads.html');
  const skelShown = await page.locator('#cr-all .skeleton[role="status"]').isVisible();
  await page.unroute(/\/api\/ads\?/);
  await page.waitForSelector('#cr-all .cr-toolbar');
  check('a page waiting for data shows the one loading skeleton, then the data', skelShown && (await page.locator('#cr-all .skeleton').count()) === 0);
  await page.evaluate(async () => { const m = await import('/js/ui.js'); m.confirmDialog({ title: 'QA notice', confirm: 'Done', cancel: false }); });
  await page.waitForSelector('dialog.confirm[open]');
  const notice = await page.evaluate(() => ({ cancel: !!document.querySelector('dialog.confirm #cd-cancel'), focus: document.activeElement.id }));
  await page.click('dialog.confirm #cd-ok');
  check('a notice is the one dialog with a single button, focused (Team uses it for a temporary password)', !notice.cancel && notice.focus === 'cd-ok', JSON.stringify(notice));
  const accepted = await page.evaluate(async () => { const r = await fetch('/api/proposals/999999999/approve', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); return (await r.json()).error; });
  check('the server speaks the same words: a missing suggestion is "Suggestion not found"', accepted === 'Suggestion not found', accepted);
  await page.keyboard.press('Tab');
  const firstStop = await page.evaluate(() => document.activeElement.className);
  const hashBefore = await page.evaluate(() => location.hash);
  await page.keyboard.press('Enter');
  const skipped = await page.evaluate(() => ({ id: document.activeElement.id, hash: location.hash }));
  check('the first Tab reaches "Skip to the page", which moves focus to the page without touching the hash', firstStop === 'skip-link' && skipped.id === 'main' && skipped.hash === hashBefore, `${firstStop} → ${JSON.stringify(skipped)}`);
  // Real tablists: arrow keys move and open, one tab in the Tab order, the panel names its tab.
  await page.goto(BASE + '/ad.html?id=120252672229400312');
  await page.waitForSelector('#cr-tabs [role="tab"][aria-selected="true"]');
  await page.waitForSelector('#preview-frame');
  await page.waitForTimeout(800);  // the tabs are drawn again once the ad's data is in
  await page.focus('#cr-tabs [data-tab="overview"]');
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction(() => /tab=polish/.test(location.hash));
  const tabState = await page.evaluate(() => {
    const tabs = [...document.querySelectorAll('#cr-tabs [role="tab"]')];
    const sel = tabs.find((t) => t.getAttribute('aria-selected') === 'true');
    const panel = document.getElementById('cr-main');
    return { focused: document.activeElement.dataset.tab, selected: sel && sel.dataset.tab, inOrder: tabs.filter((t) => t.tabIndex === 0).length,
      panel: panel.getAttribute('role') === 'tabpanel' && panel.getAttribute('aria-labelledby') === sel.id && sel.getAttribute('aria-controls') === 'cr-main' };
  });
  check('ad page tabs: → moves to the next tab and opens it, only that tab is in the Tab order, its panel names it', tabState.focused === 'polish' && tabState.selected === 'polish' && tabState.inOrder === 1 && tabState.panel, JSON.stringify(tabState));
  await page.keyboard.press('End');
  await page.waitForFunction(() => /tab=history/.test(location.hash));
  check('End jumps to the last tab', (await page.evaluate(() => document.activeElement.dataset.tab)) === 'history');
  // Inbox draws its box tabs again after each switch: focus follows to the new copy.
  await page.goto(BASE + '/inbox.html');
  await page.waitForSelector('#ib-box [role="tab"]');
  await page.waitForTimeout(800);
  const ibFrom = await page.getAttribute('#ib-box [role="tab"][aria-selected="true"]', 'data-box');
  await page.focus('#ib-box [role="tab"][aria-selected="true"]');
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction((f) => document.querySelector('#ib-box [aria-selected="true"]')?.dataset.box !== f, ibFrom);
  await page.waitForTimeout(600);
  const ib = await page.evaluate(() => ({ focus: document.activeElement.dataset.box, sel: document.querySelector('#ib-box [aria-selected="true"]').dataset.box,
    panel: document.getElementById('ib-panel').getAttribute('aria-labelledby') === document.querySelector('#ib-box [aria-selected="true"]').id }));
  check('Inbox boxes (Needs action, For your information, All) work as tabs: → switches, focus stays on the chosen tab after the list redraws, the list names it', ib.focus === ib.sel && ib.sel !== ibFrom && ib.panel, `${ibFrom} → ${JSON.stringify(ib)}`);
  // Money dialogs start on Cancel; Escape gives focus back to the switch that opened them.
  await page.goto(BASE + '/ads.html');
  const sw = '[data-toggle="ad:120252672229400312"]';
  await page.waitForSelector(sw);
  const swOnBefore = await page.getAttribute(sw, 'aria-checked');
  await page.focus(sw);
  await page.keyboard.press('Enter');
  await page.waitForSelector('dialog.confirm');
  const startFocus = await page.evaluate(() => document.activeElement.id);
  await page.keyboard.press('Enter');  // a stray Enter lands on Cancel
  await page.waitForSelector('dialog.confirm', { state: 'detached' });
  const back = await page.evaluate((s) => document.activeElement === document.querySelector(s), sw);
  check('a confirm without a field opens on Cancel: a stray Enter changes nothing, and focus returns to the switch',
    startFocus === 'cd-cancel' && (await page.getAttribute(sw, 'aria-checked')) === swOnBefore && back, `${startFocus} ${back}`);
  // A toast raised while a dialog is open shows above it.
  await page.focus(sw);
  await page.keyboard.press('Enter');
  await page.waitForSelector('dialog.confirm');
  await page.evaluate(async () => (await import('/js/ui.js')).toast('QA toast over a dialog', 'bad'));
  // Behind the dialog's backdrop the toast's red would be dimmed: read one pixel of its padding from the screen.
  const tr = await page.evaluate(() => { const r = document.querySelector('.toast').getBoundingClientRect(); return { x: Math.round(r.left + 4), y: Math.round(r.top + r.height / 2) }; });
  const shot = (await page.screenshot({ clip: { x: tr.x, y: tr.y, width: 1, height: 1 } })).toString('base64');
  const px = await page.evaluate(async (b64) => { const img = new Image(); img.src = `data:image/png;base64,${b64}`; await img.decode();
    const c = document.createElement('canvas'); c.width = c.height = 1; const g = c.getContext('2d'); g.drawImage(img, 0, 0); return [...g.getImageData(0, 0, 1, 1).data].slice(0, 3); }, shot);
  const want = await page.evaluate(() => getComputedStyle(document.querySelector('.toast')).backgroundColor.match(/\d+/g).map(Number));
  check('a toast shows above an open dialog, not dimmed behind it', await page.evaluate(() => document.querySelector('.toast').matches(':popover-open'))
    && px.every((v, i) => Math.abs(v - want[i]) <= 6), `${px} vs ${want}`);
  // Outside an open modal dialog everything is inert: the toast must sit inside it to reach a screen reader.
  const heard = await page.evaluate(() => { const t = document.querySelector('.toast'); return { inDialog: !!t.closest('dialog[open]'), inert: !!t.closest('[inert]'), role: t.getAttribute('role') }; });
  check('a toast raised over a dialog is inside it (not inert) and is an alert', heard.inDialog && !heard.inert && heard.role === 'alert', JSON.stringify(heard));
  await page.keyboard.press('Escape');
  await page.waitForSelector('dialog.confirm', { state: 'detached' });
  await page.waitForTimeout(100);
  const after = await page.evaluate(() => { const t = document.querySelector('.toast'); return { onPage: t.parentNode === document.body, open: t.matches(':popover-open') }; });
  check('when the dialog closes, the toast goes back to the page and stays up', after.onPage && after.open, JSON.stringify(after));
  // A budget the dialog refuses marks the field invalid and points at the reason.
  await page.goto(BASE + '/ads.html?level=campaign');
  await page.waitForSelector('[data-budget^="campaign:"]');
  await page.click('[data-budget^="campaign:"]');
  await page.fill('#cd-input', '0.2');
  await page.click('dialog.confirm #cd-ok');
  const inv = await page.evaluate(() => { const i = document.getElementById('cd-input'); return `${i.getAttribute('aria-invalid')} ${i.getAttribute('aria-describedby')}`; });
  await page.fill('#cd-input', '30');
  const cleared = await page.evaluate(() => document.getElementById('cd-input').getAttribute('aria-invalid'));
  check('a refused amount sets aria-invalid and describes the field with the reason, typing clears it', inv === 'true cd-hint cd-err' && cleared === null, `${inv} / ${cleared}`);
  await page.click('dialog.confirm #cd-cancel');
  // Rows open the quick look from the keyboard; the drawer keeps focus and hands it back.
  await page.goto(BASE + '/ads.html');
  await page.waitForSelector('.tbl tbody tr[data-row]');
  const pkInert = await page.evaluate(() => !document.querySelector('.pk') || document.querySelector('.pk').inert);
  const rowStops = await page.evaluate(() => [...document.querySelectorAll('.tbl tbody tr[data-row]')].filter((r) => r.tabIndex === 0).length);
  const rowKey = await page.getAttribute('.tbl tbody tr[data-row]', 'data-row');
  await page.focus('.tbl tbody tr[data-row]');
  await page.keyboard.press('ArrowDown');
  const movedTo = await page.evaluate(() => document.activeElement.dataset.row);
  const roving = await page.evaluate(() => [...document.querySelectorAll('.tbl tbody tr[data-row]')].filter((r) => r.tabIndex === 0).map((r) => r.dataset.row));
  check('the table is one Tab stop: only one row is in the Tab order, and it follows ↓', rowStops === 1 && roving.length === 1 && roving[0] === movedTo, `${rowStops} ${roving}`);
  await page.keyboard.press('ArrowUp');
  await page.keyboard.press('Enter');
  await page.waitForSelector('.pk.open');
  const inDrawer = await page.evaluate(() => document.querySelector('.pk').contains(document.activeElement));
  for (let i = 0; i < 40; i++) await page.keyboard.press('Tab');
  const stillIn = await page.evaluate(() => document.querySelector('.pk').contains(document.activeElement));
  await page.keyboard.press('Escape');
  await page.waitForSelector('.pk:not(.open)');
  const backTo = await page.evaluate(() => ({ row: document.activeElement.dataset.row, inert: document.querySelector('.pk').inert }));
  check('rows: ↓ ↑ move, Enter opens the quick look with focus inside, Tab stays inside, Escape closes it and returns to the row',
    pkInert && movedTo && movedTo !== rowKey && inDrawer && stillIn && backTo.row === rowKey && backTo.inert, `${movedTo} ${inDrawer} ${stillIn} ${JSON.stringify(backTo)}`);
  // Charts say what they show in words.
  await page.goto(BASE + '/performance.html');
  await page.waitForSelector('#c-spend svg');
  const chartWords = await page.evaluate(() => { const svg = document.querySelector('#c-spend svg'); const d = document.getElementById(svg.getAttribute('aria-describedby')); return d ? d.textContent : ''; });
  check('the spend chart has a summary in words (total and best day)', /^Spend per day, .+ to .+: (\$[\d,.]+ in total, the most on .+|nothing on any day\.)/.test(chartWords), chartWords);
  // Less motion when the system asks for it.
  const calm = await (await browser.newContext({ reducedMotion: 'reduce' })).newPage();
  await calm.goto(BASE + '/login.html');
  const calmMs = await calm.evaluate(() => { const b = document.querySelector('.btn, button'); return parseFloat(getComputedStyle(b).transitionDuration) * 1000; });
  check('with reduced motion asked for, transitions are cut to nothing', calmMs < 1, `${calmMs} ms`);
  // Sign-in errors sit on the field they're about; what isn't about one field sits above Sign in.
  {
    let tries = 0;
    calm.on('request', (r) => { if (/\/api\/auth\/login$/.test(r.url())) tries++; });
    await calm.click('button[type=submit]');
    const blank = await calm.evaluate(() => [...document.querySelectorAll('#login .field.error')].map((f) => `${f.querySelector('input').name}: ${f.querySelector('.err').textContent}`));
    await calm.fill('#email', 'eugene');
    await calm.fill('#password', 'something');
    await calm.click('button[type=submit]');
    const badEmail = await calm.evaluate(() => ({ marked: [...document.querySelectorAll('#login [aria-invalid="true"]')].map((i) => i.name).join(), focus: document.activeElement.id }));
    check('sign-in marks each empty or wrong field on its own, focuses the first, and asks the server nothing',
      blank.join(' | ') === 'email: Type the email you sign in with. | password: Type your password.' && badEmail.marked === 'email' && badEmail.focus === 'email' && tries === 0,
      `${blank.join(' | ')} / ${JSON.stringify(badEmail)} / ${tries} requests`);
    const server = await calm.evaluate(async () => { const r = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: ' ', password: '' }) });
      return { status: r.status, fields: ((await r.json()).errors || []).map((e) => e.field).join() }; });
    check('the server names the same fields (400 with each one)', server.status === 400 && server.fields === 'email,password', JSON.stringify(server));
    await calm.fill('#email', 'eugene@edgebourne.com');
    await calm.route('**/api/auth/login', (r) => r.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ error: "That email and password don't match" }) }), { times: 1 });
    await calm.click('button[type=submit]');
    await calm.waitForSelector('#login-error:not([hidden])');
    await calm.waitForTimeout(300); // let the border colours finish their change
    const wrong = await calm.evaluate(() => ({ note: document.getElementById('login-error').textContent, marked: [...document.querySelectorAll('#login [aria-invalid="true"]')].map((i) => i.name).join(),
      fieldErrs: document.querySelectorAll('#login .field .err').length, focus: document.activeElement.id, border: getComputedStyle(document.getElementById('email')).borderTopColor }));
    check("a wrong email or password is said once above Sign in (naming neither), both fields marked, the password ready to type again",
      /don't match/.test(wrong.note) && wrong.marked === 'email,password' && wrong.fieldErrs === 0 && wrong.focus === 'password', JSON.stringify(wrong));
    await calm.type('#password', 'x');
    await calm.waitForTimeout(300);
    const calmBorder = await calm.evaluate(() => getComputedStyle(document.getElementById('email')).borderTopColor);
    check('typing again clears that message', await calm.isHidden('#login-error'));
    check('a marked sign-in field is drawn in the error colour, not just flagged for screen readers', wrong.border === 'rgb(200, 55, 45)' && calmBorder !== wrong.border, `${wrong.border} vs ${calmBorder}`);
    await calm.route('**/api/auth/login', (r) => r.fulfill({ status: 429, contentType: 'text/html', body: '<html>429</html>' }), { times: 1 });
    await calm.click('button[type=submit]');
    await calm.waitForSelector('#login-error:not([hidden])');
    check('too many tries says so in plain words, not "Request failed"', /Too many tries/.test(await calm.textContent('#login-error')), await calm.textContent('#login-error'));
  }
  await calm.context().close();
  }
  // Phones: no page wider than the screen.
  const phonePage = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })).newPage();
  await phonePage.goto(BASE + '/login.html');
  await phonePage.fill('#email', 'eugene@edgebourne.com'); await phonePage.fill('#password', 'localdev-pass-123');
  await Promise.all([phonePage.waitForURL('**/home.html**'), phonePage.click('button[type=submit]')]);
  const tooWide = [];
  for (const p of ['/home.html', '/inbox.html', '/leads.html', '/ads.html', '/campaign.html?id=120252638288040312', '/adset.html?id=120252672227950312', '/ad.html?id=120252672229400312', '/performance.html', '/report.html', '/desk.html', '/team.html', '/settings.html', '/new-campaign.html']) {
    await phonePage.goto(BASE + p); await phonePage.waitForTimeout(1500);
    const sw = await phonePage.evaluate(() => document.documentElement.scrollWidth);
    if (sw > 391) tooWide.push(`${p} ${sw}px`);
  }
  check('on a 390px phone no page is wider than the screen', tooWide.length === 0, tooWide.join(' | '));
  await phonePage.goto(BASE + '/ad.html?id=120252672229400312');
  await phonePage.waitForSelector('#cr-state');
  const phoneTops = await phonePage.evaluate(() => ['#cr-state', '.cr-figs', '.preview-panel'].map((x) => Math.round(document.querySelector(x).getBoundingClientRect().top)));
  check('on a phone the ad opens on its status and numbers, the preview after them', phoneTops[0] < phoneTops[1] && phoneTops[1] < phoneTops[2], phoneTops.join());
  await phonePage.goto(BASE + '/ad.html?id=120252672230740312#tab=history');
  await phonePage.reload();
  await phonePage.waitForSelector('#cr-main ol.tl li');
  const phoneTl = await phonePage.evaluate(() => ({
    cols: getComputedStyle(document.querySelector('#cr-main ol.tl li')).gridTemplateColumns.split(' ').length,
    links: document.querySelectorAll('#cr-main ol.tl a, #cr-main ol.tl button').length,
    small: [...document.querySelectorAll('#cr-main ol.tl a, #cr-main ol.tl button')].filter((e) => e.getClientRects().length)
      .map((e) => { const r = e.getBoundingClientRect(); return [e.textContent.trim().slice(0, 20), Math.round(r.width), Math.round(r.height)]; })
      .filter(([, w, h]) => w < 43.5 || h < 43.5),
    wide: document.documentElement.scrollWidth,
  }));
  check("on a phone the ad's History puts the date under each line, and its links are 44px to tap", phoneTl.cols === 2 && phoneTl.links > 0 && phoneTl.small.length === 0 && phoneTl.wide <= 391,
    JSON.stringify(phoneTl).slice(0, 300));
  {
  const smallOnes = [];
  for (const p of guards.TARGET_PAGES) {
    await phonePage.goto(BASE + p); await phonePage.waitForTimeout(1500);
    const small = await phonePage.evaluate(guards.smallTargets);
    if (small.length) smallOnes.push(`${p}: ${small.slice(0, 4).join(', ')}${small.length > 4 ? ` +${small.length - 4}` : ''}`);
  }
  check('on a phone every control on the main pages is at least 44 × 44 px', smallOnes.length === 0, smallOnes.join(' | '));
  await phonePage.goto(BASE + '/performance.html');
  await phonePage.waitForSelector('#c-spend svg');
  const phoneLook = await phonePage.evaluate(() => {
    const sum = document.querySelector('details.table-view > summary');
    const cs = getComputedStyle(sum), mark = getComputedStyle(sum, '::before').content;
    const svg = document.querySelector('#c-spend svg');
    return { marker: cs.display === 'list-item' || (mark && mark !== 'none'), scale: svg.getBoundingClientRect().width / svg.viewBox.baseVal.width };
  });
  check('on a phone a "show more" summary still shows its ▸ marker', phoneLook.marker, JSON.stringify(phoneLook));
  check('on a phone charts are drawn at their real width, so 12px labels stay 12px', Math.abs(phoneLook.scale - 1) < 0.02, String(phoneLook.scale));
  await openSettings('email', phonePage);
  const groups = await phonePage.evaluate(() => {
    const nav = document.querySelector('.settings-nav'), cur = nav.querySelector('[aria-current="page"]').getBoundingClientRect(), box = nav.getBoundingClientRect();
    return { names: [...nav.querySelectorAll('.set-group')].filter((e) => e.getBoundingClientRect().width > 0).map((e) => e.textContent).join('|'),
      oneRow: new Set([...nav.querySelectorAll('a')].map((a) => Math.round(a.getBoundingClientRect().top))).size === 1, inView: cur.left >= box.left && cur.right <= box.right };
  });
  check('on a phone Settings\' sections are one row that keeps "This account" and "Whole console", scrolled to the open one',
    groups.names === 'This account|Whole console' && groups.oneRow && groups.inView, JSON.stringify(groups));
  // Team on a phone: one card per person, nothing scrolls sideways; Team, Your account and sign-in have 44px controls.
  await phonePage.goto(BASE + '/team.html');
  await phonePage.waitForSelector('#team-table tbody tr');
  const teamCards = await phonePage.evaluate(() => { const t = document.getElementById('team-table'), box = t.parentElement;
    return { sideways: box.scrollWidth - box.clientWidth, head: getComputedStyle(t.querySelector('thead')).display,
      labels: [...t.querySelectorAll('tbody tr:first-child td[data-label]')].map((td) => getComputedStyle(td, '::before').content).join('|') }; });
  check('on a phone Team is one card per person with the labels written in, and nothing scrolls sideways',
    teamCards.sideways <= 1 && teamCards.head === 'none' && teamCards.labels === '"Access"|"Campaigns"|"Last signed in"', JSON.stringify(teamCards));
  const smallMore = [];
  for (const p of ['/team.html', '/account.html', '/login.html', '/settings.html#email']) {
    await phonePage.goto(BASE + p); await phonePage.waitForTimeout(1200);
    const small = await phonePage.evaluate(guards.smallTargets);
    if (small.length) smallMore.push(`${p}: ${small.slice(0, 4).join(', ')}`);
  }
  check('on a phone every control on Team, Your account, sign-in and a whole-console Settings section is at least 44 × 44 px', smallMore.length === 0, smallMore.join(' | '));
  }
  // ← All leads on a phone keeps the source filter in the URL, which the next poll reads.
  await phonePage.goto(`${BASE}/leads.html?ad=${adOpt.slice(2)}`);
  await phonePage.waitForSelector('.lead-row');
  await phonePage.click('.lead-row');
  await phonePage.waitForSelector('#layout.showing-detail #back');
  await phonePage.click('#back');
  await phonePage.waitForTimeout(200);
  check('← All leads keeps the lead source filter (?ad=) in the URL', new URL(phonePage.url()).searchParams.get('ad') === adOpt.slice(2)
    && !(await phonePage.getAttribute('#layout', 'class')).includes('showing-detail'), phonePage.url());
  // 9.3a: on a phone a lead and an Inbox item cover their list, and the phone's Back closes them.
  await phonePage.click('.lead-row');
  await phonePage.waitForSelector('#layout.showing-detail #back');
  check('on a phone opening a lead puts it in the address', /#lead=\d+/.test(phonePage.url()), phonePage.url());
  await phonePage.goBack();
  await phonePage.waitForFunction(() => !document.getElementById('layout').classList.contains('showing-detail'));
  check('on a phone Back closes the lead and stays on Leads with its filter', /\/leads\.html\?ad=/.test(phonePage.url()) && !/#lead=/.test(phonePage.url()), phonePage.url());
  await phonePage.goto(BASE + '/inbox.html?box=all');
  await phonePage.waitForSelector('.ib-item');
  await phonePage.locator('.ib-item').first().click();
  await phonePage.waitForSelector('#ib-panel.showing-detail #ib-detail h2');
  const ibOpen = phonePage.url();
  check('on a phone an Inbox item opens over the list with a way back', /#item=/.test(ibOpen) && await phonePage.isVisible('#ib-detail [data-ib-back]') && await phonePage.isHidden('#ib-list'), ibOpen);
  await phonePage.goBack();
  await phonePage.waitForFunction(() => !document.getElementById('ib-panel').classList.contains('showing-detail'));
  check('on a phone Back closes the Inbox item and shows the list', /\/inbox\.html\?box=all$/.test(phonePage.url()) && await phonePage.isVisible('.ib-item'), phonePage.url());
  await phonePage.locator('.ib-item').first().click();
  await phonePage.waitForSelector('#ib-panel.showing-detail [data-ib-back]');
  await phonePage.click('#ib-detail [data-ib-back]');
  await phonePage.waitForFunction(() => !document.getElementById('ib-panel').classList.contains('showing-detail') && !/item=/.test(location.hash));
  check('← Inbox shows the list and leaves no extra step behind', !/#item=/.test(phonePage.url()) && await phonePage.evaluate(() => !(history.state && history.state.layer)), phonePage.url());
  {
    const n = await phonePage.locator('.ib-item').count();
    const far = phonePage.locator('.ib-item').nth(Math.max(0, n - 1));
    await far.scrollIntoViewIfNeeded();
    const y0 = await phonePage.evaluate(() => window.scrollY);
    const farKey = await far.getAttribute('data-key');
    await far.click();
    await phonePage.waitForSelector('#ib-panel.showing-detail [data-ib-back]');
    const backFocused = await phonePage.evaluate(() => document.activeElement?.hasAttribute('data-ib-back'));
    const gap = await phonePage.evaluate(() => { const h = document.querySelector('.main h1'); return h ? Math.round(h.getBoundingClientRect().top + window.scrollY) : -1; });
    check('on a phone a short page (an open Inbox item) starts right under the top bar', gap > 0 && gap < 120, String(gap));
    await phonePage.click('#ib-detail [data-ib-back]');
    await phonePage.waitForFunction(() => !document.getElementById('ib-panel').classList.contains('showing-detail'));
    await phonePage.waitForTimeout(300);
    const back = await phonePage.evaluate(() => ({ y: window.scrollY, focus: document.activeElement?.dataset?.key || '' }));
    check('on a phone an Inbox item takes focus to ← Inbox, and the list comes back where it was with that item focused',
      backFocused && Math.abs(back.y - y0) <= 2 && back.focus === farKey, JSON.stringify({ n, y0, backFocused, ...back, farKey }));
  }
  // 9.3b phone: Ads sorts and filters by campaign without column headers, the bulk bar fits, More says Claude has work for you.
  await phonePage.goto(BASE + '/ads.html?sort=ctr&dir=desc');
  await phonePage.waitForSelector('#sort-pick');
  const otherSort = await phonePage.evaluate(() => { const s = document.getElementById('sort-pick'); return s.options[s.selectedIndex].textContent; });
  check('on a phone a sort chosen on a computer says what it sorts by', otherSort === 'Sorted by click rate', otherSort);
  await phonePage.goto(BASE + '/ads.html');
  await phonePage.waitForSelector('.pl li');
  await phonePage.selectOption('#sort-pick', 'cpl:asc');
  await phonePage.waitForFunction(() => /sort=cpl/.test(location.search));
  const phoneCpl = await phonePage.evaluate(() => [...document.querySelectorAll('.pl li small')].map((s) => { const m = s.textContent.match(/·\s*(\$[\d,.]+|–|—)(?:\s|$)/g); const last = m ? m[m.length - 1] : ''; const v = last.match(/\$([\d,.]+)/); return v ? Number(v[1].replace(/,/g, '')) : null; }));
  const priced = phoneCpl.filter((v) => v !== null);
  const firstBlank = phoneCpl.indexOf(null);
  const sortedOk = priced.length > 1 && priced.every((v, i) => i === 0 || v >= priced[i - 1]) && (firstBlank === -1 || phoneCpl.slice(firstBlank).every((v) => v === null));
  check('on a phone Ads sorts by "Lowest cost per lead" (ads without leads last)', new URL(phonePage.url()).searchParams.get('dir') === 'asc' && sortedOk, JSON.stringify(phoneCpl));
  const adsTree = await phonePage.evaluate(async () => (await fetch('/api/ads?range=7')).json());
  const pickCamp = adsTree.campaigns.find((c) => c.adsets.some((s) => s.ads.length)) || adsTree.campaigns[0];
  await phonePage.selectOption('#camp-pick', pickCamp.id);
  await phonePage.waitForFunction((id) => new URLSearchParams(location.search).get('campaign') === id, pickCamp.id);
  const campRows = await phonePage.locator('.pl li').count();
  const campAds = pickCamp.adsets.reduce((n, s) => n + s.ads.length, 0);
  check('on a phone Ads filters by campaign', await phonePage.isVisible('#camp-pick') && campRows === campAds, `${campRows} rows, ${campAds} ads in ${pickCamp.name}`);
  await phonePage.goto(BASE + '/ads.html');
  await phonePage.waitForSelector('.pl li');
  for (const w of [390, 320]) {
    await phonePage.setViewportSize({ width: w, height: 760 });
    await phonePage.waitForTimeout(200);
    if (!(await phonePage.isVisible('.bk'))) { await phonePage.locator('.pl li .pick').nth(0).click(); await phonePage.locator('.pl li .pick').nth(4).click(); }
    await phonePage.waitForSelector('.bk [data-bulk="off"]');
    const fit = await phonePage.evaluate(() => {
      const bar = document.querySelector('.bk'), r = bar.getBoundingClientRect();
      const btns = [...bar.querySelectorAll('[data-bulk]')].map((b) => b.getBoundingClientRect());
      return { scroll: bar.scrollWidth - bar.clientWidth, left: r.left, right: r.right, vw: innerWidth, small: btns.filter((b) => b.height < 44 || b.width < 44).length,
        clipped: btns.filter((b) => b.right > r.right + 0.5 || b.left < r.left - 0.5).length, labels: [...bar.querySelectorAll('.bk-acts .btn span')].map((s) => s.scrollWidth <= s.clientWidth + 1) };
    });
    check(`on a ${w}px phone the bulk bar fits: every action in view, 44px or more, no sideways scroll`, fit.scroll <= 1 && fit.left >= 0 && fit.right <= fit.vw && !fit.small && !fit.clipped && fit.labels.every(Boolean), JSON.stringify(fit));
  }
  await phonePage.click('.bk [data-bulk="clear"]');
  for (const w of [390, 320]) {
    await phonePage.setViewportSize({ width: w, height: 760 });
    await phonePage.goto(BASE + '/compare.html');
    await phonePage.waitForSelector('#cmp-pick .cmp-opt');
    const foot = await phonePage.evaluate(() => {
      const f = document.querySelector('.cmp-pick-foot').getBoundingClientRect(), t = document.querySelector('.tabbar').getBoundingClientRect();
      return { foot: Math.round(f.bottom * 10) / 10, tabs: Math.round(t.top * 10) / 10, wide: document.documentElement.scrollWidth - innerWidth };
    });
    check(`on a ${w}px phone the picker's Compare bar sits right on the tab bar, with no gap for cards to show through`, Math.abs(foot.foot - foot.tabs) <= 1 && foot.wide <= 0, JSON.stringify(foot));
  }
  await phonePage.setViewportSize({ width: 390, height: 844 });
  await phonePage.goto(BASE + '/adset.html?id=120252672227950312');
  await phonePage.waitForSelector('#range-pick');
  const rangeFit = await phonePage.evaluate(() => { const r = document.getElementById('range-pick'); return { w: Math.round(r.getBoundingClientRect().width), cut: r.scrollWidth - r.clientWidth }; });
  check('on a phone the ad set page gives the date range room to be read', rangeFit.w >= 140, JSON.stringify(rangeFit));
  const proposalsWaiting = (await phonePage.evaluate(async () => (await fetch('/api/refresh')).json())).proposals || 0;
  await phonePage.goto(BASE + '/home.html');
  await phonePage.waitForTimeout(1200);
  const more = await phonePage.evaluate(() => { const c = document.querySelector('.tabbar [data-more] [data-claude-count]'); return { shown: c && !c.hidden, n: c?.querySelector('[aria-hidden="true"]')?.textContent ?? null, label: c?.querySelector('.sr-only')?.textContent || '' }; });
  check('on a phone More carries a badge with Claude\'s waiting suggestions', proposalsWaiting > 0 ? more.shown && more.n === String(proposalsWaiting) && /waiting/.test(more.label) : !more.shown, `${proposalsWaiting} ${JSON.stringify(more)}`);
  await phonePage.click('.tabbar [data-more]');
  await phonePage.waitForSelector('dialog.sheet[open]');
  const sheetOrder = await phonePage.evaluate(() => ({ links: [...document.querySelectorAll('dialog.sheet nav a')].map((a) => a.querySelector('span')?.textContent || a.textContent.trim()), focus: document.activeElement?.textContent.trim() }));
  check('More lists Claude first, then Creative, and opens on Claude, not on the account switcher', sheetOrder.links[0] === 'Claude' && sheetOrder.links[1] === 'Creative' && sheetOrder.links.indexOf('Insights') > 1 && /^Claude/.test(sheetOrder.focus || ''), JSON.stringify(sheetOrder));
  await phonePage.keyboard.press('Escape');
  // A page that doesn't exist gets the console's own page, and the API keeps its own answer.
  const missing = await phonePage.goto(BASE + '/no-such-page.html?x=1');
  const nf = await phonePage.evaluate(() => ({ h1: document.querySelector('h1')?.textContent, path: document.getElementById('nf-path')?.textContent, home: !!document.querySelector('a[href="/home.html"]'),
    wide: document.documentElement.scrollWidth }));
  check('a missing page shows "Page not found" with the address and a way to Today, at phone width', missing.status() === 404 && nf.h1 === 'Page not found' && nf.path === '/no-such-page.html?x=1' && nf.home && nf.wide <= 390, JSON.stringify({ status: missing.status(), ...nf }));
  const apiMissing = await phonePage.evaluate(async () => { const r = await fetch('/api/no-such-thing'); return { status: r.status, page: /Page not found/.test(await r.text()) }; });
  check('a missing API address still answers 404 from the server, not the page', apiMissing.status === 404 && !apiMissing.page, JSON.stringify(apiMissing));
  // Offline: the page that couldn't load says so, and opens by itself once the connection is back.
  {
    const offCtx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const off = await offCtx.newPage();
    await off.goto(BASE + '/login.html');
    await off.fill('#email', 'eugene@edgebourne.com'); await off.fill('#password', 'localdev-pass-123');
    await Promise.all([off.waitForURL('**/home.html**'), off.click('button[type=submit]')]);
    await off.evaluate(() => navigator.serviceWorker.ready);
    if (!(await off.evaluate(() => !!navigator.serviceWorker.controller))) await off.reload();
    await off.waitForFunction(() => !!navigator.serviceWorker.controller);
    await offCtx.setOffline(true);
    await off.goto(BASE + '/leads.html').catch(() => {});
    await off.waitForSelector('#off-retry');
    const offText = await off.evaluate(() => ({ h1: document.querySelector('h1').textContent, url: location.pathname, styled: getComputedStyle(document.querySelector('.btn-primary')).backgroundColor !== 'rgba(0, 0, 0, 0)' }));
    await off.click('#off-retry');
    await off.waitForFunction(() => /Still no connection/.test(document.getElementById('off-state').textContent));
    check('offline, a page shows "No connection" with its styles, and Try again says it is still offline', offText.h1 === 'No connection' && offText.url === '/leads.html' && offText.styled, JSON.stringify(offText));
    await offCtx.setOffline(false);
    await off.waitForSelector('.lead-row, .lead-list', { timeout: 20000 }).catch(() => {});
    check('the offline page opens the page that was asked for by itself once the connection is back', await off.evaluate(() => location.pathname === '/leads.html' && !document.getElementById('off-retry')), off.url());
    await offCtx.close();
  }
  // Phones keep their size: iOS zooms into any field under 16px; anything past the edge makes the browser shrink the page.
  const narrow = await (await browser.newContext({ viewport: { width: 320, height: 700 }, isMobile: true, hasTouch: true })).newPage();
  await narrow.goto(BASE + '/login.html?next=//example.com/x');
  await narrow.fill('#email', 'eugene@edgebourne.com'); await narrow.fill('#password', 'localdev-pass-123');
  await Promise.all([narrow.waitForURL('**/home.html**'), narrow.click('button[type=submit]')]);
  check('sign-in refuses to send people to another site', narrow.url().startsWith(BASE));
  const tabCtx = await browser.newContext();
  const tabPage = await tabCtx.newPage();
  await tabPage.goto(BASE + '/login.html?next=%2F%09%2Fexample.com%2Fx');
  await tabPage.fill('#email', 'eugene@edgebourne.com'); await tabPage.fill('#password', 'localdev-pass-123');
  await Promise.all([tabPage.waitForURL('**/home.html**'), tabPage.click('button[type=submit]')]);
  check('sign-in also refuses a next= address hidden behind a tab (/%09/example.com)', tabPage.url().startsWith(BASE), tabPage.url());
  // Signing out ends the sign-in on the server: a copy of the cookie taken before stops working.
  const copyCtx = await browser.newContext();
  await copyCtx.addCookies(await tabCtx.cookies());
  const copyPage = await copyCtx.newPage();
  await copyPage.goto(BASE + '/offline.html');
  const meStatus = () => copyPage.evaluate(async () => (await fetch('/api/auth/me')).status);
  const copyBefore = await meStatus();
  await tabPage.evaluate(() => fetch('/api/auth/logout', { method: 'POST', headers: { 'X-Requested-With': 'ebads' } }));
  const copyAfter = await meStatus();
  check('signing out stops a copied session cookie too', `${copyBefore} ${copyAfter}` === '200 401', `${copyBefore} ${copyAfter}`);
  await copyCtx.close(); await tabCtx.close();
  const zoomers = [];
  const spilling = [];
  for (const p of ['/home.html', '/inbox.html', '/leads.html', '/ads.html', '/ad.html?id=120252672229400312', '/new-ad.html', '/new-campaign.html', '/performance.html', '/ideas.html', '/research.html', '/desk.html', '/settings.html', '/team.html', '/account.html']) {
    await narrow.goto(BASE + p); await narrow.waitForTimeout(1200);
    const r = await narrow.evaluate(() => {
      const inScroller = (el) => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) if (/auto|scroll|hidden|clip/.test(getComputedStyle(e).overflowX)) return true; return false; };
      const all = [...document.querySelectorAll('body *')];
      return { meta: document.querySelector('meta[name=viewport]').content, width: innerWidth,
        small: all.filter((e) => /^(INPUT|SELECT|TEXTAREA)$/.test(e.tagName) && !['checkbox', 'radio', 'hidden', 'range', 'color', 'file'].includes(e.type) && parseFloat(getComputedStyle(e).fontSize) < 16).map((e) => e.id || e.className),
        over: all.filter((e) => getComputedStyle(e).position !== 'fixed' && e.getBoundingClientRect().width && e.getBoundingClientRect().right > innerWidth + 1 && !inScroller(e)).slice(0, 3).map((e) => `${e.tagName}:${e.textContent.slice(0, 30)}`) };
    });
    if (r.small.length || !/maximum-scale=1/.test(r.meta)) zoomers.push(`${p}: ${r.small.join()}`);
    if (r.width !== 320 || r.over.length) spilling.push(`${p} ${r.width}: ${r.over.join(' / ')}`);
  }
  check('no field on a phone is small enough to make iOS zoom', zoomers.length === 0, zoomers.join(' | '));
  check('on a 320px phone nothing runs past the edge', spilling.length === 0, spilling.join(' | '));
  await narrow.goto(BASE + '/forms.html');
  await narrow.waitForSelector('.form-tbl');
  const formCards = await narrow.evaluate(() => { const t = document.querySelector('.form-tbl'), box = t.parentElement;
    return { sideways: box.scrollWidth - box.clientWidth, right: Math.round(Math.max(...[...t.querySelectorAll('td')].map((td) => td.getBoundingClientRect().right))), vw: innerWidth,
      head: getComputedStyle(t.querySelector('thead')).display }; });
  check('on a 320px phone each lead form is a card that fits, with no sideways scroll', formCards.sideways <= 1 && formCards.right <= formCards.vw && formCards.head === 'none', JSON.stringify(formCards));
  await narrow.goto(BASE + '/leads.html');
  await narrow.waitForSelector('.lead-row');
  await narrow.click('.lead-row');
  await narrow.waitForSelector('#stages');
  const leadFit = await narrow.evaluate(() => ['#detail', '#detail .detail-top', '#detail .reach', '#stages', ...[...document.querySelectorAll('#stages button')].map((_, i) => `#stages button:nth-child(${i + 1})`)]
    .map((sel) => [sel, Math.round(document.querySelector(sel)?.getBoundingClientRect().right || 0)]).filter(([, r]) => r > innerWidth + 1));
  check('on a 320px phone the lead detail and every stage button fit on screen', leadFit.length === 0, JSON.stringify(leadFit));
  await narrow.goto(BASE + '/ideas.html?range=7');
  await narrow.waitForSelector('#range-pick');
  const ideaRange = await narrow.evaluate(() => { const el = document.getElementById('range-pick'), twin = el.cloneNode(true);
    twin.removeAttribute('id'); twin.style.cssText = 'position:absolute;visibility:hidden;flex:none;width:auto'; document.body.append(twin);
    const r = { shown: Math.round(el.getBoundingClientRect().width), natural: Math.round(twin.getBoundingClientRect().width), right: Math.round(el.getBoundingClientRect().right), vw: innerWidth };
    twin.remove(); return r; });
  check('on a 320px phone the dates on Ideas keep their full width, so "Last 7 days" is not cut', ideaRange.shown >= ideaRange.natural && ideaRange.right <= ideaRange.vw, JSON.stringify(ideaRange));
  await narrow.goto(BASE + '/desk.html#new');
  await narrow.waitForSelector('#cv-seeds:not([hidden])');
  await narrow.waitForTimeout(300);
  const fits = await narrow.evaluate(() => ({ cv: document.querySelector('#cv').getBoundingClientRect().bottom, h: innerHeight, page: document.documentElement.scrollHeight, tabs: getComputedStyle(document.querySelector('.tabbar')).display }));
  check('a conversation fills the phone exactly, with no tab bar over the reply box', Math.abs(fits.cv - fits.h) <= 1 && fits.page <= fits.h + 1 && fits.tabs === 'none', JSON.stringify(fits));
  // The refusals above are the point of these checks; the browser logs each as a failed load. Real page errors stay.
  errors.splice(a2Seen, errors.length - a2Seen, ...errors.slice(a2Seen).filter((e) => !/Failed to load resource: the server responded with a status of 4\d\d/.test(e)));

  }
  await browser.close();
  console.log(results.join('\n'));
  console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'no console errors');
  const failed = results.filter((r) => r.startsWith('FAIL')).length;
  console.log(`${results.length - failed} passed, ${failed} failed, ${errors.length} console errors`);
  process.exit(failed || errors.length ? 1 : 0);
})().catch((e) => { console.log(results.join('\n')); console.error(e); process.exit(1); });
