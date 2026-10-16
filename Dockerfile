FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LANGSMITH_TRACING=false PROCUREFLOW_HOME=/data PROCUREFLOW_MODE=demo
WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app && mkdir /data && chown app:app /data
COPY pyproject.toml requirements.lock README.md LICENSE ./
COPY procureflow ./procureflow
COPY scripts ./scripts
RUN python -m pip install --no-cache-dir -r requirements.lock
USER app
EXPOSE 8040
VOLUME ["/data"]
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8040/api/health',timeout=2)"
CMD ["python", "-m", "uvicorn", "procureflow.api:app", "--host", "0.0.0.0", "--port", "8040"]
