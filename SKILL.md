---
name: rstp
description: "Use when an agent needs to track its own skill progression — a portable, dependency-free skill tree (tiers, practice reps, points, fusion, self-report). Drop this folder into any skills directory, no install required."
license: MIT
---

# RSTP — Reflex Skill Tree Protocol

A skill tree for AI agents to track their own progression on *other* skills —
practice reps promote nodes through 5 tiers, points unlock them, related
skills can fuse into something new, and `report` gives a cheap one-call
"where do I actually stand" digest.

Full protocol: `SPEC.md`. Full usage/API: `README.md`. This file is the
quick-start for an agent that just found this folder in its skills
directory and wants to use it immediately.

## Zero-install quick start

This package is **pure stdlib Python, zero dependencies** — it works by
being present, no `pip install` required:

```bash
# from anywhere, pointing PYTHONPATH at wherever this folder lives:
PYTHONPATH=/path/to/this/folder python3 -m rstp status --tree ./my-tree.json
```

If your harness already puts this skill's own directory on `sys.path`
(many do), drop the `PYTHONPATH=` prefix entirely — `python3 -m rstp ...`
just works. A `pip install -e .` also works if you'd rather have a bare
`rstp` command on PATH; neither is required.

## When to use

- You (the agent) want to record that you practiced something and track
  whether you're actually getting better at it, not just that you tried.
- You want a cheap self-awareness check before deciding what to do next:
  `rstp report` returns tier counts, unspent points, and what's closest to
  its next promotion — read that instead of re-deriving it from a raw
  tree dump.
- You're importing an existing skill library (any folder of SKILL.md files,
  this format or similar) and want each skill to start as a trackable node:
  `python3 -m rstp import-skills <dir> --tree tree.json`

## Core commands

```bash
python3 -m rstp seed <node.json> --branch <b> --id <id> --tree tree.json
python3 -m rstp status --tree tree.json [--verbose]
python3 -m rstp practice <id> --session <s> --tree tree.json
python3 -m rstp allocate <id> --tree tree.json
python3 -m rstp fuse <branch> <new_id> --title T --from <id> --from <id> --tree tree.json
python3 -m rstp report --tree tree.json [--json]
python3 -m rstp check --tree tree.json
python3 -m rstp import-skills <skills_dir> --tree tree.json
```

## Notes for the harness this lands in

- No network calls, no telemetry, no external dependency of any kind.
- `tree.json` is plain JSON you can read/edit by hand — it's your data,
  it lives wherever you point `--tree`, nothing phones home.
- This is a protocol + reference implementation, not a hosted service.
  Source: https://github.com/Vektra-Industries/reflex-skill-tree
