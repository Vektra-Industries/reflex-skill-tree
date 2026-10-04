# Changelog

All notable changes to this project are documented here. Versions follow
`MAJOR.MINOR.PATCH` loosely — this is a young protocol, not a stable API yet.

## [0.5.0] - 2026-10-04

### Added
- **Fusion** (`Tree.fuse()` / `rstp fuse`). Combine two or more Adept+
  nodes into a genuinely new node — Chrono Trigger Dual/Triple Tech-style:
  sources are never consumed, demoted, or changed. The new node's
  `prerequisites` are set to its sources automatically, so the fusion's
  lineage is a real DAG edge, not a separate rendering concept — it shows
  up in `status --verbose` and the viewer (new dashed-border + ⚡ badge
  styling) for free. Refuses to fuse unproven sources, refuses to
  overwrite an existing node id.
- **Self-report** (`Tree.self_report()` / `Tree.narrate()` / `rstp report
  [--json]`). A compact progress digest — tier counts, unspent points,
  affinity, branch levels, allocated nodes, fusion nodes, and the nodes
  closest to their next promotion — meant to be cheap for an agent to read
  before deciding what to practice/allocate/fuse next, instead of parsing
  a full tree dump.

## [0.4.0] - 2026-10-04

### Added
- `viewer/` — a standalone, dependency-free HTML/SVG tree viewer. Open
  `viewer/index.html` locally (no server, no build step, no network), pick
  a `tree.json` file, and see the actual tree: nodes color-coded by tier,
  allocated nodes outlined, solid edges for AND-prerequisites, dashed edges
  for OR-prerequisites (`prerequisites_any`). Rendering logic lives in
  `viewer/app.js`; `viewer/smoke-test.html` + `viewer/example-tree.json`
  let a headless browser verify it renders correctly without touching the
  file picker.
- `rstp --version`.
- `py.typed` marker (PEP 561) so consumers' type checkers pick up this
  package's types.
- `project.urls` (Homepage/Repository/Issues/Changelog) and classifiers in
  `pyproject.toml`.

### Fixed
- README previously said `pip install rstp`. The package has never been
  published to PyPI — that line was wrong. Install instructions now say
  what's actually true: `pip install -e .` from a clone.

## [0.3.0] - 2026-10-04

### Changed (breaking, schema version 2 -> 3)
Reflex's original guard framing didn't work: an independent A/B test
against a strong model showed zero measurable benefit, because the host
runtime's own skill auto-attach already primed context before any guard
hook could fire. Rather than keep narrowing the definition of "a guard
that actually does something," this release cuts the pretense entirely.

- **Removed:** `pitfall`, `do`, `triggers`, `always_guard_tools` node
  fields; the `prevented`/`ineffective`/`unknown` outcome vocabulary;
  `Node.matches()` / the `--match` CLI flag; the `log <outcome>` command;
  the vektra-reflex porting example.
- **Added:** a single `practice` rep counter replaces the outcome
  vocabulary (`Tree.practice(node_id)` / `rstp practice <node_id>`);
  `prerequisites_any` (OR-gated prerequisites, alongside the existing
  AND-gated `prerequisites`).
- **Kept:** tier progression (renamed Guardian -> Expert, since "Guardian"
  implied enforcement that no longer exists), DAG/cycle rejection, the
  points economy, affinity, branch-usage leveling — the actual
  game-design-inspired progression mechanics, none of the guard pretense.
- New CLI surface: `status` / `practice` / `seed` / `allocate` / `check`.

## [0.2.0] - 2026-10-04

### Added
- **Points** (Diablo 4 Paragon-style): a `Tree.points` wallet, earned per
  logged outcome, spent via `Tree.allocate(node_id)` to turn a node's
  enforcement on.
- **Affinity** (Grim Dawn devotion-style): `Node.affinity` grants named
  points once a node is allocated and Adept+; `Node.affinity_requirements`
  gates allocation on another node's affinity total.
- **Branch usage / leveling-by-use** (Skyrim-style): every logged outcome
  raises its branch's usage counter; `Node.min_branch_level` gates
  allocation on that counter.
- `rstp.importers.skills` — a generic importer that walks any on-disk
  "SKILL.md with YAML frontmatter" library (Claude-Code/Hermes-style) and
  turns every discovered skill into a namespaced Tier-0 Seed node. Proven
  against a real 326-skill library during development; caught and fixed a
  real name-collision bug (bare name -> `<category>/<name>` namespacing)
  and a `.archive/`-directory leak in the process.
- `rstp allocate` CLI command.

## [0.1.0] - 2026-10-04

### Added
- Initial release. DAG-based skill-tree data model (`rstp.tree`): nodes
  with `title`/`pitfall`/`do`/`triggers`, tiers Seed -> Novice -> Adept ->
  Guardian -> Master, cycle-rejecting `upsert()`, evidence-gated promotion/
  demotion (`prevented`/`ineffective`/`unknown` outcomes).
- CLI (`rstp status` / `log` / `seed` / `check`).
- `SPEC.md` — the protocol document, implementation-agnostic.
- Ported from [`vektra-reflex`](https://github.com/Vektra-Industries/vektra-reflex),
  a Hermes-plugin mistake-prevention guard that hit a hard wall: Hermes's
  own plugin security scanner permanently blocked installing it (430
  findings, all in the plugin's own test fixtures simulating attacks it
  was built to detect — a real false-positive the scanner structurally
  cannot distinguish from a genuine threat). A skill has no such
  installation gate, so this project started here instead: plain portable
  JSON + a stdlib script, no plugin API dependency at all.
