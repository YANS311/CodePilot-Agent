FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application and runtime assets
COPY app/ ./app/
COPY skills/ ./skills/
COPY profiles/ ./profiles/
COPY mcp.json ./mcp.json
COPY workspace/ ./workspace/
COPY evaluation/ ./evaluation/
COPY scripts/ ./scripts/

# Ensure runtime directories exist
RUN mkdir -p workspace/uploads reports

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
