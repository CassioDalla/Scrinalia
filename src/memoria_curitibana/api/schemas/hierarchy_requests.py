"""HTTP payloads of the description hierarchy (Fase 2.5)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DescriptionLevelCreateRequest(BaseModel):
    """Registers a rung of the level ladder."""

    ordinal: int = Field(ge=0, description="Posição na escada.")
    code: str = Field(min_length=1, max_length=20, description="Chave de máquina estável, ex.: 'serie'.")
    name: str = Field(min_length=1, max_length=60, description="O que o arquivista lê.")
    description: str | None = Field(default=None, description="Documentação da gaveta para o curador.")
    aliases: list[str] = Field(default_factory=list, description="Grafias equivalentes aceitas no casamento.")
    requires_parent: bool = Field(default=False, description="Um nó deste nível não pode ser raiz.")
    allows_children: bool = Field(default=True, description="Um nó deste nível pode ter filhos.")

    model_config = ConfigDict(extra="forbid")


class DescriptionLevelUpdateRequest(BaseModel):
    """Partial update of a rung. ``ordinal`` is not editable: it would silently re-rank the tree."""

    name: str | None = Field(default=None, min_length=1, max_length=60)
    description: str | None = None
    aliases: list[str] | None = None
    requires_parent: bool | None = None
    allows_children: bool | None = None
    is_active: bool | None = None

    model_config = ConfigDict(extra="forbid")


class HierarchyNodeCreateRequest(BaseModel):
    """Creates an arrangement node that has no counterpart in the source."""

    reference_code: str = Field(min_length=1, description="Código do novo nó, ex.: 'BR PRADAP SMU'.")
    title: str = Field(min_length=1, description="Título do nó.")
    level_id: int | None = None
    parent_id: str | None = Field(default=None, description="Descrição superior; omita para criar na raiz.")
    scope_content: str | None = None
    changed_by: str | None = None
    note: str | None = None

    model_config = ConfigDict(extra="forbid")


class HierarchyNodeMoveRequest(BaseModel):
    """
    Moves and/or re-levels one description.

    ``new_parent_id`` is always stated, and ``null`` means "to the root": the endpoint says where
    the node goes. Omitted ``level_id`` keeps the current rung.
    """

    new_parent_id: str | None = Field(default=None, description="Nova unidade superior; null promove à raiz.")
    level_id: int | None = None
    changed_by: str | None = None
    note: str | None = None

    model_config = ConfigDict(extra="forbid")


class HierarchyProposalRequest(BaseModel):
    """Options of the proposal run. Read-only: there is nothing to approve here."""

    include_existing: bool = Field(default=True, description="Incluir códigos que já têm registro.")
    limit: int = Field(default=500, ge=1, le=5000, description="Teto de nós devolvidos.")

    model_config = ConfigDict(extra="forbid")


class HierarchyPlanDecisionRequest(BaseModel):
    """
    The archivist's verdict on one rung of the proposal.

    ``collapse_into_code`` is the operation the code cannot do for itself — ``AL`` and ``CONSTR``
    are one level of the arrangement, and no reading of the string says so. An empty string undoes
    a previous collapse; omitting the field leaves it as it is.
    """

    status: Literal["SUGGESTED", "APPROVED", "REJECTED"]
    level_id: int | None = None
    title: str | None = Field(default=None, max_length=300)
    reference_code: str | None = Field(default=None, max_length=500)
    collapse_into_code: str | None = Field(default=None, max_length=500)
    decided_by: str | None = None
    note: str | None = None

    model_config = ConfigDict(extra="forbid")


class HierarchyMaterialisationRequest(BaseModel):
    """Who authorised the run, and why. The decisions themselves live in the plan rows."""

    changed_by: str | None = None
    note: str | None = None
    limit: int = Field(default=500, ge=1, le=5000, description="Teto de itens no preview.")

    model_config = ConfigDict(extra="forbid")
