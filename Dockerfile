FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer is cached on code-only changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source modules used by app.py
COPY extractor.py parser.py parser_v2.py generator.py matcher.py tailor.py app.py ./

# Copy the default INTM DDC template bundled with the app
COPY "INTM_DDC_Mohamad_ELHAF - Template 2 (002).docx" ./

ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
EXPOSE 8501

# Use Python's built-in urllib so curl is not needed in the image
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
