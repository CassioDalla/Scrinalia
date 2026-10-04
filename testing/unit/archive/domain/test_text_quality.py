"""Unit tests of the pure text-quality rules (no database, no model)."""

from memoria_curitibana.domains.archive.domain.text_quality import (
    EXCERPT_MIN_LENGTH,
    ExcerptSuggestionAggregator,
    excerpt_fingerprint,
    excerpt_shape,
    normalize_excerpt,
    split_excerpt_segments,
    title_prefix_candidates,
)

BLOCK = (
    "Acervo de 35.327 fotografias que retratam a cidade de Curitiba no âmbito do "
    "Planejamento, Urbanização e Fiscalização; - Parques, Bosques, Praças, Bairros e Ruas de Curitiba; "
    "- Pavimentação urbana, dragagem, canalização;"
)


# ==========================================
# NORMALIZATION AND FINGERPRINT
# ==========================================


def test_normalize_excerpt_collapses_whitespace_and_trims() -> None:
    assert normalize_excerpt("  dois   espaços\n\ne uma\tquebra ") == "dois espaços e uma quebra"


def test_normalize_excerpt_collapses_the_non_breaking_space() -> None:
    """
    Regression for the measured divergence: PostgreSQL's ``[[:space:]]`` does not match
    U+00A0 while Python's ``\\s`` does, so the two sides share ``WHITESPACE_PATTERN``.
    """
    assert normalize_excerpt("a\u00a0b   c") == "a b c"


def test_excerpt_fingerprint_ignores_whitespace_differences() -> None:
    """Whitespace variants of the same block are one catalog row, not three."""
    assert excerpt_fingerprint("bloco  repetido") == excerpt_fingerprint("bloco repetido")
    assert excerpt_fingerprint("bloco repetido") != excerpt_fingerprint("outro bloco")


def test_excerpt_shape_removes_all_whitespace() -> None:
    assert excerpt_shape("a b\tc") == "abc"


# ==========================================
# CANDIDATE VIEWS
# ==========================================


def test_split_excerpt_segments_drops_the_too_short_ones() -> None:
    text = f"curto; {BLOCK}"
    segments = split_excerpt_segments(text)

    assert all(len(segment) >= EXCERPT_MIN_LENGTH for segment in segments)
    assert any(segment.startswith("Acervo de 35.327") for segment in segments)


def test_title_prefix_candidates_stop_before_the_specific_part() -> None:
    prefixes = title_prefix_candidates("Registros Fotográficos - Rua Izaac Ferreira da Cruz")

    assert "Registros Fotográficos" in prefixes
    assert "Registros Fotográficos -" in prefixes
    # The whole title is never a prefix: proposing it would delete the title.
    assert "Registros Fotográficos - Rua Izaac Ferreira da Cruz" not in prefixes


def test_title_prefix_candidates_are_empty_for_a_short_title() -> None:
    assert title_prefix_candidates("Rua Izaac") == []


# ==========================================
# AGGREGATOR
# ==========================================


def test_aggregator_counts_a_document_once_even_with_repeated_text() -> None:
    aggregator = ExcerptSuggestionAggregator()
    aggregator.observe("doc-1", "scope_content", BLOCK)
    aggregator.observe("doc-1", "scope_content", BLOCK)

    candidate = next(c for c in aggregator.candidates(min_count=1, similarity=1.0) if c.text == BLOCK)
    assert candidate.occurrence_count == 1


def test_aggregator_groups_whitespace_variants_and_uses_the_union_count() -> None:
    """
    The measured family: 1930 + 480 + 57 documents spelling the same block differently.
    Grouping by shape keeps the smallest variant from being dropped by the floor, and the
    count is the union of documents — never the sum, which would double-count.
    """
    aggregator = ExcerptSuggestionAggregator()
    for index in range(3):
        aggregator.observe(f"a-{index}", "scope_content", BLOCK)
    for index in range(2):
        aggregator.observe(f"b-{index}", "scope_content", BLOCK.replace(";", " ;"))

    candidates = [c for c in aggregator.candidates(min_count=4) if c.text.startswith("Acervo de 35.327")]
    assert len(candidates) == 1
    assert candidates[0].occurrence_count == 5


def test_aggregator_keeps_a_variant_below_the_floor_when_the_family_passes() -> None:
    aggregator = ExcerptSuggestionAggregator()
    for index in range(5):
        aggregator.observe(f"a-{index}", "scope_content", BLOCK)
    aggregator.observe("b-0", "scope_content", BLOCK.replace(";", " ;"))

    candidates = [c for c in aggregator.candidates(min_count=5) if c.text.startswith("Acervo de 35.327")]
    assert len(candidates) == 1
    assert candidates[0].occurrence_count == 6
    # The longest spelling leads and the majority spelling becomes its variant.
    assert candidates[0].variants == [BLOCK]


def test_aggregator_prunes_a_sentence_contained_in_the_repeated_block() -> None:
    aggregator = ExcerptSuggestionAggregator()
    for index in range(4):
        aggregator.observe(f"doc-{index}", "scope_content", BLOCK)

    texts = [candidate.text for candidate in aggregator.candidates(min_count=2)]
    assert BLOCK in texts
    # The sentences of the block are the same decision; listing them is noise.
    assert not any(text.startswith("- Parques, Bosques") for text in texts)


def test_aggregator_never_doubles_a_prefix_count() -> None:
    """``"Registros Fotográficos"`` and ``"... -"`` cover the same documents."""
    aggregator = ExcerptSuggestionAggregator()
    for index in range(6):
        # Distinct specific parts, as in the real collection: only the fixed prefix repeats.
        aggregator.observe(f"doc-{index}", "original_title", f"Registros Fotográficos - Rua número {index}")

    candidates = [c for c in aggregator.candidates(min_count=5) if c.text.startswith("Registros Fotográficos")]
    assert len(candidates) == 1
    assert candidates[0].occurrence_count == 6
    # The longest spelling leads, so the trailing separator does not survive the removal.
    assert candidates[0].text == "Registros Fotográficos -"


def test_aggregator_keeps_samples_bounded_to_the_limit() -> None:
    aggregator = ExcerptSuggestionAggregator()
    for index in range(12):
        aggregator.observe(f"doc-{index:02d}", "scope_content", BLOCK)

    candidate = next(c for c in aggregator.candidates(min_count=2) if c.text == BLOCK)
    assert candidate.occurrence_count == 12
    assert candidate.sample_document_ids == [
        f"doc-{index:02d}" for index in range(ExcerptSuggestionAggregator.SAMPLE_LIMIT)
    ]


def test_aggregator_reports_the_columns_where_the_excerpt_appears() -> None:
    aggregator = ExcerptSuggestionAggregator()
    aggregator.observe("doc-1", "scope_content", BLOCK)
    aggregator.observe("doc-2", "admin_bio_history", BLOCK)

    candidate = next(c for c in aggregator.candidates(min_count=1) if c.text == BLOCK)
    assert candidate.columns == ["admin_bio_history", "scope_content"]


# ==========================================
# SCOPE PER CONSUMER (measured decision)
# ==========================================


def test_aggregator_scopes_a_title_prefix_to_the_title_suggestion() -> None:
    """
    Removing the repeated title prefix from the embedded vector made the ranking worse in
    the benchmark, while it is exactly what the derived title needs: the proposal carries
    the scope that the measurement justified.
    """
    aggregator = ExcerptSuggestionAggregator()
    for index in range(6):
        aggregator.observe(f"doc-{index}", "original_title", f"Registros Fotográficos - Rua número {index}")

    candidate = next(c for c in aggregator.candidates(min_count=5) if c.text.startswith("Registros Fotográficos"))
    assert candidate.scope == ["TITLE"]


def test_aggregator_scopes_a_body_excerpt_to_the_ai_text() -> None:
    aggregator = ExcerptSuggestionAggregator()
    for index in range(6):
        aggregator.observe(f"doc-{index}", "scope_content", BLOCK)

    candidate = next(c for c in aggregator.candidates(min_count=5) if c.text == BLOCK)
    assert candidate.scope == ["EMBEDDING", "NER"]
