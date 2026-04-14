FROM python:3.11-slim AS builder

WORKDIR /app

RUN pip install poetry==1.8.3
RUN poetry config virtualenvs.create false

# Copy dependency files
COPY packages/hwarang-shared/pyproject.toml packages/hwarang-shared/
COPY modules/hwarang-core/pyproject.toml modules/hwarang-core/
COPY modules/hwarang-api/pyproject.toml modules/hwarang-api/

# Copy source
COPY packages/hwarang-shared/src packages/hwarang-shared/src/
COPY modules/hwarang-core/src modules/hwarang-core/src/
COPY modules/hwarang-core/configs modules/hwarang-core/configs/
COPY modules/hwarang-api/src modules/hwarang-api/src/

WORKDIR /app/modules/hwarang-api
RUN poetry install --no-interaction --no-ansi --only main

FROM python:3.11-slim AS runtime

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Worker entry point
CMD ["python", "-m", "hwarang_api.distributed.worker", \
     "--model-path", "/models/hwarang-small", \
     "--model-id", "hwarang-small", \
     "--redis-url", "redis://redis:6379"]
