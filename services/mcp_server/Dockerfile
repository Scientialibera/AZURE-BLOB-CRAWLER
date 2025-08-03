# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for Azure packages
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY services/mcp_server/requirements.txt .

# Upgrade pip and install Python dependencies with verbose output
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --verbose -r requirements.txt

# Copy shared libraries
COPY shared/ /app/shared/

# Copy application code
COPY services/mcp_server/app/ /app/

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Expose port for MCP server
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the MCP server
CMD ["python", "app.py"]
