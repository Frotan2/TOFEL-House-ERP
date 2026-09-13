// Real Chromium against the unchanged Education portal, not a simulated UI.
import { chromium } from 'playwright';
import fs from 'node:fs';
if (process.env.GITHUB_ACTIONS !== 'true') throw new Error('Disposable Actions runner only');
const records = JSON.parse(fs.readFileSync(process.env.FOUNDATION_BUSINESS_REPORT)).records;
const output = process.env.FOUNDATION_BROWSER_REPORT;
const report = { status: 'running', scope: 'Chromium; native portal behind loopback Nginx; synthetic data', checks: [], phase2_gate_passed: false };
function requireCondition(ok, message) { if (!ok) throw new Error(message); }
async function check(name, fn) {
  try { report.checks.push({ name, status: 'pass', observation: await fn() }); }
  catch (e) { report.checks.push({ name, status: 'fail', exception: e.name, message: String(e.message).slice(0, 250) }); }
  fs.writeFileSync(output, JSON.stringify(report, null, 2));
}
let browser;
try {
  browser = await chromium.launch({ headless: true });
  report.browser_version = browser.version();
  const contexts = {};
  for (const [index, label] of ['alpha', 'beta'].entries()) {
    await check(label + '-native-login-and-portal', async () => {
      const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
      contexts[label] = context;
      const page = await context.newPage();
      await page.goto('http://foundation.localhost:8080/login');
      await page.locator('#login_email').fill(`validation-${label}@example.test`);
      await page.locator('#login_password').fill(process.env.FOUNDATION_TEST_PASSWORD);
      const [response] = await Promise.all([
        page.waitForResponse(r => r.url().endsWith('/api/method/login') && r.request().method() === 'POST'),
        page.locator('.for-login .form-login .btn-login[type=submit]').click(),
      ]);
      requireCondition(response.status() === 200, 'native login failed');
      // Try to select the other student through URL and persisted portal selection.
      await page.goto('http://foundation.localhost:8080/edu-portal');
      await page.evaluate(other => localStorage.setItem('education-active_student', JSON.stringify(other)), records.students[1-index]);
      const [r] = await Promise.all([
        page.waitForResponse(r => r.url().includes('education.education.api.get_student_invoices'), { timeout: 30000 }),
        page.goto('http://foundation.localhost:8080/edu-portal/fees?student=' + encodeURIComponent(records.students[1-index])),
      ]);
      requireCondition(r.status() === 200, 'portal invoices RPC failed');
      const data = (await r.json()).message;
      if (label === 'alpha') {
        requireCondition(data.invoices.some(i => i.invoice === records.invoice), 'own invoice absent');
        await page.getByText('Validation Program', { exact: true }).first().waitFor({ state: 'visible' });
      } else {
        requireCondition(!data.invoices.some(i => i.invoice === records.invoice), 'other invoice disclosed through portal');
      }
      requireCondition(await page.locator('#app').innerText() !== '', 'portal did not render');
      await page.setViewportSize({ width: 390, height: 844 });
      requireCondition(await page.locator('#app').isVisible(), 'portal absent at mobile viewport');
      return { native_login: true, portal_rendered: true, tampered_student_selection_isolated: true, mobile_render_only: true };
    });
  }
  for (const [label, index] of [['alpha',0], ['beta',1]]) {
    await check(label+'-browser-rest-rpc-and-file-isolation', async () => {
      const page = contexts[label].pages()[0];
      const result = await page.evaluate(async ({ own, other, file, owner }) => {
        const get = async path => {
          const r = await fetch(path, { credentials: 'same-origin' });
          return { status: r.status, response: r };
        };
        const a = await get('/api/resource/Student/' + encodeURIComponent(own));
        const b = await get('/api/resource/Student/' + encodeURIComponent(other));
        const c = await get('/api/method/education.education.api.get_student_context?student=' + encodeURIComponent(other));
        const d = await get(file);
        let hash;
        if (owner && d.status === 200) {
          const digest = await crypto.subtle.digest('SHA-256', await d.response.arrayBuffer());
          hash = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2,'0')).join('');
        }
        return { own: a.status, other: b.status, rpc: c.status, file: d.status, hash };
      }, { own: records.students[index], other: records.students[1-index], file: records.private_file_url, owner: label==='alpha' });
      requireCondition(result.own===200 && result.other===403 && result.rpc===403, 'browser API/RPC isolation failed');
      requireCondition(label==='alpha' ? result.file===200 && result.hash===records.private_file_sha256 : result.file===403, 'browser private file isolation failed');
      return { own_http:result.own, other_http:result.other, rpc_http:result.rpc, file_http:result.file };
    });
  }
  await check('browser-cross-site-session-replay-denied', async () => {
    const cookies = await contexts.alpha.cookies('http://foundation.localhost:8080');
    const sid = cookies.find(c => c.name==='sid');
    requireCondition(sid && sid.value !== 'Guest', 'source session missing');
    const target = await browser.newContext();
    await target.addCookies([{ ...sid, domain: 'restore.localhost' }]);
    const page = await target.newPage();
    const r = await page.goto('http://restore.localhost:8080/api/method/frappe.auth.get_logged_user');
    requireCondition([401,403].includes(r.status()), 'source session accepted on restore site');
    await target.close();
    return { cross_site_sid_rejected: true };
  });
} catch (e) {
  report.checks.push({name:'browser-prerequisite',status:'fail',exception:e.name,message:String(e.message).slice(0,250)});
} finally {
  if (browser) await browser.close();
  report.status = report.checks.length && report.checks.every(c=>c.status==='pass') ? 'pass' : 'fail';
  fs.writeFileSync(output, JSON.stringify(report, null, 2));
}
process.exitCode = report.status==='pass' ? 0 : 1;
