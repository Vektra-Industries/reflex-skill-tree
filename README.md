# RSTP — Reflex Skill Tree Protocol

An open, model-agnostic mistake-prevention system for AI agents, shaped like a
video-game skill tree instead of a plugin.

No hooks. No daemon. No framework lock-in. **One JSON file an agent reads, and
one small script it calls before and after a risky action.** Any model, any
agent, any framework — Hermes, LangChain, a raw OpenAI/Anthropic loop, a bash
script calling an LLM API, anything that can read a file and run a CLI.

## Why

Built out of real evidence from testing [`vektra-reflex`](https://github.com/Vektra-Industries/vektra-reflex),
a Hermes-plugin version of the same idea. Two honest findings from that work
drove this design:

1. **A plugin hook can be a no-op against a strong model.** Modern agent
   runtimes often auto-attach relevant context (skills, docs, retrieved
   lessons) *before* a hook ever fires — so a plugin that only speaks through
   hooks has nothing left to add on that path. A plain file + script has no
   such blind spot: any agent can check it any time, regardless of what its
   host runtime did or didn't auto-load.
2. **"I read the rule" isn't "I will follow it."** Even when a model has
   genuinely seen the relevant lesson, that's not the same as it obeying the
   lesson on the very next matching call. RSTP's answer is the **Guardian**
   tier (see below) — borrowed directly from the "keystone" concept in games
   like Path of Exile: a commitment that stays enforced regardless of what
   else the agent has already read this session.

## The game model

Researched real skill-tree design (Path of Exile's shared DAG, Diablo's
tiered talents, Final Fantasy X's Sphere Grid) and kept what transfers:

- **Node, not flat rule.** One lesson = one node: `title`, `pitfall`, `do`,
  `triggers` (which tool + what pattern fires it).
- **DAG, not a list.** A node can require prerequisite nodes be proven first
  (`prerequisites`). Cycles are rejected at write time — a bad edit never
  corrupts the tree.
- **Tiers carry real weight**, not just a label:

  | Tier | Name | Enforcement |
  |---|---|---|
  | 0 | Seed | Drafted, unproven. Informational only — the agent may ignore it. |
  | 1 | Novice | Proven once. The agent reminds itself when the trigger matches. |
  | 2 | Adept | Proven twice clean. The `do` is a hard rule for that exact call. |
  | 3 | **Guardian** | Keystone-equivalent — stays enforced even if the agent already read the related material this session. Set via `always_guard_tools`. |
  | 4 | Master | Proven across many sessions. Retire it: fold the rule into the agent's standing instructions and delete the node — a Master node sitting in the tree forever is clutter, not progress. |

- **Promotion is evidence-gated**, never self-reported. Every real trigger
  match gets logged as `prevented` / `ineffective` / `unknown`. A node
  promotes after enough clean `prevented` outcomes with zero `ineffective`
  since the last change; it demotes immediately on `ineffective`, no grace
  period, same as a build-defining keystone being wrong.
- **Any agent is a starting position on one shared tree**, not a fork. Trees
  are plain portable JSON — fork one, merge two, or start fresh from someone
  else's already-proven nodes.

See [`SPEC.md`](SPEC.md) for the full protocol and [`rstp/tree.py`](rstp/tree.py)
for the reference implementation (stdlib-only, ~250 lines).

## Install

```bash
pip install rstp   # or: pip install -e . from a clone
```

No dependencies. Python 3.9+. Works with any model/agent — RSTP has no
opinion on what's calling it.

## Quickstart

```bash
# seed one real lesson
cat > cred.json <<'EOF'
{"title": "Safe .env editing",
 "pitfall": "Rewriting a .env wholesale mangles escaped/non-ASCII values.",
 "do": "Back it up, change one line with a targeted patch, diff to verify.",
 "tier": 3,
 "triggers": {"tool_names": ["write_file", "patch"], "path_glob": ["*.env"]},
 "always_guard_tools": ["write_file"]}
EOF
rstp seed cred.json --branch credential-ops --id cred-001

# before a risky call, check the tree
rstp status --match "write_file /home/user/.env"

# after the call, log the real outcome
rstp log cred-001 prevented --session my-agent-session-42
```

Or drive it as a library from any agent loop:

```python
from rstp import load, save

tree = load("tree.json")
hits = tree.match(tool_name="write_file", text="write_file /home/user/.env")
for node in hits:
    if node.tier >= 2:            # Adept or higher: treat `do` as a hard rule
        print(node.do)
    if node.always_guard_tools and "write_file" in node.always_guard_tools:
        # Guardian: stays enforced even if you already read the linked docs
        block_the_call()

# ... after the call actually ran:
tree.record("cred-001", "prevented", session="my-agent-session-42")
save(tree, "tree.json")
```

## Porting lessons from vektra-reflex

A vektra-reflex `Lesson` (`title`/`pitfall`/`do`/`skill`/`triggers`/
`guard_until`/`always_guard_tools`) maps directly onto an RSTP `Node` — same
field names for everything except `mode`/`guard_until`, which become a tier.
See [`examples/from-vektra-reflex.json`](examples/from-vektra-reflex.json).

## Status

v0.1.0. Reference implementation is stdlib-only Python with 23 unit tests
covering matching, DAG/cycle rejection, promotion/demotion, and persistence —
see `tests/`. This is a protocol + reference implementation, not a hosted
service: your tree, your file, your repo.

## License

MIT — see [`LICENSE`](LICENSE).
