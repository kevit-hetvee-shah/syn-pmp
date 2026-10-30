variable "application" {
  type        = string
  description = "Application name — first segment in this agent's resource names."
}

variable "agent_name" {
  type        = string
  description = "Agent name (matches the folder under agents/)."
}

variable "environment" {
  type        = string
  description = "Environment name (dev, stage, prod)."
}

variable "region" {
  type        = string
  description = "AWS region."
}

variable "tags" {
  type        = map(string)
  description = "Resource tags."
  default     = {}
}

variable "vpc_private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for the runtime's VPC network mode."
  default     = []
}

variable "vpc_security_group_ids" {
  type        = list(string)
  description = "Security group IDs for the runtime's VPC network mode."
  default     = []
}

variable "auth_protocol" {
  type        = string
  description = "Inbound auth protocol: A2A, AGUI, HTTP, MCP."
  default     = "A2A"
}

variable "jwt_discovery_url" {
  type        = string
  description = "Entra ID OIDC discovery URL for inbound JWT auth."
  default     = ""
}

variable "jwt_audiences" {
  type        = list(string)
  description = "Accepted JWT audiences (typically your Azure App ID URI)."
  default     = []
}

variable "request_header_allowlist" {
  type        = list(string)
  description = "HTTP headers forwarded to the agent container."
  default     = ["Authorization"]
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch log retention in days."
  default     = 14
}

variable "memory_enabled" {
  type        = bool
  description = "Enable AgentCore Memory."
  default     = false
}

variable "memory_expiry_days" {
  type        = number
  description = "Memory TTL in days."
  default     = 30
}

variable "environment_variables" {
  type        = map(string)
  description = "Runtime environment variables (PORT, LOG_LEVEL, ALLOWED_AD_GROUPS, etc.)."
  default     = {}
}

variable "additional_iam_statements" {
  type = list(object({
    sid       = optional(string)
    effect    = optional(string, "Allow")
    actions   = list(string)
    resources = list(string)
    condition = optional(any)
  }))
  description = "Extra IAM statements appended to the runtime role policy. Use for team-specific grants — e.g. S3 for code-interpreter file I/O (s3:GetObject/PutObject on the bucket + s3:ListBucket), DynamoDB, KMS. The module owns the base policy; this is the supported extension point."
  default     = []
}
