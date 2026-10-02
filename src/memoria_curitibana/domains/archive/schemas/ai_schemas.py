from typing import Literal

from pydantic import BaseModel


class EntityTagDecisionSchema(BaseModel):
    winner: Literal["TAG", "ENTITY"]
    confidence: float
    reason: str
