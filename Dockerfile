# SeeSee — Multi-stage Docker build
# Lightweight, self-hosted sent email log aggregator.

FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

FROM base AS builder

WORKDIR /build
COPY pyproject.toml .
COPY seesee/ seesee/

RUN pip install --no-cache-dir --prefix=/install .

FROM base AS runtime

# Create non-root user
RUN groupadd --gid 1000 seesee && \
    useradd --uid 1000 --gid seesee --shell /bin/bash --create-home seesee

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
WORKDIR /app
COPY seesee/ seesee/

# Create data directory for SQLite
RUN mkdir -p /data && chown seesee:seesee /data

# Default environment
ENV SEESEE_DB_PATH=/data/seesee.db \
    SEESEE_PORT=8080

# Switch to non-root user
USER seesee

# Expose HTTP and SMTP ports
EXPOSE 8080 2525

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/v1/health')" || exit 1

# Persistent storage
VOLUME ["/data"]

CMD ["python", "-m", "seesee"]
