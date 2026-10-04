"""Real tests for rstp.tree — stdlib unittest, no external deps.

Pure skill-tree software: no triggers, no guard, no mistake-catching.

Run: python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rstp.tree import (
    CycleError,
    Node,
    RSTPError,
    TierName,
    Tree,
    load,
    save,
    validate_dag,
)


def make_node(node_id="n1", branch="b1", prereqs=None, prereqs_any=None, tier=TierName.SEED, **kw) -> Node:
    return Node(
        id=node_id,
        branch=branch,
        title=kw.get("title", f"title-{node_id}"),
        description=kw.get("description", "a skill"),
        tier=tier,
        prerequisites=prereqs or [],
        prerequisites_any=prereqs_any or [],
        cost=kw.get("cost", 1),
        affinity=kw.get("affinity", {}),
        affinity_requirements=kw.get("affinity_requirements", {}),
        min_branch_level=kw.get("min_branch_level", 0),
    )


class TestPracticePromotion(unittest.TestCase):
    def test_seed_promotes_to_novice_after_one_rep(self):
        n = make_node(tier=TierName.SEED)
        result = n.practice_once()
        self.assertEqual(result, "promoted")
        self.assertEqual(n.tier, TierName.NOVICE)

    def test_novice_needs_two_reps_to_reach_adept(self):
        n = make_node(tier=TierName.NOVICE)
        self.assertIsNone(n.practice_once())  # 1/2, no promotion yet
        self.assertEqual(n.tier, TierName.NOVICE)
        result = n.practice_once()  # 2/2
        self.assertEqual(result, "promoted")
        self.assertEqual(n.tier, TierName.ADEPT)

    def test_master_does_not_promote_further(self):
        n = make_node(tier=TierName.MASTER)
        result = None
        for _ in range(20):
            result = n.practice_once()
        self.assertIsNone(result)
        self.assertEqual(n.tier, TierName.MASTER)

    def test_session_dedup(self):
        n = make_node()
        n.practice_once(session="s1")
        n.practice_once(session="s1")
        n.practice_once(session="s2")
        self.assertEqual(n.practice.sessions_seen, ["s1", "s2"])

    def test_reps_accumulate_across_calls(self):
        n = make_node()
        n.practice_once()
        n.practice_once()
        n.practice_once()
        self.assertEqual(n.practice.reps, 3)


class TestDAG(unittest.TestCase):
    def test_simple_cycle_detected(self):
        tree = Tree()
        a = make_node("a", prereqs=["b"])
        b = make_node("b", prereqs=["a"])
        tree.upsert(b)  # dangling prereq tolerated mid-build
        with self.assertRaises(CycleError):
            tree.upsert(a)

    def test_self_loop_detected(self):
        tree = Tree()
        a = make_node("a", prereqs=["a"])
        with self.assertRaises(CycleError):
            tree.upsert(a)

    def test_long_chain_cycle_detected(self):
        tree = Tree()
        tree.upsert(make_node("c", prereqs=["a"]))
        tree.upsert(make_node("b", prereqs=["c"]))
        with self.assertRaises(CycleError):
            tree.upsert(make_node("a", prereqs=["b"]))

    def test_diamond_shape_is_fine(self):
        tree = Tree()
        tree.upsert(make_node("root"))
        tree.upsert(make_node("left", prereqs=["root"]))
        tree.upsert(make_node("right", prereqs=["root"]))
        tree.upsert(make_node("tip", prereqs=["left", "right"]))
        self.assertEqual(validate_dag(tree), [])

    def test_dangling_prerequisite_reported_not_raised(self):
        tree = Tree()
        tree.upsert(make_node("a", prereqs=["ghost"]))
        problems = validate_dag(tree)
        self.assertTrue(any("ghost" in p for p in problems))

    def test_or_group_cycle_detected(self):
        tree = Tree()
        a = make_node("a", prereqs_any=["b"])
        b = make_node("b", prereqs_any=["a"])
        tree.upsert(b)
        with self.assertRaises(CycleError):
            tree.upsert(a)


class TestUnlock(unittest.TestCase):
    def test_no_prereq_always_unlocked(self):
        tree = Tree()
        tree.upsert(make_node("a"))
        self.assertTrue(tree.unlocked("a"))

    def test_locked_until_prereq_is_adept(self):
        tree = Tree()
        tree.upsert(make_node("a", tier=TierName.NOVICE))
        tree.upsert(make_node("b", prereqs=["a"]))
        self.assertFalse(tree.unlocked("b"))
        a = tree.get("a")
        assert a is not None
        a.practice_once()  # NOVICE -> ADEPT (needs 2, has 1 already)
        a.practice_once()
        tree.upsert(a)
        self.assertTrue(tree.unlocked("b"))

    def test_or_group_satisfied_by_either(self):
        tree = Tree()
        tree.upsert(make_node("a", tier=TierName.ADEPT))
        tree.upsert(make_node("b", tier=TierName.SEED))
        tree.upsert(make_node("c", prereqs_any=["a", "b"]))
        self.assertTrue(tree.unlocked("c"))  # a alone is enough

    def test_or_group_fails_when_none_satisfied(self):
        tree = Tree()
        tree.upsert(make_node("a", tier=TierName.SEED))
        tree.upsert(make_node("b", tier=TierName.SEED))
        tree.upsert(make_node("c", prereqs_any=["a", "b"]))
        self.assertFalse(tree.unlocked("c"))

    def test_unknown_node_raises(self):
        tree = Tree()
        with self.assertRaises(RSTPError):
            tree.unlocked("nope")


class TestPersistence(unittest.TestCase):
    def test_round_trip(self):
        tree = Tree()
        tree.upsert(make_node("a", description="learn to do a thing"))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tree.json"
            save(tree, p)
            reloaded = load(p)
            node = reloaded.get("a")
            self.assertIsNotNone(node)
            assert node is not None
            self.assertEqual(node.description, "learn to do a thing")

    def test_load_missing_file_returns_empty_tree(self):
        tree = load("/tmp/this-path-should-not-exist-rstp-test.json")
        self.assertEqual(tree.nodes(), {})

    def test_save_refuses_a_cyclic_tree(self):
        # build a cycle by mutating branches directly, bypassing upsert's guard,
        # to prove save() itself double-checks before writing to disk
        tree = Tree()
        tree.branches["b"] = {
            "title": "b",
            "nodes": {
                "a": make_node("a", prereqs=["b"]).to_dict(),
                "b": make_node("b", prereqs=["a"]).to_dict(),
            },
        }
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tree.json"
            with self.assertRaises(RSTPError):
                save(tree, p)
            self.assertFalse(p.exists())


class TestPoints(unittest.TestCase):
    """Diablo 4 Paragon-style: practice earns points, allocation spends them."""

    def test_practice_earns_a_point(self):
        tree = Tree()
        tree.upsert(make_node("a"))
        self.assertEqual(tree.points, 0)
        tree.practice("a")
        self.assertEqual(tree.points, 1)

    def test_allocate_spends_points_and_marks_allocated(self):
        tree = Tree()
        tree.upsert(make_node("a", cost=1))
        tree.practice("a")  # earns 1pt
        tree.allocate("a")
        node = tree.get("a")
        assert node is not None
        self.assertTrue(node.allocated)
        self.assertEqual(tree.points, 0)

    def test_allocate_fails_without_enough_points(self):
        tree = Tree()
        tree.upsert(make_node("a", cost=5))
        tree.practice("a")  # only 1pt, need 5
        with self.assertRaises(RSTPError):
            tree.allocate("a")

    def test_allocate_twice_fails(self):
        tree = Tree()
        tree.upsert(make_node("a", cost=1))
        tree.practice("a")
        tree.allocate("a")
        with self.assertRaises(RSTPError):
            tree.allocate("a")

    def test_allocate_unknown_node_fails(self):
        tree = Tree()
        with self.assertRaises(RSTPError):
            tree.allocate("ghost")


class TestAffinity(unittest.TestCase):
    """Grim Dawn devotion-style: cross-branch affinity gates a node."""

    def test_affinity_only_counts_allocated_adept_plus_nodes(self):
        tree = Tree()
        tree.upsert(make_node("a", tier=TierName.ADEPT, affinity={"order": 3}))
        self.assertEqual(tree.affinity_totals(), {})  # not allocated yet
        a = tree.get("a")
        assert a is not None
        a.allocated = True
        tree.upsert(a)
        self.assertEqual(tree.affinity_totals(), {"order": 3})

    def test_affinity_below_adept_does_not_count_even_if_allocated(self):
        tree = Tree()
        node = make_node("a", tier=TierName.NOVICE, affinity={"order": 3})
        node.allocated = True
        tree.upsert(node)
        self.assertEqual(tree.affinity_totals(), {})

    def test_affinity_requirement_gates_allocation(self):
        tree = Tree()
        donor = make_node("donor", tier=TierName.ADEPT, affinity={"order": 5})
        donor.allocated = True
        tree.upsert(donor)
        tree.points = 0
        gated = make_node("gated", affinity_requirements={"order": 5}, cost=0)
        tree.upsert(gated)
        ok, reasons = tree.allocatable("gated")
        self.assertTrue(ok, reasons)  # donor already supplies exactly enough

    def test_affinity_requirement_blocks_when_insufficient(self):
        tree = Tree()
        donor = make_node("donor", tier=TierName.ADEPT, affinity={"order": 2})
        donor.allocated = True
        tree.upsert(donor)
        gated = make_node("gated", affinity_requirements={"order": 5}, cost=0)
        tree.upsert(gated)
        ok, reasons = tree.allocatable("gated")
        self.assertFalse(ok)
        self.assertTrue(any("order" in r for r in reasons))

    def test_affinity_sums_across_branches(self):
        tree = Tree()
        a = make_node("a", branch="b1", tier=TierName.ADEPT, affinity={"chaos": 2})
        a.allocated = True
        b = make_node("b", branch="b2", tier=TierName.ADEPT, affinity={"chaos": 3})
        b.allocated = True
        tree.upsert(a)
        tree.upsert(b)
        self.assertEqual(tree.affinity_totals(), {"chaos": 5})


class TestBranchUsage(unittest.TestCase):
    """Skyrim-style: a branch levels from real usage, not from declaring intent."""

    def test_usage_increments_on_every_practice_call(self):
        tree = Tree()
        tree.upsert(make_node("a", branch="combat"))
        tree.practice("a")
        tree.practice("a")
        tree.practice("a")
        self.assertEqual(tree.branch_usage["combat"], 3)

    def test_branch_level_follows_usage_per_level_constant(self):
        tree = Tree()
        tree.upsert(make_node("a", branch="combat"))
        for _ in range(5):  # 5 = _USAGE_PER_LEVEL
            tree.practice("a")
        self.assertEqual(tree.branch_level("combat"), 1)

    def test_branch_level_zero_before_threshold(self):
        tree = Tree()
        tree.upsert(make_node("a", branch="combat"))
        tree.practice("a")
        self.assertEqual(tree.branch_level("combat"), 0)

    def test_min_branch_level_gates_allocation(self):
        tree = Tree()
        gated = make_node("a", branch="combat", min_branch_level=1, cost=0)
        tree.upsert(gated)
        ok, reasons = tree.allocatable("a")
        self.assertFalse(ok)
        self.assertTrue(any("usage level" in r for r in reasons))
        for _ in range(5):
            tree.practice("a")
        ok, reasons = tree.allocatable("a")
        self.assertTrue(ok, reasons)

    def test_unrelated_branch_unaffected(self):
        tree = Tree()
        tree.upsert(make_node("a", branch="combat"))
        tree.upsert(make_node("b", branch="stealth"))
        tree.practice("a")
        self.assertEqual(tree.branch_usage.get("stealth", 0), 0)


class TestAllocatableCombined(unittest.TestCase):
    """All gates (prereqs + affinity + branch level + points), combined —
    proving they compose rather than silently overriding each other."""

    def test_all_gates_must_pass_at_once(self):
        tree = Tree()
        prereq = make_node("prereq", branch="b", tier=TierName.ADEPT)
        tree.upsert(prereq)
        node = make_node(
            "final", branch="b", prereqs=["prereq"],
            affinity_requirements={"order": 1}, min_branch_level=1, cost=3,
        )
        tree.upsert(node)
        ok, reasons = tree.allocatable("final")
        self.assertFalse(ok)
        self.assertGreaterEqual(len(reasons), 2)  # affinity AND usage-level both unmet

    def test_round_trip_preserves_points_and_usage(self):
        tree = Tree()
        tree.upsert(make_node("a", cost=1))
        tree.practice("a")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tree.json"
            save(tree, p)
            reloaded = load(p)
            self.assertEqual(reloaded.points, tree.points)
            self.assertEqual(reloaded.branch_usage, tree.branch_usage)


class TestFusion(unittest.TestCase):
    """Chrono-Trigger-Dual-Tech-style: combine proven skills into something
    new, without consuming or demoting either source."""

    def _adept_pair(self, tree):
        tree.upsert(make_node("a", tier=TierName.ADEPT))
        tree.upsert(make_node("b", tier=TierName.ADEPT))

    def test_fuse_requires_at_least_two_sources(self):
        tree = Tree()
        tree.upsert(make_node("a", tier=TierName.ADEPT))
        with self.assertRaises(RSTPError):
            tree.fuse(["a"], "combo", title="Combo")

    def test_fuse_rejects_unknown_source(self):
        tree = Tree()
        tree.upsert(make_node("a", tier=TierName.ADEPT))
        with self.assertRaises(RSTPError):
            tree.fuse(["a", "ghost"], "combo", title="Combo")

    def test_fuse_rejects_under_tier_source(self):
        tree = Tree()
        tree.upsert(make_node("a", tier=TierName.ADEPT))
        tree.upsert(make_node("b", tier=TierName.NOVICE))
        with self.assertRaises(RSTPError):
            tree.fuse(["a", "b"], "combo", title="Combo")

    def test_fuse_creates_new_node_with_prerequisites_and_lineage(self):
        tree = Tree()
        self._adept_pair(tree)
        node = tree.fuse(["a", "b"], "combo", title="Combo move", description="d")
        self.assertEqual(node.id, "combo")
        self.assertEqual(sorted(node.prerequisites), ["a", "b"])
        self.assertEqual(sorted(node.fused_from), ["a", "b"])
        self.assertEqual(node.tier, TierName.NOVICE)  # default
        self.assertIn("combo", tree.nodes())

    def test_fuse_does_not_consume_or_change_sources(self):
        tree = Tree()
        self._adept_pair(tree)
        tree.fuse(["a", "b"], "combo", title="Combo")
        a = tree.get("a")
        b = tree.get("b")
        assert a is not None and b is not None
        self.assertEqual(a.tier, TierName.ADEPT)  # untouched
        self.assertEqual(b.tier, TierName.ADEPT)  # untouched

    def test_fuse_refuses_to_overwrite_existing_id(self):
        tree = Tree()
        self._adept_pair(tree)
        tree.fuse(["a", "b"], "combo", title="Combo")
        with self.assertRaises(RSTPError):
            tree.fuse(["a", "b"], "combo", title="Combo again")

    def test_fuse_defaults_branch_to_first_source(self):
        tree = Tree()
        tree.upsert(make_node("a", branch="music", tier=TierName.ADEPT))
        tree.upsert(make_node("b", branch="music", tier=TierName.ADEPT))
        node = tree.fuse(["a", "b"], "combo", title="Combo")
        self.assertEqual(node.branch, "music")

    def test_fuse_explicit_branch_overrides_default(self):
        tree = Tree()
        self._adept_pair(tree)
        node = tree.fuse(["a", "b"], "combo", title="Combo", branch="other")
        self.assertEqual(node.branch, "other")

    def test_fuse_three_way(self):
        tree = Tree()
        tree.upsert(make_node("a", tier=TierName.ADEPT))
        tree.upsert(make_node("b", tier=TierName.ADEPT))
        tree.upsert(make_node("c", tier=TierName.ADEPT))
        node = tree.fuse(["a", "b", "c"], "triple", title="Triple combo")
        self.assertEqual(sorted(node.fused_from), ["a", "b", "c"])

    def test_fusion_survives_round_trip(self):
        tree = Tree()
        self._adept_pair(tree)
        tree.fuse(["a", "b"], "combo", title="Combo")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tree.json"
            save(tree, p)
            reloaded = load(p)
            node = reloaded.get("combo")
            assert node is not None
            self.assertEqual(sorted(node.fused_from), ["a", "b"])


class TestSelfReport(unittest.TestCase):
    """The tree's own compact self-awareness digest."""

    def test_empty_tree_report(self):
        tree = Tree()
        r = tree.self_report()
        self.assertEqual(r["total_nodes"], 0)
        self.assertEqual(r["closest_to_promotion"], [])

    def test_narrate_empty_tree(self):
        tree = Tree()
        self.assertIn("Empty", tree.narrate())

    def test_report_counts_by_tier(self):
        tree = Tree()
        tree.upsert(make_node("a", tier=TierName.SEED))
        tree.upsert(make_node("b", tier=TierName.ADEPT))
        tree.upsert(make_node("c", tier=TierName.ADEPT))
        r = tree.self_report()
        self.assertEqual(r["by_tier"]["Seed"], 1)
        self.assertEqual(r["by_tier"]["Adept"], 2)

    def test_report_lists_allocated_and_fusions(self):
        tree = Tree()
        tree.upsert(make_node("a", tier=TierName.ADEPT))
        tree.upsert(make_node("b", tier=TierName.ADEPT))
        tree.fuse(["a", "b"], "combo", title="Combo")
        a = tree.get("a")
        assert a is not None
        a.allocated = True
        tree.upsert(a)
        r = tree.self_report()
        self.assertEqual(r["allocated"], ["a"])
        self.assertEqual(r["fusions"], ["combo"])

    def test_closest_to_promotion_sorted_ascending(self):
        tree = Tree()
        far = make_node("far", tier=TierName.NOVICE)       # need=2, 0 reps -> remaining=2
        near = make_node("near", tier=TierName.ADEPT)      # need=4
        near.practice.reps = 3                              # remaining=1, strictly closer
        tree.upsert(far)
        tree.upsert(near)
        r = tree.self_report()
        ids_in_order = [c["id"] for c in r["closest_to_promotion"]]
        self.assertEqual(ids_in_order[0], "near")

    def test_master_tier_excluded_from_closest(self):
        tree = Tree()
        tree.upsert(make_node("done", tier=TierName.MASTER))
        r = tree.self_report()
        self.assertEqual(r["closest_to_promotion"], [])

    def test_narrate_mentions_fusion_count(self):
        tree = Tree()
        tree.upsert(make_node("a", tier=TierName.ADEPT))
        tree.upsert(make_node("b", tier=TierName.ADEPT))
        tree.fuse(["a", "b"], "combo", title="Combo")
        self.assertIn("1 fusion node(s)", tree.narrate())


if __name__ == "__main__":
    unittest.main()
