FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache --no-install-project
COPY . .

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=builder /app .
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8002
CMD ["python", "mcp_server.py"]
