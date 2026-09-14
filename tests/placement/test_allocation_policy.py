"""Pure local unit checks for the increment-3 read-boundary matrix.

Allocation-era records (case/attempt/manifest/exposure) are staff-only;
the allocation guard is an internal lock row readable by no business role.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house.policy import can_read


class AllocationReadBoundaryTests(unittest.TestCase):
    def test_publisher_reads_all_allocation_records(self):
        for kind in ("case", "attempt", "manifest", "exposure"):
            with self.subTest(kind=kind):
                self.assertTrue(can_read(kind, ["Placement Publisher"], "p", "someone"))

    def test_auditor_reads_all_allocation_records(self):
        for kind in ("case", "attempt", "manifest", "exposure"):
            with self.subTest(kind=kind):
                self.assertTrue(can_read(kind, ["Placement Auditor"], "a", "someone"))

    def test_author_reads_no_allocation_records(self):
        for kind in ("case", "attempt", "manifest", "exposure"):
            with self.subTest(kind=kind):
                self.assertFalse(can_read(kind, ["Placement Author"], "a", "a"))

    def test_unrelated_roles_read_no_allocation_records(self):
        for roles in ([], ["Student"], ["Guest"], ["Assessor"]):
            for kind in ("case", "attempt", "manifest", "exposure"):
                with self.subTest(roles=roles, kind=kind):
                    self.assertFalse(can_read(kind, roles, "x", "x"))

    def test_guard_is_internal_for_every_role(self):
        for roles in ([], ["Placement Author"], ["Placement Publisher"],
                      ["Placement Auditor"],
                      ["Placement Author", "Placement Publisher", "Placement Auditor"]):
            with self.subTest(roles=roles):
                self.assertFalse(can_read("guard", roles, "x", "x"))

    def test_role_union_does_not_widen_allocation_reads(self):
        # An author + auditor user still only reads what the auditor may
        # read; the author's own-content rule never applies to these kinds.
        self.assertTrue(can_read("case", ["Placement Author", "Placement Auditor"],
                                 "a", "someone-else"))
        self.assertFalse(can_read("guard", ["Placement Author", "Placement Auditor"],
                                  "a", "x"))

    def test_increment1_2_boundaries_unchanged(self):
        # Guard branch must not have shadowed existing kinds.
        self.assertTrue(can_read("item", ["Placement Publisher"], "p", "a", "Draft"))
        self.assertFalse(can_read("key", ["Placement Auditor"], "a", "a"))
        self.assertTrue(can_read("key", ["Placement Author"], "a", "a"))
        self.assertTrue(can_read("audit", ["Placement Auditor"], "a", "x"))
        self.assertFalse(can_read("operation", ["Placement Publisher"], "p", "x"))
        self.assertTrue(can_read("blueprint", ["Placement Author"], "a", "a", "Draft"))
        self.assertFalse(can_read("blueprint", ["Placement Author"], "a", "b", "Retired"))


if __name__ == "__main__":
    unittest.main()
