// Real Chromium against the real Desk (2026-10-18). Synthetic data only.
// Logs in as the dedicated HR user, opens the Job Opening Template whose Text Editor value was stored
// with hostile payloads, and checks the rendered page. Checks run on the first open and after a reload.
// A positive control runs first: an inline handler inserted through innerHTML must execute on this page.
// Without that control, "nothing executed" could only mean the detector never saw anything.
// The markup checks are scoped to the rendered description field, where the stored value appears.
// Page-wide counts are recorded for diagnosis only, because Desk chrome may carry its own handlers.
import { chromium } from 'playwright';
import fs from 'node:fs';

if (process.env.GITHUB_ACTIONS !== 'true') throw new Error('Disposable Actions runner only');
const fixture = JSON.parse(fs.readFileSync(process.env.FOUNDATION_DESK_FIXTURE, 'utf-8'));
const output = process.env.FOUNDATION_DESK_REPORT;
const base = 'http://foundation.localhost:8080';
const flag = '__synthetic_pwned';
const fieldSelector = '[data-fieldname="description"]';
const report = { status: 'running', scope: 'Chromium; Desk form; stored HRMS Text Editor value; synthetic data', checks: [] };

function save() { fs.writeFileSync(output, JSON.stringify(report, null, 2)); }
function requireCondition(ok, message) { if (!ok) throw new Error(message); }
// One line, no page content: the failing stage, the error class, and a short message restricted to a
// safe character set (our own fixed assertion texts). The runtime turns this line into a check annotation,
// because hosted job logs and artifacts cannot be downloaded from the validation environment.
function stageLine(stage, e) {
  const text = String(e && e.message ? e.message : '').replace(/\s+/g, ' ').replace(/[^A-Za-z0-9 .,:'()=_/-]/g, '').slice(0, 120).trim();
  const errorName = String(e && e.name ? e.name : 'Error').replace(/[^A-Za-z]/g, '').slice(0, 40) || 'Error';
  return `DESK-RENDER-STAGE-FAILED ${stage} ${errorName} ${text}`.trimEnd();
}
async function check(name, fn) {
  try {
    report.checks.push({ name, status: 'pass', observation: await fn() });
    save();
  } catch (e) {
    report.checks.push({ name, status: 'fail', exception: e.name, message: String(e.message).slice(0, 250) });
    save();
    console.error(stageLine(name, e));
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
    // The login response returns before the browser follows the redirect into Desk. Wait for the
    // navigation to settle, so no evaluation runs in a context that is about to be replaced.
    await page.waitForURL((url) => url.pathname !== '/login', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('domcontentloaded');
    return { login: 'ok', user_role: 'HR User (dedicated fixture user)', landed_path: new URL(page.url()).pathname };
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
      // Prefer the wrapper that holds the synthetic value; fall back to the first wrapper so that a
      // missing value fails on the explicit assertions below rather than on a selector guess.
      await page.waitForFunction((sel) => {
        const all = [...document.querySelectorAll(sel)];
        return all.some((f) => f.innerText.includes('SYNTHETIC'));
      }, fieldSelector, { timeout: 90000 });
      await page.waitForTimeout(2000);
      const state = await page.evaluate(({ name, sel }) => {
        const all = [...document.querySelectorAll(sel)];
        const field = all.find((f) => f.innerText.includes('SYNTHETIC')) || all[0] || null;
        const scoped = (query) => (field ? field.querySelectorAll(query) : []);
        return {
          executed: window[name] !== undefined,
          field_found: !!field,
          field_inline_handlers: scoped('[onerror],[onload]').length,
          field_javascript_links: [...scoped('a[href]')]
            .filter((a) => /^\s*javascript:/i.test(a.getAttribute('href') || '')).length,
          field_srcdoc_frames: scoped('iframe[srcdoc]').length,
          field_formatting_rendered: [...scoped('strong')].some((s) => s.textContent.includes('formatted')),
          field_outer_html_sample: field ? field.outerHTML.slice(0, 800) : '',
          page_wide_inline_handlers: document.querySelectorAll('[onerror],[onload]').length,
          page_wide_javascript_links: [...document.querySelectorAll('a[href]')]
            .filter((a) => /^\s*javascript:/i.test(a.getAttribute('href') || '')).length,
        };
      }, { name: flag, sel: fieldSelector });
      requireCondition(!state.executed, 'a hostile handler executed in the rendered Desk form');
      requireCondition(state.field_found, 'description field wrapper not found in the Desk form');
      requireCondition(state.field_inline_handlers === 0, 'inline event handler present in the rendered description field');
      requireCondition(state.field_javascript_links === 0, 'javascript: link present in the rendered description field');
      requireCondition(state.field_srcdoc_frames === 0, 'srcdoc frame present in the rendered description field');
      requireCondition(state.field_formatting_rendered, 'legitimate formatting was not rendered in the description field');
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
  if (!report.checks.some((c) => c.status === 'fail')) console.error(stageLine('launch', e));
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
}
