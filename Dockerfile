FROM ghcr.io/astral-sh/uv:0.13.3 AS uv
FROM docker:29-cli AS docker-cli
FROM python:3.13-slim-bookworm

COPY --from=uv /uv /usr/local/bin/uv
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

ARG REVISION=unknown
ARG SOURCE=https://github.com/Yb1ku/raspberry_mcp
LABEL org.opencontainers.image.source=$SOURCE \
      org.opencontainers.image.revision=$REVISION
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    RASPBERRY_MCP_REVISION=$REVISION
HEALTHCHECK --interval=15s --timeout=12s --start-period=20s --retries=3 \
    CMD ["python", "-m", "raspberry_mcp.healthcheck"]
CMD ["raspberry-mcp"]
