# syntax=docker/dockerfile:1.6
FROM --platform=linux/arm64 python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir uv

COPY pyproject.toml .
RUN --mount=type=secret,id=gitlab_token \
    TOKEN=$(cat /run/secrets/gitlab_token) && \
    uv pip install --system --no-cache . \
      --extra-index-url "https://__token__:${TOKEN}@gitlab.com/api/v4/projects/80473976/packages/pypi/simple"

COPY . .

EXPOSE 8081

# ai-foundry-serve hydrates telemetry secrets into the environment, then execs
# opentelemetry-instrument — required so ADOT reads the Datadog OTLP header at startup.
CMD ["ai-foundry-serve", "opentelemetry-instrument", "python", "-u", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8081"]
