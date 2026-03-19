FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files
COPY extractor.py parser.py parser_v2.py adapter.py generator.py main.py app.py ./

# Streamlit config: disable telemetry, set port
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
EXPOSE 8501

# Health check
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]