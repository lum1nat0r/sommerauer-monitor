# syntax=docker/dockerfile:1

FROM node:22.14.0-bookworm-slim AS frontend-build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY frontend ./frontend
COPY vite.config.ts ./
RUN npm run build

FROM python:3.12.9-slim-bookworm AS backend-build
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /src
RUN pip install --no-cache-dir uv==0.12.2
COPY pyproject.toml uv.lock README.md ./
COPY backend ./backend
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12.9-slim-bookworm AS runtime
ARG APP_VERSION=0.1.0
ARG BUILD_REVISION=unknown
ARG APP_UID=99
ARG APP_GID=100
LABEL org.opencontainers.image.title="Sommerauer Monitor" \
      org.opencontainers.image.description="Lokales, lesendes Heizungsmonitoring" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${BUILD_REVISION}"
ENV PATH="/opt/venv/bin:${PATH}" \
    APP_VERSION="${APP_VERSION}" \
    BUILD_REVISION="${BUILD_REVISION}" \
    DATA_DIR=/data \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN groupadd --gid "${APP_GID}" --non-unique monitor \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --no-create-home \
       --shell /usr/sbin/nologin monitor \
    && install -d -o monitor -g monitor /data
COPY --from=backend-build /opt/venv /opt/venv
COPY --from=backend-build /src/backend ./backend
COPY --from=frontend-build /src/dist ./static
USER ${APP_UID}:${APP_GID}
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import json,sys,urllib.request; response=urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=2); sys.exit(0 if json.load(response).get('status') == 'ok' else 1)"
STOPSIGNAL SIGTERM
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "15"]
