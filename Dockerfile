FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY alembic.ini ./alembic.ini
COPY config ./config
COPY docs ./docs
COPY migrations ./migrations
COPY mkdocs.yml ./mkdocs.yml
COPY src ./src
COPY templates ./templates

RUN python -m pip install --upgrade pip \
    && python -m pip install ".[postgres,s3,docs]"

CMD ["hal", "--help"]
