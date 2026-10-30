# test_pmp_agents

Multi-agent monorepo built with the [AI Foundry Platform SDK](https://gitlab.com/syngentagroup/ai-foundry/ai-foundry-platform-sdk).

## Before CI Can Run

Set in Project → Settings → CI/CD → Variables (Masked + Protected):

- `GITLAB_PYPI_TOKEN` — personal access token with `read_api` on the SDK package group

`NONPROD_AWS_ROLE_ARN` and `PROD_AWS_ROLE_ARN` are defined in the root `.gitlab-ci.yml`
`variables:` block. Edit them there, or override with a project CI/CD variable of the same name.
> One or both ARNs were left blank during `init` — fill them in before pushing.

Repo-level checklist (job-token allowlist) is printed by `ai-foundry init`. Per-agent
setup (Portkey secret, Entra ID, AD groups) is printed by `ai-foundry new-agent`.

## Add a New Agent

```bash
ai-foundry new-agent --name "My Agent" --description "What it does"
```

This creates a **self-contained** agent under `agents/<slug>/` (its own ECR, secret,
IAM role, and runtime) and wires its CI include. Nothing is shared between agents.

## Deploy

Each agent owns its Terraform stack. Deploy provisions ECR + runtime first (from a
bootstrap image); CI's build job then pushes the real image.

```bash
ai-foundry deploy --env dev                 # every agent
ai-foundry deploy --agent <slug> --env dev  # one agent
```

## Environments

| Environment | Deploy Trigger |
|-------------|----------------|
| dev | Push to `main` (agent changes) |
| stage | Git tag |
| prod | Manual approval on tag |
