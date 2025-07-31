# Multi-stage build for smaller final image
FROM python:3.11-slim as builder

# Set working directory  
WORKDIR /app

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY ms/mcp-search-service/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /root/.local

# Update PATH to include user packages
ENV PATH=/root/.local/bin:$PATH

# Copy the application files
COPY ms/mcp-search-service/mcp_search_server.py .

# Copy shared libraries (these paths are relative to build context)
COPY ms/shared ./shared

# Create non-root user for security and copy packages to user directory
RUN useradd --create-home --shell /bin/bash app \
    && cp -r /root/.local /home/app/.local \
    && chown -R app:app /app /home/app/.local
USER app

# Update PATH for the app user
ENV PATH=/home/app/.local/bin:$PATH

# Expose port
EXPOSE 50052

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:50052/health')" || exit 1

# Start the application
CMD ["python", "mcp_search_server.py"]
