"""The AlgorithmTrace dataclass — contract between algorithms and the UI.

Every algorithm implemented in later phases will return
`(result, AlgorithmTrace)`. Programmer Mode in the UI uses the trace to
render technical details (complexity, runtime, code, formulas).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AlgorithmTrace:
    name: str                                          # "Dijkstra's Algorithm"
    complexity_time: str                               # "O((V+E) log V)"
    complexity_space: str                              # "O(V)"
    nodes_explored: list[Any] = field(default_factory=list)
    edges_relaxed: int = 0
    runtime_ms: float = 0.0
    parameters: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""                              # Plain-English, 1-3 sentences
    formula: str | None = None                         # Optional LaTeX-friendly string
    code_snippet: str = ""                             # The actual function source
    extra: dict[str, Any] = field(default_factory=dict)
