"""
The input guards the host command lines share.

A bounded run is a flag of two layers — ``--limit`` on the scrape and on the transform — and ``0``
has to be a usage error in both: ``LIMIT 0`` reads nothing and exits successfully, which an operator
cannot tell apart from "the queue is empty". One definition of "a positive count" keeps the two
command lines from answering that differently, which is the same reason the queue predicates are
shared rather than rewritten per caller.
"""

import argparse


def positive_int(value: str) -> int:
    """An argparse type: a count that must be at least one."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def non_negative_int(value: str) -> int:
    """An argparse type: a count that may be zero (a retry budget, for instance)."""
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number
