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
FROM pgvector/pgvector:pg15

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-15-postgis-3 \
    && rm -rf /var/lib/apt/lists/*
