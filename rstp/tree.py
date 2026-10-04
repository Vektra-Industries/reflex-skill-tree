"""RSTP core — DAG-based skill tree for AI-agent mistake prevention.

Design borrows the genre's proven levers (see ../SPEC.md for citations):
  - DAG, not a flat list: nodes may require prerequisite nodes (Path of Exile,
    Supreme Commander tech trees). Acyclicity is enforced on every write.
  - Tiers carry real semantic weight, not just a label (PoE: filler/notable/
    keystone/mastery). RSTP's tiers are SEED -> NOVICE -> ADEPT -> GUARDIAN ->
    MASTER, each with a different enforcement strength (see TierName).
  - Promotion is evidence-gated, counted per real outcome, never self-reported
    (Sphere Grid's AP-threshold, PoE's point-cost curve) — see Node.record().
  - A node can carry a drawback, same as a PoE keystone: "always_guard_tools"
    is RSTP's keystone-style hard commitment — it stays enforced even once the
    related material has already been read this session (closes the exact gap
    vektra-reflex's flat remind/guard modes had against a strong model that
    reads once and still slips).
  - Any agent/model is just a *starting position* on a tree it can share with
    others (PoE: "class is a vector into shared geometry"). RSTP trees are
    plain portable JSON for exactly this reason — fork, merge, or start fresh
    from someone else's proven nodes.
"""
from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

# clean "prevented" outcomes needed to promote FROM this tier, with zero
# "ineffective" outcomes recorded since the last promotion/demotion.
_PROMOTE_AT = {0: 1, 1: 2, 2: 4, 3: 8}


class TierName(IntEnum):
    """Enforcement strength, not just a label — see docstring above."""

    SEED = 0        # drafted, not proven; informational only, agent may ignore
    NOVICE = 1      # proven once; agent reminds itself when the trigger matches
    ADEPT = 2       # proven >=2x; the "do" is a hard rule for that exact call
    GUARDIAN = 3    # keystone-equivalent: stays enforced even if the agent
                    # already read the related material this session
    MASTER = 4      # proven across many sessions; retire into standing
                    # behavior (the agent's own instructions), remove from tree

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.name.capitalize()


class CycleError(ValueError):
    """Raised when an edit would make the prerequisite graph cyclic."""


class RSTPError(ValueError):
    """Raised on any other schema/semantic violation."""


@dataclass
class Evidence:
    prevented: int = 0
    ineffective: int = 0
    unknown: int = 0
    sessions_seen: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Evidence":
        d = d or {}
        return cls(
            prevented=int(d.get("prevented", 0)),
            ineffective=int(d.get("ineffective", 0)),
            unknown=int(d.get("unknown", 0)),
            sessions_seen=list(d.get("sessions_seen", [])),
        )


@dataclass
class Node:
    """One lesson. Shape is intentionally close to a vektra-reflex Lesson
    (title/pitfall/do/triggers) so existing lesson data ports over directly,
    plus the DAG/tier/keystone fields the plugin never had.
    """

    id: str
    branch: str
    title: str
    pitfall: str = ""
    do: str = ""
    tier: int = TierName.SEED
    prerequisites: list[str] = field(default_factory=list)
    triggers: dict[str, list[str]] = field(default_factory=lambda: {"tool_names": [], "path_glob": []})
    always_guard_tools: list[str] = field(default_factory=list)  # keystone-style hard commit
    evidence: Evidence = field(default_factory=Evidence)
    skill: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def matches(self, tool_name: str, text: str) -> bool:
        """True if a call like (tool_name, "write_file /path/.env") trips this node."""
        globs = self.triggers.get("path_glob") or []
        names = self.triggers.get("tool_names") or []
        if names and tool_name not in names:
            return False
        if not globs:
            return bool(names)
        return any(fnmatch.fnmatch(text, f"*{g}*") for g in globs)

    def record(self, outcome: str, session: str | None = None) -> str | None:
        """Log a real outcome. Returns 'promoted'/'demoted'/None. Mutates in place."""
        if outcome not in ("prevented", "ineffective", "unknown"):
            raise RSTPError(f"unknown outcome: {outcome!r}")
        setattr(self.evidence, outcome, getattr(self.evidence, outcome) + 1)
        if session and session not in self.evidence.sessions_seen:
            self.evidence.sessions_seen.append(session)
        self.updated_at = _now()
        if outcome == "prevented" and self.tier < TierName.MASTER:
            need = _PROMOTE_AT.get(self.tier, 999)
            if self.evidence.prevented >= need and self.evidence.ineffective == 0:
                self.tier += 1
                return "promoted"
        elif outcome == "ineffective" and self.tier >= TierName.ADEPT:
            self.tier -= 1
            return "demoted"
        return None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence"] = self.evidence.to_dict()
        return d

    @classmethod
    def from_dict(cls, branch: str, node_id: str, d: dict[str, Any]) -> "Node":
        return cls(
            id=node_id,
            branch=branch,
            title=d.get("title", ""),
            pitfall=d.get("pitfall", ""),
            do=d.get("do", ""),
            tier=int(d.get("tier", TierName.SEED)),
            prerequisites=list(d.get("prerequisites", [])),
            triggers=dict(d.get("triggers") or {"tool_names": [], "path_glob": []}),
            always_guard_tools=list(d.get("always_guard_tools", [])),
            evidence=Evidence.from_dict(d.get("evidence")),
            skill=d.get("skill"),
            provenance=dict(d.get("provenance") or {}),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )


@dataclass
class Tree:
    version: int = SCHEMA_VERSION
    branches: dict[str, dict[str, Any]] = field(default_factory=dict)

    # ---- node access -----------------------------------------------------

    def nodes(self) -> dict[str, Node]:
        out: dict[str, Node] = {}
        for bid, branch in self.branches.items():
            for nid, raw in (branch.get("nodes") or {}).items():
                out[nid] = Node.from_dict(bid, nid, raw)
        return out

    def get(self, node_id: str) -> Node | None:
        return self.nodes().get(node_id)

    def match(self, tool_name: str, text: str) -> list[Node]:
        return [n for n in self.nodes().values() if n.matches(tool_name, text)]

    def unlocked(self, node_id: str) -> bool:
        """A node is unlocked once every prerequisite is at ADEPT or higher —
        the DAG gate. Nodes with no prerequisites are always unlocked."""
        node = self.get(node_id)
        if node is None:
            raise RSTPError(f"no such node: {node_id}")
        nodes = self.nodes()
        return all(
            p in nodes and nodes[p].tier >= TierName.ADEPT for p in node.prerequisites
        )

    # ---- mutation ----------------------------------------------------------

    def upsert(self, node: Node) -> None:
        all_nodes = self.nodes()
        all_nodes[node.id] = node
        _assert_acyclic(all_nodes)
        branch = self.branches.setdefault(node.branch, {"title": node.branch, "nodes": {}})
        branch.setdefault("nodes", {})[node.id] = node.to_dict()

    def record(self, node_id: str, outcome: str, session: str | None = None) -> str | None:
        node = self.get(node_id)
        if node is None:
            raise RSTPError(f"no such node: {node_id}")
        result = node.record(outcome, session)
        self.upsert(node)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "branches": self.branches}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Tree":
        return cls(version=int(d.get("version", SCHEMA_VERSION)), branches=dict(d.get("branches") or {}))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _assert_acyclic(nodes: dict[str, Node]) -> None:
    """DFS cycle check. Raises CycleError naming the exact cycle found."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in nodes}
    path: list[str] = []

    def visit(nid: str) -> None:
        color[nid] = GRAY
        path.append(nid)
        for p in nodes[nid].prerequisites if nid in nodes else []:
            if p not in nodes:
                continue  # dangling prerequisite tolerated here; validate_dag() reports it
            if color.get(p) == GRAY:
                cyc = " -> ".join(path[path.index(p):] + [p])
                raise CycleError(f"cyclic prerequisites: {cyc}")
            if color.get(p) == WHITE:
                visit(p)
        path.pop()
        color[nid] = BLACK

    for nid in list(nodes):
        if color[nid] == WHITE:
            visit(nid)


def validate_dag(tree: Tree) -> list[str]:
    """Non-raising check. Returns a list of problems (empty = clean)."""
    problems: list[str] = []
    nodes = tree.nodes()
    for nid, node in nodes.items():
        for p in node.prerequisites:
            if p not in nodes:
                problems.append(f"{nid}: dangling prerequisite {p!r}")
    try:
        _assert_acyclic(nodes)
    except CycleError as e:
        problems.append(str(e))
    return problems


def load(path: str | Path) -> Tree:
    path = Path(path)
    if not path.exists():
        return Tree()
    raw = json.loads(path.read_text(encoding="utf-8")) or {}
    return Tree.from_dict(raw)


def save(tree: Tree, path: str | Path) -> None:
    path = Path(path)
    problems = validate_dag(tree)
    if problems:
        raise RSTPError("refusing to save an invalid tree: " + "; ".join(problems))
    path.write_text(json.dumps(tree.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
