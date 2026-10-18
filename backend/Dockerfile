FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /app/uploads && chown app:app /app/uploads
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
USER 10001:10001
EXPOSE 8000
# Only trusted Compose services can reach this unpublished port. Nginx replaces XFF.
CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*", "--no-access-log"]

FROM runtime AS test
USER root
COPY requirements-dev.txt ./
RUN python -m pip install --no-cache-dir -r requirements-dev.txt
COPY pyproject.toml ./
COPY tests ./tests
USER 10001:10001
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
