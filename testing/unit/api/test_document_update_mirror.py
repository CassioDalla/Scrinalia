"""The PATCH body and the review command are one field set, not two.

``DocumentUpdateRequest`` is the HTTP shape and ``DocumentReviewCommand`` is the domain command; the
controller forwards one into the other with ``**data.model_dump(exclude_unset=True)``. That makes a
field added to only one of them a defect neither the compiler nor the contract can see: in the body
it is a field the route quietly accepts and the command refuses (a 500), and in the command it is a
field no client can ever send. The set equality is the gate.

The pair drifted once already: the archive gained the ISAD(G) columns, the command declared them, and
the body did not — so the contract never offered them and the screen had nothing to send.
"""

from scrinalia.api.schemas.documents import DocumentUpdateRequest
from scrinalia.domains.archive.schemas.command_schema import DocumentReviewCommand

#: The two fields the route owns: the id comes from the path, the author from the session.
ROUTE_OWNED = frozenset({"description_id", "changed_by"})


def test_the_body_covers_the_whole_command() -> None:
    body = set(DocumentUpdateRequest.model_fields)
    command = set(DocumentReviewCommand.model_fields) - ROUTE_OWNED

    missing_from_body = sorted(command - body)
    missing_from_command = sorted(body - command)

    assert missing_from_body == [], f"o corpo não declara: {missing_from_body}"
    assert missing_from_command == [], f"a command não declara: {missing_from_command}"
