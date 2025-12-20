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
RUN pyinstaller --onefile --strip --clean edge_app.py

# ============= STAGE 3: Runtime Image =============
FROM alpine:3.23.2 AS runtime

RUN apk add --no-cache ca-certificates

# Copy the compiled binary from the compile stage
COPY --from=compile /app/dist/edge_app /usr/local/bin/edge_app

RUN chmod +x /usr/local/bin/edge_app

# Run as non-root user for security
RUN addgroup -S appgroup && adduser -S -G appgroup appuser
# RUN mkdir -p /app && chown appuser:appuser /app
RUN mkdir -p /app/data && chown -R appuser:appuser /app/data

USER appuser


# Expose port for web server
EXPOSE 5000

# Allow configuring the web server port via environment variable
ENV EDGE_WEB_PORT=5000

# Default command to run the edge app
ENTRYPOINT ["/usr/local/bin/edge_app"]
