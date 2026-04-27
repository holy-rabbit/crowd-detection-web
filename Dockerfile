# Use Python base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Update Debian mirror for better connectivity
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources || true && \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list || true

# Install system dependencies with retries
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create directories for uploads and outputs
RUN mkdir -p static/uploads static/output

# Copy requirements first (for Docker layer caching)
COPY requirements.txt .

# Install Python dependencies
# Upgrade pip first, then install with SSL/timeout workarounds
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    --default-timeout=1000 \
    --retries=10 \
    --trusted-host pypi.python.org \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    -r requirements.txt

# Copy the rest of the application
COPY . .

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Expose Flask port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Run Flask app
CMD ["python", "app.py"]