# One image, one process: the API **and** the curator SPA.
#
# That is not a shortcut, it is the shape the code already assumes. ``create_app()`` mounts
# ``apps/curator/dist`` at ``/`` when the build exists (``api/spa.py``), so the SPA has no process of
# its own, the browser stays on the same origin as the API and the project needs no CORS — which is
# also what makes the session cookie first-party and what ``origin_guard`` compares against. Two
# containers here would mean a second web server in front of the API to re-create the same origin
# that the API already provides, plus a CORS configuration the project deliberately does not have.
#
# What stays **outside** the image is infrastructure, not the application: PostgreSQL (with
# pgvector/PostGIS), an S3-compatible bucket (whichever product serves it) and the Ollama host. They
# are reached through ``DB_*``, ``S3_*`` and ``OLLAMA_HOST_URL``.
#
# License: AGPL-3.0-only plus the attribution term in ``LICENSE-ADDITIONAL-TERMS.md``. If you modify
# this image and offer the service over a network, section 13 requires you to publish your source.

# ------------------------------------------------------------------------------------------------
# Stage 1 — the curator SPA (Bun + Vite, per docs/adr/0003; Bun manages, Vite bundles)
#
# Every base image is pinned by **digest**, not by tag: the tags this file used to carry
# (``python:3.12-slim-bookworm``, ``oven/bun:1.3.14-slim``, ``ghcr.io/astral-sh/uv:0.11.14``) are
# rebuilt upstream, so the same commit would produce a different image on a different day — which is
# the one thing a lockfile exists to prevent. Bump a digest deliberately, with:
#
#   docker inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' <image:tag>
# ------------------------------------------------------------------------------------------------
FROM oven/bun:1.3.14-slim@sha256:d56a2534ffd262e92c12fd3249d3924d296d97086da773f821d7d0477435ea04 AS curator

WORKDIR /app

# The lockfile is frozen: the image must build the commit's dependency graph, not whatever is
# current on the registry today. Only the manifests the install needs are copied first, so editing
# the front-end reuses the install layer.
COPY package.json bun.lock ./
COPY apps/curator/package.json apps/curator/package.json
RUN bun install --frozen-lockfile

# ``bun run build`` is ``tsc --noEmit && vite build``, and ``tsc`` is a devDependency — so NODE_ENV
# must **not** be set to production here, or the type-check step loses its compiler.
COPY apps/curator apps/curator
RUN bun run --cwd apps/curator build

# ------------------------------------------------------------------------------------------------
# Stage 2 — the Python environment (uv, from the same uv version that produced uv.lock)
# ------------------------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS python-env

COPY --from=ghcr.io/astral-sh/uv:0.11.14@sha256:1025398289b62de8269e70c45b91ffa37c373f38118d7da036fb8bb8efc85d97 /uv /uvx /bin/

# UV_LINK_MODE=copy: hardlinks into a virtualenv that is then copied into another stage are a
# reliable way to ship a broken interpreter, and the default link mode is hardlink when it can.
#
# UV_COMPILE_BYTECODE pre-compiles the ~18 000 modules uv installs into site-packages. It does **not**
# cover the project itself: the editable install is a ``.pth`` pointing at /app/src, so the
# application's own 208 modules are compiled in memory at every start. Measured, that costs nothing
# (1.40 s to import the app with the cache, 1.48 s without — noise), so a ``compileall`` step is not
# warranted; the runtime sets PYTHONDONTWRITEBYTECODE so nothing even tries to write into /app.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# psycopg2 is the only dependency without a manylinux wheel (its uv.lock entry carries win_amd64
# wheels only), so it is compiled from source and needs libpq's headers plus a C toolchain. Both stay
# in this stage: the runtime image below needs only libpq5.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, the project last: a code change then reuses the heavy torch/transformers layer
# instead of re-resolving it. ``--no-install-project`` is what makes that split possible.
#
# No BuildKit-only instruction is used anywhere in this file, so it also builds with the classic
# builder (``docker build`` without the buildx component). The price is not mounting uv's download
# cache; the layer cache already covers the common case, where only the application code changed.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# hatchling reads ``readme`` and ``license-files`` from pyproject.toml to build the metadata, so the
# project cannot be installed without these three files sitting next to it.
COPY README.md LICENSE LICENSE-ADDITIONAL-TERMS.md ./
COPY src src
COPY main.py ./

# ``uv sync`` installs the project **editable** by default, and here that is load-bearing:
# ``api/spa.py`` derives the SPA directory from its own ``__file__`` (``parents[3]``), so a wheel in
# site-packages would look for the build under /usr/lib/python3.12 and silently serve an API with no
# UI. Do not add ``--no-editable``, and keep the source tree at /app/src.
RUN uv sync --frozen --no-dev

# ------------------------------------------------------------------------------------------------
# Stage 3 — runtime
# ------------------------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS runtime

# libpq5 only: psycopg2 links against it at import time. The image runs as a normal user because
# nothing in the application needs root — the two directories it writes to are created below and
# mounted as volumes.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --user-group scrinalia

# CUDA_VISIBLE_DEVICES="" mirrors the Procfile: the application runs on CPU, so a host without the
# NVIDIA driver must not make the process fail on start-up.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIRTUAL_ENV=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    CUDA_VISIBLE_DEVICES="" \
    HOME=/home/scrinalia \
    LOG_DIR=/app/logs \
    HF_HOME=/home/scrinalia/.cache/huggingface

WORKDIR /app

# The environment, the application and the SPA build, then the two things the entrypoint needs and
# that are not part of the wheel: the Alembic config and its revisions.
#
# One instruction, not three, and that is a measured decision: ``COPY --from=<stage>`` is keyed on the
# **whole stage's** final layer, not on the path it copies, so splitting this into ``/app/.venv`` +
# ``/app/src`` + ``/app/main.py`` does not keep the ~6 GB venv cached when only the source changed —
# measured, 343 s against 303 s, the same full re-copy either way. A source edit therefore costs a
# ~5 minute rebuild: this image is a release artifact, and ``bun run dev`` is the development loop.
# The SPA bundle comes from stage 1 and never from the context, where ``apps/curator/dist`` is
# gitignored and may be stale.
COPY --from=python-env --chown=scrinalia:scrinalia /app /app
COPY --from=curator --chown=scrinalia:scrinalia /app/apps/curator/dist /app/apps/curator/dist
COPY --chown=scrinalia:scrinalia alembic.ini ./
COPY --chown=scrinalia:scrinalia migrations migrations
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh \
    && mkdir -p /app/logs "$HF_HOME" \
    && chown -R scrinalia:scrinalia /app/logs /home/scrinalia

USER scrinalia

EXPOSE 8000

# Liveness, not readiness: ``/health/live`` touches nothing, so a database that is down takes the
# instance out of rotation through ``/health/ready`` instead of making the orchestrator restart a
# process that is answering. This probe therefore uses the Python already in the image rather than
# curl, which is not installed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3).status == 200 else 1)"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# One worker, explicitly. The API owns an in-process worker executor and ``api/lifespan.py`` marks
# every QUEUED/RUNNING run it finds at start-up as INTERRUPTED — that recovery is only correct with a
# single process, so scaling to ``--workers > 1`` requires moving the executor out first.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
