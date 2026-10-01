from typing import Literal

from pydantic import BaseModel, Field

# As colunas permitidas para o utilizador interagir no Frontend
AllowedColumns = Literal["original_title", "scope_content", "admin_bio_history", "provenance", "archivist_notes"]


class CreateCleaningRuleRequest(BaseModel):
    """Payload recebido do Frontend quando o utilizador clica em 'Salvar Regra'."""

    rule_name: str = Field(..., max_length=150, description="Nome identificador da regra.")
    target_column: AllowedColumns = Field(..., description="Coluna alvo da limpeza.")
    regex_pattern: str = Field(..., description="Padrão Regex compatível com Python.")
    replacement_string: str = Field(default="", description="Pelo que substituir. Deixe vazio para apagar.")


class DryRunRequest(BaseModel):
    """Payload recebido do Frontend para testar o 'Antes e Depois' (Simulação)."""

    target_column: AllowedColumns
    regex_pattern: str
    replacement_string: str = ""
