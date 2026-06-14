from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from domains.ingestion.models import RawData
from domains.staging.models import StagingDocument
from domains.staging.schemas import StagingDocumentDTO


def get_pending_raw_records(db: Session) -> list[dict[str, Any]]:
    """
    Identifica documentos brutos que aguardam transformação ou reprocessamento.

    Implementa o padrão Change Data Capture (CDC) por meio de Rastreamento de Hash.
    Faz um LEFT JOIN entre os dados brutos recém-adquiridos (RawData) e a tabela
    estruturada (StagingDocument).

    Retorna o payload apenas se:
      1. O documento for inédito (não existe na Staging).
      2. O hash do documento bruto atual for diferente do hash processado anteriormente
         (indicando que o documento sofreu atualizações no acervo da origem).

    Args:
        db (Session): Sessão ativa do SQLAlchemy.

    Returns:
        list[dict[str, Any]]: Lista de dicionários contendo os dados brutos prontos
        para o parser do Pydantic.
    """

    stmt = (
        select(RawData.description_id, RawData.payload, RawData.content_hash, RawData.raw_title)
        .outerjoin(StagingDocument, RawData.description_id == StagingDocument.description_id)
        .where((StagingDocument.description_id.is_(None)) | (StagingDocument.raw_content_hash != RawData.content_hash))
    )

    result = db.execute(stmt)
    return [dict(row._mapping) for row in result]


def upsert_staging_document(db: Session, record: StagingDocumentDTO) -> None:
    """
    Persiste um documento validado e estruturado na camada de Staging.

    Utiliza um comando 'UPSERT' nativo do PostgreSQL. Se o identificador do
    documento for inédito, realiza o INSERT. Se já existir (cenário de reprocessamento
    por alteração na origem), realiza o UPDATE substituindo os valores defasados
    pelos novos extraídos do modelo Pydantic.

    Args:
        db (Session): Sessão ativa do SQLAlchemy.
        record (StagingDocumentSchema): Objeto DTO validado com as regras ISAD(G).
    """

    # Converte o modelo validado para um dicionário, descartando chaves não preenchidas
    staging_dict = record.model_dump(exclude_unset=True)

    stmt = insert(StagingDocument).values(staging_dict)

    # Monta o dicionário de atualização usando stmt.excluded para garantir
    # que o PostgreSQL pegue exatamente os valores que ele tentou inserir.
    # Excluímos a chave primária 'description_id' pois ela não deve ser atualizada.
    update_dict = {col.name: col for col in stmt.excluded if col.name != "description_id"}

    stmt = stmt.on_conflict_do_update(index_elements=["description_id"], set_=update_dict)

    db.execute(stmt)
