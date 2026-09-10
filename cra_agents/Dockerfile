FROM python:3.12-slim

WORKDIR /app

COPY cra_agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "google-adk[extensions]"

# Copy agent source
COPY cra_agents/ /app/cra_agents/

# Copy root-level modules imported by agent tools
COPY partis_batch.py /app/

# ADK web serves on port 8000 by default
EXPOSE 8080

CMD ["adk", "web", "--host", "0.0.0.0", "--port", "8080"]
