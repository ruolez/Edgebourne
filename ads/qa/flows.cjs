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
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/facebook\.com|preview_iframe/.test(m.text())) errors.push(m.text()); });
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
  check('switch turns an ad off after confirming', before === 'true');
  // Cancel leaves it alone.
  await page.locator('[data-toggle="ad:120252672229400312"]').click();
  await page.click('dialog.confirm #cd-cancel');
  await page.waitForTimeout(400);
  check('cancel changes nothing', (await page.locator('[data-toggle="ad:120252672229400312"]').getAttribute('aria-checked')) === 'false');
  // Back on.
  await page.locator('[data-toggle="ad:120252672229400312"]').click();
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => document.querySelector('[data-toggle="ad:120252672229400312"]')?.getAttribute('aria-checked') === 'true');
  check('switch turns it back on', true);

  // 2. Budget: validation, +20% warning, then a real change.
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
  check('campaign budget changes to $26/day', true);

  // 3. Ad page: format switch, duplicate.
  await page.goto(BASE + '/ad.html?id=120252672232030312');
  await page.waitForSelector('#formats button');
  await page.click('#formats button[data-format="INSTAGRAM_STORY"]');
  await page.waitForSelector('#preview-frame iframe');
  await page.waitForSelector('#preview-frame iframe:not(.preview-loading)', { timeout: 15000 });
  check('the preview placeholder stays until Meta\'s frame has loaded', (await page.locator('#preview-frame .preview-skeleton').count()) === 0);
  check('preview loads an iframe for Instagram Stories', /INSTAGRAM_STORY/.test(await page.getAttribute('#preview-frame iframe', 'src')));
  await page.click('#dup');
  await page.waitForSelector('dialog.confirm #cd-input');
  await page.fill('#cd-input', 'N4 - Weekly report (flow copy)');
  await Promise.all([page.waitForURL('**created=1**'), page.click('dialog.confirm #cd-ok')]);
  await page.waitForSelector('.claude-note');
  check('duplicate opens the new ad with the "created, off" note', (await page.textContent('#cr-title')).includes('flow copy'));
  await page.screenshot({ path: `${OUT}/flow-3-duplicate.png`, fullPage: true });

  // 4. New ad with an uploaded image.
  if (IMG) {
    await page.goto(BASE + '/new-ad.html');
    await page.waitForSelector('#template option', { state: 'attached' });
    await page.selectOption('#template', '120252672229040312');
    await page.setInputFiles('#file', IMG);
    await page.waitForSelector('#chosen:not([hidden]) .ok-text');
    await page.fill('#name', 'N7 - Flow test image ad');
    await page.fill('#title', 'One system for the whole shop');
    await page.screenshot({ path: `${OUT}/flow-4-new-ad.png`, fullPage: true });
    await Promise.all([page.waitForURL('**/ad.html?id=**created=1**'), page.click('#create')]);
    await page.waitForSelector('#cr-status .pill');
    check('new image ad is created and opens off', (await page.textContent('#cr-status')).includes('Off'), await page.textContent('#cr-title'));
  }

  // 4b. Polish: start a run from the ad page, then turn Claude's new-headline proposal into an ad.
  await page.goto(BASE + '/ad.html?id=120252672230740312#tab=polish');
  await page.reload();
  await page.waitForSelector('#polish-form');
  await page.click('[data-preset="quick"]');
  check('quick preset picks 4 passes', (await page.textContent('#run-polish')).includes('Run 4 passes'));
  await page.click('#run-polish');
  await page.waitForSelector('#runs .task.queued');
  check('polish run is queued for the Mac', true);
  await page.screenshot({ path: `${OUT}/flow-polish.png`, fullPage: true });
  // Don't leave a real run for a connected Mac to pick up.
  await page.locator('#runs .task.queued [data-cancel]').first().click();
  await page.waitForSelector('#runs .task.cancelled');
  check('a queued polish run can be cancelled', true);
  const create = page.locator('.proposal.variant [data-approve]').first();
  if (await create.count()) {
    await create.click();
    await page.waitForSelector('dialog.confirm');
    await Promise.all([page.waitForURL('**created=1**'), page.click('dialog.confirm #cd-ok')]);
    await page.waitForSelector('#cr-status .pill');
    check('approving a new-copy proposal creates that ad, switched off',
      (await page.textContent('#cr-title')).includes('·') && (await page.textContent('#cr-status')).includes('Off'), await page.textContent('#cr-title'));
  } else results.push('SKIP new-headline proposal — none pending');

  // Refresh: on every page, pulls from Meta, then the page reloads its data and the label updates.
  require('child_process').execSync(`docker exec -w /app edgebourne-ads-backend python -c "import settings_store,time;settings_store.set('last_refresh_at',str(time.time()-600))"`); // outside the 60 s throttle
  await page.goto(BASE + '/ads.html');
  await page.waitForSelector('.page-head [data-refresh]');
  await page.click('.page-head [data-refresh]');
  await page.waitForFunction(() => /Updated just now/.test(document.querySelector('.page-head [data-updated]')?.textContent || ''), null, { timeout: 60000 });
  check('Refresh pulls from Meta and shows when', true, await page.textContent('.page-head [data-updated]'));
  const again = await page.evaluate(() => fetch('/api/refresh', { method: 'POST' }).then((r) => r.json()));
  check('a second Refresh within a minute does not hit Meta again', again.ran === false);
  for (const p of ['leads', 'performance', 'desk', 'research', 'settings', 'team', 'account']) {
    await page.goto(`${BASE}/${p}.html`, { waitUntil: 'networkidle' });
    check(`Refresh is on ${p}`, await page.isVisible('.page-head [data-refresh]'));
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

  // Lead stages to Meta: a real-looking lead moved to Qualified sends Lead, Contacted and Qualified once each.
  const leadId = Number(require('child_process').execSync(`docker exec edgebourne-ads-backend python -c "
import db
db.execute(\\"DELETE FROM leads WHERE meta_lead_id = '9876543210123456'\\")
r = db.execute(\\"INSERT INTO leads (meta_lead_id, created_time, full_name, campaign_id, campaign_name) VALUES ('9876543210123456', now() - interval '2 hours', 'QA Stage Lead', '120252638288040312', 'Edge Bourne - Free intro call - Leads') RETURNING id\\", returning=True)
print(r['id'])"`).toString().trim());
  await page.goto(BASE + '/settings.html');
  await page.waitForSelector('#crm-state .pill');
  if (!(await page.isChecked('#crm_send_enabled'))) await page.check('#crm_send_enabled');
  await page.click('#crm-form button[type=submit]');
  await page.waitForSelector('#crm-state .pill.ok');
  check('Settings turns lead stages on', true, await page.textContent('#crm-state'));
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
  await page.goto(BASE + '/settings.html');
  await page.waitForSelector('#crm-state .pill');
  await page.uncheck('#crm_send_enabled');
  await page.click('#crm-form button[type=submit]');
  await page.waitForFunction(() => document.querySelector('#crm-state')?.textContent === 'Off');
  check('Settings turns lead stages off again', true);

  // Automatic refresh: the interval is set in Settings; open pages reload when the server has newer data.
  await page.selectOption('#auto-minutes', '5');
  await page.click('#auto-form button[type=submit]');
  await page.waitForFunction(() => document.querySelector('#auto-state')?.textContent === 'Every 5 minutes');
  check('Settings sets the automatic refresh interval', true);
  await page.goto(BASE + '/ads.html', { waitUntil: 'networkidle' });
  check('the Refresh button says how often it updates by itself', /every 5 min/.test(await page.getAttribute('.page-head [data-refresh]', 'title')));
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
  await page.goto(BASE + '/settings.html');
  await page.waitForSelector('#auto-state .pill');
  await page.selectOption('#auto-minutes', '15');
  await page.click('#auto-form button[type=submit]');
  await page.waitForFunction(() => document.querySelector('#auto-state')?.textContent === 'Every 15 minutes');

  // Telegram: the admin adds the bot, a person connects their chat, a new lead reaches it within seconds.
  const sh = (cmd) => require('child_process').execSync(cmd).toString();
  const tgSent = () => JSON.parse(sh(`docker exec edgebourne-ads-backend python -c "import requests;print(requests.get('http://fake-meta:5001/telegram/_sent').text)"`));
  sh(`docker exec edgebourne-ads-backend python -c "import db;db.execute('UPDATE users SET telegram_chat_id=NULL, telegram_name=NULL, telegram_link_code=NULL');db.execute(\\"DELETE FROM leads WHERE full_name = 'Telegram QA Lead'\\")"`);
  await page.goto(BASE + '/settings.html');
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
  check('Settings connects the Telegram bot', true);
  await page.goto(BASE + '/account.html');
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
  check('a new lead reaches Telegram in under 30 s, with a link to it', Boolean(alert) && /Phone: \+15550001111/.test(alert.text), alert ? `${Math.round((Date.now() - t0) / 1000)} s` : 'not sent');
  await page.screenshot({ path: `${OUT}/flow-telegram-account.png` });

  // Lead replies: templates in Settings, an email from the lead page, then the automatic reply.
  const mailSent = () => JSON.parse(sh(`docker exec edgebourne-ads-backend python -c "import requests;print(requests.get('http://fake-meta:5001/mail/_sent').text)"`));
  await page.goto(BASE + '/settings.html');
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
  errors.splice(rpSeen); // the refused link logs an expected 400
  check('a booking link without https is refused', true);
  await page.fill('#booking_link', 'https://cal.com/eugene');
  await page.click('#rp-form button[type=submit]');
  await page.waitForFunction(() => document.querySelector('#rp-state')?.textContent === 'By hand');
  const tgLeadId = await page.evaluate(() => fetch('/api/leads?q=Telegram%20QA%20Lead&status=all').then((r) => r.json()).then((d) => d.leads[0].id));
  await page.goto(`${BASE}/leads.html#lead=${tgLeadId}`);
  await page.waitForSelector('#reply-open');
  await page.click('#reply-open');
  await page.waitForFunction(() => /Hi Telegram,/.test(document.querySelector('#reply-body')?.value || ''));
  const draft = await page.inputValue('#reply-body');
  check('Email them opens a draft filled in for this lead', /\(555\) 000-1111/.test(draft) && /https:\/\/cal\.com\/eugene/.test(draft), draft.split('\n')[0]);
  await page.fill('#reply-body', draft.replace('Thanks for asking', 'Thanks a lot for asking'));
  const mailsBefore = mailSent().length;
  await page.click('#reply-send');
  await page.waitForSelector('.email-sent');
  const mail = mailSent().slice(mailsBefore).find((m) => m.to.includes('tgqa@example.com'));
  check('the email goes out with the edits, from Eugene, answers back to him', Boolean(mail) && /Thanks a lot for asking/.test(mail.text) && /Eugene/.test(mail.from) && mail.reply_to === 'eugene@edgebourne.com', mail ? `${mail.from} / ${mail.reply_to}` : 'no mail');
  check('sending moves the lead to Contacted and lists the email', (await page.getAttribute('[data-stage="contacted"]', 'aria-pressed')) === 'true' && /emailed them/.test(await page.textContent('.history')));
  await page.screenshot({ path: `${OUT}/flow-lead-reply.png`, fullPage: true });
  await page.goto(BASE + '/settings.html');
  await page.waitForSelector('#rp-auto');
  await page.check('#rp-auto');
  await page.click('#rp-form button[type=submit]');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => document.querySelector('#rp-state')?.textContent === 'Automatic reply on');
  check('the automatic reply needs a confirmation to turn on', true);
  const autoLead = '7700' + String(Date.now() + 7).slice(-12);
  const mailsBeforeAuto = mailSent().length;
  sh(`docker exec edgebourne-ads-backend python -c "
import json, hmac, hashlib, requests, settings_store
body = json.dumps({'entry': [{'changes': [{'field': 'leadgen', 'value': {'leadgen_id': '${autoLead}'}}]}]}).encode()
sig = 'sha256=' + hmac.new(settings_store.get('meta_app_secret').encode(), body, hashlib.sha256).hexdigest()
requests.post('http://localhost:5000/webhooks/meta', data=body, headers={'X-Hub-Signature-256': sig, 'Content-Type': 'application/json'})"`);
  let autoMail = null;
  for (let i = 0; i < 30 && !autoMail; i++) { await page.waitForTimeout(1000); autoMail = mailSent().slice(mailsBeforeAuto).find((m) => /Your free intro call/.test(m.subject)); }
  check('a new lead gets the automatic reply by itself', Boolean(autoMail), autoMail ? autoMail.subject : 'none');
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
  check('Leads shows how fast leads hear back', /Last 30 days: half heard back within .* of \d+ within 5 min/.test(await page.textContent('#response')), await page.textContent('#response'));

  // Desk schedules: switch one on, change its time, a due schedule files one run (not a pile), the finish reaches Telegram.
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute('UPDATE desk_schedules SET enabled=FALSE, next_run_at=NULL, skipped=0, last_task_id=NULL')"`);
  await page.goto(BASE + '/desk.html#schedules', { waitUntil: 'networkidle' });
  await page.waitForSelector('.sched');
  check('Schedules lists the five checks, all off', (await page.locator('.sched').count()) === 5 && (await page.locator('.sched [aria-checked="true"]').count()) === 0);
  await page.click('#sched-1 [data-sched-toggle]');
  await page.waitForFunction(() => /next/.test(document.querySelector('#sched-1 .sched-when')?.textContent || ''));
  check('switching the daily health check on shows its next run', /Every day at 8:30 AM · next/.test(await page.textContent('#sched-1 .sched-when')), await page.textContent('#sched-1 .sched-when'));
  await page.click('#sched-1 .sched-edit summary');
  await page.selectOption('#every-1', 'days');
  await page.selectOption('#days-1', '2');
  await page.fill('#at-1', '07:15');
  await page.click('#sched-1 .sched-rule button[type=submit]');
  await page.waitForFunction(() => /Every 2 days at 7:15 AM/.test(document.querySelector('#sched-1 .sched-when')?.textContent || ''));
  check('the time can be changed', true);
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
  await page.click('#tab-runs');
  check('the run is labelled with its schedule', /Daily health check/.test(await page.textContent('#view')));
  await page.screenshot({ path: `${OUT}/flow-schedules.png`, fullPage: true });
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db,json;db.execute('UPDATE desk_schedules SET enabled=FALSE, next_run_at=NULL, skipped=0, last_task_id=NULL, rule=%s WHERE id = 1', (json.dumps({'every': 'day', 'at': '08:30'}),))"`);

  // Alerts: rules in Settings; a rejected ad raises one alert (Telegram + Today), not twice, and it clears by itself.
  await page.goto(BASE + '/settings.html');
  await page.waitForSelector('#al-rules li');
  check('Settings lists the alert rules', (await page.locator('#al-rules li').count()) === 13);
  await page.fill('[data-rule="no_leads"][data-key="days"]', '4');
  await page.click('#al-form button[type=submit]');
  await page.waitForTimeout(500);
  // Targets live in one place now (audit A19): the cost-per-lead target is in Targets, the alert reads it.
  await page.fill('#t-lead', '15');
  await page.click('#tg-targets button[type=submit]');
  await page.waitForTimeout(500);
  await page.reload();
  await page.waitForSelector('#al-rules li');
  check('alert thresholds are saved', (await page.inputValue('[data-rule="no_leads"][data-key="days"]')) === '4' && (await page.inputValue('#t-lead')) === '15');
  check('the cost-per-lead alert names the target from Targets', /Target \$15\.00 per lead/.test(await page.textContent('#al-rules')));
  await page.fill('[data-rule="no_leads"][data-key="days"]', '3');
  await page.click('#al-form button[type=submit]');
  await page.waitForTimeout(400);
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
  await page.waitForSelector('.attention');
  check('the alert shows on Today', /Meta stopped “QA rejected ad”/.test(await page.textContent('.attention')));
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
  await page.fill('#cr-q', 'zzz no such ad');
  check('no match says so and offers every ad', /No ad called/.test(await page.textContent('#cr-panel')) && await page.isVisible('#cr-panel [data-clear]'));
  await page.click('#cr-panel [data-clear]');
  check('Show all ads brings every ad back', (await page.locator('.results-table tbody tr').count()) === Number(await page.textContent('#cr-filter [data-filter="all"] .n'))
    && (await page.inputValue('#cr-q')) === '');
  await page.click('#cr-filter [data-filter="running"]');
  const st = await cells(1);
  check('Running shows only ads that are on', st.length > 0 && st.every((t) => t === 'Running'), st.join(' '));
  await page.click('#cr-filter [data-filter="spent"]');
  check('with one campaign there is no campaign picker', await page.isHidden('#campaign-pick'));
  const one = await page.evaluate(async () => {
    const all = await (await fetch('/api/performance?range=7')).json();
    const c = await (await fetch('/api/performance?range=7&campaign=' + all.campaigns[0].id)).json();
    const none = await (await fetch('/api/performance?range=7&campaign=999')).json();
    return [all.totals.spend_cents, c.totals.spend_cents, none.totals.spend_cents, none.ads.length];
  });
  check('a campaign narrows the numbers to that campaign', one[0] === one[1] && one[2] === 0 && one[3] === 0, one.join(' '));
  await page.screenshot({ path: `${OUT}/flow-results.png`, fullPage: true });

  // 5. Claude page: decisions first, then each ad's story, then every run (dev copy of the real Desk).
  require('child_process').execSync('docker cp dev/seed_desk.py edgebourne-ads-backend:/tmp/seed_desk.py && docker exec edgebourne-ads-backend sh -c "cd /app && python /tmp/seed_desk.py"', { cwd: __dirname + '/..' });
  await page.goto(BASE + '/desk.html', { waitUntil: 'networkidle' });
  await page.waitForSelector('#view .decision');
  check('Claude opens on the decisions waiting', (await page.getAttribute('#tab-waiting', 'aria-selected')) === 'true' && (await page.locator('#view .decision').count()) === 2);
  check('a waiting decision is grouped under its ad with its versions', /Original.*headline Run it all.*v2/s.test(await page.textContent('#view .family .versions')));
  check('a new-ad decision shows what changes', /Everything in one system → No more digging for numbers/.test(await page.textContent('#view .decision .changes')));
  await page.waitForSelector('#view .decision-preview iframe', { timeout: 10000 });
  check('a new-ad decision loads Meta\'s preview of the ad', true);
  check('the Ask Claude form stays folded until asked for', await page.isHidden('#composer'));
  await page.click('#ask-open');
  check('Ask Claude opens the form', await page.isVisible('#prompt'));
  await page.click('#ask-close');
  await page.screenshot({ path: `${OUT}/flow-5-claude-waiting.png`, fullPage: true });
  await page.click('#views [data-view="ads"]');
  await page.waitForSelector('#view .runs');
  const story = await page.textContent('#view .family');
  check('By ad tells the ad\'s story with outcomes', /Created, off/.test(story) && /made in the New version run/.test(story) && /Not about one ad/.test(await page.textContent('#view')), story.replace(/\s+/g, ' ').trim().slice(0, 60));
  await page.screenshot({ path: `${OUT}/flow-5-claude-ads.png`, fullPage: true });
  await page.locator('#view .decide-link').first().click();
  await page.waitForFunction(() => document.querySelector('#tab-waiting')?.getAttribute('aria-selected') === 'true');
  check('Decide jumps to the decision', await page.isVisible('#view .decision.flash, #view .decision'));
  const second = page.locator('#view .decision', { hasText: 'the next hire' });
  await second.locator('[data-decline]').click();
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => document.querySelectorAll('#view .decision').length === 1);
  check('declining removes it from the waiting list', /1/.test(await page.textContent('#tab-waiting')));
  await page.locator('#view .decision [data-approve]').click();
  await page.waitForSelector('dialog.confirm');
  await Promise.all([page.waitForURL('**/ad.html?id=**created=1**'), page.click('dialog.confirm #cd-ok')]);
  await page.waitForFunction(() => /angle where it lives/.test(document.querySelector('#cr-title')?.textContent || ''));
  check('approving a new-ad decision creates the ad, switched off', /Off/.test(await page.textContent('#cr-status')), await page.textContent('#cr-title'));
  await page.goto(BASE + '/desk.html#runs', { waitUntil: 'networkidle' });
  await page.waitForSelector('#view .task');
  check('All runs folds the scorecard', !(await page.isVisible('#view .scorecard')));

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
  check('a test needs at least two arms', /at least two arms/.test(await page.textContent('dialog .field.error')));
  errors.splice(testsSeen); // the refused test logs an expected 400
  await page.click('dialog #arm-add');
  await page.click('dialog #arm-add');
  check('up to four arms can be added', (await page.locator('dialog [data-arm]').count()) === 4 && await page.isHidden('dialog #arm-add'));
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
  await page.click('.test [data-reopen]');
  await page.waitForFunction(() => document.querySelector('[data-n="running"]')?.textContent === '1');
  check('Reopen puts it back to running without a winner', await page.evaluate(async () => (await (await fetch('/api/experiments')).json()).items[0].winner === null));

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
  check('Claude can suggest a test: its arms and number show on the decision',
    /Portal.*N2 - Order portal.*Report.*N4 - Weekly report.*Hook rate/s.test(await sugg.textContent()) && /Track this test/.test(await sugg.textContent()));
  await sugg.locator('[data-approve]').click();
  await page.waitForSelector('dialog.confirm');
  await Promise.all([page.waitForURL('**/experiments.html#*'), page.click('dialog.confirm #cd-ok')]);
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
  await page.goto(BASE + '/settings.html');
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
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db,settings_store;db.execute('DELETE FROM experiments');settings_store.set('meta_ab_tests',None)"`);

  // Lead forms: build one with a live check and phone preview, create it on the Page, use it in a new ad.
  const fake = (p) => JSON.parse(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/fake/${p}').read().decode())"`));
  await page.goto(BASE + '/ads.html');
  await Promise.all([page.waitForURL('**/forms.html'), page.click('#forms-link')]);
  await page.waitForSelector('#list table');
  check('Lead forms lists the Page forms with their leads', /EB \| Free AI workflow review/.test(await page.textContent('#list')));
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
  check('a prohibited question is caught before creating, with the reason', /financial details/.test(await page.textContent('#f-check')) && await page.isDisabled('#f-create'));
  await page.fill('#q-label-0', 'How many people work at your company?');
  await page.fill('#q-opts-0', '1-5\n6-20\n21 or more');
  await page.check('#form-edit input[name="type"][value="intent"]');
  await page.waitForFunction(() => /Ready/.test(document.getElementById('f-check').textContent));
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
  await page.goto(BASE + '/ads.html');
  await Promise.all([page.waitForURL('**/new-adset.html?campaign=**'), page.locator('.campaign-add').first().click()]);
  await page.waitForSelector('#pl-list li b');
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
  await page.click('#create');
  await page.waitForSelector('dialog.confirm');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForSelector('#as-form .field.error .err');
  check('Advantage+ audience refuses a minimum age over 25, saying why', /at most 25/.test(await page.textContent('#as-form .field.error')));
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

  // New campaign: one form for campaign, ad set, form and ads; created off; resumes after a refusal; publish needs the budget typed.
  await page.goto(BASE + '/ads.html');
  await Promise.all([page.waitForURL('**/new-campaign.html'), page.click('#campaign-link')]);
  await page.waitForSelector('#nc-list li b');
  await page.waitForFunction(() => /Still to do/.test(document.getElementById('review').textContent));
  check('the wizard lists what is still missing, by step', /Goal.*Give the campaign a name.*Budget/s.test(await page.textContent('#review')) && await page.isDisabled('#nc-create'));
  await page.fill('#c-name', 'QA Payroll - Leads');
  await page.fill('#c-budget', '90');
  await page.fill('#s-name', 'QA SoCal - Instant form');
  await page.fill('#a-name-0', 'QA N6 - Payroll');
  await page.fill('#a-title-0', 'Payroll in one click');
  await page.waitForFunction(() => /more than 3 times what runs now/.test(document.getElementById('review').textContent));
  check('a budget far above what runs now is refused', true);
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
  const order = sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;print(','.join(r['level'] for r in db.query(\\"SELECT level FROM meta_changes WHERE action = 'status' AND new_value = 'ACTIVE' ORDER BY id DESC LIMIT 4\\")[::-1]))"`).trim();
  check('publishing turns on the ads, then the ad set, then the campaign last', order === 'ad,ad,adset,campaign' && Object.values(fake('_campaigns')).slice(-1)[0].status === 'ACTIVE', order);
  await page.screenshot({ path: `${OUT}/flow-new-campaign.png`, fullPage: true });

  // Meta's automatic changes on an ad: read in plain words, warn on the rewriting ones, switch one with a new creative.
  await page.goto(BASE + '/ad.html?id=120252672230740312');
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
  await page.goto(BASE + '/performance.html');
  await page.waitForSelector('.ideas-table');
  const hooks = await page.$$eval('.ideas-table tbody th b', (b) => b.map((x) => x.textContent));
  check('Results groups ads by hook, with both outcome-promise ads in one row', hooks.includes('Outcome promise') && hooks.includes('Question')
    && /N2 - Order portal, N5 - Quote to invoice/.test(await page.textContent('.ideas-table')), hooks.join(' | '));
  check('the cheapest idea says how sure that is', /cheapest/.test(await page.textContent('#ideas')) && /sure/.test(await page.textContent('#ideas .note')));
  await page.click('#idea-by [data-idea="persona"]');
  await page.waitForFunction(() => /Ops and office managers/.test(document.getElementById('ideas').textContent));
  check('the grouping switches to who it is for', /Wholesale and distribution/.test(await page.textContent('#ideas')));
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
  check('Claude can suggest tags: the decision shows them', /Hook.*Outcome promise/s.test(await tp.textContent()) && !/bogus/.test(await tp.textContent()) && /Apply the tags/.test(await tp.textContent()));
  await tp.locator('[data-approve]').click();
  await page.waitForSelector('dialog.confirm');
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction((id) => !document.getElementById(`p-${id}`), tagProp);
  check('approving applies them, marked as from Claude', sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;r=db.query(\\"SELECT value, source FROM ad_tags WHERE ad_id = '120252672233160312' AND dimension = 'hook'\\", one=True);print(r['value'], r['source'])"`).trim() === 'Outcome promise claude');

  // Swipe file: save a competitor ad, long runs flagged, watched Pages, Claude adds what it found.
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute('DELETE FROM swipes');db.execute('DELETE FROM watched_pages')"`);
  await page.goto(BASE + '/research.html');
  await page.waitForSelector('#swipes p');
  await page.fill('#w-name', 'Acme Business Software');
  await page.fill('#w-terms', 'custom software Riverside');
  await page.click('#watch-form button[type=submit]');
  await page.waitForFunction(() => /Acme Business Software/.test(document.getElementById('watched').textContent));
  check('a competitor Page can be watched', /custom software Riverside · not checked yet/.test(await page.textContent('#watched')));
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
    && /checked/.test(await page.textContent('#watched')) && !/not checked yet/.test(await page.textContent('#watched')));
  await page.click('#swipe-filter [data-sf="long"]');
  check('Running 30+ days shows only the long runs', (await page.locator('.swipe').count()) === 2);
  check('the note was kept', await page.evaluate(() => [...document.querySelectorAll('.swipe-note')].some((i) => i.value === 'Same promise as N1')));
  await page.goto(BASE + '/desk.html#schedules');
  await page.waitForSelector('#view');
  await page.waitForTimeout(600);
  check('a weekly Competitor check schedule is offered, off', /Competitor check/.test(await page.textContent('#view')));

  // Meta's advice on Today: score, suggestions in plain words, apply one through the +20% warning, benchmarks from the Mac.
  sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;urllib.request.urlopen(urllib.request.Request('http://localhost:5001/v24.0/120252638288040312?access_token=x', data=b'daily_budget=2000'))"`);
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db,settings_store;settings_store.set('meta_advice',None);settings_store.set('meta_benchmarks',None);db.execute('UPDATE campaigns SET daily_budget_cents = 2000 WHERE id = %s', ('120252638288040312',))"`);
  await page.goto(BASE + '/home.html');
  await page.waitForSelector('.advice-list');
  check("Today shows Meta's Opportunity Score and its suggestions, most points first",
    /87\/100/.test(await page.textContent('#advice')) && (await page.$$eval('.advice-list .ttl b', (b) => b.map((x) => x.textContent))).join('|') === "Spend more on a campaign that's doing well|Add a vertical 9:16 video for Reels");
  check('a suggestion that needs new media points to Ads Manager instead of an Apply button',
    (await page.locator('.advice-list li').nth(1).locator('[data-apply]').count()) === 0 && /Needs a new 9:16 video/.test(await page.textContent('.advice-list li:nth-child(2)')));
  check('a budget suggestion shows the step in dollars and flags more than +20%', /\$20\.00 → \$26\.00 a day \(\+30%\): more than \+20%/.test(await page.textContent('.advice-list li:first-child')));
  const budgetBefore = Object.values(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/v24.0/120252638288040312?access_token=x').read().decode())"`).match(/"daily_budget":"?(\d+)/).slice(1))[0];
  await page.click('[data-apply]');
  await page.waitForSelector('dialog.confirm');
  check('applying it asks first, with the +20% warning, and says "Apply anyway"', /More than \+20% in one step/.test(await page.textContent('dialog.confirm')) && /Apply anyway/.test(await page.textContent('dialog.confirm #cd-ok')));
  await page.click('dialog.confirm #cd-ok');
  await page.waitForFunction(() => /96\/100/.test(document.getElementById('advice').textContent));
  const budgetAfter = sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/v24.0/120252638288040312?access_token=x').read().decode())"`).match(/"daily_budget":"?(\d+)/)[1];
  check('Meta applies it: the budget moves by its step, the score rises, the suggestion goes', budgetBefore === '2000' && budgetAfter === '2600'
    && (await page.locator('.advice-list li').count()) === 1 && /▲ 9/.test(await page.textContent('#advice')), `${budgetBefore} → ${budgetAfter}`);
  check('the change is logged like any other', sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;r=db.query('SELECT action, ok FROM meta_changes ORDER BY id DESC LIMIT 1', one=True);print(r['action'], r['ok'])"`).trim() === 'recommendation True');
  check('without benchmarks yet it says where they come from', /come with Claude's Monday summary/.test(await page.textContent('#advice')));
  const bmk = JSON.parse(sh('docker cp dev/qa_agent_benchmarks.py edgebourne-ads-backend:/app/qa_agent_benchmarks.py && docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python qa_agent_benchmarks.py; docker exec edgebourne-ads-backend rm -f /app/qa_agent_benchmarks.py').trim().split('\n').pop());
  await page.reload();
  await page.waitForSelector('#advice .bench');
  check("the Monday summary's benchmarks show on Today", bmk.body.saved === 2 && /Cost per lead\s*\$4\.79\s*\$18–\$42/.test(await page.textContent('#advice .bench')) && /From Claude's Monday summary, 2026-11-09/.test(await page.textContent('#advice')));
  sh(`docker exec -w /app edgebourne-ads-backend python -c "import db;db.execute(\\"UPDATE campaigns SET daily_budget_cents = 2000 WHERE id = '120252638288040312'\\")"`);

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
  await page.goto(BASE + '/settings.html');
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
  check('a client can change nothing (every change refused) and cannot switch accounts', leak.client_writes_not_refused.length === 0 && leak.client_switch_status === 403 && leak.client_stays_on_own_account,
    leak.client_writes_not_refused.slice(0, 4).join(' | '));
  check('each account still sees its own data', leak.admin_sees_account2_on_account2 && leak.client_sees_own_leads);
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
db.execute(\\"UPDATE accounts SET archived_at = now() WHERE name = 'QA Studio'\\")"`);
  const cctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
  const cp = await cctx.newPage();
  cp.on('pageerror', (e) => errors.push('client page: ' + e.message));
  await cp.goto(BASE + '/login.html');
  await cp.fill('#email', 'client-qa@burdanova.test');
  await cp.fill('#password', 'client-pass-123');
  await Promise.all([cp.waitForURL('**/home.html**'), cp.click('button[type=submit]')]);
  await cp.waitForSelector('.rail .nav a .label');
  const nav = await cp.$$eval('.rail .nav a .label', (a) => a.map((x) => x.textContent.trim()));
  check('a client signs in to their own account with the read-only menu', nav.join() === 'Today,Leads,Ads,Results,Reports' && /Burdanova QA/.test(await cp.textContent('.rail')), nav.join());
  await cp.goto(BASE + '/leads.html');
  await cp.waitForSelector('.lead-row');
  await cp.click('.lead-row');
  await cp.waitForSelector('#stages');
  check("a client sees their leads but not the controls that change them", /ACCT2MARK Lead Person/.test(await cp.textContent('#list'))
    && !(await cp.isVisible('#note-form')) && (await cp.locator('#stages button:visible').count()) <= 1);
  await cp.goto(BASE + '/report.html');
  await cp.waitForSelector('.r-head');
  check("a client opens their own account's report, without the share button", /Burdanova QA/.test(await cp.textContent('.r-head')) && await cp.isHidden('#share'));
  await cctx.close();

  // Client reports: the five parts, a share link without sign-in, the print layout, the scheduled email.
  await page.goto(BASE + '/report.html');
  await page.waitForSelector('.r-head');
  const rep = await page.textContent('#report');
  check('the report reads in the five parts, business result first, with its footnotes',
    /1\. What happened.*Cost per (qualified )?lead.*2\. Why.*3\. What we did.*4\. What's next.*5\. What we need from you/s.test(rep) && /attribution setting/.test(rep), rep.slice(0, 160));
  check('the first sentence measures against the target per qualified lead', /against the \$60\.00 target/.test(await page.textContent('.r-headline')));
  await page.click('#kind [data-kind="month"]');
  await page.waitForFunction(() => /Month/.test(document.querySelector('.r-kicker')?.textContent || ''));
  check('a month report covers the last complete month', /Oct 1 – Oct 31, 2026/.test(await page.textContent('.r-head')));
  const shareUrl = await page.evaluate(async () => (await (await fetch('/api/reports/share', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"kind":"week"}' })).json()).url);
  const anonCtx = await browser.newContext();
  const anon = await anonCtx.newPage();
  await anon.goto(BASE + '/report.html?' + shareUrl.split('?')[1]);
  await anon.waitForSelector('.r-head');
  check('a share link opens the report without signing in, with no menu', /Edge Bourne/.test(await anon.textContent('.r-head')) && (await anon.locator('.rail').count()) === 0 && /This link works until/.test(await anon.textContent('.r-foot')));
  const rSeen = errors.length;
  await anon.goto(BASE + '/report.html?' + shareUrl.split('?')[1].replace(/.$/, (c) => (c === 'a' ? 'b' : 'a')));
  await anon.waitForSelector('#report .note');
  errors.splice(rSeen);
  check('a changed link is refused', /isn't valid or has expired/.test(await anon.textContent('#report')));
  await anon.emulateMedia({ media: 'print' });
  await anonCtx.close();
  await page.emulateMedia({ media: 'print' });
  check('the PDF (print) layout hides the menu and buttons', await page.isHidden('#pdf') && await page.isHidden('.rail'));
  await page.emulateMedia({ media: 'screen' });
  const mailBefore = JSON.parse(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/mail/_sent').read().decode())"`)).length;
  const sent = sh(`docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -c "
import account_ctx, db, settings_store, reports_api
from datetime import datetime, timezone
a2 = db.query(\\"SELECT id FROM accounts WHERE name = 'Burdanova QA'\\", one=True)['id']
with account_ctx.use(a2):
    settings_store.set('report_email', 'weekly'); settings_store.set('report_last_sent', None)
    monday = datetime(2026, 11, 16, 17, 0, tzinfo=timezone.utc)
    print(reports_api.send_due(monday), reports_api.send_due(monday))
    settings_store.set('report_email', None)"`).trim();
  const mails = JSON.parse(sh(`docker exec edgebourne-fake-meta python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:5001/mail/_sent').read().decode())"`)).slice(mailBefore);
  const m = mails.find((x) => /client-qa@burdanova\.test/.test(JSON.stringify(x)));
  check("on Monday the account's clients get the report by email once, with a link that works", sent === '1 0' && !!m && /report\.html\?t=/.test(JSON.stringify(m)) && /Burdanova QA/.test(JSON.stringify(m)), `${sent} ${JSON.stringify(m || {}).slice(0, 160)}`);


  // Ad blockers hide elements whose class or id looks like an ad (EasyList: .ad-cell, .adset, #ads-panel …).
  // An ads console is full of them, so no class or id may start with ad- / ads- / adset / advert / sponsor / banner / promo.
  const risky = [];
  for (const p of ['home.html', 'ads.html', 'ad.html?id=120252672229400312', 'performance.html', 'new-campaign.html', 'new-ad.html', 'desk.html']) {
    await page.goto(BASE + '/' + p);
    await page.waitForTimeout(1500);
    risky.push(...(await page.evaluate(() => [...document.querySelectorAll('[class], [id]')].flatMap((e) => [...(typeof e.className === 'string' ? e.className.split(/\s+/) : []), e.id])
      .filter((n) => /^(ad|ads|adset|adsets|advert|advertisement|sponsor|sponsored|banner|promo|promoted)([-_]|$)/i.test(n)))).map((n) => `${p}: ${n}`));
  }
  check('no class or id an ad blocker would hide', risky.length === 0, [...new Set(risky)].slice(0, 6).join(' | '));

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
  await page.waitForSelector(`[data-proposal="${seeded.budget}"] [data-approve]`);
  await page.click(`[data-proposal="${seeded.budget}"] [data-approve]`);
  await page.waitForSelector('dialog.confirm .big-change');
  const dlg = (await page.textContent('dialog.confirm .big-change')).replace(/\s+/g, ' ');
  check('approving shows the live budget → the new one in dollars', dlg.includes(`$${(seeded.live / 100).toFixed(2)}`) && dlg.includes(`$${(want / 100).toFixed(2)}`), dlg);
  await page.click('dialog.confirm #cd-ok');
  await page.waitForTimeout(1500);
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
  await page.goto(BASE + '/settings.html');
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
    && Object.values(leak.account_admin_limits).every((s) => s === 403) && leak.cross_account_writes.length === 0, JSON.stringify(leak.account_admin_limits) + leak.cross_account_writes.join(' | '));
  check('background work started from one account stays in that account', leak.resync_thread_account.join() === String(leak.account2) && leak.account2_assignments_seen_from_1 === 0);
  // A new ad from nothing: the account's Page, the chosen form, an image from the library.
  const libItem = (await call('GET', '/api/media')).body.items.find((i) => i.kind === 'image' || (i.kind === 'video' && i.ready));
  const crBefore = Object.keys(fake('_creatives')).length;
  const scratch = await call('POST', '/api/ads/new', { adset_id: '120252672227950312', name: 'QA scratch ad', body: 'New words', title: 'New headline',
    media: libItem.kind === 'image' ? { kind: 'image', hash: libItem.hash } : { kind: 'video', video_id: libItem.video_id }, form_id: '1132280359202136' });
  const scr = Object.values(fake('_creatives')).slice(crBefore)[0];
  check('a new ad can start from nothing: the Page, the chosen form, its own image or video', scratch.status === 201 && scr && scr.object_story_spec.page_id
    && (scr.object_story_spec.link_data || scr.object_story_spec.video_data).call_to_action.value.lead_gen_form_id === '1132280359202136', JSON.stringify(scr && scr.object_story_spec).slice(0, 200));
  // Phones: no page wider than the screen.
  const phonePage = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })).newPage();
  await phonePage.goto(BASE + '/login.html');
  await phonePage.fill('#email', 'eugene@edgebourne.com'); await phonePage.fill('#password', 'localdev-pass-123');
  await Promise.all([phonePage.waitForURL('**/home.html**'), phonePage.click('button[type=submit]')]);
  const tooWide = [];
  for (const p of ['/home.html', '/leads.html', '/ads.html', '/ad.html?id=120252672229400312', '/performance.html', '/report.html', '/desk.html', '/team.html', '/settings.html', '/new-campaign.html']) {
    await phonePage.goto(BASE + p); await phonePage.waitForTimeout(1500);
    const sw = await phonePage.evaluate(() => document.documentElement.scrollWidth);
    if (sw > 391) tooWide.push(`${p} ${sw}px`);
  }
  check('on a 390px phone no page is wider than the screen', tooWide.length === 0, tooWide.join(' | '));
  // The refusals above are the point of these checks; the browser logs each as a failed load. Real page errors stay.
  errors.splice(a2Seen, errors.length - a2Seen, ...errors.slice(a2Seen).filter((e) => !/Failed to load resource: the server responded with a status of 4\d\d/.test(e)));

  }
  await browser.close();
  console.log(results.join('\n'));
  console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'no console errors');
})().catch((e) => { console.log(results.join('\n')); console.error(e); process.exit(1); });
