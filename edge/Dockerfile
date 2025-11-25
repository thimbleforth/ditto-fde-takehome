# Use a small, secure base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (if needed for psycopg2, SQLite, etc.)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    sqlite3 \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# explicitly added the sqlite3 related packages above
# just to avoid issues

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run as non-root user for security
RUN useradd -m appuser
# RUN mkdir -p /app && chown appuser:appuser /app
# RUN mkdir -p /app/data && chown appuser:appuser /app/data

USER appuser


# Expose port (adjust for edge/cloud service)
# I don't think I need any of these but we'll see.
# EXPOSE 5000

# Default command to run the edge app
CMD ["python", "edge_app.py"]
