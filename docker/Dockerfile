# syntax=docker/dockerfile:1
# ----------------------------------------------------------------------------
# QuantBot image — Python 3.12 slim, non-root, installs the package + deps.
# ----------------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build deps for numpy/scipy/psycopg2 wheels that may compile.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Install the package.
COPY pyproject.toml ./
COPY src ./src
COPY sql ./sql
COPY scripts ./scripts
COPY config ./config
RUN pip install -e .

# Non-root runtime user.
RUN useradd --create-home --uid 10001 quant \
    && mkdir -p /app/artifacts /app/reports /app/logs \
    && chown -R quant:quant /app
USER quant

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Default: launch the monitoring dashboard.  Override `command` for the engine.
EXPOSE 8000
CMD ["uvicorn", "quantbot.monitoring.dashboard:app", "--host", "0.0.0.0", "--port", "8000"]
