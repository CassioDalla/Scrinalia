"""
Integration tests for the typology bench (issue #69).

The load-bearing one is the pin: the bench must read the text the worker reads. It is measured by
running the real worker with a fake engine and comparing what the worker handed to the model with
what the bench composes for the same document — a bench that composed the text in Python would
measure a text the worker never sees (principle IV).
"""

from __future__ import annotations

from scrinalia.domains.archive.engines.classification import registry as typology_registry
from scrinalia.domains.archive.models import ArchiveDocument
from scrinalia.domains.archive.repository.text_quality_repo import TextQualityRepository
from scrinalia.domains.archive.schemas.text_quality_schema import TemplateCreateCommand
from scrinalia.domains.archive.workers.worker_typology import execute
from testing.evaluation.typology_quality import (
    ABSTAINED,
    LabelledRow,
    Truth,
    parse_config,
    read_collection,
    read_input_text,
    score_live,
    score_stored,
    stored_collection_distribution,
)

BLOCK = "Acervo de 35.327 fotografias que retratam a cidade de Curitiba no âmbito do Planejamento"


def labelled(description_id: str, expected: str | None) -> LabelledRow:
    return LabelledRow(
        description_id=description_id,
        truth=Truth(labels=None if expected is None else frozenset({expected})),
        needs_decision=False,
        note="",
    )


def test_the_bench_reads_the_same_text_the_worker_reads(
    use_test_db,
    db_session,
    generate_archive_doc,
    generate_typology,
    mock_registry,
):
    """
    The pin of the pair, with an approved excerpt in the middle.

    The excerpt is what makes the test load-bearing: if the bench forgot the catalog rules and
    composed the columns itself, the boilerplate would still be there and the two strings would
    differ. The worker's own default is the title alone, so the columns are widened here for the
    scope field to carry the excerpt.
    """
    typology = generate_typology(id=99, name="Fotografia")
    generate_archive_doc(
        description_id="same1",
        original_title="Registros Fotográficos - Rua Izaac",
        scope_content=BLOCK,
    )
    TextQualityRepository(db_session).create_template(TemplateCreateCommand(text=BLOCK))

    MockClass = mock_registry(typology_registry)
    engine = MockClass.return_value
    engine.classify.return_value = [{"labels": [typology.name], "scores": [0.99]}]

    columns = ["original_title", "scope_content"]
    execute(
        db=db_session,
        engine_name="motor_fake",  # type: ignore[arg-type]
        preset="preset_teste",  # type: ignore[arg-type]
        columns_to_classify=columns,
    )

    worker_text = engine.classify.call_args.args[0][0]
    bench_text = read_input_text(db_session, ["same1"], columns)["same1"]

    assert worker_text == "Registros Fotográficos - Rua Izaac"
    assert bench_text == worker_text


def test_score_stored_reads_the_typology_the_run_wrote(
    use_test_db,
    db_session,
    generate_archive_doc,
    generate_typology,
):
    """The stored mode answers "how did the run that shipped do?" without loading a model."""
    typology = generate_typology(id=99, name="Fotografia")
    document = generate_archive_doc(description_id="stored1", original_title="Registros Fotográficos - Rua Izaac")
    document.typology_id = typology.typology_id
    db_session.commit()

    scored = score_stored(db_session, [labelled("stored1", "Fotografia")])

    assert scored[0].prediction.label == "Fotografia"
    assert scored[0].correct


def test_score_stored_reports_an_untouched_document_as_an_abstention(
    use_test_db,
    db_session,
    generate_archive_doc,
):
    """
    The limitation, pinned rather than described: ``typology_id`` is NULL both when the run abstained
    and when it never reached the document, and the bench can only read the column.
    """
    generate_archive_doc(description_id="untouched", original_title="Registros Fotográficos - Rua Izaac")

    scored = score_stored(db_session, [labelled("untouched", "Fotografia")])

    assert scored[0].prediction.label is None
    assert not scored[0].correct


def test_stored_collection_distribution_counts_the_untouched_as_abstention(
    use_test_db,
    db_session,
    generate_archive_doc,
    generate_typology,
):
    """The collapse view covers the whole collection, so a never-run document is in the denominator."""
    typology = generate_typology(id=99, name="Fotografia")
    linked = generate_archive_doc(description_id="linked", original_title="Registros Fotográficos - Rua Izaac")
    linked.typology_id = typology.typology_id
    generate_archive_doc(description_id="pending", original_title="Projeto de uma casa para João do ano de 1924")
    db_session.commit()

    counts = stored_collection_distribution(db_session)

    assert counts["Fotografia"] == 1
    assert counts[ABSTAINED] == 1


def test_stored_collection_distribution_leaves_the_hierarchy_nodes_out(
    use_test_db,
    db_session,
    generate_archive_doc,
):
    """A fundo is not an item: the classifier never sees one, so it cannot be an abstention."""
    generate_archive_doc(description_id="node_abc123", original_title="Registros Fotográficos")
    generate_archive_doc(description_id="item1", original_title="Projeto de uma casa para João do ano de 1924")
    db_session.commit()

    counts = stored_collection_distribution(db_session)

    assert sum(counts.values()) == 1
    assert db_session.get(ArchiveDocument, "node_abc123") is not None


def test_a_formatted_run_hands_the_model_the_labels_and_still_scores_catalogue_names(
    use_test_db,
    db_session,
    generate_archive_doc,
    generate_typology,
    mock_registry,
):
    """
    The end of the format path, pinned where it can actually go wrong.

    The fake engine echoes the candidate label it was handed, which is what ``DebertaEngine`` does.
    So this pins both halves at once: the model really reads the formatted proposition, and what
    reaches the placar is the catalogue name and not the proposition — a bench that skipped the
    translation would score every row of this run as a miss.
    """
    generate_typology(id=99, name="Fotografia")
    generate_archive_doc(description_id="fmt1", original_title="Registros Fotográficos - Rua Izaac")

    MockClass = mock_registry(typology_registry)
    engine = MockClass.return_value
    engine.classify.side_effect = lambda texts, labels, **kwargs: [
        {"labels": [labels[0]], "scores": [0.99]} for _ in texts
    ]

    config = parse_config("motor_fake:preset_teste:original_title:0.40", ("original_title",), 0.40)
    scored, _seconds = score_live(db_session, config, [labelled("fmt1", "Fotografia")], label_format="sentence")

    assert engine.classify.call_args.args[1] == ["um documento do tipo Fotografia"]
    assert scored[0].prediction.label == "Fotografia"
    assert scored[0].correct


#: Real titles of the reference collection, one per stratum pattern, with the form the pattern owns.
#:
#: They are the collection's own titles and not invented ones because the patterns are **PostgreSQL**
#: regular expressions: the ones carrying ``\m``/``\M`` cannot be pinned by Python's ``re``, and the
#: ``livro\b`` that PostgreSQL does not read as a word boundary (#134) passed every Python reading
#: while matching nothing in the picker. An integration test is the only one that pins the dialect
#: the picker actually runs.
#:
#: The two synthetic Câmara cases are the exception, and they exist so the fix of #163 needs no new
#: collection title in versioned code: one petition that must stay in the stratum, one plan that only
#: names the Câmara as its client and must fall through to ``Planta Arquitetônica``.
#:
#: The order is load-bearing too, which is why the table includes collisions: the photographic prefix
#: beats "vistoria" (Relatório Técnico), "Decreto / Lei / Portaria" beats the ``^Projeto`` of a bill,
#: and "Relatório Técnico" beats the "inventário" that would send the same title to NENHUMA.
STRATUM_CASES: tuple[tuple[str, str], ...] = (
    (
        "Registros Fotográficos - Vistoria na área do futuro Parque de Eventos Quielse Crisóstomo da Silva, "
        "Campina Grande do Sul",
        "Fotografia",
    ),
    ("Registros Fotográficos - 1° Encontro Nacional de Municípios e Meio Ambiente", "Fotografia"),
    ("Croqui de um terreno para Benedito Sabino de Souza", "Mapa / Croqui Urbanístico"),
    ("Projeto da fachada de uma casa para Valentim Demetrio do ano de 1900", "Planta Arquitetônica"),
    ("Processo 10194 de 1915 - Fábrica de Erva Mate de David Carneiro", "Processo Administrativo"),
    (
        "Projeto de Lei 110 de 1969 - Autoriza doação de imóvel à Federação Parananense de Futebol",
        "Decreto / Lei / Portaria",
    ),
    (
        "Depósito de inflamáveis - Relatório e Inventario do Patrimônio Municipal de 1930",
        "Relatório Técnico",
    ),
    (
        "Requerimentos Câmara Municipal de Curitiba janeiro a julho de 1887",
        "Requerimento à Câmara Municipal",
    ),
    ("Requerimento de um particular à Câmara Municipal", "Requerimento à Câmara Municipal"),
    ("Projeto de planta para a Câmara Municipal", "Planta Arquitetônica"),
    (
        "Registro de Sepultamentos Cemitério Municipal São Francisco de Paula de 04 dez 1912 a 22 out 1919",
        "Livro de Sepultamento",
    ),
    ("LIVRO AZUL CIDADE DE CURITYBA", "Publicação Impressa"),
    ("Boletim PMC janeiro e fevereiro 1943", "Publicação Impressa"),
    ("Inventário e Avaliações do Matadouro Modelo Atuba", "NENHUMA"),
)


def test_the_strata_match_the_real_titles_they_were_written_for(
    use_test_db,
    db_session,
    generate_archive_doc,
):
    """
    Every stratum keeps the titles it owns, in the dialect the picker evaluates them in.

    ``LIVRO AZUL CIDADE DE CURITYBA`` is the regression this pins: the pattern said ``livro\\b``,
    PostgreSQL has no ``\\b``, and the printed book fell through every stratum — so a bench that
    claimed to propose "Publicação Impressa" never saw the collection's only book (#134).
    """
    expected: dict[str, str] = {}
    for index, (title, stratum) in enumerate(STRATUM_CASES):
        description_id = f"stratum_{index}"
        generate_archive_doc(description_id=description_id, original_title=title)
        expected[description_id] = stratum

    rows = {row.description_id: row for row in read_collection(db_session) if row.description_id in expected}

    assert {description_id: row.stratum for description_id, row in rows.items()} == expected


def test_a_title_that_names_the_subject_is_not_swept_into_a_form(
    use_test_db,
    db_session,
    generate_archive_doc,
):
    """
    The residue #134 measured is not control material, and it is not a photograph either.

    A title can name the subject ("Contestação de Rescisão de contrato Matadouro Modelo Atuba") and
    never name the medium. The curator files it as a processo, but the title does not say so; a rule
    broad enough to propose it as ``Fotografia`` would swallow a genuinely different form. Pinned as
    no stratum, so widening the photographic pattern is a deliberate act and not a silent one.
    """
    generate_archive_doc(
        description_id="subject_title",
        original_title="Contestação de Rescisão de contrato Matadouro Modelo Atuba",
    )

    rows = [row for row in read_collection(db_session) if row.description_id == "subject_title"]

    assert rows[0].stratum is None
