FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY workspace/ ./workspace/
COPY evaluation/ ./evaluation/
COPY scripts/ ./scripts/

# Create uploads dir
RUN mkdir -p workspace/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
