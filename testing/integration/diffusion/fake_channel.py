"""Test definitions of an export channel, before the first real adapter exists (#214).

The registry is code: the tests add these to ``CHANNELS`` with ``monkeypatch.setitem`` so the
service, the scheduler, the runner and the API exercise the real resolution path against a channel
that writes nothing.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from scrinalia.domains.diffusion.diffusion_registry import (
    DiffusionCapability,
    DiffusionChannelSummary,
    DiffusionConfigField,
)


class FakeExportConfig(BaseModel):
    """A configuration with one optional field, so the validation path is real."""

    model_config = ConfigDict(extra="forbid")

    destination: str | None = None


FAKE_EXPORT = DiffusionChannelSummary(
    code="fake_export",
    label="Canal de teste",
    description="Um canal EXPORT que os testes usam antes do primeiro adaptador real.",
    capability=DiffusionCapability.EXPORT,
    config_model=FakeExportConfig,
    config_fields=(DiffusionConfigField(name="destination", label="Destino", help="Onde o pacote é escrito."),),
    adapter="testing.integration.diffusion.fake_adapter",
)

#: The same definition without an adapter: the enqueue and the scheduler must skip it, not queue a
#: run that fails for a reason the operator cannot fix.
FAKE_WITHOUT_ADAPTER = DiffusionChannelSummary(
    code="fake_without_adapter",
    label="Canal sem adaptador",
    description="Um canal EXPORT que o pacote traz sem o módulo que o escreve.",
    capability=DiffusionCapability.EXPORT,
    config_model=FakeExportConfig,
    config_fields=(),
    adapter=None,
)
