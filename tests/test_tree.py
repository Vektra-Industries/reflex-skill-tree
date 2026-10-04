"""Real tests for rstp.tree — stdlib unittest, no external deps.

Run: python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rstp.tree import CycleError, Node, RSTPError, Tree, TierName, load, save, validate_dag


def make_node(node_id="n1", branch="b1", prereqs=None, tier=TierName.SEED, **kw) -> Node:
    return Node(
        id=node_id,
        branch=branch,
        title=kw.get("title", f"title-{node_id}"),
        pitfall=kw.get("pitfall", "pitfall"),
        do=kw.get("do", "do"),
        tier=tier,
        prerequisites=prereqs or [],
        triggers=kw.get("triggers", {"tool_names": ["write_file"], "path_glob": ["*.env"]}),
        always_guard_tools=kw.get("always_guard_tools", []),
        cost=kw.get("cost", 1),
        affinity=kw.get("affinity", {}),
        affinity_requirements=kw.get("affinity_requirements", {}),
        min_branch_level=kw.get("min_branch_level", 0),
    )


class TestMatching(unittest.TestCase):
    def test_matches_on_tool_and_glob(self):
        n = make_node()
        self.assertTrue(n.matches("write_file", "write_file /home/x/.env"))

    def test_no_match_wrong_tool(self):
        n = make_node()
        self.assertFalse(n.matches("read_file", "read_file /home/x/.env"))

    def test_no_match_wrong_path(self):
        n = make_node()
        self.assertFalse(n.matches("write_file", "write_file /home/x/notes.md"))

    def test_tool_only_trigger_matches_any_text(self):
        n = make_node(triggers={"tool_names": ["terminal"], "path_glob": []})
        self.assertTrue(n.matches("terminal", "anything at all"))


class TestEvidencePromotion(unittest.TestCase):
    def test_seed_promotes_to_novice_after_one_prevented(self):
        n = make_node(tier=TierName.SEED)
        result = n.record("prevented")
        self.assertEqual(result, "promoted")
        self.assertEqual(n.tier, TierName.NOVICE)

    def test_novice_needs_two_to_reach_adept(self):
        n = make_node(tier=TierName.NOVICE)
        self.assertIsNone(n.record("prevented"))  # 1/2, no promotion yet
        self.assertEqual(n.tier, TierName.NOVICE)
        result = n.record("prevented")  # 2/2
        self.assertEqual(result, "promoted")
        self.assertEqual(n.tier, TierName.ADEPT)

    def test_ineffective_resets_the_promotion_clock(self):
        n = make_node(tier=TierName.NOVICE)
        n.record("prevented")  # 1/2
        n.record("ineffective")
        # still needs a fresh run of 2 prevented with zero ineffective since
        result = n.record("prevented")  # prevented=2 but ineffective=1 now -> no promotion
        self.assertIsNone(result)
        self.assertEqual(n.tier, TierName.NOVICE)

    def test_adept_demotes_on_ineffective(self):
        n = make_node(tier=TierName.ADEPT)
        result = n.record("ineffective")
        self.assertEqual(result, "demoted")
        self.assertEqual(n.tier, TierName.NOVICE)

    def test_seed_does_not_demote_below_zero(self):
        n = make_node(tier=TierName.SEED)
        result = n.record("ineffective")
        self.assertIsNone(result)
        self.assertEqual(n.tier, TierName.SEED)

    def test_master_does_not_promote_further(self):
        n = make_node(tier=TierName.MASTER)
        result = None
        for _ in range(20):
            result = n.record("prevented")
        self.assertIsNone(result)
        self.assertEqual(n.tier, TierName.MASTER)

    def test_unknown_outcome_rejected(self):
        n = make_node()
        with self.assertRaises(RSTPError):
            n.record("maybe")

    def test_session_dedup(self):
        n = make_node()
        n.record("prevented", session="s1")
        n.record("prevented", session="s1")
        n.record("prevented", session="s2")
        self.assertEqual(n.evidence.sessions_seen, ["s1", "s2"])


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
        a.record("prevented")  # NOVICE -> ADEPT (needs 2, but already has evidence)
        a.record("prevented")
        tree.upsert(a)
        self.assertTrue(tree.unlocked("b"))

    def test_unknown_node_raises(self):
        tree = Tree()
        with self.assertRaises(RSTPError):
            tree.unlocked("nope")


class TestPersistence(unittest.TestCase):
    def test_round_trip(self):
        tree = Tree()
        tree.upsert(make_node("a", always_guard_tools=["write_file"]))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tree.json"
            save(tree, p)
            reloaded = load(p)
            node = reloaded.get("a")
            self.assertIsNotNone(node)
            assert node is not None
            self.assertEqual(node.always_guard_tools, ["write_file"])

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
    """Diablo 4 Paragon-style: evidence earns points, allocation spends them."""

    def test_recording_prevented_earns_a_point(self):
        tree = Tree()
        tree.upsert(make_node("a"))
        self.assertEqual(tree.points, 0)
        tree.record("a", "prevented")
        self.assertEqual(tree.points, 1)

    def test_ineffective_and_unknown_earn_nothing(self):
        tree = Tree()
        tree.upsert(make_node("a"))
        tree.record("a", "ineffective")
        tree.record("a", "unknown")
        self.assertEqual(tree.points, 0)

    def test_allocate_spends_points_and_marks_allocated(self):
        tree = Tree()
        tree.upsert(make_node("a", cost=1))
        tree.record("a", "prevented")  # earns 1pt
        tree.allocate("a")
        node = tree.get("a")
        assert node is not None
        self.assertTrue(node.allocated)
        self.assertEqual(tree.points, 0)

    def test_allocate_fails_without_enough_points(self):
        tree = Tree()
        tree.upsert(make_node("a", cost=5))
        tree.record("a", "prevented")  # only 1pt, need 5
        with self.assertRaises(RSTPError):
            tree.allocate("a")

    def test_allocate_twice_fails(self):
        tree = Tree()
        tree.upsert(make_node("a", cost=1))
        tree.record("a", "prevented")
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

    def test_usage_increments_on_every_log_regardless_of_outcome(self):
        tree = Tree()
        tree.upsert(make_node("a", branch="combat"))
        tree.record("a", "prevented")
        tree.record("a", "ineffective")
        tree.record("a", "unknown")
        self.assertEqual(tree.branch_usage["combat"], 3)

    def test_branch_level_follows_usage_per_level_constant(self):
        tree = Tree()
        tree.upsert(make_node("a", branch="combat"))
        for _ in range(5):
            tree.record("a", "unknown")  # 5 = _USAGE_PER_LEVEL, earns no points
        self.assertEqual(tree.branch_level("combat"), 1)

    def test_branch_level_zero_before_threshold(self):
        tree = Tree()
        tree.upsert(make_node("a", branch="combat"))
        tree.record("a", "unknown")
        self.assertEqual(tree.branch_level("combat"), 0)

    def test_min_branch_level_gates_allocation(self):
        tree = Tree()
        gated = make_node("a", branch="combat", min_branch_level=1, cost=0)
        tree.upsert(gated)
        ok, reasons = tree.allocatable("a")
        self.assertFalse(ok)
        self.assertTrue(any("usage level" in r for r in reasons))
        for _ in range(5):
            tree.record("a", "unknown")
        ok, reasons = tree.allocatable("a")
        self.assertTrue(ok, reasons)

    def test_unrelated_branch_unaffected(self):
        tree = Tree()
        tree.upsert(make_node("a", branch="combat"))
        tree.upsert(make_node("b", branch="stealth"))
        tree.record("a", "prevented")
        self.assertEqual(tree.branch_usage.get("stealth", 0), 0)


class TestAllocatableCombined(unittest.TestCase):
    """All three v0.2 gates (prereqs + affinity + branch level) plus points,
    combined — proving they compose rather than silently overriding each other."""

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
        tree.record("a", "prevented")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tree.json"
            save(tree, p)
            reloaded = load(p)
            self.assertEqual(reloaded.points, tree.points)
            self.assertEqual(reloaded.branch_usage, tree.branch_usage)


if __name__ == "__main__":
    unittest.main()
