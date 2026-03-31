FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --gid 1000 appuser \
    && useradd --create-home --uid 1000 --gid 1000 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

RUN chmod +x /app/scripts/run-local.sh /app/scripts/smoke-test.sh /app/scripts/container-entrypoint.sh \
    && mkdir -p /app/data \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app

EXPOSE 8080

CMD ["./scripts/container-entrypoint.sh"]
