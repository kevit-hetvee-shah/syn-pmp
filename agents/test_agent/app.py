"""AG-UI Test Agent agent — built on the AI Foundry Platform SDK."""

import os
from ai_foundry_platform_sdk.agent import AgentDefinition, AuthConfig, PortkeyConfig, Skill, ToolDefinition
from ai_foundry_platform_sdk.agent.prompt import PromptAssembler
from ai_foundry_platform_sdk.app import create_agui_app
from ai_foundry_platform_sdk.model import EnvVarResolver, ModelConfig, ModelProvider

# To enable code interpreter with S3 file I/O, uncomment the import below
# and add code_interpreter_tool(...) to the tools list. In
# infra/envs/<env>.tfvars.json: grant the bucket via an additional_iam_statements
# entry (s3:GetObject/PutObject on the bucket + s3:ListBucket) and set
# CODE_INTERPRETER_S3_BUCKET in environment_variables. See
# docs/03-tools-and-connectors.md for the end-to-end walk-through.
# from ai_foundry_platform_sdk.tools.code_interpreter import code_interpreter_tool

agent = AgentDefinition(
    name="Test Agent",
    description="Test agent working",
    domain_prompt="You are a helpful assistant that can answer questions about the Test Agent.",
    skills=[
        Skill(
            id="test_agent",
            name="Test Agent",
            description="Test agent working",
            tags=["test_agent"],
        ),
    ],
    # auth=AuthConfig(
    #     allowed_groups=os.environ.get("ALLOWED_AD_GROUPS", "").split(","),
    # ),
    model_config=ModelConfig(model_id="@az-openai/gpt-4.1-mini"),
    portkey=PortkeyConfig(
        # The SDK always stamps three platform-governed metadata keys on every
        # Portkey request for cost analytics — "_user" (from the verified JWT)
        # plus "environment"/"application" (from this deployment's OTEL
        # resource). That is not configurable here.
        #
        # allow_caller_kwargs: let callers tune Portkey per request (trace_id,
        # cache namespace, extra metadata such as feature/session_id) via the
        # request body — A2A task metadata or AG-UI forwarded_props under a
        # "portkey_options" key. Credentials, provider selection, and debug stay
        # guarded regardless.
        allow_caller_kwargs=True,
        # debug_logging: verbose Portkey gateway/HTTP logging. Leave off in
        # production — credentials and metadata are redacted, but the volume is
        # high. A startup warning fires when it is on.
        debug_logging=True,
    ),
)

# Local dev only, explicit opt-in: OFFLINE_PROMPTS=true skips Portkey's
# prompts.render() call entirely (PromptAssembler falls back to the SDK's
# bundled base-prompt file instead of a live network call — see
# ai_foundry_platform_sdk/agent/prompt.py). This agent has no
# domain_prompt_id, so with no portkey_loader, create_agui_app's full
# startup path (secret resolution, prompt validation, conflict detection,
# tool validation) makes zero network calls. NEVER set this in a deployed
# environment: it bypasses the platform-owned, centrally-managed base
# prompt that Portkey serves in production.
#
# create_agui_app() only loads .env internally once it starts running (via
# its own env_file argument), which is *after* this flag would need to be
# read — so load .env ourselves first (idempotent, load_dotenv won't
# override already-exported vars) to make OFFLINE_PROMPTS=true in .env
# actually take effect without needing a shell export.
from dotenv import load_dotenv

load_dotenv(".env")
_offline_prompts = os.environ.get("OFFLINE_PROMPTS", "").strip().lower() in ("1", "true", "yes")

# Local dev only, explicit opt-in: ModelProvider's default secret_resolver is
# AWSSecretsManagerResolver, which hard-requires AGENT_SECRET_NAME (or legacy
# PORTKEY_SECRET_NAME) pointing at a real AWS Secrets Manager secret — there
# is no built-in "just use PORTKEY_API_KEY directly" fallback in that path
# (confirmed against ai_foundry_platform_sdk.model.provider's source,
# 2026-11-02), unlike what this file's own .env.example comment implies.
# When AGENT_SECRET_NAME/PORTKEY_SECRET_NAME are unset but PORTKEY_API_KEY
# is, swap in EnvVarResolver (an SDK-provided resolver, explicitly documented
# as "For local dev and testing") so the agent can start with a plain env var
# instead of real AWS access. NEVER set AGENT_SECRET_NAME in a deployed
# environment, so this branch never activates there.
_model_provider = (
    ModelProvider(secret_name="PORTKEY_API_KEY", secret_resolver=EnvVarResolver())
    if not os.environ.get("AGENT_SECRET_NAME")
    and not os.environ.get("PORTKEY_SECRET_NAME")
    and os.environ.get("PORTKEY_API_KEY")
    else None
)

app = create_agui_app(
    agent,
    # Local dev only: lets a browser-based test UI running on another origin/port
    # call this agent. Set CORS_ORIGINS="*" (or a comma-separated allowlist) in
    # .env for local testing; leave unset in deployed environments.
    cors_origins=os.environ["CORS_ORIGINS"].split(",") if os.environ.get("CORS_ORIGINS") else None,
    prompt_assembler=PromptAssembler(portkey_loader=None) if _offline_prompts else None,
    model_provider=_model_provider,
)

# Meeting Context intake step (wizard step 1) — plain REST, mock data only.
# This router never imports the agent/model path above and cannot trigger a
# Portkey call; see context_api.py's module docstring for the scope boundary.
from context_api import router as meeting_context_router  # noqa: E402

app.include_router(meeting_context_router, prefix="/api")
