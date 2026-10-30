provider "aws" {
  region = var.region
}

# Self-contained per-agent stack: this module creates the agent's own ECR
# repo (with a bootstrap image so the runtime can be created before the real
# image is built), Secrets Manager secret, IAM role, log group, and the
# AgentCore runtime. No shared infrastructure and no remote-state reads —
# every value the runtime needs comes from this agent's own tfvars.

module "agent" {
  source  = "gitlab.com/syngentagroup/agentcore-iac/aws//modules/agent"
  version = "~> 2.0"

  application = var.application
  agent_name  = var.agent_name
  environment = var.environment
  region      = var.region
  tags        = var.tags

  vpc_private_subnet_ids = var.vpc_private_subnet_ids
  vpc_security_group_ids = var.vpc_security_group_ids

  auth_protocol            = var.auth_protocol
  jwt_discovery_url        = var.jwt_discovery_url
  jwt_audiences            = var.jwt_audiences
  request_header_allowlist = var.request_header_allowlist

  log_retention_days    = var.log_retention_days
  memory_enabled        = var.memory_enabled
  memory_expiry_days    = var.memory_expiry_days
  environment_variables = var.environment_variables

  additional_iam_statements = var.additional_iam_statements
}
