"""The reference code is a *path*, not a name: vocabulary-aware slicing (H3).

The collection is hierarchical and the evidence is the ``reference_code``, filled in for 100%
of the 3,608 real descriptions. But slicing it on every space is wrong for a third of the
acervo, and the measurement is what showed it::

    BR PRADAP IPPUC FOTOGRAFIA 00680            -> the token layout is structure + serial
    BR PRADAP SMU ED AL CONSTR 2154 1903        -> ... and here a number sits in the middle

Naive prefix slicing turns ``BR PRADAP SMU ED AL`` into **1,123 parents of one document each**,
because the code interleaves the arrangement vocabulary with the identifiers of the leaf. This
module separates the two: the arrangement is carried by the alphabetic tokens, and a trailing
run of identifiers belongs to the node they close, not to a rung of the tree.

The classification is deliberately conservative and never guesses:

* an **alphabetic** token is arrangement vocabulary (``IPPUC``, ``ED``, ``AL``, ``CONSTR``).
  ``str.isalpha`` is Unicode-aware, so ``LEGISLAÇÃO`` is vocabulary;
* anything else — digits, ``(1)``, ``369B``, ``998-1``, ``11925_1916`` — is an identifier;
* an identifier that is **not** a clean number is flagged ``UNPARSED_TAIL`` instead of being
  silently swallowed, because that is exactly the ~20 malformed codes a curator has to see;
* an identifier that survives *before* the last vocabulary token is flagged
  ``MID_CODE_IDENTIFIER`` (``BR PRADAP SEPLAD OF 478 1959 DUP``) and kept in the path: dropping
  it would invent a node, keeping it quietly would invent a rung.

Nothing here reads or writes the database. It answers one question — "which tokens describe the
arrangement, and which ones only name the leaf?" — and the proposal service decides what to do
with the answer.
"""

import enum
import re
from dataclasses import dataclass

# ``\s`` does not cover U+00A0 in every engine, and the real payloads carry it (the text
# quality work hit the same trap). The class is explicit so the two agree.
_WHITESPACE = re.compile(r"[\s\u00a0]+")

#: A trailing identifier the code expresses as a plain number is expected; anything else is a
#: spelling the curator should look at.
_PLAIN_NUMBER = re.compile(r"^\d+$")

#: The shallowest arrangement a code can name: ``BR PRADAP``, the custodian entity's own collection.
#: Kept here so the slicer, the proposal and the migration cannot disagree about where the ladder
#: starts.
ROOT_MIN_TOKENS = 2


class CodeFlag(enum.StrEnum):
    """What the slicer noticed about a code. Advisory: it never changes the outcome silently."""

    #: An identifier sits before the last vocabulary token, so the segmentation is a guess.
    MID_CODE_IDENTIFIER = "MID_CODE_IDENTIFIER"
    #: The trailing identifiers are not plain numbers (``(1)``, ``369B``, ``998-1``, ``(II)``).
    UNPARSED_TAIL = "UNPARSED_TAIL"
    #: No alphabetic token at all: the code carries no arrangement vocabulary.
    NO_STRUCTURAL_TOKEN = "NO_STRUCTURAL_TOKEN"


@dataclass(frozen=True)
class SlicedReferenceCode:
    """One ``reference_code`` split into arrangement vocabulary and trailing identifiers."""

    raw: str
    tokens: tuple[str, ...]
    #: Tokens up to and including the last vocabulary token: the arrangement the code declares.
    structural: tuple[str, ...]
    #: Tokens that only identify the leaf. They are contracted into the node, never a rung.
    dropped_tail: tuple[str, ...]
    flags: tuple[CodeFlag, ...]

    @property
    def structural_code(self) -> str:
        """The arrangement path as a string (``"BR PRADAP SMU ED AL CONSTR"``)."""
        return " ".join(self.structural)

    @property
    def is_clean(self) -> bool:
        """True when no identifier sits before the last vocabulary token and the tail is numeric."""
        return not self.flags

    def rungs(self) -> tuple[str, ...]:
        """
        Every rung of the arrangement this code sits on, root first, the code itself last.

        The prefixes are the containers the code implies and that the source may never have sent as
        records — ``BR PRADAP``, ``BR PRADAP SMU``, ``BR PRADAP SMU ED`` … for a SMU process. They
        are expressed in **codes**, not ids, because the proposal is computed before any node
        exists; materialising them (H4) is what translates a code into an id.
        """
        return tuple(" ".join(self.structural[:size]) for size in range(ROOT_MIN_TOKENS, len(self.structural) + 1))


def tokenize(reference_code: str) -> tuple[str, ...]:
    """Splits a reference code on whitespace, dropping the empty parts a double space creates."""
    return tuple(part for part in _WHITESPACE.split(reference_code.strip()) if part)


def normalize_reference_code(reference_code: str) -> str:
    """
    Canonical form used to compare codes across records.

    Whitespace is collapsed and the text upper-cased: the source is not consistent about either,
    and two records whose codes differ only in spacing are the same arrangement rung. Punctuation
    is left alone — ``369B`` and ``998-1`` are real codes, not typos, and folding them would make
    two different descriptions collide.
    """
    return " ".join(tokenize(reference_code)).upper()


def is_structural_token(token: str) -> bool:
    """
    True when the token names part of the arrangement rather than a leaf.

    ``str.isalpha`` is the whole rule, and the measurement is the reason it is enough: across
    all 3,608 real codes, every arrangement token is alphabetic (``IPPUC``, ``SMICS``,
    ``CONSTR``, ``LEGISLAÇÃO``) and every identifier carries a digit or a bracket.
    """
    return token.isalpha()


def slice_reference_code(reference_code: str) -> SlicedReferenceCode:
    """Separates the arrangement vocabulary of a code from the identifiers of its leaf."""
    tokens = tokenize(reference_code)

    last_structural = -1
    for index in range(len(tokens) - 1, -1, -1):
        if is_structural_token(tokens[index]):
            last_structural = index
            break

    if last_structural < 0:
        return SlicedReferenceCode(
            raw=reference_code,
            tokens=tokens,
            structural=(),
            dropped_tail=tokens,
            flags=(CodeFlag.NO_STRUCTURAL_TOKEN,),
        )

    structural = tokens[: last_structural + 1]
    dropped_tail = tokens[last_structural + 1 :]

    flags: list[CodeFlag] = []
    if any(not _PLAIN_NUMBER.match(token) for token in dropped_tail):
        flags.append(CodeFlag.UNPARSED_TAIL)
    if any(not is_structural_token(token) for token in structural):
        flags.append(CodeFlag.MID_CODE_IDENTIFIER)

    return SlicedReferenceCode(
        raw=reference_code,
        tokens=tokens,
        structural=structural,
        dropped_tail=dropped_tail,
        flags=tuple(flags),
    )
