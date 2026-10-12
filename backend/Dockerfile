FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY data ./data
COPY train_model.py ingest_pubmed.py ./
RUN useradd --create-home appuser && mkdir -p models && chown appuser models
USER appuser
# Models are trained from data/*.csv on first start (or run: python train_model.py)
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
