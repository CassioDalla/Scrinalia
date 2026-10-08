"""add the typology catalogue state

Gives `archive_typologies` the `is_active` column and seeds the typologies the collection
already carries.

The column is what makes "deactivate instead of delete" a real choice: the FK from
`archive_documents.typology_id` is `SET NULL`, so deleting a row would unclassify every
description pointing at it while destroying the record that the type ever existed. It is also
what removes a type from the zero-shot classifier's candidate labels — the ones the archivist
retired — without touching a single classified description.

The seed is deliberately `ON CONFLICT (name) DO NOTHING`: a database that already has curated
rows (the dev volume did, inserted out of band, with no migration to reproduce them) keeps
them and their ids, so no `archive_documents.typology_id` is rewritten. A fresh volume would
otherwise be born with an empty catalogue and a classifier with nothing to say.

Revision ID: d1bc15fb6beb
Revises: 9c7d5d501f95
Create Date: 2026-10-06 19:12:11.607721

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1bc15fb6beb"
down_revision: str | None = "9c7d5d501f95"
branch_labels: str | None = None
depends_on: str | None = None

#: name -> what the classifier is documented with. The context is *documentation*: it is never
#: appended to the zero-shot label, because the entailment collapses as the label grows.
SEED: tuple[tuple[str, str], ...] = (
    (
        "Planta Arquitetônica",
        "Projetos de construção, aumento de área, projeto de muro, projeto de aumento, reformas, "
        "fachadas, alvarás de obras",
    ),
    ("Mapa / Croqui Urbanístico", "Loteamentos, zoneamento, arruamento, cartografia, traçados de ruas e bairros"),
    (
        "Fotografia",
        "Registros fotográficos, negativos, ampliações, imagens de ruas, imagens de eventos, imagens de obras",
    ),
    ("Decreto / Lei / Portaria", "Atos normativos, legislação municipal, diário oficial, regulamentações"),
    (
        "Ofício / Memorando",
        "Comunicação oficial interna ou externa entre secretarias, correspondências institucionais",
    ),
    ("Audiovisual", "Fitas magnéticas, VHS, gravações de áudio, entrevistas, vídeos institucionais"),
    ("Ata de Reunião", "Registros de encontros, deliberações de conselhos, comitês ou assembleias"),
    ("Relatório Técnico", "Estudos de impacto, vistorias, laudos técnicos, balanços de gestão, diagnósticos"),
    ("Processo Administrativo", "Autos de infração, desapropriações, licitações, contratos públicos consolidados"),
    ("Dossiê Funcional", "Fichas de funcionários, histórico de servidores públicos, prontuários"),
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("archive_typologies", sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False))

    # Seeded with `ON CONFLICT DO NOTHING` so a curated catalogue is never rewritten: the
    # classifier's labels are a curation decision, and a name the archivist renamed must not be
    # resurrected by a redeploy.
    for name, context in SEED:
        op.execute(
            sa.text(
                """
                INSERT INTO archive_typologies (name, context_description, is_active)
                VALUES (:name, :context, true)
                ON CONFLICT (name) DO NOTHING
                """
            ).bindparams(name=name, context=context)
        )


def downgrade() -> None:
    """Downgrade schema."""
    # The seeded rows are left behind: this migration cannot tell one it inserted from one the
    # archivist created afterwards, and deleting a catalogue row cascades nothing but does orphan
    # descriptions. The column goes, and with it the distinction.
    op.drop_column("archive_typologies", "is_active")
