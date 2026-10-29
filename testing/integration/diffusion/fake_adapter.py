"""A fake export adapter: records the call and writes nothing.

The infrastructure of #212 is testable before the first real adapter (#214): the registry names a
module, the worker resolves its ``execute``, and this module is what the test definitions point at.
It is deliberately a module with one function — the shape ``DiffusionAdapter`` describes — so the
resolution path is exercised and not mocked away.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from scrinalia.domains.diffusion.models import DiffusionChannel

#: Every call this adapter received, in order. The tests clear it before they run.
CALLS: list[dict[str, Any]] = []


def execute(channel: DiffusionChannel, *, db_session: Session, run_control: Any | None = None) -> None:
    """Records the channel the worker resolved; a real adapter would write the destination."""
    CALLS.append({"code": channel.code, "enabled": channel.enabled, "run_control": run_control})
