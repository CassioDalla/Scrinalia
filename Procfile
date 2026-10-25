# The curator SPA has no process of its own: `create_app()` mounts `apps/curator/dist` at `/`
# when the build exists, which keeps the browser on the same origin as the API. Build it before
# deploying with `bun install && bun run curator:build`. Without the build the API still serves,
# it just has no UI mounted.
#
# `api` only enqueues since ADR 0014; `runner` is the process that claims the queue and runs the
# workers. They are separate process types on purpose: the runner can live on the machine with the
# models, and the API can be scaled. Both need the same `DB_*` (or the runner its own
# `RUNNER_DATABASE_URL`) and the same `S3_*`/`OLLAMA_HOST_URL`.
api: CUDA_VISIBLE_DEVICES="" uv run uvicorn main:app --reload
runner: CUDA_VISIBLE_DEVICES="" uv run python -m scrinalia.domains.archive.workers.runner_daemon --name heroku
