FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY src ./src
COPY migrations ./migrations
COPY scripts ./scripts
RUN pip install --no-cache-dir . && useradd --create-home app && mkdir /app/media && chown app:app /app/media
USER app
EXPOSE 8000
CMD ["uvicorn", "src.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
