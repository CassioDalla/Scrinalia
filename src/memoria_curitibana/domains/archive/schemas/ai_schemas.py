from typing import Literal

from pydantic import BaseModel


class EntityTagDecisionSchema(BaseModel):
    winner: Literal["TAG", "ENTITY"]
    confidence: float
    reason: str


class TitleQualityDecision(BaseModel):
    """
    Opinion of a language model about one title.

    Deliberately tiny: the structural validator does the deterministic work and this is the
    opt-in extra. ``is_suspect`` is the flag, ``confidence`` lets the caller ignore a weak
    opinion and ``reason`` is what the archivist reads in ``anomaly_reasons``.
    """

    is_suspect: bool
    confidence: float
    reason: str
