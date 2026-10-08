# The curator SPA has no process of its own: `create_app()` mounts `apps/curator/dist` at `/`
# when the build exists, which keeps the browser on the same origin as the API. Build it before
# deploying with `bun install && bun run curator:build`. Without the build the API still serves,
# it just has no UI mounted.
api: CUDA_VISIBLE_DEVICES="" uv run uvicorn main:app --reload
