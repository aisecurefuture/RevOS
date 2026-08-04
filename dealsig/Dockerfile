FROM python:3.12.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:$PATH"

RUN python -m venv /opt/venv
COPY requirements.txt /tmp/requirements.txt
RUN pip install --requirement /tmp/requirements.txt

RUN groupadd --system --gid 10001 dealsig \
    && useradd --system --uid 10001 --gid dealsig --home-dir /app --shell /usr/sbin/nologin dealsig

WORKDIR /app
COPY --chown=dealsig:dealsig app ./app
COPY --chown=dealsig:dealsig DealSigAI.PNG ./DealSigAI.PNG
COPY --chown=dealsig:dealsig DealSigAI_Dark.PNG ./DealSigAI_Dark.PNG
COPY --chown=dealsig:dealsig pyproject.toml ./pyproject.toml

USER dealsig
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=4s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips=*"]
