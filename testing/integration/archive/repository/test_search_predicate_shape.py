"""Regression guard for the shape of a search, and for what it cost when it was wrong (#140).

A search returned the **right** documents in the **right** order while a selective term took 18
seconds. Every gate we had was green: the defect was not in the answer, it was in how the answer was
reached, and only a plan could see it. The term reached the facets as an ``OR`` of correlated
``EXISTS``, so it was evaluated once per row of whatever it was joined to — 64,504 entity links to
find 12 descriptions — and the ``OR`` was enough to keep the planner away from the generated
``search_vector`` GIN index.

A behavioural test cannot catch a regression here: an ``OR`` of ``EXISTS`` and a pre-filtered set of
ids return the same rows. So this pins the **shape** of the emitted SQL, the way
``test_trigram_joins.py`` pins the absence of a redundant disjunct: the term has to arrive at the page,
the count and every facet as a predicate on ``archive_documents.description_id``.

Measured on the live collection, before and after (18 query/mode/filter cases, results identical):

| case | before | after |
| --- | ---: | ---: |
| lexical ``enchente`` (12 matches) | 17.5 s | 0.21 s |
| lexical ``curitiba`` (3,286) | 6.4 s | 0.41 s |
| hybrid ``enchente`` | 18.0 s | 0.31 s |
"""

from __future__ import annotations

from sqlalchemy import event

from scrinalia.domains.archive.repository import DocumentRepository
from scrinalia.domains.archive.schemas.query_schema import DocumentSearchQuery


def _search_statements(db_session, call) -> list[str]:
    """Runs ``call`` and returns every statement SQLAlchemy sent, whitespace collapsed."""
    statements: list[str] = []
    bind = db_session.get_bind()

    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(" ".join(statement.split()))

    event.listen(bind, "before_cursor_execute", record)
    try:
        call()
    finally:
        event.remove(bind, "before_cursor_execute", record)

    return statements


def _facet_statements(statements: list[str]) -> list[str]:
    """The statements that group a link table's rows into the sidebar's counts."""
    return [
        statement
        for statement in statements
        if "GROUP BY" in statement
        and ("archive_document_entities" in statement or "archive_document_tags" in statement)
    ]


def test_a_search_filters_the_documents_before_it_joins_the_link_tables(use_test_db, db_session, generate_archive_doc):
    """
    The structural guard, and the only test here that would have caught the 18-second search.

    ``archive_documents.description_id IN (SELECT ...)`` is the fix's signature: it says the term
    narrowed the documents **before** the link table was joined. Reverting to an ``OR`` of correlated
    ``EXISTS`` removes it, returns exactly the same page, and costs a factor of 80 on a selective
    term — which is why the assertion is about the SQL and not about the result.
    """
    generate_archive_doc(description_id="shape1", original_title="Enchente em região marginalizada")
    db_session.flush()

    statements = _search_statements(
        db_session, lambda: DocumentRepository(db_session).search(DocumentSearchQuery(term="enchente", limit=25))
    )

    facets = _facet_statements(statements)
    assert facets, "as consultas de faceta não foram emitidas"
    for statement in facets:
        assert "archive_documents.description_id IN (" in statement, (
            "Uma faceta não recebeu o conjunto de documentos: o termo deixou de chegar como "
            f"predicado sobre ``description_id``. Ver #140. A consulta emitida foi: {statement[:400]}"
        )
        assert "EXISTS (SELECT 1" not in statement, (
            "Uma faceta voltou a filtrar o termo depois de juntar a tabela de ligação — o EXISTS "
            "correlacionado com archive_documents é a assinatura disso. Assim o predicado é "
            "reavaliado uma vez por linha de ligação (64.504 na faceta de entidade, para achar 12 "
            "descrições) e o OR ainda impede o GIN index do search_vector. Medido: 17,5 s contra "
            "0,21 s na mesma busca, com resultado idêntico. Nenhum filtro de faceta está ativo neste "
            f"teste, então nada legítimo precisa de um EXISTS aqui. Ver #140. A consulta foi: {statement[:400]}"
        )


def test_the_fused_search_filters_the_documents_before_it_joins_the_link_tables(
    use_test_db, db_session, generate_archive_doc
):
    """
    The fused clause is a set of documents too: the full-text matches unioned with the semantic
    window, and not an ``OR`` of the two. The ``OR`` cost every one of the seven statements a probe
    of all 4,831 documents with a 100-element array comparison (2.1 s against 0.31 s).
    """
    generate_archive_doc(description_id="fused1", original_title="Enchente", embedding=[1.0] + [0.0] * 383)
    db_session.flush()

    statements = _search_statements(
        db_session,
        lambda: DocumentRepository(db_session).search(
            DocumentSearchQuery(term="enchente", mode="hybrid", limit=25),
            query_embedding=[1.0] + [0.0] * 383,
        ),
    )

    facets = _facet_statements(statements)
    assert facets, "as consultas de faceta não foram emitidas"
    for statement in facets:
        assert "archive_documents.description_id IN (" in statement, (
            "A faceta do modo híbrido não recebeu o conjunto de candidatos. Ver #140. A consulta "
            f"emitida foi: {statement[:400]}"
        )
        assert "OR (archive_documents.description_id IN (" not in statement, (
            "A faceta do modo híbrido voltou a somar dois conjuntos no WHERE em vez de uni-los. O OR "
            "não vira semi-join: o plano percorre todos os documentos comparando com o array da "
            "janela semântica. Medido: 2,1 s contra 0,31 s, com resultado idêntico. Ver #140. A "
            f"consulta emitida foi: {statement[:400]}"
        )
        assert "SELECT unnest(" in statement, (
            "A janela semântica deixou de ser um membro do conjunto de candidatos e voltou a entrar "
            "como uma comparação por documento — o ``= ANY(array)`` que o OR produzia. Se a forma "
            "mudou de propósito, re-meça antes de apagar esta linha: a diferença era 2,1 s contra "
            "0,31 s com o mesmo resultado, e só o plano mudava. Ver #140. A consulta emitida foi: "
            f"{statement[:400]}"
        )
