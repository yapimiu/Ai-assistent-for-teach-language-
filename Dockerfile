FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then \
      SSL_CERT_FILE=/run/secrets/build_ca uv sync --system-certs --frozen --no-dev; \
    else uv sync --frozen --no-dev; fi
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "app.bot"]
