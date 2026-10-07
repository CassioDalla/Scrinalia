"""Contracts of the orchestrator's health endpoints.

They are not the panel's. ``SystemHealthResponse`` answers a person asking *which piece is down*;
these answer a load balancer asking *should this instance receive traffic*. Mixing the two would
either make the human screen lie (it deliberately degrades one probe at a time) or make the probe
expensive (the screen pays for Ollama and object storage on every read).
"""

from typing import Literal

from pydantic import BaseModel


class LivenessResponse(BaseModel):
    """The process is up and answering. Says nothing about its dependencies, on purpose."""

    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    """Whether this instance should receive traffic. The reason lives in the log, never here."""

    status: Literal["ok", "unavailable"]
