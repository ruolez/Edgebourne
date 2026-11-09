// Local E2E of the Ads controls against the fake Meta server (docker-compose.dev.yml).
// node ads/qa/flows.cjs <out-dir>
const { chromium } = require('/Users/ruolez/Desktop/Dev/meta-ads/creatives/2026-11-07-new5/src/node_modules/playwright-core');
const EXE = process.env.HOME + '/Library/Caches/ms-playwright/chromium-1248/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';
const BASE = process.env.BASE || 'http://ads.localhost:8090';
const OUT = process.argv[2] || 'qa/out';
const IMG = process.argv[3];
const results = [];
const check = (name, ok, extra = '') => { results.push(`${ok ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`); };

(async () => {
  require('fs').mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
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
  check('duplicate opens the new ad with the "created, off" note', (await page.textContent('#ad-name')).includes('flow copy'));
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
    await page.waitForSelector('#ad-status .pill');
    check('new image ad is created and opens off', (await page.textContent('#ad-status')).includes('Off'), await page.textContent('#ad-name'));
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
    await page.waitForSelector('#ad-status .pill');
    check('approving a new-copy proposal creates that ad, switched off',
      (await page.textContent('#ad-name')).includes('·') && (await page.textContent('#ad-status')).includes('Off'), await page.textContent('#ad-name'));
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
  await page.waitForFunction(() => /Archived/.test(document.querySelector('#ad-status')?.textContent || ''));
  check('Archive marks the ad archived and hides the Archive button', !(await page.isVisible('#archive')), await page.textContent('#ad-status'));
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
  check('Schedules lists the four checks, all off', (await page.locator('.sched').count()) === 4 && (await page.locator('.sched [aria-checked="true"]').count()) === 0);
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
  await page.waitForFunction(() => /angle where it lives/.test(document.querySelector('#ad-name')?.textContent || ''));
  check('approving a new-ad decision creates the ad, switched off', /Off/.test(await page.textContent('#ad-status')), await page.textContent('#ad-name'));
  await page.goto(BASE + '/desk.html#runs', { waitUntil: 'networkidle' });
  await page.waitForSelector('#view .task');
  check('All runs folds the scorecard', !(await page.isVisible('#view .scorecard')));

  await browser.close();
  console.log(results.join('\n'));
  console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'no console errors');
})().catch((e) => { console.log(results.join('\n')); console.error(e); process.exit(1); });
