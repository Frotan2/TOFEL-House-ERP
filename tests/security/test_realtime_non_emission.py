# -*- coding: utf-8 -*-
"""Pins the realtime non-emission invariant (SEC-RT-TASK-01 product side).

Evidence basis: docs/engineering/UPSTREAM-TRACKING.md §1 recorded on
2026-09-16 that owned code contains **zero** realtime emit/publish sites —
the product never enqueues task/progress/business-payload socket events —
while `apps/foundation_security` supplies the deny-by-default
subscription-side authorizer. That grep was a one-off record; without a
mechanical pin a future feature could quietly introduce an emit site and the
guard's fail-closed design would be reading an invariant that no longer
exists. This test runs the same check on every suite execution:

- no `publish_realtime` / `realtime_subscribe` (Python emit APIs),
- no `frappe.realtime.emit` / `socketio.emit` / `realtime.emit` (JS emit
  paths),

anywhere under `apps/` (Python, JS, CJS/MJS, JSON, HTML, CSS). Subscription
is deliberately not forbidden: client listeners are authorized server-side by
the guard, which stays deny-by-default. The guard's own runtime behaviour is
covered by tests/foundation/test_realtime_guard.cjs; this pin covers the
emit side across the whole owned tree.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPS = ROOT / "apps"

FORBIDDEN = (
    "publish_realtime",
    "realtime_subscribe",
    "frappe.realtime.emit",
    "socketio.emit",
    "realtime.emit",
)

SUFFIXES = {".py", ".js", ".cjs", ".mjs", ".json", ".html", ".css"}


def _owned_files():
    for path in sorted(APPS.rglob("*")):
        if path.is_file() and path.suffix in SUFFIXES:
            yield path


class RealtimeNonEmissionTests(unittest.TestCase):

    def test_owned_tree_has_no_realtime_emit_sites(self):
        offenders = []
        for path in _owned_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in FORBIDDEN:
                if token in text:
                    offenders.append(f"{path.relative_to(ROOT)}: {token}")
        self.assertEqual([], offenders,
                         "realtime emit sites are prohibited in owned code; "
                         "see UPSTREAM-TRACKING.md §1 / SEC-RT-TASK-01")

    def test_the_scan_is_not_vacuous(self):
        # Guard against the scan silently covering nothing after a future
        # restructure: both apps must be walked and must contain sources.
        files = list(_owned_files())
        self.assertGreater(len(files), 100, "scan must cover the owned tree")
        roots = {p.relative_to(APPS).parts[0] for p in files}
        self.assertEqual({"toefl_house", "foundation_security"}, roots)


if __name__ == "__main__":  # pragma: no cover - direct execution aid
    unittest.main()
