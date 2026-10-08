"""HTTP contract of the curator's work list."""

from litestar.testing import TestClient

from scrinalia.domains.archive.schemas.curation_schema import CurationInbox, CurationQueue
from scrinalia.domains.archive.services.curation_service import QUEUE_CATALOGUE, CurationService


def _inbox(*, count: int = 0) -> CurationInbox:
    from datetime import UTC, datetime

    return CurationInbox(
        queues=[
            CurationQueue(key=key, label=label, count=count, route=route, description="d")
            for key, label, route, _description in QUEUE_CATALOGUE
        ],
        generated_at=datetime.now(UTC),
    )


def test_inbox_lists_every_queue_with_its_route(client: TestClient, mocker) -> None:
    """One request answers "what needs me today", and each card says where it is resolved."""
    mock_inbox = mocker.patch.object(CurationService, "inbox")
    mock_inbox.return_value = _inbox(count=0)

    response = client.get("/api/v1/curation/inbox")

    assert response.status_code == 200
    body = response.json()
    assert {queue["key"] for queue in body["queues"]} == {key for key, *_ in QUEUE_CATALOGUE}
    assert all(queue["route"].startswith("/") for queue in body["queues"])


def test_an_empty_queue_is_returned_with_zero_not_omitted(client: TestClient, mocker) -> None:
    """
    Zero is information.

    The archivist has to know a queue exists and is empty; hiding it would make the contract
    indistinguishable from "this queue was never built".
    """
    mock_inbox = mocker.patch.object(CurationService, "inbox")
    mock_inbox.return_value = _inbox(count=0)

    body = client.get("/api/v1/curation/inbox").json()

    assert len(body["queues"]) == len(QUEUE_CATALOGUE)
    assert all(queue["count"] == 0 for queue in body["queues"])


def test_the_service_asks_for_every_key_the_catalogue_declares(mocker) -> None:
    """
    The catalogue and the repository must agree on the vocabulary.

    This is the failure the design invites: a queue is a line in ``QUEUE_CATALOGUE`` plus a count in
    ``count_pending``, and adding only one of the two would raise ``KeyError`` at request time
    instead of at review time.
    """
    repo = mocker.Mock()
    repo.count_pending.return_value = {key: 1 for key, *_ in QUEUE_CATALOGUE}

    inbox = CurationService(repo).inbox()

    assert [queue.count for queue in inbox.queues] == [1] * len(QUEUE_CATALOGUE)
