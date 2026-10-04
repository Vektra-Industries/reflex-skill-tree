"""RSTP — Reflex Skill Tree Protocol.

Stdlib-only reference implementation. Pure skill-tree software: no plugin,
no hooks, no daemon, no guard. A tree.json file and a library/CLI that
reads and writes it.

Any AI agent, any model, any framework. See SPEC.md for the protocol.
"""
from __future__ import annotations

from .tree import (
    Node,
    TierName,
    Tree,
    load,
    save,
    validate_dag,
)

__version__ = "0.7.0"
__all__ = ["Node", "TierName", "Tree", "__version__", "load", "save", "validate_dag"]
