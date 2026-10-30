# AI Foundry project and workflow

This document describes the repository as it exists today and the AI Foundry
Platform SDK workflow used to add, run, and deploy agents. The repository is a
monorepo scaffold with one example agent; most platform behavior comes from the
external `ai-foundry-platform-sdk` package, not from code under `src/`.

## Project at a glance

```text
.
├── .ai-foundry.json             # Monorepo/app and shared environment settings
├── pyproject.toml               # Root CLI dependency and `ai-foundry` entry point
├── src/ai_foundry/__init__.py   # Root package entry point
├── .gitlab-ci.yml               # Shared deploy/build templates and agent includes
└── agents/
    └── data_analyst/             # Self-contained AG-UI agent example
        ├── app.py                # Agent definition and FastAPI app
        ├── tools.py              # Strands tool functions
        ├── tests/                # Endpoint smoke tests
        ├── Dockerfile            # ARM64 AgentCore runtime image
        ├── .gitlab-ci.yml        # Per-agent dev/stage/prod jobs
        └── infra/                # Per-agent Terraform and environment config
```

The root `ai-foundry` Python package is currently just a CLI shim: its console
script delegates to the SDK CLI, while `src/ai_foundry/__init__.py` contains
only a placeholder `main()` function. The root dependency is
`ai-foundry-platform-sdk[cli]>=1.3.1`; `uv.lock` currently resolves SDK 1.3.1.
The agent separately depends on `ai-foundry-platform-sdk[all]`. Do not assume
the SDK implementation itself is in this repository.

## How an agent is defined and served

The example agent is in [agents/data_analyst/app.py](./agents/data_analyst/app.py).
It builds an `AgentDefinition` from:

- A name and description, which identify the agent and populate its advertised
  capability information.
- `ToolDefinition` entries. The example registers a Strands tool from
  [tools.py](./agents/data_analyst/tools.py); the factory supplies it to the
  SDK when a request builds the agent.
- `Skill` declarations. Here this advertises the agent's capability; it is
  not the same thing as an on-disk skill package.
- `AuthConfig`, populated from `ALLOWED_AD_GROUPS`.
- `PortkeyConfig`, which controls whether callers may pass approved per-request
  Portkey options and whether verbose Portkey logging is enabled.

The app is created with `create_agui_app(agent)`. This is the AG-UI protocol
variant, listens on port 8081, and streams AG-UI responses. The SDK manages the
request lifecycle around the definition, including model-provider setup,
authorization, tools, hooks, and cleanup. The agent card and `/ping` health
route are exposed by the generated app and covered by the smoke tests.

The SDK also supports an A2A protocol option in its scaffolder (port 9000).
The selected protocol must be kept consistent across the app factory, runtime
Terraform `auth_protocol`, container port, environment configuration, and
callers. For multi-agent compositions, the SDK exposes managed-agent building
primitives; the current example does not implement a multi-agent graph or
workflow.

### Adding agent behavior

1. Implement tool functions in `tools.py` (or focused modules) and register
   them as `ToolDefinition`s in `app.py`. Use the SDK's provided tool helpers
   for integrations such as code execution or MCP where applicable.
2. Keep the tool's resource requirements explicit. For example, tools that
   need session resources or AWS access require corresponding SDK wiring and
   runtime IAM permissions; a code-interpreter S3 bucket needs S3 grants and a
   runtime environment variable as well as a tool in the agent definition.
3. Use `Skill` for advertised agent-card capabilities. Use the SDK's
   `SkillPackage`/`skill_packages` mechanism for on-disk `SKILL.md` packages
   loaded by the model; these are distinct concepts.
4. Add or update tests under `agents/<slug>/tests/`. The example checks the
   health route and the agent-card route with FastAPI's `TestClient`.
5. Keep credentials out of source, `.env.example`, and committed Terraform
   variables. Provide them via local environment or the per-agent AWS secret.

## SDK CLI workflow

Run these commands from the monorepo root. The CLI is installed with the root
project dependency; `uv run` runs it in the project's environment.

```bash
# See options and commands
uv run ai-foundry --help

# Initialize a monorepo (already initialized in this repository)
uv run ai-foundry init --help

# Scaffold an agent into agents/<slug>/
uv run ai-foundry new-agent \
  --name "My Agent" \
  --description "What the agent does" \
  --protocol agui \
  --with-tools \
  --with-memory

# Provision one agent or every agent in agents/ that has infra/main.tf
uv run ai-foundry deploy --agent my_agent --env dev
uv run ai-foundry deploy --env dev
```

`init` creates the monorepo configuration and shared CI chassis. It collects
the application name, AWS region, account/role information, state buckets,
VPC details, and JWT audiences. `new-agent` uses `.ai-foundry.json` to scaffold
a separate agent directory with its app, dependency manifest, Dockerfile,
tests, Terraform files, environment configs, and per-agent GitLab CI. It also
adds that CI file to the root `include` list when the include marker exists.
Scaffolding options include A2A vs AG-UI, starter tools, memory, skills, and
Portkey request/debug settings.

`deploy` checks for `.ai-foundry.json`, Terraform, the selected agent's
`infra/main.tf`, environment tfvars, and backend config. It runs Terraform
`init`, `plan`, and `apply`, then prints Terraform outputs. Without `--agent`,
it deploys all agent directories with an `infra/main.tf`. It provisions
infrastructure; it does not build/push the application image. The default is
interactive approval; `--auto-approve` is used by CI.

## Per-agent infrastructure and release flow

Each agent owns an independent Terraform stack under
`agents/<slug>/infra/`. In this repository, `main.tf` calls the
`agentcore-iac` Terraform Registry module (`modules/agent`, version `~> 2.0`).
That module owns the agent's ECR repository, bootstrap image, Secrets Manager
secret, IAM role, CloudWatch log group, and AgentCore runtime. Agent stacks do
not read shared Terraform state; their runtime configuration is supplied by
their own tfvars.

- `infra/envs/{dev,stage,prod}.tfvars.json` supplies application/agent names,
  region, networking, inbound auth, log retention, memory, runtime environment
  variables, IAM extensions, and tags.
- `infra/backend-configs/*.s3.tfbackend` selects the S3 state bucket and
  distinct state key per environment and agent. State locking is enabled with
  `use_lockfile = true`.
- `infra/variables.tf` exposes the module inputs, including
  `additional_iam_statements` as the supported extension point for least-
  privilege service access such as S3.
- `infra/outputs.tf` exports runtime identifiers, ECR URL, role ARN, secret
  name/ARN, and log-group name.

Deployment deliberately precedes image build. Terraform first creates ECR and
the runtime using the bootstrap image; then CI builds and pushes the real
agent image to the ECR repository. Root CI contains shared job templates, and
the agent CI fragment instantiates per-environment deploy/build jobs:

| Environment | Trigger in this repository | AWS role |
|---|---|---|
| dev | Push to `main` when the agent directory changes; merge-request pipelines are excluded | Non-prod |
| stage | Git tag | Non-prod |
| prod | Manual deploy on a Git tag, followed by build | Prod |

Builds use Docker Buildx for `linux/arm64`, QEMU for cross-compilation, and a
GitLab PyPI token mounted as a Docker build secret to install the private SDK
dependency. Keep `--provenance=false` and `--sbom=false`: this pipeline
documents that AgentCore cannot pull the OCI image index produced otherwise.
The Dockerfile starts the runtime through `ai-foundry-serve`, which hydrates
telemetry keys from Secrets Manager before starting
`opentelemetry-instrument` and Uvicorn. This ordering matters because OTLP
headers are read when telemetry initializes.

## Local development and tests

The agent's [README](./agents/data_analyst/README.md) documents a pip-based
quick start:

```bash
cd agents/data_analyst
pip install -e ".[dev]"
cp .env.example .env
uvicorn app:app --host 0.0.0.0 --port 8081
pytest
```

From the monorepo root, the CLI and its options can be inspected with
`uv run ai-foundry --help`. The current container uses Python 3.12; the agent
manifest requires Python 3.11+ and its Hatch test matrix names Python 3.11.
The root CLI package currently requires Python 3.14+. Keep these separate
runtime requirements in mind when choosing the interpreter for development or
CI.

## Configuration and operational checklist

Before deploying or accepting requests:

1. Fill in AWS account and OIDC role details. `.ai-foundry.json` currently
   contains blank account and role values; the root CI role variables are also
   blank and must be configured or overridden in GitLab CI/CD settings.
2. Configure project CI/CD variable `GITLAB_PYPI_TOKEN` as a masked/protected
   token with `read_api` access to the private SDK package group. Allow this
   repository's GitLab job token to read the `agentcore-iac` Terraform module.
3. Check per-environment VPC subnet/security-group IDs and JWT audiences in
   `infra/envs/*.tfvars.json`; configure allowed Entra ID groups in
   `environment_variables.ALLOWED_AD_GROUPS`.
4. Seed the created agent secret in AWS Secrets Manager with `PORTKEY_API_KEY`
   and any optional telemetry keys (`DD_API_KEY`, `AMPLITUDE_API_KEY`,
   `CONFIDENT_API_KEY`). Do not assume a created secret contains usable
   credentials.
5. Confirm the selected auth protocol matches the app. Inbound authorization
   and allowed-group membership are separate requirements. The SDK documents
   an empty allowed-group list as rejecting all requests; blank JWT audiences
   also need to be resolved for the deployed identity setup.
6. Review the current per-agent `.gitlab-ci.yml` ECR repository URLs. In this
   checkout they begin with `.dkr.ecr...` (no AWS account ID), so they need
   valid account-specific registry URLs before the build can log in and push.
7. Review agent `PortkeyConfig` before production. In the example,
   `debug_logging=True` is enabled although the agent README advises leaving
   verbose logging off in production. Caller options can be disabled when not
   needed; their availability does not permit callers to set credentials or
   select providers.

## Useful platform behaviors and development notes

- Each agent has its own ECR, runtime, secret, IAM role, and state. This
  isolates releases and IAM scope but means shared resources should be
  intentionally modeled rather than assumed.
- The SDK applies platform-governed Portkey analytics attribution: `_user`
  from the verified caller JWT plus `environment` and `application` from OTEL
  resource attributes. These are server-derived. Caller-provided request-body
  `portkey_options` can carry additional trace/cache/metadata dimensions when
  enabled.
- The example's model-preset header is explicitly allowlisted at the runtime
  boundary. If adding a request header, verify both the Terraform
  `request_header_allowlist` and how the SDK/application consumes it.
- Keep environment-specific configuration in the agent's tfvars and use
  `additional_iam_statements` for narrowly scoped AWS permissions. Avoid
  embedding secrets or broad permissions in the repository.
- A scaffolded `infra/envs` file is a starting point, not proof that the
  account, network, auth, secret, or CI values are valid. Review each
  environment before running `deploy`.
