# Test Agent

Test agent working

Protocol: **AG-UI** (port 8081)

Built with the [AI Foundry Platform SDK](https://gitlab.com/syngentagroup/ai-foundry/ai-foundry-platform-sdk).

## Before CI Can Run

Set in Project → Settings → CI/CD → Variables (Masked + Protected):

- `GITLAB_PYPI_TOKEN` — personal access token with `read_api` on the SDK package group

`NONPROD_AWS_ROLE_ARN` and `PROD_AWS_ROLE_ARN` (used by this agent's deploy/build jobs)
are defined in the **root** `.gitlab-ci.yml` `variables:` block. Override with a project
CI/CD variable of the same name if you prefer not to commit them.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env

# Run locally
uvicorn app:app --host 0.0.0.0 --port 8081
```

## Test

```bash
pytest
```

## Deploy

This agent is a self-contained Terraform stack (its own ECR, secret, IAM role, and
runtime) under `infra/`. Run `ai-foundry deploy` from the **monorepo root** — deploy
provisions the ECR + runtime first (from a bootstrap image), then CI's build job pushes
the real image.

```bash
# Edit infra/envs/dev.tfvars.json if VPC / auth values changed, then:
ai-foundry deploy --agent test_agent --env dev
ai-foundry deploy --agent test_agent --env stage
ai-foundry deploy --agent test_agent --env prod
```

After the first deploy, seed the Portkey secret (`<app>-<env>-test_agent-secret`)
in AWS Secrets Manager.

## Structure

```
test_agent/
├── app.py                              # Agent definition + app entry point
├── pyproject.toml                      # Dependencies
├── Dockerfile                          # ARM64 container for AgentCore Runtime
├── .env.example                        # Environment variable reference
├── .gitlab-ci.yml                      # GitLab CI pipeline (deploy + build)
├── tests/
│   └── test_agent.py                   # pytest smoke tests
└── infra/                              # Self-contained stack (//modules/agent)
    ├── backend.tf
    ├── main.tf
    ├── variables.tf
    ├── outputs.tf
    ├── envs/
    │   ├── dev.tfvars.json             # Dev environment config
    │   ├── stage.tfvars.json           # Stage environment config
    │   └── prod.tfvars.json            # Prod environment config
    └── backend-configs/
        ├── dev.s3.tfbackend            # Dev state bucket (non-prod account)
        ├── stage.s3.tfbackend          # Stage state bucket (non-prod account)
        └── prod.s3.tfbackend           # Prod state bucket (prod account)
```

## Environments

| Environment | AWS Account | Deploy Trigger |
|-------------|-------------|----------------|
| dev | Non-prod | Push to `main` |
| stage | Non-prod | Git tag |
| prod | Prod | Manual approval on tag |

## Infrastructure Config

Edit `infra/envs/<env>.tfvars.json` to configure per-environment infrastructure:

| Field | Required | Description |
|-------|----------|-------------|
| `agent_name` | Yes | Agent identifier (matches folder name) |
| `environment` | Yes | `dev`, `stage`, or `prod` |
| `region` | Yes | AWS region |
| `vpc_private_subnet_ids` | Yes | Private subnet IDs for VPC mode |
| `vpc_security_group_ids` | Yes | Security group IDs |
| `memory_enabled` | No | Enable AgentCore Memory (default: `false`) |
| `memory_expiry_days` | No | Memory TTL in days (default: `30`) |
| `auth_protocol` | No | Inbound auth protocol (default: `A2A`) |
| `jwt_discovery_url` | No | OIDC discovery URL for JWT auth |
| `jwt_audiences` | No | Accepted JWT audiences |
| `request_header_allowlist` | No | HTTP headers forwarded to agent (default: `["Authorization"]`) |
| `log_retention_days` | No | CloudWatch log retention (default: `14`) |
| `environment_variables` | No | Runtime env vars (Portkey, telemetry, etc.) |
| `tags` | No | AWS resource tags |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AGENT_SECRET_NAME` | Yes | Shared AWS Secrets Manager secret (Portkey key + optional DD/Amplitude/Confident keys). Legacy `PORTKEY_SECRET_NAME` still accepted |
| `PORTKEY_BASE_URL` | No | Portkey gateway URL |
| `PORTKEY_MODEL_ID` | No | Default model ID |
| `AGENTCORE_RUNTIME_URL` | No | Runtime URL for agent card |
| `ALLOWED_AD_GROUPS` | Yes | Comma-separated Entra ID group object-IDs for RBAC |
| `LOG_LEVEL` | No | Logging level (default: `INFO`) |

## Portkey Runtime Configurability

The SDK routes every LLM call through the Portkey gateway and stamps **three
platform-governed metadata keys** on each request so cost and usage attribute to
the real caller and the deployment that served it:

- **`_user`** — the caller, from the verified JWT (local part of
  `preferred_username` or `upn`, else `oid`); maps to Portkey's reserved
  analytics key.
- **`environment`** and **`application`** — this deployment's OTEL resource
  (`deployment.environment.name` and the full `service.name`), which the IaC
  renders from your Terraform `otel_tags`.

This is platform-governed — always on, and callers cannot tune or overwrite it.
Keys with no resolvable value are omitted rather than stamped blank. The
standard's `feature`/`request_id`/`session_id` dimensions have no server-side
source; supply them yourself as caller `portkey_options` metadata (below).

`PortkeyConfig` in `app.py` exposes two per-agent knobs:

- **`allow_caller_kwargs`** (default `True`) — whether callers may pass typed
  Portkey options (e.g. `trace_id`, `cache_namespace`, extra `metadata`) with a
  request. Callers supply them in the **request body**, not headers: A2A task
  metadata or AG-UI `forwarded_props`, under a reserved `portkey_options` key.
  Credentials, provider selection, and `debug` stay guarded regardless — an
  attempt to set one fails the request.
- **`debug_logging`** (default `False`) — turns on verbose Portkey gateway/HTTP
  logging with automatic redaction of credentials, bearer tokens, and metadata.
  Leave off in production; a startup warning fires when on.

Neither knob needs a `request_header_allowlist` change: derived attribution is
computed server-side (the `_user` claim from the already-allowlisted
`Authorization` header, `environment`/`application` from the OTEL resource), and
caller options ride the request body — no new headers cross the AgentCore
boundary.
