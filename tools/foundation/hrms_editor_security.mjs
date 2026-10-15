// Compile and exercise HRMS's actual FormField/TextEditor with its installed
// dependencies. This is a built-component test, not full authenticated-site E2E.
// Run after secure_hrms.py and the ordinary HRMS asset build. Never serve this
// synthetic harness from the product: temporary inputs and output are removed.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const [frontendArg, playwrightArg, executablePath] = process.argv.slice(2);
assert(frontendArg && playwrightArg, 'usage: node hrms_editor_security.mjs HRMS/frontend PLAYWRIGHT_PACKAGE [CHROMIUM_EXECUTABLE]');
const frontend = path.resolve(frontendArg);
const requireApp = createRequire(path.join(frontend, 'package.json'));
const { build } = await import(pathToFileURL(path.join(path.dirname(requireApp.resolve('vite/package.json')), 'dist/node/index.js')));
const { default: vue } = await import(pathToFileURL(requireApp.resolve('@vitejs/plugin-vue')));
const { chromium } = await import(pathToFileURL(path.resolve(playwrightArg, 'index.mjs')));
const temp = await fs.mkdtemp(path.join(frontend, '.security-editor-'));
let server, browser;
let stage = 'build';
try {
  await fs.writeFile(path.join(temp, 'index.html'), '<!doctype html><html><body><div id="app"></div><script type="module" src="./entry.js"></script></body></html>');
  await fs.writeFile(path.join(temp, 'entry.js'), `
import { createApp, h, reactive, nextTick } from 'vue';
import FormField from '../src/components/FormField.vue';
const state = reactive({html: '<p>Safe initial text</p>', readOnly: false, key: 0});
window.__executed = 0;
window.editorTest = {
  importHTML: async (html, readOnly = false) => { state.html = html; state.readOnly = readOnly; state.key++; await nextTick(); },
  html: () => state.html,
};
const app = createApp({render: () => h(FormField, {
  key: state.key, fieldtype: 'Text Editor', label: 'SYNTHETIC Security Editor',
  modelValue: state.html, readOnly: state.readOnly,
  'onUpdate:modelValue': html => { state.html = html; },
})});
app.provide('$translate', s => s);
app.mount('#app');
`);
  const originalCwd = process.cwd();
  try {
    process.chdir(frontend);
    await build({
      configFile: false, root: temp, plugins: [vue()],
      resolve: { alias: { '@': path.join(frontend, 'src') } },
      build: { outDir: path.join(temp, 'output'), emptyOutDir: true },
    });
  } finally { process.chdir(originalCwd); }
  const output = path.join(temp, 'output');
  server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url, 'http://localhost');
      const relative = url.pathname === '/' ? 'index.html' : url.pathname.slice(1);
      const file = path.resolve(output, relative);
      if (!file.startsWith(output + path.sep)) throw new Error('invalid path');
      response.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
      response.end(await fs.readFile(file));
    } catch { response.writeHead(404); response.end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ headless: true, ...(executablePath ? {executablePath} : {}), args: ['--no-sandbox'] });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('dialog', dialog => dialog.accept());
  await page.route('**/*', route => route.request().url().startsWith(origin + '/') ? route.continue() : route.abort());
  await page.goto(origin);
  await page.locator('.ProseMirror').waitFor();
  stage = 'setup';
  const payloads = [
    '<p>kept<script>window.__executed++</script></p>',
    '<img src=x onerror="window.__executed++"><p>kept</p>',
    '<a href="javascript:window.__executed++">kept</a>',
    '<a href="java&#x09;script:window.__executed++">kept</a>',
    '<svg onload="window.__executed++"><a xlink:href="javascript:window.__executed++">kept</a></svg>',
    '<math><mtext><table><mglyph><style><!--</style><img title="--><img src=x onerror=window.__executed++>">',
    '<svg><foreignObject><div><img src=x onerror="window.__executed++"></div></foreignObject></svg>',
    '<iframe srcdoc="<script>parent.__executed++</script>"></iframe><p>kept</p>',
    '<p style="background:url(javascript:window.__executed++)" onclick="window.__executed++">kept</p>',
  ];
  const assertSafe = async () => {
    // Event dispatch plus two animation frames gives mutations and image error
    // handlers an opportunity to execute; also inspect the resulting DOM.
    const result = await page.evaluate(async () => {
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      const root = document.querySelector('.ProseMirror');
      root.querySelectorAll('a').forEach(a => a.click());
      return {
        executed: window.__executed,
        scripts: root.querySelectorAll('script,iframe,object,embed,svg,math').length,
        eventAttributes: [...root.querySelectorAll('*')].flatMap(el => [...el.attributes]).filter(a => /^on/i.test(a.name)).length,
        scriptLinks: [...root.querySelectorAll('a[href]')].filter(a => /^(javascript|vbscript|data):/i.test(a.getAttribute('href').replace(/\s/g, ''))).length,
      };
    });
    assert.deepEqual(result, {executed: 0, scripts: 0, eventAttributes: 0, scriptLinks: 0});
    assert.deepEqual(errors, [], 'built editor raised an uncaught exception');
  };
  for (const html of payloads) {
    stage = 'import-and-read-only';
    for (const readOnly of [false, true]) {
      await page.evaluate(({html, readOnly}) => window.editorTest.importHTML(html, readOnly), {html, readOnly});
      await assertSafe();
    }
    stage = 'paste';
    await page.evaluate(() => window.editorTest.importHTML('<p>paste target</p>'));
    await page.locator('.ProseMirror').click();
    await page.evaluate(html => {
      const clipboardData = new DataTransfer();
      clipboardData.setData('text/html', html);
      clipboardData.setData('text/plain', 'kept');
      document.querySelector('.ProseMirror').dispatchEvent(new ClipboardEvent('paste', {clipboardData, bubbles: true, cancelable: true}));
    }, html);
    await assertSafe();
  }
  // Frappe UI has a separate Markdown-to-HTML clipboard path. Exercise that
  // conversion too, not only ProseMirror's ordinary text/html paste handling.
  for (const html of payloads) {
    stage = 'markdown-paste';
    await page.evaluate(() => window.editorTest.importHTML('<p>Markdown paste target</p>'));
    await page.locator('.ProseMirror').click();
    await page.evaluate(html => {
      const clipboardData = new DataTransfer();
      clipboardData.setData('text/plain', '**Markdown**\n\n' + html);
      document.querySelector('.ProseMirror').dispatchEvent(new ClipboardEvent('paste', {clipboardData, bubbles: true, cancelable: true}));
    }, html);
    await assertSafe();
  }
  stage = 'legitimate-editing';
  await page.evaluate(() => window.editorTest.importHTML('<p><strong>Valid bold</strong> <em>and italic</em></p><ul><li>List item</li></ul>'));
  assert.equal(await page.locator('.ProseMirror strong').textContent(), 'Valid bold');
  assert.equal(await page.locator('.ProseMirror em').textContent(), 'and italic');
  assert.equal(await page.locator('.ProseMirror li').textContent(), 'List item');
  await page.locator('.ProseMirror').click();
  await page.keyboard.press('Control+End');
  await page.keyboard.type(' editing works');
  assert.match(await page.evaluate(() => window.editorTest.html()), /editing works/);
  await assertSafe();
  // Keyboard formatting shortcut on an ordinary selection (Mod-b = bold).
  stage = 'keyboard-formatting';
  await page.evaluate(() => window.editorTest.importHTML('<p>formatme</p>'));
  await page.locator('.ProseMirror').click();
  await page.keyboard.press('Control+Home');
  await page.keyboard.press('Shift+End');
  // ProseMirror syncs its selection from the DOM on selectionchange, which
  // the browser dispatches after the keystroke. Flush two frames before the
  // shortcut; without this, Chromium 153 + Playwright 1.58 raced and dropped Mod-b.
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.keyboard.press('Control+b');
  assert.equal(await page.locator('.ProseMirror strong').textContent(), 'formatme', 'keyboard bold shortcut must still format');
  await assertSafe();
  // Read-only must reject keyboard input and leave the stored content unchanged.
  stage = 'read-only-keyboard';
  await page.evaluate(() => window.editorTest.importHTML('<p>locked text</p>', true));
  await page.locator('.ProseMirror').click({force: true});
  await page.keyboard.type('ZZTAMPER');
  const lockedHtml = await page.evaluate(() => window.editorTest.html());
  assert.doesNotMatch(lockedHtml, /ZZTAMPER/, 'read-only editor accepted keyboard input');
  await assertSafe();
  // Stored-content reload: serialize what the editor holds, reload it as if
  stage = 'stored-reload';
  // from storage, and require the same safe, legitimate content back.
  await page.evaluate(() => window.editorTest.importHTML('<p><strong>Stored bold</strong> and <em>italic</em></p><ul><li>Kept item</li></ul>'));
  const stored = await page.evaluate(() => window.editorTest.html());
  await page.evaluate(() => window.editorTest.importHTML('<p>placeholder</p>'));
  await page.evaluate(html => window.editorTest.importHTML(html, false), stored);
  await assertSafe();
  assert.equal(await page.locator('.ProseMirror strong').first().textContent(), 'Stored bold');
  assert.equal(await page.locator('.ProseMirror li').textContent(), 'Kept item');
  console.log(JSON.stringify({status: 'pass', payloads: payloads.length, paths: ['import', 'read-only rendering', 'paste', 'markdown paste', 'stored reload', 'read-only keyboard rejection'], legitimateEditing: true, keyboardFormatting: true}));
} catch (error) {
  // One line, no page content: the failing stage and the error class only.
  console.error(`HRMS-EDITOR-STAGE-FAILED ${stage} ${error && error.name ? error.name : 'Error'}`);
  throw error;
} finally {
  if (browser) await browser.close();
  if (server) await new Promise(resolve => server.close(resolve));
  await fs.rm(temp, {recursive: true, force: true});
}
