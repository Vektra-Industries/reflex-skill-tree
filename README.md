# RSTP — Reflex Skill Tree Protocol

[![CI](https://github.com/Vektra-Industries/reflex-skill-tree/actions/workflows/ci.yml/badge.svg)](https://github.com/Vektra-Industries/reflex-skill-tree/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An open, model-agnostic **skill tree** for AI agents — a video-game-shaped
way to track an agent's own capabilities leveling up over time. Nodes are
skills, tiers are mastery, prerequisites form a tree (a DAG, really), and
practice is what moves you up it.

This is **not** a mistake-catcher, a guard, or a safety hook. Earlier drafts
of this project tried that (see History below) and the honest result was:
it didn't work — a strong model's host runtime already auto-attaches
relevant context before any hook fires, so a plugin that only speaks
through hooks had nothing left to add. Rather than keep chasing that, this
is the clean cut: **pure skill tree, no guard pretense.**

No hooks. No daemon. No framework lock-in. **One JSON file an agent reads,
and one small script it calls to log practice.** Any model, any agent, any
framework — Hermes, LangChain, a raw OpenAI/Anthropic loop, a bash script
calling an LLM API, anything that can read a file and run a CLI.

## Where this sits in the skills ecosystem

The SKILL.md format (a folder with a YAML-frontmatter file, lazy-loaded —
an agent reads just the name + description at session start, pulls the
full body in only once it's relevant) has spread fast across Claude Code,
Codex, Cursor, Gemini CLI, Hermes, Windsurf and more through directories
like `obra/superpowers` and `ComposioHQ/awesome-claude-skills`. Those
projects are *workflow* skills (an agent's methodology). RSTP is different
in kind: it's a skill *tracker* — it doesn't tell an agent how to do
something, it tracks whether the agent is actually getting better at the
things it already does. The two compose: `rstp import-skills` turns any
of those workflow-skill libraries into a tree of trackable nodes in one
command.

RSTP ships two ways to land in that ecosystem:
- As a **library + CLI** (`pip install -e .`), for scripts and CI.
- As a **skill directory** (this repo, dropped whole into any agent's
  skills folder — see the root `SKILL.md`): zero `pip install` required,
  because the implementation is stdlib-only Python. Set `PYTHONPATH` at
  the folder and `python3 -m rstp ...` just works.

## The game model

Researched real skill-tree design (Path of Exile's shared DAG, Diablo 4's
Paragon boards, Grim Dawn's devotion constellations, Skyrim's leveling-by-
use, Final Fantasy X's Sphere Grid) and kept what transfers to tracking an
agent's own abilities:

- **Node, not flat rule.** One skill = one node: `title`, `description`,
  which branch it lives in.
- **DAG, not a list.** A node can require prerequisite nodes be proven first
  (`prerequisites`, AND-gated; `prerequisites_any`, OR-gated — Skyrim-style
  "either of these two"). Cycles are rejected at write time — a bad edit
  never corrupts the tree.
- **Tiers carry real weight**, not just a label:

  | Tier | Name | Meaning |
  |---|---|---|
  | 0 | Seed | Drafted, unpracticed. |
  | 1 | Novice | Practiced once. |
  | 2 | Adept | Practiced repeatedly; starts granting affinity if allocated. |
  | 3 | Expert | Deeply practiced. |
  | 4 | Master | Fully mastered — the ceiling. |

- **Promotion is practice-gated**, never self-reported. Every real practice
  rep is logged; a node promotes after enough reps, same spirit as a Sphere
  Grid's AP-threshold or PoE's point-cost curve.
- **Skill Points** (Diablo 4 Paragon). Practicing a node earns a point;
  *allocating* it — making it a real, chosen part of the build — spends
  points equal to its `cost`. Recording practice is always free; allocating
  is the real, finite choice.
- **Affinity** (Grim Dawn devotion constellations). A node can grant
  `affinity` in named categories once allocated and Adept+. Another node can
  require a minimum affinity total before *it's* allocatable — rewards
  breadth across branches, not just one deep chain.
- **Branch usage / leveling by use** (Skyrim). Every logged practice rep
  raises its branch's usage counter, regardless of which node it hit. A node
  can require a minimum branch level before it unlocks.
- **Fusion** (Chrono Trigger Dual/Triple Techs). Two or more proven skills
  can combine into a genuinely new node — neither source is consumed,
  demoted, or changed, same as learning a Dual Tech doesn't erase either
  character's base move. The fused node's prerequisites are set to its
  sources automatically, so the lineage shows up in `status`/the viewer for
  free.
- **Self-report**. A compact, structured progress digest (`Tree.self_report()`
  / `rstp report --json`) an agent can read cheaply before deciding what to
  do next, instead of parsing a full tree dump — tier counts, unspent
  points, affinity, branch levels, what's allocated, what's fused, and
  what's closest to its next promotion.
- **Any agent is a starting position on one shared tree**, not a fork. Trees
  are plain portable JSON — fork one, merge two, or start fresh from someone
  else's already-leveled nodes.

See [`SPEC.md`](SPEC.md) for the full protocol and [`rstp/tree.py`](rstp/tree.py)
for the reference implementation (stdlib-only).

## Install

Not yet published to PyPI — clone and install from source:

```bash
git clone https://github.com/Vektra-Industries/reflex-skill-tree.git
cd reflex-skill-tree
pip install -e .
```

No dependencies. Python 3.9+. Ships a `py.typed` marker, so your type
checker picks up its types. Works with any model/agent — RSTP has no
opinion on what's calling it.

## Quickstart

```bash
# seed one real skill
cat > guitar.json <<'EOF'
{"title": "Playing guitar",
 "description": "Fingerstyle technique, major/minor scales.",
 "cost": 1}
EOF
rstp seed guitar.json --branch music --id guitar

# log practice as it happens
rstp practice guitar --session my-agent-session-42

# see where everything stands
rstp status --verbose

# once it's earned enough points and prerequisites, lock it into the build
rstp allocate guitar
```

Or drive it as a library from any agent loop:

```python
from rstp import load, save

tree = load("tree.json")
tree.practice("guitar", session="my-agent-session-42")
ok, reasons = tree.allocatable("guitar")
if ok:
    tree.allocate("guitar")
save(tree, "tree.json")
```

## Self-awareness: what an agent should read before acting

Instead of parsing a full tree dump, an agent can pull a compact digest:

```bash
rstp report               # one-paragraph narration
rstp report --json        # structured, for an agent to parse directly
```

```python
tree = load("tree.json")
print(tree.narrate())
# "4 node(s) across 2 branch(es): 2 Adept, 1 Novice, 1 Seed. 3pt unspent,
#  1 node(s) allocated. Closest to leveling: 'scales' (1 rep(s) from next tier)."

report = tree.self_report()
# {"total_nodes": 4, "by_tier": {...}, "points_unspent": 3, "affinity": {...},
#  "branch_levels": {...}, "allocated": [...], "fusions": [...],
#  "closest_to_promotion": [{"id": "scales", "tier": "Adept", "reps_remaining": 1}, ...]}
```

## Frontline: experience-ranked, not task-judged

A precise claim worth being exact about: RSTP does **not** decide which
skill is best for an agent's current task — that judgment call always stays
with the agent (or whatever primes its context, e.g. Hermes's own skill
auto-attach). What RSTP *can* do is hand back a shortlist ranked purely by
earned experience — tier first, then rep count — so an agent (or the
harness around it) can consult "what have I actually gotten good at"
independently of a fresh judgment call:

```bash
rstp frontline                        # top 10, all branches, text
rstp frontline --branch music --top 3 # scoped + limited
rstp frontline --json                 # structured
```

```python
tree.frontline()
# [{"id": "autonomous-ai-agents/hermes-agent", "tier": "Expert", "reps": 4, ...},
#  {"id": "software-development/ilo-intel-maid", "tier": "Adept", "reps": 2, ...}, ...]
```

Nodes with zero logged practice reps never appear here, no matter how
relevant their title looks — `frontline()` ranks earned use, not promise.
It never injects anything into an agent's context and never picks for it;
same no-guard philosophy as the rest of the tree (see `rstp/tree.py`'s
module docstring for why an earlier, more active "guard" design was tried
and dropped).

## Fusion: combining proven skills into something new

Once two (or more) skills are each proven (Adept+), they can combine into a
genuinely new node — Chrono Trigger Dual/Triple Tech-style: neither source
is consumed, demoted, or changed. Learning the combo doesn't erase either
base move.

```bash
rstp fuse music lead-guitar \
  --title "Lead guitar improvisation" \
  --description "Soloing over chord changes using scale knowledge." \
  --from chords --from scales
```

```python
node = tree.fuse(
    ["chords", "scales"], "lead-guitar",
    title="Lead guitar improvisation",
    description="Soloing over chord changes using scale knowledge.",
)
# node.prerequisites == ["chords", "scales"]  -- lineage is a real DAG edge
# node.fused_from    == ["chords", "scales"]  -- explicit fusion provenance
# node.tier          == TierName.NOVICE       -- new, but not unproven Seed
```

The fused node's `prerequisites` are set to its sources automatically, so
its lineage shows up in `rstp status --verbose` and in the viewer (dashed
border + ⚡ badge) with no extra bookkeeping.

## Growing a tree from an existing skill library

`rstp.importers.skills` walks any on-disk "SKILL.md with YAML frontmatter"
library (the common Claude-Code/Hermes-style layout: `category/skill-name/
SKILL.md`, or a bare `skill-name/SKILL.md` at the root) and turns every
skill it finds into a Tier-0 Seed node — one per skill, namespaced
`<category>/<skill-name>` so two skills that happen to share a name in
different categories never collide:

```python
from rstp.importers.skills import import_skills
from rstp.tree import save

tree = import_skills("/path/to/your/skills/directory")
save(tree, "tree.json")
```

Or from the CLI directly, no Python needed:

```bash
rstp import-skills /path/to/your/skills/directory --tree tree.json
```

Re-running the import is safe — it never overwrites a node that's already
earned real practice; new skills on disk are added, nothing proven is
reset. A skill node levels up exactly like any other: log a practice rep
each time the skill is actually used.

Dotted directories (`.archive/`, etc) are skipped automatically — retired
material doesn't re-enter the live tree.

## Visualizing a tree

**Live demo (no install): https://vektra-industries.github.io/reflex-skill-tree/**

`docs/index.html` is a standalone, dependency-free skill-tree renderer —
no server, no build step, no network call, nothing leaves your machine
when run locally. Open it in a browser, pick a `tree.json` file, and see
the actual tree: nodes color-coded by tier, allocated nodes outlined in
white, fusion nodes marked with a dashed border and a ⚡ badge, solid edges
for AND-prerequisites (including fusion lineage), dashed edges for
OR-prerequisites.

```bash
# any static file server works, e.g.:
python3 -m http.server 8000 --directory docs
# then open http://localhost:8000/index.html and pick a tree.json
```

(Opening `index.html` directly via `file://` also works in most browsers;
some sandboxed/snap browser builds block local file access entirely, in
which case the quick server above sidesteps it.)

`docs/example-tree.json` + `docs/smoke-test.html` exist so the rendering
logic can be verified headlessly (fetch the example tree, render it,
screenshot) without driving a real file-picker — useful if you're
modifying `docs/app.js` and want to confirm it still renders correctly.
This directory is also what GitHub Pages serves as the live demo above —
one source, no build step, no duplication.

## History

This started as [`vektra-reflex`](https://github.com/Vektra-Industries/vektra-reflex),
a Hermes-plugin mistake-prevention guard. An independent A/B test against a
strong model showed the guard hook made no measurable difference — Hermes's
own skill auto-attach already primed context before the model acted, so the
plugin's hook had nothing left to add. That result, plus a plugin-security
scanner that permanently blocked installing it, is what led here: strip the
guard pretense entirely, keep the one part that was actually good design —
a DAG-shaped progression tree — and ship it as plain, portable, open
software instead of a plugin that depends on a specific host's hooks.

Full version history: [`CHANGELOG.md`](CHANGELOG.md).

## Status

v0.5.0. Reference implementation is stdlib-only Python with 62 unit tests
covering the DAG/cycle rejection, promotion, points/affinity/branch-usage
gating, fusion, self-report, the skill-library importer, and persistence —
see `tests/`. Plus a dependency-free HTML/SVG viewer (`docs/`, also served
live via GitHub Pages),
screenshot-verified against a real multi-branch tree including a fusion
node. This is a protocol + reference implementation, not a hosted service:
your tree, your file, your repo.

## License

MIT — see [`LICENSE`](LICENSE).
