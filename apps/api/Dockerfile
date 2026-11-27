# Backend image: the API and the container simulator (same Python stack). Build from the repo root:
#   docker build -f apps/api/Dockerfile -t zyrcle-api .
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /src
# Every dependency at the exact version and hashes of the lock file (docs/adr/0044), so a new
# release of a library reaches production only through apps/api/scripts/lock.sh and CI.
COPY apps/api/requirements.txt apps/api/requirements.txt
RUN pip install --require-hashes -r apps/api/requirements.txt
COPY packages/protocol packages/protocol
COPY device/simulator device/simulator
COPY apps/api apps/api
# Our three packages on top, without letting pip fetch anything else; pip check stops the build
# when a pyproject.toml asks for a package or version the lock file does not have.
RUN pip install --no-deps ./packages/protocol ./device/simulator ./apps/api && pip check

FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin zyrcle \
 && mkdir -p /keys && chown zyrcle /keys  # a fresh named volume at /keys inherits this owner
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/migrations ./migrations
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER zyrcle
EXPOSE 8000
CMD ["zyrcle-api", "serve", "--host", "0.0.0.0", "--port", "8000"]
