FROM python:3.9-slim

WORKDIR /app

# Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create necessary directories
RUN mkdir -p /app/translated_files \
    /app/src/web/static \
    /app/src/web/templates

# Create a non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

ARG PORT=5000
ENV PORT=$PORT
EXPOSE $PORT

VOLUME /app/translated_files

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; import os; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", 5000)}/api/health')" || exit 1

# Switch to non-root user
USER appuser

CMD ["python", "translation_api.py"]