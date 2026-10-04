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


if __name__ == "__main__":
    unittest.main()
