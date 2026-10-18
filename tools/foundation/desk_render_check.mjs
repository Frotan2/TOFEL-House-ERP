// Real Chromium against the real Desk (2026-10-18). Synthetic data only.
// Logs in as the dedicated HR user, opens the Job Opening Template whose Text Editor value was stored
// with hostile payloads, and checks the rendered page. Checks run on the first open and after a reload.
// A positive control runs first: an inline handler inserted through innerHTML must execute on this page.
// Without that control, "nothing executed" could only mean the detector never saw anything.
import { chromium } from 'playwright';
import fs from 'node:fs';

if (process.env.GITHUB_ACTIONS !== 'true') throw new Error('Disposable Actions runner only');
const fixture = JSON.parse(fs.readFileSync(process.env.FOUNDATION_DESK_FIXTURE, 'utf-8'));
const output = process.env.FOUNDATION_DESK_REPORT;
const base = 'http://foundation.localhost:8080';
const flag = '__synthetic_pwned';
const report = { status: 'running', scope: 'Chromium; Desk form; stored HRMS Text Editor value; synthetic data', checks: [] };

function save() { fs.writeFileSync(output, JSON.stringify(report, null, 2)); }
function requireCondition(ok, message) { if (!ok) throw new Error(message); }
async function check(name, fn) {
  try {
    report.checks.push({ name, status: 'pass', observation: await fn() });
    save();
  } catch (e) {
    report.checks.push({ name, status: 'fail', exception: e.name, message: String(e.message).slice(0, 250) });
    save();
    throw e;
  }
}

let browser;
try {
  browser = await chromium.launch({ headless: true });
  report.browser_version = browser.version();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  let dialogs = 0;
  page.on('dialog', async (dialog) => { dialogs += 1; await dialog.dismiss(); });

  await check('desk-login', async () => {
    await page.goto(base + '/login');
    await page.locator('#login_email').fill(fixture.user);
    await page.locator('#login_password').fill(process.env.FOUNDATION_TEST_PASSWORD);
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().endsWith('/api/method/login') && r.request().method() === 'POST'),
      page.locator('.for-login .form-login .btn-login[type=submit]').click(),
    ]);
    requireCondition(response.status() === 200, 'desk login failed');
    return { login: 'ok', user_role: 'HR User (dedicated fixture user)' };
  });

  await check('detector-positive-control', async () => {
    const executed = await page.evaluate(() => new Promise((resolve) => {
      const holder = document.createElement('div');
      holder.innerHTML = '<img src=x onerror="window.__synthetic_control=1">';
      document.body.appendChild(holder);
      setTimeout(() => { holder.remove(); resolve(window.__synthetic_control === 1); }, 500);
    }));
    requireCondition(executed === true, 'detector did not observe a control handler: the check is blind');
    return { control_handler_executed: true };
  });

  const formUrl = base + '/app/job-opening-template/' + encodeURIComponent(fixture.name);
  for (const phase of ['first-open', 'reload']) {
    await check('desk-form-' + phase, async () => {
      await page.goto(formUrl, { waitUntil: 'domcontentloaded' });
      if (phase === 'reload') await page.reload({ waitUntil: 'domcontentloaded' });
      await page.waitForFunction(() => document.body.innerText.includes('SYNTHETIC'), null, { timeout: 90000 });
      await page.waitForTimeout(2000);
      const state = await page.evaluate((name) => ({
        executed: window[name] !== undefined,
        inline_handlers: document.querySelectorAll('[onerror],[onload]').length,
        javascript_links: [...document.querySelectorAll('a[href]')]
          .filter((a) => /^\s*javascript:/i.test(a.getAttribute('href') || '')).length,
        srcdoc_frames: document.querySelectorAll('iframe[srcdoc]').length,
        formatting_rendered: [...document.querySelectorAll('strong')].some((s) => s.textContent.includes('formatted')),
      }), flag);
      requireCondition(!state.executed, 'a hostile handler executed in the rendered Desk form');
      requireCondition(state.inline_handlers === 0, 'inline event handler present in the rendered form');
      requireCondition(state.javascript_links === 0, 'javascript: link present in the rendered form');
      requireCondition(state.srcdoc_frames === 0, 'srcdoc frame present in the rendered form');
      requireCondition(state.formatting_rendered, 'legitimate formatting was not rendered');
      requireCondition(dialogs === 0, 'a dialog opened during rendering');
      return { ...state, dialogs };
    });
  }
  report.status = 'pass';
  save();
} catch (e) {
  report.status = 'fail';
  report.message = String(e.message).slice(0, 250);
  save();
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
}
