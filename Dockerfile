FROM node:20-bookworm-slim AS frontend

WORKDIR /build/app
COPY app/package.json app/package-lock.json ./
RUN npm ci
COPY app/ ./
RUN npm run build


FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /uvx /bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ripgrep \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY src/ src/
COPY config/ config/
COPY scripts/ scripts/
COPY data/mock/ data/mock/
COPY public-knowledge/ public-knowledge/
COPY readme.md LICENSE ./
COPY --from=frontend /build/app/dist app/dist

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED="1"

EXPOSE 8000

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
