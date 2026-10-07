"""add the collection vocabulary catalogues and seed the reference collection

Revision ID: b3d6f1a2c4e7
Revises: fe7fcab37207
Create Date: 2026-10-07 17:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3d6f1a2c4e7"
down_revision: str | Sequence[str] | None = "fe7fcab37207"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The arrangement vocabulary of the reference collection. Duplicated from
#: ``domain.collection_vocabulary.ARRANGEMENT_TERMS`` on purpose: a migration must keep describing
#: the state it produced even if the application constant is edited later, otherwise replaying
#: history stops reproducing it. A test pins the two together.
ARRANGEMENT_TERMS: tuple[tuple[str, str], ...] = (
    ("BR PRADAP", "Acervo da entidade custodiadora"),
    ("IPPUC", "IPPUC - Instituto de Pesquisa e Planejamento Urbano de Curitiba"),
    ("SMU", "SMU - Secretaria Municipal de Urbanismo"),
    ("SMMA", "SMMA - Secretaria Municipal do Meio Ambiente"),
    ("SEPLAD", "SEPLAD - Secretaria Municipal do Planejamento"),
    ("CMC", "CMC - Câmara Municipal de Curitiba"),
    ("FAS", "FAS - Fundação de Ação Social"),
    ("SGM", "SGM - Secretaria Municipal de Governo"),
    ("SMCS", "SMCS - Secretaria Municipal da Comunicação Social"),
    ("SMDS", "SMDS - Secretaria Municipal da Defesa Social"),
    ("FOTOGRAFIA", "Registros Fotográficos"),
    ("FOTOGRAFIAS", "Registros Fotográficos"),
    ("ED", "Edificações"),
    ("AL", "Alvenaria"),
    ("CONSTR", "Construções"),
    ("CVCO", "Certificados de Vistoria e Conclusão de Obras"),
    ("OUVIDORIA", "Ouvidoria Municipal de Curitiba"),
    ("LEGISLAÇÃO", "Referência Legislativa"),
    ("MICROFILME", "Microfilme"),
    ("PROC", "Processos"),
    ("MATADOURO", "Matadouro Municipal"),
    ("DIAPOSITIVO", "Diapositivos"),
    ("JORN", "Jornais"),
    ("REQUERIMENTOS", "Requerimentos"),
    ("REQ", "Requerimentos"),
    ("OF", "Ofícios"),
    ("HIST", "Histórico"),
    ("PP", "Pareceres e Projetos"),
    ("DUP", "Duplicatas"),
    ("GAZ", "Gazeta"),
    ("MERC", "Mercado"),
    ("ATUBA", "Atuba"),
    ("INVENT", "Inventário"),
    ("MODELO", "Modelo"),
    ("BOMBAS", "Bombas"),
    ("INFLAMAVEIS", "Inflamáveis"),
    ("DEPOSITO", "Depósito"),
    ("PEQ", "Pequenos"),
)

#: The non-subject terms of the reference collection, as ``(term, kind)``. Also duplicated from
#: ``domain.collection_vocabulary.COLLECTION_TERMS`` and pinned by the same test.
COLLECTION_TERMS: tuple[tuple[str, str], ...] = (
    ("curitiba antiga", "DISTRICT"),
    ("centro", "DISTRICT"),
    ("centro cívico", "DISTRICT"),
    ("centro histórico", "DISTRICT"),
    ("batel", "DISTRICT"),
    ("boqueirão", "DISTRICT"),
    ("alto boqueirão", "DISTRICT"),
    ("campinas", "DISTRICT"),
    ("cajuru", "DISTRICT"),
    ("uberaba", "DISTRICT"),
    ("pinheirinho", "DISTRICT"),
    ("portão", "DISTRICT"),
    ("pilarzinho", "DISTRICT"),
    ("mossunguê", "DISTRICT"),
    ("bigorrilho", "DISTRICT"),
    ("bacacheri", "DISTRICT"),
    ("rebouças", "DISTRICT"),
    ("guabirotuba", "DISTRICT"),
    ("tatuquara", "DISTRICT"),
    ("barreirinha", "DISTRICT"),
    ("juvevê", "DISTRICT"),
    ("capão", "DISTRICT"),
    ("capão da imbuia", "DISTRICT"),
    ("capão raso", "DISTRICT"),
    ("santa felicidade", "DISTRICT"),
    ("alto da glória", "DISTRICT"),
    ("alto da xv", "DISTRICT"),
    ("são francisco", "DISTRICT"),
    ("sítio cercado", "DISTRICT"),
    ("cristo rei", "DISTRICT"),
    ("campo comprido", "DISTRICT"),
    ("prado velho", "DISTRICT"),
    ("vila", "DISTRICT"),
    ("curitiba", "MUNICIPALITY"),
    ("são paulo", "MUNICIPALITY"),
    ("joinville", "MUNICIPALITY"),
    ("paris", "MUNICIPALITY"),
    ("zurique", "MUNICIPALITY"),
    ("zurich", "MUNICIPALITY"),
    ("washington", "MUNICIPALITY"),
    ("campina grande do sul", "MUNICIPALITY"),
    ("araucária", "MUNICIPALITY"),
    ("pinhais", "MUNICIPALITY"),
    ("mandirituba", "MUNICIPALITY"),
    ("balsa nova", "MUNICIPALITY"),
    ("paraná", "STATE"),
    ("santa catarina", "STATE"),
    ("bahia", "STATE"),
    ("região metropolitana de curitiba", "REGION"),
    ("rmc", "REGION"),
    ("australia", "COUNTRY"),
    ("austrália", "COUNTRY"),
    ("suíça", "COUNTRY"),
    ("frança", "COUNTRY"),
    ("alemanha", "COUNTRY"),
    ("jaime lerner", "PERSON"),
    ("oscar niemeyer", "PERSON"),
    ("lúcio costa", "PERSON"),
    ("mário de miranda", "PERSON"),
    ("joel rocha", "PERSON"),
    ("poty lazzarotto", "PERSON"),
    ("tadeusz kościuszko", "PERSON"),
    ("ernesto guaita", "PERSON"),
    ("lina faria", "PERSON"),
    ("michelangelo cuniberti", "PERSON"),
    ("marilia kranz", "PERSON"),
    ("paulo spzak", "PERSON"),
    ("eduardo fernando chaves", "PERSON"),
    ("aristeu dias", "PERSON"),
    ("joão zaco paraná", "PERSON"),
    ("abrão assad", "PERSON"),
)


def upgrade() -> None:
    """
    Creates the two vocabulary catalogues and seeds the reference collection.

    Both seeds are idempotent with ``DO NOTHING`` rather than ``DO UPDATE``: the seed is a starting
    point the archivist owns, and an installation that already edited a row must keep it. This is
    the opposite choice from the level ladder and the subject drawers, where the seed *is* the
    definition and the migration converges the rows toward it.

    The catalogue replaces two constants that were read at runtime: the arrangement token map the
    hierarchy proposal suggested names from, and the regex of Curitiba bairros and person names the
    subject guard refused. Reading them from rows is what lets another institution replace them
    without editing the software.
    """
    op.create_table(
        "archive_arrangement_vocabulary",
        sa.Column("term_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("token", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("term_id"),
        sa.UniqueConstraint("token", name="uq_archive_arrangement_vocabulary_token"),
    )
    op.create_table(
        "archive_collection_terms",
        sa.Column("term_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("term", sa.String(length=200), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "DISTRICT",
                "MUNICIPALITY",
                "STATE",
                "REGION",
                "COUNTRY",
                "PERSON",
                name="collection_term_kind",
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("term_id"),
        sa.UniqueConstraint("term", "kind", name="uq_archive_collection_terms_term_kind"),
    )
    op.create_index("ix_archive_collection_terms_term", "archive_collection_terms", ["term"])

    connection = op.get_bind()

    insert_arrangement = sa.text(
        """
        INSERT INTO archive_arrangement_vocabulary (token, display_name, is_active)
        VALUES (:token, :display_name, true)
        ON CONFLICT (token) DO NOTHING
        """
    )
    for token, display_name in ARRANGEMENT_TERMS:
        connection.execute(insert_arrangement, {"token": token, "display_name": display_name})

    insert_term = sa.text(
        """
        INSERT INTO archive_collection_terms (term, kind, is_active)
        VALUES (:term, :kind, true)
        ON CONFLICT (term, kind) DO NOTHING
        """
    )
    for term, kind in COLLECTION_TERMS:
        connection.execute(insert_term, {"term": term, "kind": kind})


def downgrade() -> None:
    """
    Drops both catalogues.

    The seeded rows are not restored anywhere else, and they do not need to be: before this
    revision the vocabulary was a constant of the code, which the checkout still carries as the
    seed mirror. What the downgrade cannot give back is any row the archivist wrote — it states
    that instead of pretending otherwise.
    """
    op.drop_index("ix_archive_collection_terms_term", table_name="archive_collection_terms")
    op.drop_table("archive_collection_terms")
    op.drop_table("archive_arrangement_vocabulary")
    sa.Enum(name="collection_term_kind").drop(op.get_bind(), checkfirst=True)
