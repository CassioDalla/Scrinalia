"""One list, two readers: the benches and the worker options refuse the same columns (#120).

The measured defect was two definitions of what the AI may read. The evaluation benches compared a
``--config engine:preset:columns`` against ``AI_TEXT_COLUMNS`` and refused a typo; the settings and
run paths accepted the same typo and stored it as a default, so the run failed later — in the counter
that builds the queue predicate, or in the ledger, as an ``AttributeError``.

This is the pin the issue asks for: the same spelling is accepted or refused by both readers, and the
list either of them names as the known ones is the same tuple.
"""

from __future__ import annotations

import pytest

from scrinalia.domains.archive.domain.text_quality import AI_TEXT_COLUMNS
from scrinalia.domains.archive.exceptions import InvalidWorkerSettingsError
from scrinalia.domains.archive.workers import catalogue
from scrinalia.domains.archive.workers.configuration import validate_options
from testing.evaluation.ner_quality import parse_config as parse_ner_config
from testing.evaluation.typology_quality import parse_config as parse_typology_config

TYPO = "admin_bio_historia"
KNOWN = AI_TEXT_COLUMNS


def _ner_spec() -> catalogue.WorkerSpec:
    return catalogue.WORKER_CATALOGUE["ner"]


def _typology_spec() -> catalogue.WorkerSpec:
    return catalogue.WORKER_CATALOGUE["typology"]


def test_the_ner_bench_refuses_a_column_the_write_path_also_refuses() -> None:
    with pytest.raises(SystemExit) as bench:
        parse_ner_config(f"spacy_ner:gpu:original_title,{TYPO}", KNOWN)

    with pytest.raises(InvalidWorkerSettingsError) as api:
        validate_options(_ner_spec(), {"columns_to_extract": ["original_title", TYPO]})

    for sentence in (str(bench.value), str(api.value)):
        assert TYPO in sentence
        for column in KNOWN:
            assert column in sentence


def test_the_typology_bench_refuses_a_column_the_write_path_also_refuses() -> None:
    with pytest.raises(SystemExit) as bench:
        parse_typology_config(f"deberta_typology:cpu_local:original_title,{TYPO}:0.4", KNOWN, 0.4)

    with pytest.raises(InvalidWorkerSettingsError) as api:
        validate_options(_typology_spec(), {"columns_to_classify": ["original_title", TYPO]})

    for sentence in (str(bench.value), str(api.value)):
        assert TYPO in sentence
        for column in KNOWN:
            assert column in sentence


def test_a_valid_column_set_passes_both_readers() -> None:
    columns = ["original_title", "scope_content"]
    config = parse_ner_config(f"spacy_ner:gpu:{','.join(columns)}", KNOWN)
    validate_options(_ner_spec(), {"columns_to_extract": columns})

    assert list(config.columns) == columns
    # ``unknown_ai_columns`` is the one check behind both readers, so the equality above is the pin.
    from scrinalia.domains.archive.domain.text_quality import unknown_ai_columns

    assert unknown_ai_columns(columns) == []
