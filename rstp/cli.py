#!/usr/bin/env python3
"""rstp — command-line interface for a Reflex Skill Tree.

Pure skill-tree software: nodes are skills/abilities, tiers are mastery
levels. No guard, no triggers, no mistake-catching.

  rstp status [--tree PATH] [--verbose]
  rstp practice <node_id> [--session SID] [--tree PATH]
  rstp seed <node.json> --branch BID --id NODE_ID [--tree PATH]
  rstp allocate <node_id> [--tree PATH]   # spend points to lock a node into the build
  rstp check [--tree PATH]                # validate the DAG, exit 1 on problems
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .tree import Node, TierName, load, save, validate_dag
from . import __version__

DEFAULT_TREE = Path("tree.json")


def cmd_status(args) -> int:
    tree = load(args.tree)
    nodes = tree.nodes()
    print(f"points: {tree.points} unspent")
    affinity = tree.affinity_totals()
    if affinity:
        print("affinity: " + ", ".join(f"{k}={v}" for k, v in sorted(affinity.items())))
    if not nodes:
        print(f"(empty tree at {args.tree})")
        return 0
    for bid, branch in tree.branches.items():
        branch_nodes = {nid: n for nid, n in nodes.items() if n.branch == bid}
        if not branch_nodes:
            continue
        if args.branch and bid != args.branch:
            continue
        level = tree.branch_level(bid)
        lines_for_branch: list[str] = []
        for nid, node in branch_nodes.items():
            ok, reasons = tree.allocatable(nid)
            if node.allocated:
                alloc_tag = " [ALLOCATED]"
            elif ok:
                alloc_tag = f" [ALLOCATABLE: {node.cost}pt]"
            else:
                alloc_tag = f" [LOCKED: {'; '.join(reasons)}]"
            tier = TierName(node.tier)
            lines_for_branch.append(f"  {nid}  T{int(tier)} {tier}{alloc_tag}  \"{node.title}\"")
            if args.verbose:
                if node.description:
                    lines_for_branch.append(f"      {node.description}")
                if node.prerequisites:
                    lines_for_branch.append(f"      requires: {', '.join(node.prerequisites)}")
                if node.prerequisites_any:
                    lines_for_branch.append(f"      requires any of: {', '.join(node.prerequisites_any)}")
                if node.affinity:
                    lines_for_branch.append(f"      grants affinity: {node.affinity}")
                if node.affinity_requirements:
                    lines_for_branch.append(f"      needs affinity: {node.affinity_requirements}")
            lines_for_branch.append(f"      practice reps: {node.practice.reps}")
        print(f"\n== {branch.get('title', bid)} (usage level {level}) ==")
        print("\n".join(lines_for_branch))
    return 0


def cmd_practice(args) -> int:
    tree = load(args.tree)
    try:
        result = tree.practice(args.node_id, args.session)
    except Exception as e:  # noqa: BLE001 - CLI boundary, report and exit non-zero
        print(f"error: {e}", file=sys.stderr)
        return 1
    save(tree, args.tree)
    updated = tree.get(args.node_id)
    assert updated is not None  # just wrote it above; narrows for the type checker
    tier = TierName(updated.tier)
    suffix = f" -> {result} to T{int(tier)} {tier}" if result else ""
    print(f"logged practice for {args.node_id}{suffix}  (wallet: {tree.points}pt, "
          f"branch {updated.branch!r} usage level {tree.branch_level(updated.branch)})")
    if tier == TierName.MASTER:
        print(f"*** {args.node_id} reached Master. It's fully learned. ***")
    return 0


def cmd_seed(args) -> int:
    raw = json.loads(Path(args.node_file).read_text(encoding="utf-8"))
    node = Node.from_dict(args.branch, args.id, raw)
    tree = load(args.tree)
    try:
        tree.upsert(node)
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}", file=sys.stderr)
        return 1
    save(tree, args.tree)
    print(f"seeded {args.id} into {args.branch} at tier {TierName(node.tier)}")
    return 0


def cmd_allocate(args) -> int:
    tree = load(args.tree)
    try:
        tree.allocate(args.node_id)
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}", file=sys.stderr)
        return 1
    save(tree, args.tree)
    print(f"allocated {args.node_id}  (wallet now: {tree.points}pt)")
    return 0


def cmd_check(args) -> int:
    tree = load(args.tree)
    problems = validate_dag(tree)
    if problems:
        for p in problems:
            print(f"PROBLEM: {p}", file=sys.stderr)
        return 1
    print(f"OK: {len(tree.nodes())} node(s), acyclic, no dangling prerequisites")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"rstp {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("status")
    s1.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    s1.add_argument("--branch")
    s1.add_argument("--verbose", "-v", action="store_true")
    s1.set_defaults(fn=cmd_status)

    s2 = sub.add_parser("practice")
    s2.add_argument("node_id")
    s2.add_argument("--session")
    s2.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    s2.set_defaults(fn=cmd_practice)

    s3 = sub.add_parser("seed")
    s3.add_argument("node_file")
    s3.add_argument("--branch", required=True)
    s3.add_argument("--id", required=True)
    s3.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    s3.set_defaults(fn=cmd_seed)

    s4 = sub.add_parser("check")
    s4.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    s4.set_defaults(fn=cmd_check)

    s5 = sub.add_parser("allocate")
    s5.add_argument("node_id")
    s5.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    s5.set_defaults(fn=cmd_allocate)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
