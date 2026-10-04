"""RSTP core — a DAG-based SKILL TREE for AI agents. Pure progression system:

    this is NOT a mistake-catcher. It does not watch tool calls, match
    triggers, or guard anything. It is capability-tracking software shaped
    like a video-game skill tree: nodes are skills/abilities, tiers are
    mastery levels, and an agent (or its operator) levels nodes up by
    logging real practice. That's the whole job.

(Earlier drafts of this project tried to make the tree double as a live
mistake-prevention guard -- vektra-reflex's "Lesson" plugin. An independent
A/B test showed that approach made no measurable difference against a
strong model, because Hermes's own skill auto-attach already primes context
before the model acts. Rather than keep chasing that, this is the clean
cut: pure skill tree, no guard pretense.)

Design borrows the genre's proven levers (see ../SPEC.md for citations):
  - DAG, not a flat list: a node may require prerequisite nodes (Path of
    Exile, Supreme Commander tech trees). Acyclicity is enforced on write.
  - Tiers carry real weight: SEED -> NOVICE -> ADEPT -> EXPERT -> MASTER.
    Promotion is practice-gated, counted per real logged rep, never
    self-declared (Sphere Grid's AP-threshold, PoE's point-cost curve).
  - Skill Points (Diablo 4 Paragon): practicing a node earns points;
    *allocating* a node — spending points to mark it a real, chosen part of
    the build — is a separate, finite action. Recording practice is free;
    allocating is the real choice.
  - Affinity (Grim Dawn devotion constellations): a node can grant named
    affinity once allocated and Adept+; another node can require a minimum
    affinity total before *it* can be allocated — rewards breadth across
    branches, not just one deep chain.
  - Branch usage / leveling-by-use (Skyrim): every logged practice rep
    raises its branch's usage counter regardless of which node it hit; a
    node can require a minimum branch level before it's allocatable.
  - Fusion (Chrono Trigger Dual/Triple Techs): two or more proven skills
    can combine into a genuinely new node — neither source is consumed or
    changed, same as learning a Dual Tech doesn't erase either
    character's base move. The new node's prerequisites ARE its fusion
    sources, so the lineage draws itself in the DAG/viewer for free.
  - Any agent is just a *starting position* on a tree it can share with
    others (PoE: "class is a vector into shared geometry"). Trees are
    plain portable JSON for exactly this reason.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 3

# practice reps needed to promote FROM this tier.
_PROMOTE_AT = {0: 1, 1: 2, 2: 4, 3: 8}

# skill points earned per logged practice rep (Paragon-style wallet).
_POINTS_PER_PRACTICE = 1

# practice reps needed to raise a branch's usage level by 1 (Skyrim-style
# "level by use", counted on the branch, not any one node).
_USAGE_PER_LEVEL = 5


class TierName(IntEnum):
    """Mastery level. Purely a progression label — no enforcement meaning."""

    SEED = 0      # drafted, unpracticed
    NOVICE = 1    # practiced once
    ADEPT = 2     # practiced repeatedly, grants affinity if allocated
    EXPERT = 3    # deeply practiced
    MASTER = 4    # fully mastered — the ceiling

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.name.capitalize()


class CycleError(ValueError):
    """Raised when an edit would make the prerequisite graph cyclic."""


class RSTPError(ValueError):
    """Raised on any other schema/semantic violation."""


@dataclass
class Practice:
    reps: int = 0
    sessions_seen: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> Practice:
        d = d or {}
        return cls(
            reps=int(d.get("reps", 0)),
            sessions_seen=list(d.get("sessions_seen", [])),
        )


@dataclass
class Node:
    """One skill/ability on the tree."""

    id: str
    branch: str
    title: str
    description: str = ""
    tier: int = TierName.SEED
    prerequisites: list[str] = field(default_factory=list)       # AND-gated
    prerequisites_any: list[str] = field(default_factory=list)   # OR-gated
    practice: Practice = field(default_factory=Practice)
    skill: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    # --- Paragon-style points economy --------------------------------------
    cost: int = 1                       # skill points required to allocate this node
    allocated: bool = False             # has the wallet actually been spent on it?

    # --- Grim Dawn-style affinity -------------------------------------------
    affinity: dict[str, int] = field(default_factory=dict)       # granted on reaching Adept
    affinity_requirements: dict[str, int] = field(default_factory=dict)  # gates allocation

    # --- Skyrim-style branch usage gating -----------------------------------
    min_branch_level: int = 0           # gates allocation on this node's own branch usage

    # --- Chrono-Trigger-style fusion lineage --------------------------------
    fused_from: list[str] = field(default_factory=list)  # source node ids, if this node is a fusion

    def practice_once(self, session: str | None = None) -> str | None:
        """Log one real practice rep. Returns 'promoted' or None. Mutates in place."""
        self.practice.reps += 1
        if session and session not in self.practice.sessions_seen:
            self.practice.sessions_seen.append(session)
        self.updated_at = _now()
        if self.tier >= TierName.MASTER:
            return None
        need = _PROMOTE_AT.get(self.tier, 999)
        if self.practice.reps >= need:
            self.tier += 1
            return "promoted"
        return None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["practice"] = self.practice.to_dict()
        return d

    @classmethod
    def from_dict(cls, branch: str, node_id: str, d: dict[str, Any]) -> Node:
        return cls(
            id=node_id,
            branch=branch,
            title=d.get("title", ""),
            description=d.get("description", ""),
            tier=int(d.get("tier", TierName.SEED)),
            prerequisites=list(d.get("prerequisites", [])),
            prerequisites_any=list(d.get("prerequisites_any", [])),
            practice=Practice.from_dict(d.get("practice")),
            skill=d.get("skill"),
            provenance=dict(d.get("provenance") or {}),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            cost=int(d.get("cost", 1)),
            allocated=bool(d.get("allocated", False)),
            affinity=dict(d.get("affinity") or {}),
            affinity_requirements=dict(d.get("affinity_requirements") or {}),
            min_branch_level=int(d.get("min_branch_level", 0)),
            fused_from=list(d.get("fused_from", [])),
        )


@dataclass
class Tree:
    version: int = SCHEMA_VERSION
    branches: dict[str, dict[str, Any]] = field(default_factory=dict)
    points: int = 0                               # Paragon-style wallet, earned via practice
    branch_usage: dict[str, int] = field(default_factory=dict)  # Skyrim-style raw usage counters

    # ---- node access -----------------------------------------------------

    def nodes(self) -> dict[str, Node]:
        out: dict[str, Node] = {}
        for bid, branch in self.branches.items():
            for nid, raw in (branch.get("nodes") or {}).items():
                out[nid] = Node.from_dict(bid, nid, raw)
        return out

    def get(self, node_id: str) -> Node | None:
        return self.nodes().get(node_id)

    def branch_level(self, branch: str) -> int:
        """Skyrim-style: a branch 'levels' purely from real usage, independent
        of any one node's own practice."""
        return self.branch_usage.get(branch, 0) // _USAGE_PER_LEVEL

    def affinity_totals(self) -> dict[str, int]:
        """Grim Dawn-style: summed affinity from every node that is both
        allocated and at Adept or higher."""
        totals: dict[str, int] = {}
        for node in self.nodes().values():
            if node.allocated and node.tier >= TierName.ADEPT:
                for cat, pts in node.affinity.items():
                    totals[cat] = totals.get(cat, 0) + pts
        return totals

    def unlocked(self, node_id: str) -> bool:
        """DAG gate only: all AND-prerequisites at Adept+, and at least one
        OR-prerequisite (prerequisites_any) at Adept+ if that list is
        non-empty. Does NOT check points/affinity/usage — see allocatable()."""
        node = self.get(node_id)
        if node is None:
            raise RSTPError(f"no such node: {node_id}")
        nodes = self.nodes()
        and_ok = all(p in nodes and nodes[p].tier >= TierName.ADEPT for p in node.prerequisites)
        if not and_ok:
            return False
        if node.prerequisites_any:
            return any(p in nodes and nodes[p].tier >= TierName.ADEPT for p in node.prerequisites_any)
        return True

    def allocatable(self, node_id: str) -> tuple[bool, list[str]]:
        """Full gate: DAG prerequisites + affinity requirements + branch
        usage level + enough unspent points. Returns (ok, reasons_if_not)."""
        node = self.get(node_id)
        if node is None:
            raise RSTPError(f"no such node: {node_id}")
        reasons: list[str] = []
        nodes = self.nodes()
        if not self.unlocked(node_id):
            missing = [p for p in node.prerequisites if p not in nodes or nodes[p].tier < TierName.ADEPT]
            if missing:
                reasons.append(f"prerequisites not yet Adept: {', '.join(missing)}")
            if node.prerequisites_any and not any(
                p in nodes and nodes[p].tier >= TierName.ADEPT for p in node.prerequisites_any
            ):
                reasons.append(f"none of prerequisites_any are Adept+: {', '.join(node.prerequisites_any)}")
        totals = self.affinity_totals()
        for cat, need in node.affinity_requirements.items():
            have = totals.get(cat, 0)
            if have < need:
                reasons.append(f"affinity {cat}: have {have}, need {need}")
        level = self.branch_level(node.branch)
        if level < node.min_branch_level:
            reasons.append(f"branch {node.branch!r} usage level {level} < required {node.min_branch_level}")
        if node.cost > self.points:
            reasons.append(f"cost {node.cost} > {self.points} available points")
        return (not reasons, reasons)

    # ---- mutation ----------------------------------------------------------

    def upsert(self, node: Node) -> None:
        all_nodes = self.nodes()
        all_nodes[node.id] = node
        _assert_acyclic(all_nodes)
        branch = self.branches.setdefault(node.branch, {"title": node.branch, "nodes": {}})
        branch.setdefault("nodes", {})[node.id] = node.to_dict()

    def practice(self, node_id: str, session: str | None = None) -> str | None:
        """Log one real practice rep against a node. Returns 'promoted' or None."""
        node = self.get(node_id)
        if node is None:
            raise RSTPError(f"no such node: {node_id}")
        result = node.practice_once(session)
        self.upsert(node)
        self.branch_usage[node.branch] = self.branch_usage.get(node.branch, 0) + 1
        self.points += _POINTS_PER_PRACTICE
        return result

    def allocate(self, node_id: str) -> None:
        """Spend points to mark a node as a chosen, active part of the build.
        Raises RSTPError with the specific unmet gate(s) if not allocatable."""
        node = self.get(node_id)
        if node is None:
            raise RSTPError(f"no such node: {node_id}")
        if node.allocated:
            raise RSTPError(f"{node_id} is already allocated")
        ok, reasons = self.allocatable(node_id)
        if not ok:
            raise RSTPError(f"cannot allocate {node_id}: " + "; ".join(reasons))
        self.points -= node.cost
        node.allocated = True
        node.updated_at = _now()
        self.upsert(node)

    def fuse(
        self,
        source_ids: list[str],
        new_id: str,
        title: str,
        description: str = "",
        branch: str | None = None,
        tier: int = TierName.NOVICE,
        **node_kwargs: Any,
    ) -> Node:
        """Combine two or more proven skills into a genuinely new node —
        Chrono Trigger Dual/Tech-style: every source stays exactly as it
        was (nothing consumed, nothing demoted), but a new, real capability
        becomes real because both are known. Requires every source to
        exist and be at Adept+ (an unproven skill has nothing to fuse).
        The new node's prerequisites are set to source_ids, so the fusion's
        lineage draws itself in the DAG and the viewer automatically.
        Raises RSTPError if new_id already exists, if fewer than two
        sources are given, or if any source is missing/under-tier.
        """
        if len(source_ids) < 2:
            raise RSTPError("fuse() needs at least two source_ids")
        if self.get(new_id) is not None:
            raise RSTPError(f"{new_id} already exists — fuse() never overwrites")
        nodes = self.nodes()
        missing = [s for s in source_ids if s not in nodes]
        if missing:
            raise RSTPError(f"cannot fuse: unknown source node(s): {', '.join(missing)}")
        under_tier = [s for s in source_ids if nodes[s].tier < TierName.ADEPT]
        if under_tier:
            raise RSTPError(
                f"cannot fuse: source(s) not yet Adept+: {', '.join(under_tier)}"
            )
        resolved_branch = branch or nodes[source_ids[0]].branch
        node = Node(
            id=new_id,
            branch=resolved_branch,
            title=title,
            description=description,
            tier=tier,
            prerequisites=list(source_ids),
            fused_from=list(source_ids),
            provenance={"source": "fuse", "fused_from": list(source_ids), "fused_at": _now()},
            **node_kwargs,
        )
        self.upsert(node)
        return node

    def self_report(self) -> dict[str, Any]:
        """A compact, structured progress digest meant to be cheap for an
        agent to read before deciding what to practice/allocate/fuse next
        — the tree's equivalent of a character sheet, not a full dump."""
        nodes = self.nodes()
        by_tier: dict[str, int] = {}
        for node in nodes.values():
            name = str(TierName(node.tier))
            by_tier[name] = by_tier.get(name, 0) + 1
        allocated = [nid for nid, n in nodes.items() if n.allocated]
        fusions = [nid for nid, n in nodes.items() if n.fused_from]
        closest: list[dict[str, Any]] = []
        for nid, n in nodes.items():
            if n.tier >= TierName.MASTER:
                continue
            need = _PROMOTE_AT.get(n.tier, 999)
            remaining = max(0, need - n.practice.reps)
            closest.append({"id": nid, "tier": str(TierName(n.tier)), "reps_remaining": remaining})
        closest.sort(key=lambda c: c["reps_remaining"])
        return {
            "total_nodes": len(nodes),
            "total_branches": len(self.branches),
            "by_tier": by_tier,
            "points_unspent": self.points,
            "affinity": self.affinity_totals(),
            "branch_levels": {b: self.branch_level(b) for b in self.branches},
            "allocated": sorted(allocated),
            "fusions": sorted(fusions),
            "closest_to_promotion": closest[:5],
        }

    def narrate(self) -> str:
        """Human-readable one-paragraph version of self_report() — meant
        for a status line, not a replacement for status's full listing."""
        r = self.self_report()
        if r["total_nodes"] == 0:
            return "Empty tree. Nothing seeded yet."
        tier_bits = ", ".join(f"{v} {k}" for k, v in r["by_tier"].items())
        lines = [
            f"{r['total_nodes']} node(s) across {r['total_branches']} branch(es): {tier_bits}.",
            f"{r['points_unspent']}pt unspent, {len(r['allocated'])} node(s) allocated.",
        ]
        if r["fusions"]:
            lines.append(f"{len(r['fusions'])} fusion node(s): {', '.join(r['fusions'])}.")
        if r["closest_to_promotion"]:
            c = r["closest_to_promotion"][0]
            if c["reps_remaining"] == 0:
                lines.append(f"'{c['id']}' is ready to promote now.")
            else:
                lines.append(f"Closest to leveling: '{c['id']}' ({c['reps_remaining']} rep(s) from next tier).")
        return " ".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "branches": self.branches,
            "points": self.points,
            "branch_usage": self.branch_usage,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Tree:
        return cls(
            version=int(d.get("version", SCHEMA_VERSION)),
            branches=dict(d.get("branches") or {}),
            points=int(d.get("points", 0)),
            branch_usage=dict(d.get("branch_usage") or {}),
        )


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
        edges = list(nodes[nid].prerequisites) + list(nodes[nid].prerequisites_any) if nid in nodes else []
        for p in edges:
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
        for p in list(node.prerequisites) + list(node.prerequisites_any):
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
