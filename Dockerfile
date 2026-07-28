# Multi-stage: the builder has compilers and dev headers, the runtime does not.
# Smaller image, smaller attack surface, faster pulls.

FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Copy only the dependency manifest first. Docker caches this layer, so
# editing application code does not reinstall every dependency.
COPY pyproject.toml README.md ./
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install .

# ---------------------------------------------------------------------------

FROM python:3.11-slim AS runtime

# Never run as root.
RUN useradd --create-home --uid 10001 pipeline

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SHOULD_I_DATA_DIR=/data

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=pipeline:pipeline . .

RUN mkdir -p /data && chown -R pipeline:pipeline /data
USER pipeline
VOLUME ["/data"]

# Fails the container health check if the warehouse is stale or corrupt.
HEALTHCHECK --interval=1h --timeout=30s --start-period=10s --retries=2 \
  CMD python -m quality.checks || exit 1

ENTRYPOINT ["python", "-m"]
CMD ["serving.morning"]
