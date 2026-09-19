#!/usr/bin/env python3
"""Project FINAL-CLOSURE-REGISTER.md from final-closure-register.json.

The JSON file is the single source of truth; the Markdown is a
mechanical projection so the two can never drift by hand-editing.
"""
from collections import OrderedDict
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/engineering/final-closure-register.json"
TARGET = ROOT / "docs/engineering/FINAL-CLOSURE-REGISTER.md"

FIELDS = ("source", "current_state", "reason", "dependency", "responsible",
          "implementation_or_evidence_required", "acceptance_test")


def main() -> None:
    reg = json.loads(SOURCE.read_text(encoding="utf-8"),
                     object_pairs_hook=OrderedDict)
    lines = [
        "# Final closure register (human-readable projection)",
        "",
        f"Date: {reg['date']} · Active branch: `{reg['active_branch']}` @ `{reg['active_sha'][:7]}`",
        "",
        "> Projected from `final-closure-register.json` (the machine-readable source of",
        "> truth). Regenerate — do not hand-edit — via:",
        "> `python3 tools/foundation/project_closure_register.py`",
        "",
    ]
    by_disp = OrderedDict((d, []) for d in reg["dispositions"])
    for item in reg["items"]:
        by_disp[item["disposition"]].append(item)
    for disp, items in by_disp.items():
        lines.append(f"## {disp} ({len(items)})")
        lines.append("")
        for item in items:
            lines.append(f"### `{item['id']}` — {item['requirement']}")
            lines.append("")
            for key in FIELDS:
                lines.append(f"- **{key}:** {item[key]}")
            lines.append("")
    TARGET.write_text("\n".join(lines), encoding="utf-8")
    print(f"projected {len(reg['items'])} items to {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
