# Stage 1: Builder
# ---------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Generate wheels for all dependencies to avoid re-compiling in final stage
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt


# Stage 2: Final
# ---------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# Default port for local testing, Cloud Run will override this with $PORT
ENV PORT 8000

# Install runtime-only dependencies (libpq5 for PostgreSQL)
RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN addgroup --system appgroup && \
    adduser --system --group --home /home/appuser appuser
ENV HOME=/home/appuser

WORKDIR /app

# Install dependencies from wheels built in the builder stage
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels

# Copy the application code
COPY . /app/

# Create directories for static and media files
# Ensure appuser owns the /app directory for runtime operations (like collectstatic)
RUN mkdir -p /app/staticfiles /app/media && \
    chown -R appuser:appgroup /app && \
    chmod +x /app/entrypoint.prod.sh /app/entrypoint.migrate.sh

# Switch to non-root user
USER appuser

# Expose port (informational, Cloud Run ignores this but good for local dev)
EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.prod.sh"]
