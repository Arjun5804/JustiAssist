FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV WORKDIR=/app

WORKDIR $WORKDIR

# Install system dependencies for build and runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root user
RUN groupadd -r justiassist && useradd -r -g justiassist justiassist

# Create directories that might be mounted to ensure correct permissions
RUN mkdir -p /app/vector_stores /app/data /app/project_datasets /app/.data/storage && \
    chown -R justiassist:justiassist /app

# Copy application code
COPY --chown=justiassist:justiassist . .

# Ensure entrypoint is executable
RUN chmod +x entrypoint.sh

ENV HF_HOME=/app/data/huggingface

USER justiassist

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
