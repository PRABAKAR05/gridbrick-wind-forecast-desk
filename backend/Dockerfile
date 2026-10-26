FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Runtime dependencies first: this layer is cached across source changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY seeds ./seeds

# The seed snapshot is readable by everyone; only the SQLite directory needs
# write access. Run as a non-root user in the container.
RUN useradd --create-home --uid 10001 gridbrick \
    && mkdir -p /app/data \
    && chown -R gridbrick:gridbrick /app

USER gridbrick

ENV GRIDBRICK_ENVIRONMENT=production \
    GRIDBRICK_DATABASE_URL=sqlite:////app/data/gridbrick.db \
    GRIDBRICK_SEED_DIR=/app/seeds

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
