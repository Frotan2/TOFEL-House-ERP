"""Reproduce the pinned setup crash and exercise the corrected lifecycle."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.foundation import fix_setup_sidebar as fix

FIXTURE = Path(__file__).parent / "fixtures" / "sidebar-988e54f3.js"
NODE_CASE = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const context = {frappe: {boot: {setup_complete: false}, ui: {}},
  SidebarEditor: class { constructor() { this.edit_mode = false; } }};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8').replace(/^import .*;\r?\n/gm, ''), context);
const Sidebar = context.frappe.ui.Sidebar;
const initial = new Sidebar();
assert.equal(initial.wrapper, undefined);
if (process.argv[2] === 'upstream') {
  assert.throws(() => initial.toggle(false), /reading 'show'/);
  assert.throws(() => initial.toggle(true), /reading 'hide'/);
} else {
  initial.toggle(false);
  initial.toggle(true);
}
// Setup completion reloads Desk and creates the fully initialized sidebar.
let shown = 0, hidden = 0;
const wrapper = {find: () => ({}), show: () => shown++, hide: () => hidden++};
Sidebar.prototype.make_dom = function () { this.wrapper = wrapper; };
Sidebar.prototype.setup_events = function () {};
context.frappe.boot.setup_complete = true;
const completed = new Sidebar();
completed.toggle(false);
completed.toggle(true);
assert.equal(shown, 1);
assert.equal(hidden, 1);
// Unexpected missing DOM after setup still fails; errors are not swallowed.
delete completed.wrapper;
assert.throws(() => completed.toggle(false), /reading 'show'/);
"""


class SetupSidebarTests(unittest.TestCase):
    def test_real_pinned_source_reproduces_crash_and_fix_preserves_normal_sidebar(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the browser lifecycle regression")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / fix.TARGET
            target.parent.mkdir(parents=True)
            target.write_bytes(FIXTURE.read_bytes())
            for stage in ("upstream", "fixed"):
                if stage == "fixed":
                    self.assertEqual(fix.apply(root), "applied")
                    self.assertEqual(fix.apply(root), "already-applied")
                    self.assertEqual(fix.apply(root, verify_only=True), "verified")
                result = subprocess.run([node, "-e", NODE_CASE, str(target), stage],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            target.write_bytes(target.read_bytes() + b"// drift\n")
            before = target.read_bytes()
            with self.assertRaisesRegex(ValueError, "Unreviewed"):
                fix.apply(root)
            self.assertEqual(target.read_bytes(), before)

    def test_verify_refuses_original_without_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / fix.TARGET
            target.parent.mkdir(parents=True)
            original = FIXTURE.read_bytes()
            target.write_bytes(original)
            with self.assertRaisesRegex(ValueError, "not applied"):
                fix.apply(root, verify_only=True)
            self.assertEqual(target.read_bytes(), original)
