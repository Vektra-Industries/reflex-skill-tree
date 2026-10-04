"""Generic importer: turn an on-disk skills library into RSTP Seed nodes.

Works with the common "SKILL.md with YAML frontmatter" layout used by Claude
Code / Hermes-style agents (a `name:` and `description:` key, optionally
nested one level under category directories) — but the parser is a minimal,
dependency-free frontmatter reader, not a YAML library, so it only needs
`name` and `description` to be simple scalars or YAML folded/literal block
scalars (`>-`/`>`/`|-`/`|`). Anything fancier in a real file is ignored
safely rather than raising.

Each discovered skill becomes one Tier-0 (Seed) node in the tree. Promote a
skill node the same way as any other: log a practice rep each time you
actually used it, and it levels up through Novice -> Adept -> Expert ->
Master the same way any hand-written node does.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..tree import Node, TierName, Tree

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_BLOCK_SCALAR_RE = re.compile(r"^([A-Za-z0-9_\-]+):\s*([>|][+-]?)\s*$")
_SIMPLE_RE = re.compile(r"^([A-Za-z0-9_\-]+):\s*(.*)$")


def parse_frontmatter(text: str) -> dict[str, str]:
    """Minimal, dependency-free YAML-frontmatter scalar reader.

    Supports plain `key: value`, quoted `key: "value"`, and folded/literal
    block scalars (`key: >-` / `key: |` etc, followed by indented lines).
    Only top-level scalar keys are returned; nested maps/lists are skipped.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    body = m.group(1)
    lines = body.split("\n")
    out: dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        block_m = _BLOCK_SCALAR_RE.match(line)
        if block_m:
            key = block_m.group(1)
            style = block_m.group(2)
            folded = style.startswith(">")
            collected: list[str] = []
            i += 1
            while i < len(lines) and (lines[i].startswith(" ") or lines[i].strip() == ""):
                collected.append(lines[i].strip())
                i += 1
            sep = " " if folded else "\n"
            out[key] = sep.join(c for c in collected if c or not folded).strip()
            continue
        simple_m = _SIMPLE_RE.match(line)
        if simple_m:
            key, val = simple_m.group(1), simple_m.group(2).strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            out[key] = val
        i += 1
    return out


def discover_skills(skills_root: str | Path) -> list[dict[str, Any]]:
    """Walk a skills directory tree, returning one dict per SKILL.md found:
    {"name", "description", "branch", "path"}. `branch` is the first-level
    subdirectory name under skills_root (the skill's category), or "general"
    for a skill directly at the root.
    """
    root = Path(skills_root)
    found: list[dict[str, Any]] = []
    for skill_md in sorted(root.rglob("SKILL.md")):
        rel_parts = skill_md.relative_to(root).parts
        if any(p.startswith(".") for p in rel_parts):
            continue  # skip .archive/ and other dotted/retired directories
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = parse_frontmatter(text)
        name = fm.get("name") or skill_md.parent.name
        description = fm.get("description", "")
        rel = skill_md.parent.relative_to(root)
        branch = rel.parts[0] if len(rel.parts) > 1 else "general"
        found.append({"name": name, "description": description, "branch": branch, "path": str(skill_md)})
    return found


def import_skills(skills_root: str | Path, tree: Tree | None = None) -> Tree:
    """Build (or extend) a Tree with one Seed node per discovered skill.
    Existing nodes with the same id are left untouched (re-running an import
    does not reset practice/tier/allocation on skills already in the tree).
    """
    tree = tree if tree is not None else Tree()
    existing = tree.nodes()
    for entry in discover_skills(skills_root):
        node_id = f"{entry['branch']}/{entry['name']}"
        if node_id in existing:
            continue  # don't clobber real practice already recorded
        node = Node(
            id=node_id,
            branch=entry["branch"],
            title=entry["name"],
            description=entry["description"],
            tier=TierName.SEED,
            skill=entry["name"],
            provenance={"source": "rstp.importers.skills.import_skills", "path": entry["path"]},
        )
        tree.upsert(node)
    return tree
