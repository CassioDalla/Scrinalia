# PostgreSQL with both vector search (pgvector) and geospatial support (PostGIS).
#
# The stock ``postgis/postgis`` images are still built on Debian 11 (bullseye), whose
# PGDG apt repository was retired, so pgvector cannot be installed there. This image
# starts from the pgvector base (Debian 12 / bookworm) and adds PostGIS from PGDG,
# keeping the same PostgreSQL major version (15) so an existing data directory keeps
# working without a dump/restore.
#
# PostGIS is installed but not enabled by any migration yet: the geospatial work (map
# by neighbourhood, pins) is still ahead. Enabling it is a one-line migration when it
# arrives, and this image is already able to run it.
# Pinned by digest, and the same digest as the test compose and the CI service: a tag can be
# re-pushed, and an image that silently changed underneath would make "it works here" mean nothing.
FROM pgvector/pgvector:pg15@sha256:47af0b65960b14f1c6945aa4ccae37836c632e9a6fe0eea9160936e616e5b2e9

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-15-postgis-3 \
    && rm -rf /var/lib/apt/lists/*
