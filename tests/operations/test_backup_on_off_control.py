"""End-to-end contracts for the independent Course Owner backup safety switch."""
import ast
import json
from pathlib import Path
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps" / "toefl_house" / "toefl_house"
CONTROL = APP / "operations" / "doctype" / "th_backup_control"
SOURCE = APP / "operations" / "owner_configuration.py"
AUDIT = APP / "configuration" / "audit.py"
DESK = APP / "desk" / "configuration.py"
CLIENT = APP / "public" / "js" / "th_role_desks.js"
WINDOWS = ROOT / "product" / "windows" / "Backup TOEFL House ERP.ps1"


class BackupSwitchContracts(unittest.TestCase):
    def test_single_setting_is_off_by_default_and_not_directly_editable(self):
        definition = json.loads((CONTROL / "th_backup_control.json").read_text(encoding="utf-8"))
        self.assertEqual(definition["name"], "TH Backup Control")
        self.assertEqual(definition["issingle"], 1)
        fields = {field["fieldname"]: field for field in definition["fields"]}
        self.assertEqual(fields["enabled"]["fieldtype"], "Check")
        self.assertEqual(fields["enabled"]["default"], "0")
        self.assertTrue(fields["switch_nonce"]["hidden"])
        self.assertTrue(fields["switch_nonce"]["read_only"])
        roles = {role["role"]: role for role in definition["permissions"]}
        self.assertEqual(set(roles), {"Course Owner"})
        self.assertEqual(roles["Course Owner"]["read"], 1)
        self.assertFalse(roles["Course Owner"]["write"])
        self.assertFalse(roles["Course Owner"]["create"])
        self.assertFalse(roles["Course Owner"]["delete"])

    def test_controller_refuses_direct_native_edits(self):
        source = (CONTROL / "th_backup_control.py").read_text(encoding="utf-8")
        self.assertIn('foundation.active_command() != "set_backup_enabled"', source)
        self.assertIn("frappe.PermissionError", source)
        self.assertIn("fresh switch identity", source)
        self.assertIn("changed_by", source)
        self.assertIn("changed_at", source)

    def test_only_course_owner_can_use_audited_post_command(self):
        text = SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(text)
        fn = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "set_backup_enabled")
        self.assertTrue(any(isinstance(dec, ast.Call) and
                            ast.unparse(dec.func) == "frappe.whitelist" and
                            ast.unparse(dec).find("POST") >= 0
                            for dec in fn.decorator_list))
        self.assertIn('configuration_audit.execute', ast.unparse(fn))
        self.assertIn('doc.save(ignore_permissions=True)', ast.unparse(fn))
        self.assertIn('secrets.token_hex(16)', ast.unparse(fn))
        authorities = next(ast.literal_eval(node.value) for node in ast.parse(
            AUDIT.read_text(encoding="utf-8")).body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "KIND_AUTHORITY"
                    for t in node.targets))
        self.assertEqual(authorities["set_backup_enabled"], "business_policy")

    def test_actual_switch_action_is_idempotent_and_does_not_start_backup(self):
        src = ast.parse(SOURCE.read_text(encoding="utf-8"))
        fn_names = {"set_backup_enabled", "_bool"}
        selected = [n for n in src.body if isinstance(n, ast.FunctionDef) and n.name in fn_names]
        module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
        saves = []
        doc = SimpleNamespace(enabled=0, switch_nonce="", changed_by=None, changed_at=None)
        doc.save = lambda **kwargs: saves.append(kwargs)
        captured = []

        def execute(kind, request_key, payload, work):
            captured.append((kind, request_key, payload))
            return work("owner@example.invalid")[0]

        gate = SimpleNamespace(execute=execute, latest_after_hash=lambda _: "last-event")
        frappe = SimpleNamespace(
            whitelist=lambda **kwargs: (lambda func: func),
            ValidationError=ValueError,
            get_single=lambda doctype: doc if doctype == "TH Backup Control" else None,
            utils=SimpleNamespace(now_datetime=lambda: "2026-10-25 12:00:00"),
        )
        space = {
            "frappe": frappe, "configuration_audit": gate,
            "BACKUP_CONTROL": "TH Backup Control",
            "secrets": SimpleNamespace(token_hex=lambda length: "a" * (length * 2)),
            "digest": lambda obj: "digest:" + str(obj),
        }
        exec(compile(module, str(SOURCE), "exec"), space)
        result = space["set_backup_enabled"]("unique-key", 1)
        self.assertEqual(result["enabled"], True)
        self.assertEqual(result["status"], "ON")
        self.assertEqual(doc.enabled, 1)
        self.assertEqual(doc.switch_nonce, "a" * 32)
        self.assertEqual(doc.changed_by, "owner@example.invalid")
        self.assertEqual(saves, [{"ignore_permissions": True}])
        self.assertEqual(captured[0], ("set_backup_enabled", "unique-key", {"enabled": True}))
        off = space["set_backup_enabled"]("another-key", 0)
        self.assertEqual(off["status"], "OFF")
        self.assertEqual(doc.enabled, 0)
        with self.assertRaisesRegex(ValueError, "true or false"):
            space["set_backup_enabled"]("invalid-key", "perhaps")

    def test_configuration_shows_toggle_without_running_backups(self):
        desk = DESK.read_text(encoding="utf-8")
        js = CLIENT.read_text(encoding="utf-8")
        script = WINDOWS.read_text(encoding="utf-8")
        self.assertIn("items=[_backup_switch_item(), _owner_policy_item(", desk)
        self.assertIn('"status": "On" if enabled else "Off (default)"', desk)
        self.assertIn('"label": "Turn backup Off" if enabled else "Turn backup On"', desk)
        self.assertIn('"args": {"enabled": 0 if enabled else 1}', desk)
        self.assertIn('"toefl_house.operations.owner_configuration.set_backup_enabled"', js)
        self.assertIn('fieldname: "enabled", label: "Backup On / Off"', js)
        self.assertIn('if ($policy.status -ceq "OFF")', script)
        self.assertLess(script.index('if ($policy.status -ceq "OFF")'),
                        script.index('Write-Host "Enabling native encrypted backups..."'))
        self.assertIn("No new backup, retention rotation or scheduled task change was made", script)


if __name__ == "__main__":
    unittest.main()
