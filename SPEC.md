# RSTP v3 — Reflex Skill Tree Protocol

Status: Draft, v3. This document is the protocol; `rstp/` in this repo is one
conforming implementation (Python, stdlib-only). Anyone may implement RSTP in
any language against this spec — a JSON file and a few pure functions is the
entire interface surface.

RSTP is **pure skill-tree software**: it tracks an agent's own capabilities
leveling up over time, the same shape as a video-game skill tree. It is not
a mistake-catcher, a guard, or a safety hook — see §7 for why that framing
was dropped.

## 1. Goals

- **Portable.** A tree is one JSON file. No database, no server, no plugin
  API, no framework dependency.
- **Model-agnostic.** The protocol does not assume any particular model or
  agent framework. It only assumes: something can read/write a JSON file and
  call a small script or library function to log practice.
- **Practice-driven.** Nothing in the tree reaches a high tier without a
  logged, timestamped, real practice rep. No self-certification.
- **A real economy, not an unlimited one.** Points, affinity, and branch
  usage are all scarce/earned, so growing the tree means actually using the
  skills in it — not declaring intent.

## 2. Data model

### 2.1 Tree

```json
{
  "version": 3,
  "branches": {
    "<branch_id>": {
      "title": "<human label>",
      "nodes": { "<node_id>": { ...Node } }
    }
  },
  "points": 0,
  "branch_usage": { "<branch_id>": 0 }
}
```

`branches` partitions nodes by topic (e.g. `music`, `cooking`,
`software-development`). Partitioning is purely organizational —
prerequisites may cross branches.

### 2.2 Node

| Field | Type | Meaning |
|---|---|---|
| `title` | string | Short human label. |
| `description` | string | What the skill/ability actually is or does. |
| `tier` | int 0-4 | See §3. Default 0 (Seed). |
| `prerequisites` | string[] | Node IDs that must ALL be at tier >= 2 (Adept) before this node is unlocked. Default `[]`. |
| `prerequisites_any` | string[] | Node IDs where at least ONE must be at tier >= 2 (Adept). Default `[]`. Evaluated in addition to `prerequisites` (both must pass). |
| `practice.reps` | int | Count of logged practice reps. See §4. |
| `practice.sessions_seen` | string[] | Opaque session identifiers that have logged a practice rep, for cross-session frequency awareness. |
| `cost` | int | Skill points required to allocate this node. Default 1. |
| `allocated` | bool | Whether points have actually been spent on this node. Default false. |
| `affinity` | object (string -> int) | Named-category points this node grants once allocated and at tier >= Adept. |
| `affinity_requirements` | object (string -> int) | Minimum affinity totals (summed from every *other* qualifying node) required before this node is allocatable. |
| `min_branch_level` | int | Minimum branch usage level (see §6) required before this node is allocatable. |
| `skill` | string\|null | Optional pointer to external documentation (a skill name, a doc path, a URL) this node represents or references. |
| `provenance` | object | Free-form: where this node came from (origin repo, importer, date). Not interpreted by the protocol, kept for audit. |
| `created_at` / `updated_at` | string | ISO-8601 UTC timestamps. |

## 3. Tiers

Tiers are mastery labels, nothing more. There is no enforcement contract —
RSTP does not call tools, intercept calls, or gate any agent action. A node
reaching a given tier means only that the practice-count threshold for that
tier has been met.

| Tier | Name | Meaning |
|---|---|---|
| 0 | Seed | Drafted, unpracticed. |
| 1 | Novice | Practiced once. |
| 2 | Adept | Practiced repeatedly. Starts granting its `affinity` if allocated. |
| 3 | Expert | Deeply practiced. |
| 4 | Master | Fully mastered — the ceiling. Does not promote further. |

Tier is an integer 0-4; implementations MUST reject out-of-range values.

## 4. Practice and promotion

A node promotes one tier when its cumulative practice rep count (since the
last tier change) reaches a threshold:

| From tier | Reps needed to promote |
|---|---|
| Seed (0) | 1 |
| Novice (1) | 2 |
| Adept (2) | 4 |
| Expert (3) | 8 |

Master (4) does not promote further. There is no demotion mechanism in v3 —
a skill that's been practiced enough to reach a tier stays there; RSTP does
not model skill decay.

### 4.1 Unlock (DAG gating)

A node is **unlocked** iff:
- every id in `prerequisites` resolves to a node at tier >= 2 (Adept), AND
- if `prerequisites_any` is non-empty, at least one id in it resolves to a
  node at tier >= 2 (Adept).

Implementations MAY surface locked nodes differently in status output but
MUST NOT silently drop them from the tree.

## 5. Points (an allocation economy)

A `Tree` carries a `points` integer wallet. Every logged practice rep
credits the wallet by a fixed amount (reference value: 1), regardless of
which node it hit. A `Node` carries a `cost` (reference default: 1) and an
`allocated` boolean. `allocate(node_id)` is the only way to set
`allocated = True`; it MUST check every gate in §6.3 and MUST decrement the
wallet by exactly `cost`, atomically — either the full allocation succeeds
(gates pass, points spent, flag set) or nothing changes. A node that is
merely practiced but never allocated is tracked progress, not yet a chosen
part of the build — allocation is the explicit "I'm keeping this" action,
same as spending a Paragon point.

## 6. Affinity and branch usage

### 6.1 Affinity (Node)

A `Node` carries `affinity: dict[str, int]`, named-category points it
grants once two conditions hold simultaneously: it is `allocated` AND its
`tier >= Adept`. `affinity_totals()` sums these across every qualifying
node, by category. A `Node` carries `affinity_requirements: dict[str, int]`;
it is not allocatable while any required category's total (from every
*other* qualifying node) is below the stated minimum.

### 6.2 Branch usage (leveling by use)

A `Tree` carries `branch_usage: dict[str, int]`, one raw counter per branch.
Every logged practice rep increments its node's branch counter by 1,
regardless of which node it hit — any real use of the branch counts.
`branch_level(branch)` is `branch_usage[branch] // USAGE_PER_LEVEL`
(reference constant: 5). A `Node` carries `min_branch_level`; it is not
allocatable until its own branch's level meets that minimum.

### 6.3 Combined allocation gate

`allocatable(node_id)` MUST check, and report failures for, all of: unmet
DAG prerequisites (§4.1), unmet affinity requirements (§6.1), insufficient
branch usage level (§6.2), and insufficient points (§5) — in any order, but
all four, every time; a conforming implementation MUST NOT short-circuit on
the first failing gate when the caller wants a reason list (the reference
CLI shows every unmet reason, not just one).

## 7. What RSTP deliberately does not do

- It does not call tools, intercept calls, or hook into any runtime. There
  is no enforcement contract of any kind.
- It does not include a scheduler, server, or multi-writer concurrency
  model. A tree file is assumed single-writer per session; merge conflicts
  across sessions are a file-merge problem (e.g. plain `git merge` on JSON),
  not a protocol concern.
- It does not interpret `skill` or `provenance` beyond storing them as
  given.
- Earlier drafts (v1/v2, see §8) tried to make the tree double as a live
  mistake-prevention guard, matching tool calls against triggers and
  enforcing a `do` action. That framing is retired. If you want a
  tool-call-time guard, that's a different, harder problem (ask: does the
  host runtime already auto-attach the relevant context before your hook
  fires? if so, your hook has nothing left to add) — RSTP v3 does not
  attempt to solve it.

## 8. History: why v1/v2's guard framing was dropped

v1/v2 of this protocol modeled nodes as mistake-prevention lessons
(`pitfall`/`do`/`triggers`/`always_guard_tools`), descended directly from
[`vektra-reflex`](https://github.com/Vektra-Industries/vektra-reflex), a
Hermes-plugin guard. An independent A/B test against a strong model showed
that approach made no measurable difference: the host runtime's own skill
auto-attach already primed context before the model acted, so a guard hook
had nothing left to add on that path. Rather than keep chasing a narrower
and narrower definition of "guard that actually does something," v3 cuts
the pretense entirely and keeps only the part of the design that was
genuinely good: a DAG-shaped, evidence/practice-gated progression system.
Fields removed in this cut: `pitfall`, `do`, `triggers`, `always_guard_tools`,
the `prevented`/`ineffective`/`unknown` outcome vocabulary (replaced by a
single, simpler `practice` rep counter), and the `matches()`/trigger-match
CLI surface (`--match`, `log <outcome>`).

## 9. Importing existing skill libraries

An implementation MAY ship an importer that converts an existing library of
agent skills/capabilities into Seed-tier nodes, one per discovered skill, so
that a library of capabilities can be tracked the same practice-gated way
as any hand-written node. Node IDs from such an importer MUST be namespaced
(e.g. `<category>/<name>`) to avoid collisions between two differently-
categorized skills that happen to share a bare name. Re-running an importer
MUST NOT reset practice/tier/allocation on a node that already exists in
the target tree — only new, not-yet-seen skills are added.

## 10. Versioning

This file describes protocol version 3 (`"version": 3` in a tree's root).
v3 is a breaking change from v1/v2 (field removal, not just addition) — see
§8. Future breaking changes to field meaning require a version bump and a
migration note in this file.
