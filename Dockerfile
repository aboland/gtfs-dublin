# Use official Python image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy UV workspace files
COPY pyproject.toml uv.lock ./
COPY mcp-server/pyproject.toml ./mcp-server/

# Install dependencies for both main project and MCP server
RUN uv sync --frozen --no-install-project

# Copy project files
COPY . /app/

# Install the projects
RUN uv sync --frozen

# Expose ports for both services
EXPOSE 8000 8001

# Set environment variable for stops (default empty)
ENV STOPS=""

# Default command - can be overridden
CMD ["uv", "run", "uvicorn", "gtfs_dublin.transport_api_server:app", "--host", "0.0.0.0", "--port", "8000"]
