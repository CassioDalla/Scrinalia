"""
The benches that measure the AI against labelled collection data.

The package is nearly empty on purpose — each bench is a script with its own entry point. It holds
the one rule the benches share about when a metric is allowed to be printed at all; the value itself
lives in the package, because the operations panel's trial shows the same metric (ADR 0018) and a
second definition of the floor would let the bench and the screen disagree.
"""

from scrinalia.domains.archive.evaluation.metrics import MIN_POSITIVES

__all__ = ["MIN_POSITIVES"]
