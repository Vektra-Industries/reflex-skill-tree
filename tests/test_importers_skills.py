"""Real tests for rstp.importers.skills — against synthetic SKILL.md files,
not the live house library (keeps CI hermetic and reviewer-reproducible)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rstp.importers.skills import discover_skills, import_skills, parse_frontmatter
from rstp.tree import TierName

SIMPLE = """---
name: example-one
description: "A simple one-line description."
version: "1.0.0"
---

# Example One
"""

FOLDED = """---
name: example-two
description: >-
  A folded block scalar description that
  spans several source lines.
---

# Example Two
"""


class TestParseFrontmatter(unittest.TestCase):
    def test_simple_scalar(self):
        fm = parse_frontmatter(SIMPLE)
        self.assertEqual(fm["name"], "example-one")
        self.assertEqual(fm["description"], "A simple one-line description.")

    def test_folded_block_scalar(self):
        fm = parse_frontmatter(FOLDED)
        self.assertEqual(fm["name"], "example-two")
        self.assertIn("spans several source lines.", fm["description"])

    def test_no_frontmatter_returns_empty(self):
        self.assertEqual(parse_frontmatter("# just a heading\n"), {})


class TestDiscoverSkills(unittest.TestCase):
    def test_discovers_nested_skills_with_branch(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "cat-a" / "skill-one").mkdir(parents=True)
            (root / "cat-a" / "skill-one" / "SKILL.md").write_text(SIMPLE, encoding="utf-8")
            (root / "cat-b" / "skill-two").mkdir(parents=True)
            (root / "cat-b" / "skill-two" / "SKILL.md").write_text(FOLDED, encoding="utf-8")
            found = discover_skills(root)
            self.assertEqual(len(found), 2)
            branches = {f["branch"] for f in found}
            self.assertEqual(branches, {"cat-a", "cat-b"})

    def test_skips_dotted_archive_directories(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".archive" / "old-one").mkdir(parents=True)
            (root / ".archive" / "old-one" / "SKILL.md").write_text(SIMPLE, encoding="utf-8")
            found = discover_skills(root)
            self.assertEqual(found, [])

    def test_root_level_skill_gets_general_branch(self):
        """A skill with no category directory (SKILL.md one level under root,
        like the real house's interview-me/SKILL.md) has no branch of its
        own to report, so it's bucketed under 'general'."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "interview-me").mkdir()
            (root / "interview-me" / "SKILL.md").write_text(SIMPLE, encoding="utf-8")
            found = discover_skills(root)
            self.assertEqual(found[0]["branch"], "general")


class TestImportSkills(unittest.TestCase):
    def test_import_creates_seed_nodes_namespaced_by_branch(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "cat-a" / "example-one").mkdir(parents=True)
            (root / "cat-a" / "example-one" / "SKILL.md").write_text(SIMPLE, encoding="utf-8")
            tree = import_skills(root)
            self.assertIn("cat-a/example-one", tree.nodes())
            node = tree.get("cat-a/example-one")
            assert node is not None
            self.assertEqual(node.tier, TierName.SEED)

    def test_same_name_different_branch_does_not_collide(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for cat in ("cat-a", "cat-b"):
                (root / cat / "example-one").mkdir(parents=True)
                (root / cat / "example-one" / "SKILL.md").write_text(SIMPLE, encoding="utf-8")
            tree = import_skills(root)
            self.assertEqual(len(tree.nodes()), 2)
            self.assertIn("cat-a/example-one", tree.nodes())
            self.assertIn("cat-b/example-one", tree.nodes())

    def test_reimport_does_not_clobber_existing_practice(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "cat-a" / "example-one").mkdir(parents=True)
            (root / "cat-a" / "example-one" / "SKILL.md").write_text(SIMPLE, encoding="utf-8")
            tree = import_skills(root)
            tree.practice("cat-a/example-one")
            tree2 = import_skills(root, tree=tree)
            node = tree2.get("cat-a/example-one")
            assert node is not None
            self.assertEqual(node.practice.reps, 1)  # not reset to 0


if __name__ == "__main__":
    unittest.main()
