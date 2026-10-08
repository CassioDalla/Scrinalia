"""
Pure rules for the text-quality catalog (Fase 3.5).

The functions here are deliberately free of SQLAlchemy: they define what an "excerpt"
is (how it is normalized, how it is fingerprinted and how a long field is broken into
candidate excerpts) so the frequency routine, the catalog and the tests all agree on
the same definition. The *application* of an approved excerpt to a document lives in
``repository/text_quality_repo.py`` and is expressed in SQL on purpose: the embedding
worker keys its idempotency stamp on an MD5 computed by PostgreSQL, so the composition
has exactly one implementation — the database's.
"""

import difflib
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field

#: Columns whose content forms the text read by the AI. ``final_title`` is here even
#: though the archivist writes it: a human title is signal, not noise.
AI_TEXT_COLUMNS: tuple[str, ...] = (
    "original_title",
    "final_title",
    "scope_content",
    "admin_bio_history",
    "provenance",
)

#: An excerpt shorter than this is not proposed by the frequency routine. Shorter
#: fragments match too much unrelated text ("da cidade", "nº 12") and a human
#: approving them would remove legitimate content.
EXCERPT_MIN_LENGTH = 40

#: A title prefix is allowed to be shorter than a sentence: the measured fixed prefix
#: is 23 characters ("Registros Fotográficos -") and it is repeated in 2467 documents.
TITLE_PREFIX_MIN_LENGTH = 12

#: Consumers of the AI text. An excerpt declares which of them must stop reading it:
#: ``EMBEDDING`` (the semantic vector), ``NER`` (extraction and classification text) and
#: ``TITLE`` (the derived title suggestion — the stored title is never rewritten).
TEMPLATE_SCOPES: tuple[str, ...] = ("EMBEDDING", "NER", "TITLE")

#: What an excerpt affects when the curator says nothing.
DEFAULT_TEMPLATE_SCOPE: tuple[str, ...] = ("EMBEDDING", "NER")

#: Sentence boundaries used to look for boilerplate *inside* an otherwise distinct
#: field (the measured case: a shared block followed by a document-specific sentence).
_SEGMENT_SPLIT_RE = re.compile(r"(?<=[.;!?])\s+|\n+")

#: Explicit whitespace class shared by the Python normalization and the SQL one.
#:
#: An explicit set is used instead of ``\s`` because the two engines do **not** agree:
#: PostgreSQL's ``[[:space:]]`` does not match U+00A0 (non-breaking space) while Python's
#: ``\s`` does. A suggested excerpt that the database cannot match is worse than useless —
#: the archivist would approve it and nothing would change. Verified against PostgreSQL 15
#: character by character.
WHITESPACE_PATTERN = (
    "[ \t\n\r\f\v\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009"
    "\u200a\u2028\u2029\u202f\u205f\u3000]+"
)

_WHITESPACE_RE = re.compile(WHITESPACE_PATTERN)


def normalize_excerpt(text: str) -> str:
    """
    Canonical spelling of an excerpt: whitespace collapsed and trimmed.

    Collapsing whitespace is what makes the catalog usable at all — the collection
    carries the same block with one and two spaces after a comma — and it is also the
    normalization PostgreSQL applies before matching (see ``normalized_column_sql``).
    Both sides must stay byte-identical on this rule, so they share ``WHITESPACE_PATTERN``.
    """
    return _WHITESPACE_RE.sub(" ", text).strip()


def excerpt_fingerprint(text: str) -> str:
    """SHA-256 of the normalized excerpt; the catalog's idempotency key."""
    return hashlib.sha256(normalize_excerpt(text).encode("utf-8")).hexdigest()


def split_excerpt_segments(text: str) -> list[str]:
    """
    Breaks a long field into sentence-like segments, dropping the too-short ones.

    Used only by the suggestion routine: the whole field is proposed as one candidate
    *and* its repeated sentences are proposed separately, because a field can be
    document-specific on the outside and boilerplate on the inside.
    """
    normalized = normalize_excerpt(text)
    segments = (segment.strip() for segment in _SEGMENT_SPLIT_RE.split(normalized))
    return [segment for segment in segments if len(segment) >= EXCERPT_MIN_LENGTH]


def title_prefix_candidates(title: str, max_words: int = 5, min_words: int = 2) -> list[str]:
    """
    Word prefixes of a title that could be a fixed template.

    The measured case is ``"Registros Fotográficos - X"``: the fixed part is a prefix
    and the specific part follows, so no sentence split ever sees it. A prefix is only
    a candidate while something is left after it — proposing the whole title would
    delete the title instead of normalizing it.
    """
    words = normalize_excerpt(title).split(" ")
    if len(words) <= min_words:
        return []

    last = min(max_words, len(words) - 1)
    return [" ".join(words[:size]) for size in range(min_words, last + 1)]


def excerpt_shape(text: str) -> str:
    """
    The excerpt with every whitespace removed; the cheap identity of a spelling family.

    Measured on the real collection: the three spellings of the 1242-character block
    differ **only** by spaces (ten insertions and one ``"terminais,"``/``" terminais, "``
    swap), so the 1930, 480 and 57-document variants collapse into one shape. Grouping by
    shape before applying the frequency floor is what stops the floor from discarding the
    smallest variant and leaving the block looking rarer than its own sentences.
    """
    return _WHITESPACE_RE.sub("", text)


@dataclass
class SuggestionCandidate:
    """A repeated excerpt found in the collection, with the evidence behind it."""

    text: str
    occurrence_count: int
    sample_document_ids: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    variants: list[str] = field(default_factory=list)
    scope: list[str] = field(default_factory=lambda: list(DEFAULT_TEMPLATE_SCOPE))


class ExcerptSuggestionAggregator:
    """
    Counts repeated excerpts across the collection, without writing anything.

    Three complementary readings of the same data, because boilerplate hides in three
    shapes and each one was measured in the real collection:

    1. **Whole field** — the same 1242-character block in 1930 documents.
    2. **Sentence** — boilerplate inside an otherwise specific field (the block plus one
       document-specific sentence).
    3. **Title prefix** — ``"Registros Fotográficos - X"``: a fixed prefix, invisible to
       any sentence split.

    The result is evidence for a human decision: counts and samples, never an edit.
    """

    SAMPLE_LIMIT = 5

    def __init__(self, title_column: str = "original_title") -> None:
        self.title_column = title_column
        self._counts: Counter[str] = Counter()
        self._documents: dict[str, set[str]] = {}
        self._columns: dict[str, set[str]] = {}
        #: Texts that were observed as the *whole* content of a field, as opposed to a
        #: sentence or a title prefix inside it. Only a whole field can make the pieces it
        #: contains redundant; a longer prefix cannot.
        self._whole_values: set[str] = set()
        #: Title prefixes that were proposed. Only these can make a longer prefix redundant:
        #: the whole block also *starts with* its own first sentence, and that is the block
        #: containing the sentence, not a refinement of it.
        self._prefixes: set[str] = set()

    def observe(self, document_id: str, column: str, value: str) -> None:
        """Registers one field of one document. A text is counted once per document."""
        normalized = normalize_excerpt(value)
        if not normalized:
            return

        candidates: list[str] = []
        if len(normalized) >= EXCERPT_MIN_LENGTH:
            candidates.append(normalized)
            self._whole_values.add(normalized)

        candidates.extend(split_excerpt_segments(normalized))

        if column == self.title_column:
            prefixes = [
                prefix for prefix in title_prefix_candidates(normalized) if len(prefix) >= TITLE_PREFIX_MIN_LENGTH
            ]
            candidates.extend(prefixes)
            self._prefixes.update(prefixes)

        # ``dict.fromkeys`` deduplicates the views of the same text (a whole field is
        # also its own first segment) so one document never counts twice.
        for candidate in dict.fromkeys(candidates):
            self._counts[candidate] += 1
            self._columns.setdefault(candidate, set()).add(column)
            self._documents.setdefault(candidate, set()).add(document_id)

    def candidates(self, min_count: int, similarity: float = 0.95) -> list[SuggestionCandidate]:
        """
        Candidates repeated at least ``min_count`` times, near-duplicates merged.

        The pipeline is ordered this way for a measured reason:

        1. **Shape buckets first, floor later.** The 57-document spelling of the big block
           is below any sensible floor on its own; filtering before grouping would drop it
           and leave the block (2410 documents) looking rarer than a sentence *inside* it
           (2467), so the sentence would never be pruned as redundant.
        2. **Union, never sum.** ``"Registros Fotográficos"`` is a prefix of
           ``"Registros Fotográficos -"``: the same 2467 documents match both, and summing
           the variants would double the evidence.
        3. **Substring pruning last**, so the decision the archivist sees is the whole
           block, not the five sentences it contains.

        ``similarity`` is deliberately high (0.95): short title prefixes grow one word at a
        time, and a looser threshold would swallow the first word of the specific part
        (``"Registros Fotográficos -"`` would become ``"... - Rua"``).
        """
        buckets: dict[str, list[str]] = {}
        for text in self._counts:
            buckets.setdefault(excerpt_shape(text), []).append(text)

        entries: list[tuple[str, list[str], set[str]]] = []
        for shape, texts in buckets.items():
            documents = set().union(*(self._documents[text] for text in texts))
            if len(documents) >= min_count:
                entries.append((shape, texts, documents))

        merged: list[tuple[str, list[str], set[str]]] = []
        for shape, texts, documents in sorted(entries, key=lambda entry: -len(entry[2])):
            for index, (other_shape, other_texts, other_documents) in enumerate(merged):
                matcher = difflib.SequenceMatcher(None, other_shape, shape)
                # ``quick_ratio`` is an upper bound and costs far less than ``ratio`` on the
                # long blocks this catalog exists for; it filters almost every pair out.
                if matcher.quick_ratio() >= similarity and matcher.ratio() >= similarity:
                    merged[index] = (other_shape, [*other_texts, *texts], other_documents | documents)
                    break
            else:
                merged.append((shape, list(texts), set(documents)))

        candidates: list[SuggestionCandidate] = []
        for _shape, texts, documents in merged:
            representative = max(texts, key=len)
            columns = sorted(set().union(*(self._columns[text] for text in texts)))
            variants = sorted((text for text in texts if text != representative), key=len, reverse=True)
            candidates.append(
                SuggestionCandidate(
                    text=representative,
                    occurrence_count=len(documents),
                    sample_document_ids=sorted(documents)[: self.SAMPLE_LIMIT],
                    columns=columns,
                    variants=variants,
                    # A decision about the title field is proposed for the derived title, not
                    # for the embedded text: measurement showed that subtracting the repeated
                    # title prefix from the vector made the ranking worse, while it is exactly
                    # what the title suggestion needs.
                    scope=["TITLE"] if columns == ["original_title"] else list(DEFAULT_TEMPLATE_SCOPE),
                )
            )

        return sorted(
            self._prune_substrings(candidates),
            key=lambda candidate: (-candidate.occurrence_count, candidate.text),
        )

    def _prune_substrings(self, candidates: list[SuggestionCandidate]) -> list[SuggestionCandidate]:
        """
        Drops a candidate that another decision already covers.

        Two ways to be redundant, evaluated against the whole candidate set so the result
        does not depend on the order the groups happened to be built in:

        * **Contained in a repeated field.** Every sentence of the 1242-character block is
          inside the block itself: same decision, listed five times.
        * **A refinement of a proposed prefix.** ``"Projeto de uma casa para"`` removes less
          than ``"Projeto de uma"`` from the same documents, because the shorter prefix is a
          prefix of it. The longer spelling is only kept when it is *more* frequent.
        """

        def is_redundant(candidate: SuggestionCandidate) -> bool:
            for other in candidates:
                if other.text == candidate.text or other.occurrence_count < candidate.occurrence_count:
                    continue
                # Every spelling of the other decision counts as a container: the block and
                # its variant differ by a space that may fall inside the tested sentence.
                if other.text in self._whole_values and any(
                    candidate.text in spelling for spelling in (other.text, *other.variants)
                ):
                    return True
                # A whole field is never a "refinement" of its own prefix: without this the
                # repeated title and its prefix would prune each other and neither would be
                # proposed.
                if (
                    candidate.text not in self._whole_values
                    and other.text in self._prefixes
                    and candidate.text.startswith(f"{other.text} ")
                ):
                    return True
            return False

        return [candidate for candidate in candidates if not is_redundant(candidate)]
