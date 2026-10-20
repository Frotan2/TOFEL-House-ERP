import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<!doctype html><html><body></body></html>', { pretendToBeVisual: true });
for (const k of ['window', 'document', 'navigator', 'Node', 'HTMLElement', 'DOMParser', 'getComputedStyle']) if (!(k in globalThis)) globalThis[k] = dom.window[k];
for (const n of ['ClipboardEvent', 'DragEvent', 'InputEvent', 'CompositionEvent', 'KeyboardEvent', 'MouseEvent', 'FocusEvent']) if (!globalThis[n]) globalThis[n] = class extends dom.window.Event {};
const { Editor } = await import('@tiptap/core');
const { default: StarterKit } = await import('@tiptap/starter-kit');
const { default: Link } = await import('@tiptap/extension-link');
const version = JSON.parse(readFileSync('node_modules/@tiptap/extension-link/package.json', 'utf8')).version;
const hrefs = (editor) => { const r = []; editor.state.doc.descendants((n) => { for (const m of n.marks || []) if (m.type.name === 'link') r.push(m.attrs.href); }); return r; };
const attempt = (label, run) => {
  const host = dom.window.document.createElement('div'); dom.window.document.body.appendChild(host);
  const editor = new Editor({ element: host, extensions: [StarterKit, Link.configure({ openOnClick: false })], content: '<p>hello world</p>' });
  editor.commands.setTextSelection({ from: 1, to: 6 });
  let result;
  try { result = run(editor); } catch (e) { result = 'threw: ' + e.message; }
  const out = { result: String(result), link_hrefs: hrefs(editor), html: editor.getHTML() };
  editor.destroy(); host.remove();
  return [label, out];
};
const payload = 'javascript:alert(1)';
const out = { version, cases: Object.fromEntries([
  attempt('setLink javascript', (e) => e.commands.setLink({ href: payload })),
  attempt('toggleLink javascript', (e) => e.commands.toggleLink({ href: payload })),
  attempt('setLink https (control)', (e) => e.commands.setLink({ href: 'https://example.com/x' })),
]) };
console.log(JSON.stringify(out));
