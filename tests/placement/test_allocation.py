"""Pure local unit checks for the synthetic allocation solver.

These verify the deterministic selection contract only; they do NOT qualify
native Frappe behavior (the hosted native checks do that).
"""
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/toefl_house"))
from toefl_house import allocation


def item(name, family, skill, difficulty, qtype="Single Choice", n_opts=4):
    return dict(name=name, family=family, skill=skill, difficulty=difficulty,
                question_type=qtype, options=["o%d" % i for i in range(1, n_opts + 1)])


def bank(skill, n_per_difficulty=3, start=0):
    """n_per_difficulty distinct families per difficulty for one skill."""
    items = []
    for d in ("Entry", "Core", "Stretch"):
        for i in range(n_per_difficulty):
            k = start + i
            items.append(item("%s-%s-%d" % (skill, d, k),
                              "SYN-BK-%s-%s-%d" % (skill[:3].upper(), d[0].upper(), k),
                              skill, d))
    return items


SEED_A = "a" * 64
SEED_B = "b" * 64


class SolverContractTests(unittest.TestCase):
    def test_deterministic_and_input_order_independent(self):
        sections = [dict(id="s1", skill="Grammar", item_count=3)]
        items = bank("Grammar")
        a = allocation.allocate(sections, items, SEED_A, {})
        shuffled = items[:]
        random.Random(7).shuffle(shuffled)
        b = allocation.allocate(sections, shuffled, SEED_A, {})
        self.assertEqual(a, b)
        self.assertEqual(a["pool_digest"], allocation.pool_digest(shuffled))

    def test_section_quotas_exact_and_blueprinted_order(self):
        sections = [dict(id="first", skill="Reading", item_count=2),
                    dict(id="second", skill="Vocabulary", item_count=3)]
        plan = allocation.allocate(sections, bank("Reading") + bank("Vocabulary"), SEED_A, {})
        by_section = {}
        for entry in plan["items"]:
            by_section.setdefault(entry["section"], []).append(entry)
        self.assertEqual(len(by_section["first"]), 2)
        self.assertEqual(len(by_section["second"]), 3)
        self.assertEqual([e["order"] for e in plan["items"]], list(range(1, 6)))
        self.assertEqual([e["occurrence_id"] for e in plan["items"]],
                         ["O001", "O002", "O003", "O004", "O005"])
        # Blueprint order is preserved in the form even if another skill's
        # pool was solved first internally.
        self.assertEqual([e["section"] for e in plan["items"]],
                         ["first", "first", "second", "second", "second"])

    def test_difficulty_strata_balanced_within_section(self):
        sections = [dict(id="s1", skill="Grammar", item_count=3),
                    dict(id="s2", skill="Grammar", item_count=2)]
        plan = allocation.allocate(sections, bank("Grammar", 3), SEED_A, {})
        for section in ("s1", "s2"):
            difficulties = sorted(e["difficulty"] for e in plan["items"] if e["section"] == section)
            # Round-robin preference yields distinct strata whenever the pool
            # supplies them.
            self.assertEqual(len(set(difficulties)), len(difficulties))
        self.assertEqual(sorted(e["difficulty"] for e in plan["items"] if e["section"] == "s1"),
                         ["Core", "Entry", "Stretch"])

    def test_low_exposure_family_preferred_on_ties(self):
        pool = [item("low", "SYN-LOW", "Grammar", "Entry"),
                item("high1", "SYN-HIGH1", "Grammar", "Entry"),
                item("high2", "SYN-HIGH2", "Grammar", "Entry")]
        plan = allocation.allocate([dict(id="s", skill="Grammar", item_count=2)], pool,
                                   SEED_A, {"SYN-LOW": 0, "SYN-HIGH1": 5, "SYN-HIGH2": 5})
        families = {e["family"] for e in plan["items"]}
        self.assertIn("SYN-LOW", families)

    def test_at_most_one_item_per_family_per_form(self):
        pool = [item("v1", "SYN-TWIN", "Grammar", "Entry"),
                item("v2", "SYN-TWIN", "Grammar", "Entry"),
                item("a", "SYN-A", "Grammar", "Core"),
                item("b", "SYN-B", "Grammar", "Stretch")]
        plan = allocation.allocate([dict(id="s", skill="Grammar", item_count=3)], pool, SEED_A, {})
        families = [e["family"] for e in plan["items"]]
        self.assertEqual(len(set(families)), len(families))

    def test_infeasible_short_supply_fails_closed(self):
        pool = bank("Listening", 2)  # 2 distinct families per difficulty = 6
        with self.assertRaises(allocation.AllocationUnavailable) as ctx:
            allocation.allocate([dict(id="s", skill="Listening", item_count=7)], pool, SEED_A, {})
        self.assertIn("insufficient eligible families for skill Listening", str(ctx.exception))
        self.assertIn("need 7, have 6", str(ctx.exception))

    def test_infeasible_missing_skill_fails_closed(self):
        with self.assertRaises(allocation.AllocationUnavailable) as ctx:
            allocation.allocate([dict(id="s", skill="Speaking", item_count=1)],
                                bank("Grammar"), SEED_A, {})
        self.assertIn("need 1, have 0", str(ctx.exception))

    def test_exact_feasibility_uses_all_families(self):
        pool = bank("Grammar", 1)  # 3 distinct families
        plan = allocation.allocate([dict(id="s", skill="Grammar", item_count=3)], pool, SEED_A, {})
        self.assertEqual(len(plan["items"]), 3)
        self.assertEqual(len({e["family"] for e in plan["items"]}), 3)

    def test_two_sections_same_skill_share_pool_without_collision(self):
        pool = bank("Grammar", 1)
        sections = [dict(id="a", skill="Grammar", item_count=2),
                    dict(id="b", skill="Grammar", item_count=1)]
        plan = allocation.allocate(sections, pool, SEED_A, {})
        self.assertEqual(len(plan["items"]), 3)
        self.assertEqual(len({e["family"] for e in plan["items"]}), 3)

    def test_expansion_budget_exhausted(self):
        with self.assertRaises(allocation.AllocationUnavailable) as ctx:
            allocation.allocate([dict(id="s", skill="Grammar", item_count=2)], bank("Grammar", 3),
                                SEED_A, {}, max_expansions=1)
        self.assertIn("expansion budget", str(ctx.exception))

    def test_wall_time_budget_exhausted(self):
        with self.assertRaises(allocation.AllocationUnavailable) as ctx:
            allocation.allocate([dict(id="s", skill="Grammar", item_count=2)], bank("Grammar", 3),
                                SEED_A, {}, max_seconds=0)
        self.assertIn("wall time budget", str(ctx.exception))

    def test_seed_required_and_bounded(self):
        with self.assertRaises(ValueError):
            allocation.allocate([dict(id="s", skill="Grammar", item_count=1)],
                                bank("Grammar"), "short", {})
        with self.assertRaises(ValueError):
            allocation.allocate([dict(id="s", skill="Grammar", item_count=1)],
                                bank("Grammar"), None, {})
        # Length is the solver-level contract bound (the api always feeds
        # secrets.token_hex(32); the manifest controller enforces hex shape).
        allocation.allocate([dict(id="s", skill="Grammar", item_count=1)],
                            bank("Grammar"), "z" * 64, {})
        # A malformed section must fail loudly.
        with self.assertRaises(ValueError):
            allocation.allocate([dict(id="s", skill="Grammar")], bank("Grammar"), SEED_A, {})

    def test_option_order_is_answer_preserving_permutation(self):
        pool = [item("x", "SYN-X", "Grammar", "Entry", n_opts=4)]
        plan = allocation.allocate([dict(id="s", skill="Grammar", item_count=1)], pool, SEED_A, {})
        order = plan["items"][0]["option_order"]
        self.assertEqual(sorted(order), ["o1", "o2", "o3", "o4"])
        # Deterministic per (seed, item, position).
        again = allocation.derive_option_order(SEED_A, "Single Choice",
                                               ["o1", "o2", "o3", "o4"], "x", 1)
        self.assertEqual(again, order)
        # A different seed produces the (verified-constant) other arrangement
        # for this fixture; both are valid permutations.
        other = allocation.derive_option_order(SEED_B, "Single Choice",
                                               ["o1", "o2", "o3", "o4"], "x", 1)
        self.assertEqual(sorted(other), ["o1", "o2", "o3", "o4"])
        self.assertNotEqual(other, order)

    def test_true_false_keeps_canonical_order(self):
        pool = [item("tf", "SYN-TF", "Grammar", "Entry", qtype="True False", n_opts=2)]
        plan = allocation.allocate([dict(id="s", skill="Grammar", item_count=1)], pool, SEED_A, {})
        self.assertIsNone(plan["items"][0]["option_order"])

    def test_plan_carries_audit_provenance(self):
        pool = bank("Grammar", 1)
        plan = allocation.allocate([dict(id="s", skill="Grammar", item_count=2)], pool, SEED_A, {})
        self.assertEqual(plan["algorithm"], allocation.ALGORITHM_VERSION)
        self.assertEqual(plan["seed"], SEED_A)
        self.assertEqual(len(plan["pool_digest"]), 64)
        self.assertEqual(plan["sections"], [dict(id="s", skill="Grammar", item_count=2)])


if __name__ == "__main__":
    unittest.main()
