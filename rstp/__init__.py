"""RSTP — Reflex Skill Tree Protocol.

Stdlib-only reference implementation. No plugin, no hooks, no daemon:
a tree.json file and a library/CLI that reads and writes it.

Any AI agent, any model, any framework. See SPEC.md for the protocol.
"""
from __future__ import annotations

from .tree import (
    Node,
    Tree,
    TierName,
    load,
    save,
    validate_dag,
)

__version__ = "0.1.0"
__all__ = ["Node", "Tree", "TierName", "load", "save", "validate_dag", "__version__"]
