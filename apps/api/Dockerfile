# Backend image: the API and the container simulator (same Python stack). Build from the repo root:
#   docker build -f apps/api/Dockerfile -t zyrcle-api .
FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /src
COPY packages/protocol packages/protocol
COPY device/simulator device/simulator
COPY apps/api apps/api
RUN pip install ./packages/protocol "./device/simulator[control]" ./apps/api

FROM python:3.13-slim
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
