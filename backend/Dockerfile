FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY data ./data
COPY train_model.py ingest_pubmed.py ./
# Train at build time so every container of an image serves identical, integrity-hashed model artifacts.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p models logs \
    && python train_model.py \
    && chown -R appuser models logs
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8000\")}/v1/ready', timeout=4)"
# Client IPs behind a reverse proxy come from TRUSTED_PROXY_HOPS (see app/security.py), not uvicorn's proxy headers.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-proxy-headers --no-server-header"]
