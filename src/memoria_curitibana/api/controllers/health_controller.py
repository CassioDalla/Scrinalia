"""Liveness and readiness for the orchestrator (load balancer, Kubernetes).

Two different questions, kept apart:

* ``GET /health/live`` answers *is the process alive?* and touches nothing. An orchestrator restarts
  the container when this fails, so no dependency may be able to fail it — a database restart would
  otherwise restart the API for no reason.
* ``GET /health/ready`` answers *may this instance receive traffic?* and is where the database check
  belongs: failing it takes the instance out of rotation without killing a process that is fine.

Both live outside ``/api/v1`` and outside the OpenAPI document. This is infrastructure, not the
domain contract, and an orchestrator must not have to know the API version to ask — the same reason
Litestar's own ``/schema`` is not part of the emitted document. The human panel
(``GET /api/v1/system/health``) is untouched: it answers *which piece is down* and pays for the
network calls that make that answer useful.
"""

from litestar import Controller, Response, get
from litestar.status_codes import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE

from memoria_curitibana.api.health_probe import database_answers
from memoria_curitibana.api.schemas.health import LivenessResponse, ReadinessResponse

#: A probe answer is only true for the moment it was produced; nothing may cache it.
NO_STORE = {"Cache-Control": "no-store"}


class HealthController(Controller):
    path = "/health"
    tags = ["Health"]  # noqa: RUF012

    @get("/live", include_in_schema=False, sync_to_thread=False)
    def live(self) -> Response[LivenessResponse]:
        """The process is answering. No database, no model server, no storage — nothing to fail."""
        return Response(LivenessResponse(), status_code=HTTP_200_OK, headers=NO_STORE)

    @get("/ready", include_in_schema=False, sync_to_thread=True)
    def ready(self) -> Response[ReadinessResponse]:
        """
        200 while the database answers, 503 when it does not.

        The body carries the verdict and nothing else. The exception text goes to the log: this
        route is unauthenticated, and a failed connection stringifies host and port.
        """
        if database_answers():
            return Response(ReadinessResponse(status="ok"), status_code=HTTP_200_OK, headers=NO_STORE)

        return Response(
            ReadinessResponse(status="unavailable"),
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            headers=NO_STORE,
        )
