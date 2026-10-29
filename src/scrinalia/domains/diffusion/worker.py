"""The diffusion export worker: the run the ledger claims, and the channel's adapter writes.

It is a worker of the same ledger as the AI pipeline (ADR 0023 §7), with the **channel** as its
axis: the run carries a ``channel_code`` instead of a ``origin_code``, and the queue is one slot per
channel. The module is deliberately thin — it resolves the channel row, refuses the states that
cannot run, and hands the row to the adapter. The adapter owns the destination and the covered set;
this worker owns the ledger's rules.

Three refusals live here and not only in the API, because a row can be queued before a deploy
changes the code under it:

* an unknown channel (its definition left the registry);
* a ``LIVE`` channel, which is read on every request and has no run;
* a paused channel, whose row and agenda stay but whose export does not.

A channel without an adapter is refused by ``resolve_adapter`` with a sentence that names it, so a
run queued before the adapter existed fails as a business refusal and not as a 500.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from scrinalia.core.i18n import t
from scrinalia.domains.archive.workers.cancellation import RunControl
from scrinalia.domains.diffusion.diffusion_registry import (
    DiffusionCapability,
    get_channel_summary,
    resolve_adapter,
)
from scrinalia.domains.diffusion.exceptions import DiffusionChannelNotFoundError, InvalidDiffusionConfigError
from scrinalia.domains.diffusion.repository import DiffusionChannelRepository


def execute(channel_code: str, db_session: Session, run_control: RunControl | None = None) -> None:
    """
    One export run of one channel.

    ``run_control`` is the ledger's cancellation; the adapter repeats its check between the batches
    it writes. The session is the run's: the adapter reads the covered set and writes the destination
    through it, and a failure raises — the ledger records the cause and the fingerprint groups it.
    """
    summary = get_channel_summary(channel_code)
    channel = DiffusionChannelRepository(db_session).get(channel_code)
    if channel is None:
        raise DiffusionChannelNotFoundError(t("O canal '{code}' não está configurado.", code=channel_code))
    if summary.capability is not DiffusionCapability.EXPORT:
        raise InvalidDiffusionConfigError(
            t("O canal '{code}' é lido a cada requisição e não tem execução.", code=channel_code)
        )
    if not channel.enabled:
        raise InvalidDiffusionConfigError(
            t("O canal '{code}' está pausado; ative-o antes de executar.", code=channel_code)
        )

    adapter = resolve_adapter(summary)
    adapter(channel, db_session=db_session, run_control=run_control)
