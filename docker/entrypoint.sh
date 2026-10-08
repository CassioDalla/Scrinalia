#!/bin/sh
#
# Entrypoint of the application image.
#
# It does exactly one thing before handing over to the CMD: brings the schema to head. The schema is
# owned by Alembic and nothing else creates it (there is no db-init), so an API started against a
# fresh volume answers 503 on /health/ready at best — and fails on every ORM read at worst.
#
# Two knobs, both environment variables:
#
#   SCRINALIA_RUN_MIGRATIONS   "true" (default) applies ``alembic upgrade head`` before the server
#                              starts. Set it to "false" when migrations are a separate step (a
#                              release job, an operator on the host), or when several replicas are
#                              started at once — Alembic takes no distributed lock, so concurrent
#                              runs are a race. The application image is designed for one process.
#   SCRINALIA_DB_WAIT_SECONDS  how long to keep retrying an unreachable database (default 60). The
#                              container usually starts before PostgreSQL accepts connections, and a
#                              crash loop there is noise: the timeout is what turns a real failure
#                              into a non-zero exit instead of an infinite retry.
#
# ``exec`` keeps the server as PID 1, so SIGTERM from the orchestrator reaches uvicorn and the
# shutdown is graceful rather than a kill.

set -eu

log() {
    printf '%s entrypoint: %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

if [ "${SCRINALIA_RUN_MIGRATIONS:-true}" = "true" ]; then
    wait_seconds="${SCRINALIA_DB_WAIT_SECONDS:-60}"
    deadline=$(( $(date +%s) + wait_seconds ))

    # libpq's own connect timeout, and it is what makes the loop below work: against a host that
    # *drops* packets instead of refusing them — a firewall, a database that has not finished
    # starting — psycopg2 waits for the operating system's TCP timeout, which is minutes, so the
    # deadline would never be reached and the container would look hung. Scoped to the migration on
    # purpose: the application's own engine keeps the behaviour it has when run on the host.
    until PGCONNECT_TIMEOUT="${PGCONNECT_TIMEOUT:-5}" alembic upgrade head; do
        if [ "$(date +%s)" -ge "$deadline" ]; then
            log "alembic upgrade head still failing after ${wait_seconds}s — giving up."
            log "Check DB_HOST/DB_PORT/DB_USER/DB_PASS/DB_NAME and that PostgreSQL is reachable."
            exit 1
        fi
        log "database not ready (or the migration failed) — retrying in 2s."
        sleep 2
    done

    log "schema is at head."
else
    log "SCRINALIA_RUN_MIGRATIONS is not 'true' — skipping alembic upgrade head."
fi

exec "$@"
