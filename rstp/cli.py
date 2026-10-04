#!/usr/bin/env python3
"""rstp — command-line interface for a Reflex Skill Tree.

  rstp status [--tree PATH] [--match "<tool> <text>"]
  rstp log <node_id> <prevented|ineffective|unknown> [--session SID] [--tree PATH]
  rstp seed <node.json> --branch BID --id NODE_ID [--tree PATH]
  rstp check [--tree PATH]           # validate the DAG, exit 1 on problems
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .tree import Node, TierName, load, save, validate_dag

DEFAULT_TREE = Path("tree.json")


def cmd_status(args) -> int:
    tree = load(args.tree)
    nodes = tree.nodes()
    if not nodes:
        print(f"(empty tree at {args.tree})")
        return 0
    matched_any = False
    for bid, branch in tree.branches.items():
        branch_nodes = {nid: n for nid, n in nodes.items() if n.branch == bid}
        if not branch_nodes:
            continue
        print(f"\n== {branch.get('title', bid)} ==")
        for nid, node in branch_nodes.items():
            hit = True
            if args.match:
                parts = args.match.split(" ", 1)
                tool = parts[0]
                text = args.match
                hit = node.matches(tool, text)
                if not hit:
                    continue
                matched_any = True
            guard_tag = " [ALWAYS-GUARD]" if node.always_guard_tools else ""
            locked_tag = "" if tree.unlocked(nid) else " [LOCKED: needs prerequisite(s)]"
            tier = TierName(node.tier)
            print(f"  {nid}  T{int(tier)} {tier}{guard_tag}{locked_tag}  \"{node.title}\"")
            if args.match:
                print(f"      pitfall: {node.pitfall}")
                print(f"      do:      {node.do}")
                if node.prerequisites:
                    print(f"      requires: {', '.join(node.prerequisites)}")
            ev = node.evidence
            print(f"      evidence: prevented={ev.prevented} ineffective={ev.ineffective} unknown={ev.unknown}")
    if args.match and not matched_any:
        print(f'(no node matches "{args.match}")')
    return 0


def cmd_log(args) -> int:
    tree = load(args.tree)
    try:
        result = tree.record(args.node_id, args.outcome, args.session)
    except Exception as e:  # noqa: BLE001 - CLI boundary, report and exit non-zero
        print(f"error: {e}", file=sys.stderr)
        return 1
    save(tree, args.tree)
    updated = tree.get(args.node_id)
    assert updated is not None  # just wrote it above; narrows for the type checker
    tier = TierName(updated.tier)
    suffix = f" -> {result} to T{int(tier)} {tier}" if result else ""
    print(f"logged {args.outcome} for {args.node_id}{suffix}")
    if tier == TierName.MASTER:
        print(f"*** {args.node_id} reached Master. Fold its rule into standing instructions, "
              f"then remove it from the tree. ***")
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
    sub = p.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("status")
    s1.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    s1.add_argument("--match")
    s1.set_defaults(fn=cmd_status)

    s2 = sub.add_parser("log")
    s2.add_argument("node_id")
    s2.add_argument("outcome", choices=["prevented", "ineffective", "unknown"])
    s2.add_argument("--session")
    s2.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    s2.set_defaults(fn=cmd_log)

    s3 = sub.add_parser("seed")
    s3.add_argument("node_file")
    s3.add_argument("--branch", required=True)
    s3.add_argument("--id", required=True)
    s3.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    s3.set_defaults(fn=cmd_seed)

    s4 = sub.add_parser("check")
    s4.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    s4.set_defaults(fn=cmd_check)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
