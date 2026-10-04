# RSTP v1 — Reflex Skill Tree Protocol

Status: Draft, v1. This document is the protocol; `rstp/` in this repo is one
conforming implementation (Python, stdlib-only). Anyone may implement RSTP in
any language against this spec — a JSON file and a few pure functions is the
entire interface surface.

## 1. Goals

- **Portable.** A tree is one JSON file. No database, no server, no plugin
  API, no framework dependency.
- **Model-agnostic.** The protocol does not assume any particular model,
  agent framework, or tool-calling format. It only assumes: *something* calls
  tools/actions by name, with some descriptive text (a path, a command), and
  *something* can read/write a JSON file before and after that call.
- **Evidence-driven.** Nothing in the tree reaches a strong enforcement tier
  without a logged, timestamped, real outcome. No self-certification.
- **Honest about its own limits.** A node that stops working says so
  (demotion) instead of silently staying trusted.

## 2. Data model

### 2.1 Tree

```json
{
  "version": 1,
  "branches": {
    "<branch_id>": {
      "title": "<human label>",
      "nodes": { "<node_id>": { ...Node } }
    }
  }
}
```

`branches` partitions nodes by topic (e.g. `credential-ops`, `git-safety`).
Partitioning is purely organizational — prerequisites may cross branches.

### 2.2 Node

| Field | Type | Meaning |
|---|---|---|
| `title` | string | Short human label. |
| `pitfall` | string | What goes wrong, described concretely. |
| `do` | string | The concrete corrective action. |
| `tier` | int 0-4 | See §3. Default 0 (Seed). |
| `prerequisites` | string[] | Node IDs that must be at tier >= 2 (Adept) before this node is considered unlocked. Default `[]`. |
| `triggers.tool_names` | string[] | Tool/action names this node watches. Empty = matches by path/text alone against any tool. |
| `triggers.path_glob` | string[] | Glob patterns matched against the call's descriptive text (path, command line, etc). Empty + non-empty `tool_names` = matches on tool name alone. |
| `always_guard_tools` | string[] | Keystone behavior (§3, tier 3). Tool names in this list stay enforced for this node even once any linked material has already been consulted this session. |
| `evidence.prevented` / `.ineffective` / `.unknown` | int | Outcome counters. See §4. |
| `evidence.sessions_seen` | string[] | Opaque session identifiers that have logged an outcome, for cross-session frequency awareness. |
| `skill` | string\|null | Optional pointer to external documentation (a skill name, a doc path, a URL) an agent should consult for this node. |
| `provenance` | object | Free-form: where this node's evidence came from (origin repo, PR, test name, date). Not interpreted by the protocol, kept for audit. |
| `created_at` / `updated_at` | string | ISO-8601 UTC timestamps. |

A **matching call** is any (tool_name, descriptive_text) pair such that:
`tool_names` is empty OR tool_name is in `tool_names`, AND
`path_glob` is empty (and `tool_names` non-empty) OR descriptive_text matches
one of the globs (as a substring match: `fnmatch(text, f"*{glob}*")`).

## 3. Tiers

Tiers are the enforcement contract, not cosmetic levels. An implementation
MUST treat them as follows:

| Tier | Name | An agent consulting this node MUST |
|---|---|---|
| 0 | Seed | Nothing required. Informational only. |
| 1 | Novice | Surface the `pitfall`/`do` to itself before acting (a reminder), but may still proceed against its own judgment. |
| 2 | Adept | Treat `do` as a hard constraint for the exact matching call — not merely a suggestion. |
| 3 | Guardian | Same as Adept, AND the constraint applies even if the agent has already consulted the node's `skill` (or any equivalent material) earlier in the same session. A node only reaches this behavior for tool names listed in `always_guard_tools`; other matching tools behave as Adept. |
| 4 | Master | The lesson is considered proven durably. Implementations SHOULD prompt folding the rule into the agent's standing instructions (system prompt, memory, docs) and removing the node from the active tree — a Master node is a graduation, not a permanent resident. |

Tier is an integer 0-4; implementations MUST reject out-of-range values.

## 4. Evidence and promotion

After any matching call actually happens, the calling agent SHOULD log one
outcome:

- `prevented` — the node's `do` (or the agent's own judgment informed by it)
  avoided the pitfall.
- `ineffective` — the pitfall happened anyway despite the node matching.
- `unknown` — the call matched but the outcome could not be determined.

### 4.1 Promotion rule (reference values; implementations MAY tune, MUST document any change)

A node promotes one tier when its cumulative `prevented` count (since the
last tier change) reaches a threshold AND `ineffective` is 0 since that same
point:

| From tier | Prevented needed to promote |
|---|---|
| Seed (0) | 1 |
| Novice (1) | 2 |
| Adept (2) | 4 |
| Guardian (3) | 8 |

Master (4) does not promote further.

### 4.2 Demotion rule

Any `ineffective` outcome on a node at tier >= 2 (Adept or higher) demotes it
one tier immediately. There is no grace period — a single failure at a tier
that implies a hard rule is reason enough to distrust it until re-proven.
Nodes at Seed or Novice do not demote further on `ineffective` (there is
nowhere below Seed to go).

### 4.3 Unlock (DAG gating)

A node is **unlocked** iff every id in its `prerequisites` resolves to a node
at tier >= 2 (Adept). Implementations MAY surface locked nodes differently in
status output but MUST NOT silently drop them from the tree.

## 5. Graph integrity

`prerequisites` form a directed graph (node -> prerequisite). Implementations
MUST reject (raise, refuse to save) any write that would introduce a cycle.
A conforming implementation detects cycles via standard DFS coloring (white/
gray/black) or an equivalent algorithm, and MUST name the exact cycle found
in its error when raising. Dangling prerequisites (pointing at a node id that
does not exist) are NOT a cycle and MAY be tolerated during incremental
building, but MUST be reported by a `validate`/`check` operation before the
tree is trusted.

## 6. What RSTP deliberately does not do

- It does not call tools, intercept calls, or hook into any runtime. The
  calling agent is responsible for checking the tree before acting and
  logging the outcome after.
- It does not include a scheduler, server, or multi-writer concurrency model.
  A tree file is assumed single-writer per session; merge conflicts across
  sessions are a file-merge problem (e.g. plain `git merge` on JSON, or an
  application-level reconciliation step), not a protocol concern in v1.
- It does not interpret `skill` or `provenance` beyond storing them as given.

## 7. Compatibility note: vektra-reflex

[`vektra-reflex`](https://github.com/Vektra-Industries/vektra-reflex) is a
Hermes-plugin implementation of a closely related idea (a `Lesson` record
with `title`/`pitfall`/`do`/`skill`/`triggers`/`mode`/`guard_until`/
`always_guard_tools`, enforced through `pre_tool_call`/`post_tool_call`
hooks). RSTP generalizes the same lesson shape into a protocol with no
framework dependency; the `mode` concept (`remind`/`guard`/`approve`) maps
onto RSTP tiers 1/2/3 respectively, and `always_guard_tools` ports over with
an identical name and meaning.

## 8. Versioning

This file describes protocol version 1 (`"version": 1` in a tree's root).
Breaking changes to field meaning (not additions) require a version bump and
a migration note in this file.
