"""LangChain model client wired to Portkey — the company's governed LLM
gateway (cost tracking, credentials, provider routing). Every agent_graphs/*
agent gets its model from `get_chat_model()` here; nothing else in this
project is allowed to build a model client directly.

Portkey's gateway is OpenAI-API-compatible, and its Model Catalog lets a
caller select the underlying provider/model with a single `model` string of
the form "@provider-slug/model-name" (e.g. "@az-openai/gpt-4.1-mini") sent
straight through the normal `/chat/completions` body — no virtual-key headers
needed. That's exactly the `model_id` value every agent_definitions/*.py
previously passed to `ModelConfig(model_id=...)`, so `ChatOpenAI(base_url=
PORTKEY_BASE_URL, api_key=<portkey key>, model=model_id)` is a drop-in
replacement.

Secret resolution mirrors ai_foundry_platform_sdk.model.secrets exactly, so
the same AWS Secrets Manager secret (one JSON blob, `PORTKEY_API_KEY` field)
already provisioned for this agent keeps working unchanged:
  1. `PORTKEY_API_KEY` env var set directly — local dev / tests, no AWS call.
  2. `AGENT_SECRET_NAME` (or legacy `PORTKEY_SECRET_NAME`) — fetch+parse the
     named secret from AWS Secrets Manager, cached for the process lifetime.
"""

from __future__ import annotations

import json
import os

from langchain_openai import ChatOpenAI

DEFAULT_MODEL_ID = "@az-openai/gpt-4.1-mini"

_cached_api_key: str | None = None


def _resolve_agent_secret_name() -> str | None:
    return os.environ.get("AGENT_SECRET_NAME") or os.environ.get("PORTKEY_SECRET_NAME")


def _fetch_portkey_api_key_from_secrets_manager(secret_id: str) -> str:
    import boto3

    region = os.environ.get("AWS_DEFAULT_REGION", "eu-central-1")
    client = boto3.client("secretsmanager", region_name=region)
    raw = client.get_secret_value(SecretId=secret_id)["SecretString"]
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    return parsed.get("PORTKEY_API_KEY", raw)


def resolve_portkey_api_key() -> str:
    """Cached for the process lifetime — same contract as the SDK's
    AWSSecretsManagerResolver. Raises RuntimeError if nothing is configured,
    since a model call with no credentials should fail loudly, not silently
    build a client that fails on first use."""
    global _cached_api_key
    if _cached_api_key is not None:
        return _cached_api_key

    env_key = os.environ.get("PORTKEY_API_KEY")
    if env_key:
        _cached_api_key = env_key
        return _cached_api_key

    secret_name = _resolve_agent_secret_name()
    if not secret_name:
        raise RuntimeError(
            "No Portkey credentials configured: set PORTKEY_API_KEY (local dev) "
            "or AGENT_SECRET_NAME (deployed, AWS Secrets Manager)."
        )
    _cached_api_key = _fetch_portkey_api_key_from_secrets_manager(secret_name)
    return _cached_api_key


def get_chat_model(model_id: str | None = None, *, temperature: float = 0.0, **kwargs: object) -> ChatOpenAI:
    """One LangChain model client per call — cheap, `ChatOpenAI` has no
    connection-setup cost. `model_id` defaults to `PORTKEY_MODEL_ID` (env) or
    `DEFAULT_MODEL_ID`, matching every agent's prior per-agent `ModelConfig`.
    """
    base_url = os.environ.get("PORTKEY_BASE_URL")
    if not base_url:
        raise RuntimeError("PORTKEY_BASE_URL is not set — required to reach the Portkey gateway.")

    resolved_model_id = model_id or os.environ.get("PORTKEY_MODEL_ID") or DEFAULT_MODEL_ID

    return ChatOpenAI(
        model=resolved_model_id,
        base_url=base_url,
        api_key=resolve_portkey_api_key(),
        temperature=temperature,
        **kwargs,
    )
