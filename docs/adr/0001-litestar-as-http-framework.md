# ADR 0001: Litestar as the HTTP framework

- **Status:** Accepted
- **Date:** 2026-10-02 (decision originally taken on 2026-06-21, in `8a523fe`)

## Context

The project needed an HTTP API to expose the archive domain to the dashboard and to
future clients. `TODO.md` had planned FastAPI, and that line survived in the roadmap
long after the implementation went the other way, which made the choice look
accidental to anyone reading the repository.

The decision was taken when the taxonomy endpoint was built (`8a523fe`). The
requirements that shaped it were specific:

- A single, declarative place to map **domain exceptions to HTTP status codes**, so
  controllers stay free of translation logic.
- **Dependency injection tied to the request**, because every service must be built
  over the request's session and transaction.
- **Per-route control over thread offloading.** Nearly every route is synchronous and
  performs blocking database I/O, so blocking the event loop is the default failure
  mode; the taxonomy route additionally dispatches CPU-bound clustering work to a
  subprocess through `anyio.to_process`.

## Decision

Use **Litestar**. FastAPI was never a dependency of this project at any point; the API
layer was created directly on Litestar.

## Rationale

The requirements above are first-class features in Litestar rather than patterns the
application has to build:

- `exception_handlers` keyed by exception class is exactly the shape of
  `api/handlers.py`, and is what lets `domains/` raise `DomainException` subclasses
  without knowing HTTP.
- `Provide` composes per-request dependencies, which is what makes
  `provide_unit_of_work` in `api/dependencies.py` a real composition root instead of a
  convention every handler must remember.
- `sync_to_thread` is explicit per route, so the blocking I/O of the repositories is
  offloaded deliberately, and the async routes are visibly different from the sync
  ones.
- Pydantic v2 is consumed directly instead of being coupled to the framework, which
  matches the domain DTOs in `domains/*/schemas/`.

## Consequences

Positive: the API layer is thin, the domain stays framework-agnostic, and the
transaction has one owner shared with the workers.

Negative, and accepted:

- **Smaller ecosystem.** Far fewer tutorials, examples and Stack Overflow answers than
  FastAPI. This is not hypothetical: parameter inference deprecations shipped in
  Litestar 2.24 went unnoticed here precisely because no external material pointed at
  them, and they had to be found by reading the framework source. The suite now fails
  loudly on those warnings.
- **Litestar 3.0 will require migration work.** The deprecated forms are already gone
  from the code (see `3bea03f`), so the remaining exposure is unknown-unknowns rather
  than the known ones.

## Alternatives considered

- **FastAPI.** Rejected: more ecosystem, but the DI/exception-handling/thread-offload
  requirements would each need application-level scaffolding, and the project would
  trade real working code for a rewrite with no functional gain.
- **Migrating now.** Rejected on the same grounds: the learning cost is already paid
  and the code is idiomatic Litestar. Revisit only if the ecosystem gap starts costing
  more than the framework features save.
- **Starlite/Django Ninja and similar.** Not evaluated in depth; the project has no
  Django footprint and the requirements above are covered by Litestar.

## Revisit trigger

Reconsider if any of these becomes true: the API grows consumers outside this
institution that demand FastAPI-specific tooling (for example OpenAPI-based SDK
generation with mature generators), or Litestar 3.0 raises a migration cost that
exceeds a rewrite.
