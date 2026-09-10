FROM python:3.12-slim

WORKDIR /app

# Install reportlab system deps (fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    reportlab google-genai neo4j python-dotenv \
    "google-adk[extensions]" rapidfuzz openpyxl litellm

# Copy backend code
COPY backend/ .

# Copy cra_agents (backend imports product_tools & neo4j_tools)
COPY cra_agents/ /app/cra_agents/

# Root-level modules imported by cra_agents tools (partis_tools imports partis_batch)
COPY partis_batch.py /app/

# Uploads volume mount point
RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
