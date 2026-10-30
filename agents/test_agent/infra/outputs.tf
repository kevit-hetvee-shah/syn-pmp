output "runtime_id" {
  description = "AgentCore runtime ID."
  value       = module.agent.runtime_id
}

output "runtime_arn" {
  description = "AgentCore runtime ARN."
  value       = module.agent.runtime_arn
}

output "runtime_name" {
  description = "AgentCore runtime name."
  value       = module.agent.runtime_name
}

output "runtime_role_arn" {
  description = "IAM role assumed by the runtime."
  value       = module.agent.runtime_role_arn
}

output "ecr_repo_url" {
  description = "ECR repository URL the CI build pushes to."
  value       = module.agent.ecr_repository_url
}

output "secret_arn" {
  description = "Secrets Manager ARN for this agent."
  value       = module.agent.secret_arn
}

output "secret_name" {
  description = "Secrets Manager secret name for this agent."
  value       = module.agent.secret_name
}

output "log_group_name" {
  description = "CloudWatch log group for the runtime."
  value       = module.agent.log_group_name
}
