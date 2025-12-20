# ============= STAGE 1: Build Image =============
# Use a small, secure base image
FROM python:3.11-slim AS builder

# Set working directory
WORKDIR /app

# Install system dependencies (if needed for psycopg2, SQLite, etc.)
# Including compilers and libraries for building the Python binary
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    sqlite3 \
    libsqlite3-dev \
    gcc \
    libffi-dev \
    musl-dev \
    && rm -rf /var/lib/apt/lists/*

# explicitly added the sqlite3 related packages above
# just to avoid issues

ENV VIRTUAL_ENV=/opt/env
RUN python -m venv ${VIRTUAL_ENV}
ENV PATH="${VIRTUAL_ENV}/bin:$PATH"

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install pyinstaller

# Copy application code
COPY . .

# ============= STAGE 2: Final Image =============
FROM builder AS compile

WORKDIR /app

# Build the frozen binary
RUN pyinstaller --onefile --strip --clean cloud_app.py

# ============= STAGE 3: Runtime Image =============
FROM alpine:3.23.2 AS runtime

RUN apk add --no-cache ca-certificates

COPY --from=compile /app/dist/cloud_app /usr/local/bin/cloud_app

RUN chmod +x /usr/local/bin/cloud_app

# Run as non-root user for security
RUN addgroup -S servergroup && adduser -S -G servergroup serveruser
# RUN mkdir -p /app && chown appuser:appuser /app
RUN mkdir -p /app/data && chown -R serveruser:serveruser /app/data

USER serveruser

# Expose port (adjust for edge/cloud service)
EXPOSE 8443

# Default command to run the cloud app
ENTRYPOINT ["/usr/local/bin/cloud_app"]
