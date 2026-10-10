"""Declarative catalogue of the AI workers, shared by the runner and the operations panel.

This module is the single definition of *what a worker is*: the order it runs in, the axis whose
registry configures it, the ledger key its idempotency stamp uses, and which function counts its
queue. The runner already owned ``WORKERS``/``PIPELINE_ORDER``; the operational panel needs the
same facts plus labels and queue predicates, and duplicating them is how a panel starts lying.

**It imports no worker.** Importing the nine worker modules at API start-up would pull spaCy,
pandas and scikit-learn into a process that never runs a worker — measured at ~1.7 s for spaCy
alone. Every function here resolves its target through ``import_module`` and caches the result, so
the cost is paid once, on the first panel request, and only for the axes actually asked about.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from importlib import import_module
from inspect import Signature, signature
from typing import Any, Literal

from sqlalchemy.orm import Session

from scrinalia.domains.archive.schemas.system_schema import EngineSource, WorkerUnit
from scrinalia.domains.archive.worker_stamp import (
    EMBEDDING,
    MACRO_CATEGORY,
    NER,
    QUALITY_VALIDATOR,
    TYPOLOGY,
    WorkerStamp,
)


@dataclass(frozen=True)
class WorkerSpec:
    """Everything the panel and the runner need to know about one worker."""

    name: str
    label: str
    description: str
    module: str
    axis: str | None = None
    unit: WorkerUnit = "document"
    governed: bool = True
    engine_source: EngineSource = "none"
    #: Stamp whose presence in ``execution_log`` means "this unit was processed". The generic
    #: processed/failed counters read it; a worker whose ledger is not a stamp leaves it ``None``
    #: and names explicit counter functions instead.
    stamp: WorkerStamp | None = None
    stamp_model: Literal["document", "tag"] | None = None
    #: Name of the queue-counter function in the worker module. ``None`` means the queue cannot be
    #: measured cheaply and ``unmeasurable_reason`` explains why.
    counter: str | None = "count_pending"
    processed_counter: str | None = None
    failed_counter: str | None = None
    unmeasurable_reason: str | None = None
    note: str | None = None


#: Registry module of each engine axis. The panel reads ``AVAILABLE_ENGINES``/``PRESETS`` from here
#: and calls ``describe_config``; importing the axis is what pulls the heavy stack, so it is lazy.
ENGINE_AXES: dict[str, str] = {
    "NER": "scrinalia.domains.archive.engines.NER.registry",
    "classification": "scrinalia.domains.archive.engines.classification.registry",
    "embeddings": "scrinalia.domains.archive.engines.embeddings.registry",
    "LLMs": "scrinalia.domains.archive.engines.LLMs.registry",
    "title_quality": "scrinalia.domains.archive.engines.title_quality.registry",
}

_WORKERS_PACKAGE = "scrinalia.domains.archive.workers"

#: The catalogue, in pipeline order. Insertion order is the order the screen shows, and it is the
#: order in which the stages unblock each other — the same reason ``PIPELINE_ORDER`` exists.
WORKER_CATALOGUE: dict[str, WorkerSpec] = {
    spec.name: spec
    for spec in (
        WorkerSpec(
            name="transfer",
            label="Transferência staging → archive",
            description=(
                "Copia o staging estruturado para o archive pelo hash CDC. É a única etapa que "
                "reescreve o conteúdo: quando o hash muda, ela zera os carimbos de IA e os "
                "enriquecimentos precisam rodar de novo."
            ),
            module=f"{_WORKERS_PACKAGE}.worker_archive_transfer",
            unit="staging",
            governed=False,
            note="Sem carimbo de IA: a unidade é o registro de staging, não a descrição.",
        ),
        WorkerSpec(
            name="cleaning",
            label="Limpeza por regras (REWRITE)",
            description=(
                "Aplica as regras de limpeza ativas que reescrevem texto. Uma regra VALIDATE nunca "
                "substitui nada: quem sinaliza é o validador de qualidade."
            ),
            module=f"{_WORKERS_PACKAGE}.worker_cleaning_regex",
            unit="document",
            note="Um documento pode estar pendente para mais de uma regra.",
        ),
        WorkerSpec(
            name="ner",
            label="Extração de entidades (NER)",
            description="Extrai nomes próprios, lugares e instituições do texto composto das descrições.",
            module=f"{_WORKERS_PACKAGE}.worker_ner",
            axis="NER",
            engine_source="signature",
            stamp=NER,
            stamp_model="document",
        ),
        WorkerSpec(
            name="typology",
            label="Classificação de tipologia",
            description="Classifica cada descrição contra o catálogo de tipologias por zero-shot.",
            module=f"{_WORKERS_PACKAGE}.worker_typology",
            axis="classification",
            engine_source="signature",
            stamp=TYPOLOGY,
            stamp_model="document",
        ),
        WorkerSpec(
            name="thumbnail",
            label="Miniaturas (S3)",
            description="Baixa a imagem original e guarda uma miniatura no storage de objetos.",
            module=f"{_WORKERS_PACKAGE}.worker_thumbnail",
            stamp=None,
            processed_counter="count_processed",
            failed_counter="count_failed",
            note="Pendente = tem imagem de origem e ainda não tem URI no storage.",
        ),
        WorkerSpec(
            name="conflict-judge",
            label="Juiz de conflito assunto x entidade",
            description=(
                "Compara o vocabulário de tags com o de entidades e consulta o LLM local para "
                "decidir se o termo ambíguo é assunto ou nome próprio."
            ),
            module=f"{_WORKERS_PACKAGE}.worker_resolve_tag_entity_conflict",
            axis="LLMs",
            unit="pair",
            governed=False,
            engine_source="signature",
            counter=None,
            processed_counter="count_judged",
            unmeasurable_reason=(
                "A fila é o produto cartesiano tags x entidades com trigram: a contagem ao vivo "
                "mediu 53 s no acervo real. O que o painel mostra é o que já foi julgado."
            ),
        ),
        WorkerSpec(
            name="macro-category",
            label="Categorização de assunto (tags)",
            description=(
                "Arquiva cada tag numa categoria de assunto. A unidade é a tag, não a descrição: o "
                "carimbo vive no log da tag e é o hash do conjunto de rótulos."
            ),
            module=f"{_WORKERS_PACKAGE}.worker_macro_category",
            axis="classification",
            unit="tag",
            governed=False,
            engine_source="signature",
            stamp=MACRO_CATEGORY,
            stamp_model="tag",
            note="Uma tag com categoria definida pelo curador está fora do alcance deste worker.",
        ),
        WorkerSpec(
            name="quality-validator",
            label="Validação de qualidade e anomalias",
            description=(
                "Valida estrutura, títulos repetidos e regras VALIDATE. O LLM de título só é "
                "construído quando existe uma regra LLM_CHECK ativa."
            ),
            module=f"{_WORKERS_PACKAGE}.worker_quality_validator",
            axis="title_quality",
            engine_source="llm_check_rule",
            stamp=QUALITY_VALIDATOR,
            stamp_model="document",
            note="A engine e o preset deste worker vivem na regra LLM_CHECK ativa (tela de regras).",
        ),
        WorkerSpec(
            name="embedding",
            label="Embeddings (busca semântica)",
            description=(
                "Gera o vetor de cada descrição para a busca semântica. O carimbo é o MD5 do texto "
                "efetivo, então mudar o texto — inclusive por edição humana — requeue o documento."
            ),
            module=f"{_WORKERS_PACKAGE}.worker_embedding",
            axis="embeddings",
            governed=False,
            engine_source="signature",
            stamp=EMBEDDING,
            stamp_model="document",
            note="Exceção documentada: não usa o guard de governança, só pula descrições REJECTED.",
        ),
    )
}


@cache
def worker_module(module_path: str) -> Any:
    """Imports a worker module once per process."""
    return import_module(module_path)


def worker_function(spec: WorkerSpec) -> Any:
    """The ``execute`` callable of the worker."""
    return worker_module(spec.module).execute


@cache
def _signature_of(module_path: str) -> Signature:
    return signature(worker_module(module_path).execute)


def worker_signature(spec: WorkerSpec) -> Signature:
    """Signature of ``execute``, used to validate overrides against what the worker accepts."""
    return _signature_of(spec.module)


@cache
def axis_registry(axis: str) -> Any:
    """Registry module of an engine axis; this is the import that pulls spaCy/transformers."""
    return import_module(ENGINE_AXES[axis])


def count_pending(spec: WorkerSpec, db: Session, **options: Any) -> int:
    """Pending units of the worker's queue, through the worker's own predicate."""
    if spec.counter is None:
        raise ValueError(f"Worker '{spec.name}' has no measurable queue.")
    counter = getattr(worker_module(spec.module), spec.counter)
    return int(counter(db, **options))


def count_processed(spec: WorkerSpec, db: Session, **options: Any) -> int:
    """Units the worker already stamped, or the worker's explicit processed counter."""
    if spec.processed_counter is not None:
        counter = getattr(worker_module(spec.module), spec.processed_counter)
        return int(counter(db, **options))
    if spec.stamp is None:
        raise ValueError(f"Worker '{spec.name}' has no processed counter.")
    from scrinalia.domains.archive.repository.worker_stamp_repo import WorkerStampRepository

    return WorkerStampRepository(db).count_stamped(spec)


def count_failed(spec: WorkerSpec, db: Session, **options: Any) -> int:
    """Units whose stamp records a failure, or the worker's explicit failed counter."""
    if spec.failed_counter is not None:
        counter = getattr(worker_module(spec.module), spec.failed_counter)
        return int(counter(db, **options))
    if spec.stamp is None:
        raise ValueError(f"Worker '{spec.name}' has no failed counter.")
    from scrinalia.domains.archive.repository.worker_stamp_repo import WorkerStampRepository

    return WorkerStampRepository(db).count_stamp_failures(spec)
