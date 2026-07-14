FROM python:3.12.11-slim

# Image metadata
LABEL org.opencontainers.image.title="Yandex Search API MCP Server"
LABEL org.opencontainers.image.description="MCP server for Yandex Search API v2 with web and AI search capabilities"
LABEL org.opencontainers.image.vendor="nebelov/yandex-direct-for-all"
LABEL org.opencontainers.image.version="1.1.0"
LABEL org.opencontainers.image.licenses="Apache-2.0"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.11.28 \
    && uv sync --frozen --no-dev \
    && useradd --create-home --uid 10001 app

COPY --chown=app:app server.py detail.py ./
ENV PATH="/app/.venv/bin:$PATH"
USER app

CMD ["python", "server.py"]
