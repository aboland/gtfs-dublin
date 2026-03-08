# Use official Python image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install system dependencies (including Git LFS)
RUN apt-get update && apt-get install -y \
    gcc \
    git \
    git-lfs \
    && rm -rf /var/lib/apt/lists/ \
    && git lfs install --system

# Copy UV workspace files
COPY pyproject.toml uv.lock ./
COPY mcp-server/pyproject.toml ./mcp-server/

# Install dependencies for both main project and MCP server
RUN uv sync --frozen --no-install-project

# Copy project files
COPY . /app/

# Initialize Git LFS and ensure GTFS data is available
RUN git lfs install --system && \
    echo "=== GTFS Data Setup ===" && \
    echo "Checking for existing GTFS files..." && \
    ls -la GTFS_Realtime/ || true && \
    echo "Attempting Git LFS pull..." && \
    git lfs pull --include="GTFS_Realtime/*.txt" 2>&1 || echo "LFS pull failed" && \
    echo "Checking if files are LFS pointers..." && \
    if grep -q "oid sha256" GTFS_Realtime/stop_times.txt 2>/dev/null; then \
        echo "Found LFS pointer, downloading fresh GTFS data..." && \
        python3 update_gtfs.py 2>&1 && \
        echo "Fresh download completed"; \
    else \
        echo "GTFS files appear to be valid"; \
    fi && \
    echo "Final verification..." && \
    if [ ! -f GTFS_Realtime/stop_times.txt ] || grep -q "oid sha256" GTFS_Realtime/stop_times.txt 2>/dev/null; then \
        echo "ERROR: GTFS data still not available after all attempts"; \
        exit 1; \
    fi && \
    echo "Sample of stop_times.txt:" && \
    head -3 GTFS_Realtime/stop_times.txt && \
    echo "GTFS setup completed successfully"

# Install the projects
RUN uv sync --frozen

# Expose ports for both services
EXPOSE 8000 8001

# Set environment variable for stops (default empty)
ENV STOPS=""

# Default command - can be overridden
CMD ["uv", "run", "uvicorn", "gtfs_dublin.transport_api_server:app", "--host", "0.0.0.0", "--port", "8000"]
