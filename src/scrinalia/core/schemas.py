"""The request models' shared base."""

from pydantic import BaseModel, ConfigDict


class RequestModel(BaseModel):
    """
    Base of every model a route binds from a request body.

    ``extra="forbid"`` because a field the route does not know is a stale client or a typo, and
    pydantic's default would accept it and drop it without a trace: measured against the 53 request
    bodies this contract carries, 22 refused it and 31 ignored it, so the same mistake answered
    **400** on one route and **200** on the next (issue #177).

    It lives in ``core`` and not in ``api``: the identity and archive domains declare the commands
    the API binds as bodies, and a domain must not import from the HTTP layer.
    """

    model_config = ConfigDict(extra="forbid")
