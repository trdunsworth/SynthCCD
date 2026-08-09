# synth911gen3 Dockerfile
# Multi-stage build for smaller production image

# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Install dependencies in a virtual environment
RUN uv sync --locked --no-dev --no-install-project

# Runtime stage
FROM python:3.12-slim AS runtime

# Create non-root user
RUN groupadd -r synth911 && useradd -r -g synth911 -d /home/synth911 -s /bin/bash synth911

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy project source
COPY --from=builder /app/src /app/src

# Create cache directory for OSM addresses
RUN mkdir -p /home/synth911/.cache/synth911gen3 && chown -R synth911:synth911 /home/synth911

# Create output directory
RUN mkdir -p /app/output && chown -R synth911:synth911 /app/output

# Switch to non-root user
USER synth911

# Set PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src:$PYTHONPATH"

# Default environment variables
ENV SYNTH911_LOG_LEVEL=INFO

# Expose port for FastAPI server
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)" || exit 1

# Default command runs the API server
CMD ["synth911gen3-serve"]