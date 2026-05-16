variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "name" {
  description = "Name prefix — must match the value used in base/"
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN for CloudWatch log encryption (output from base/)"
  type        = string
}

variable "ecr_repository_url" {
  description = "Full ECR repository URL (output from base/)"
  type        = string
}

variable "image_tag" {
  description = "Docker image tag to deploy (e.g. 'latest' or a git SHA)"
  type        = string
}

variable "execution_role_arn" {
  description = "IAM execution role ARN (output from base/)"
  type        = string
}

variable "subnet_ids" {
  description = "Private subnet IDs for the AgentCore runtime"
  type        = list(string)

  validation {
    condition     = length(var.subnet_ids) >= 1
    error_message = "At least one subnet ID must be provided."
  }
}

variable "security_group_ids" {
  description = "Security group IDs for the AgentCore runtime"
  type        = list(string)

  validation {
    condition     = length(var.security_group_ids) >= 1
    error_message = "At least one security group ID must be provided."
  }
}

variable "model_id" {
  description = "The ID of the Bedrock model to use"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "gateway_endpoint" {
  description = "AgentCore Gateway MCP endpoint URL (output from gateway module)"
  type        = string
  default     = ""
}

variable "execution_role_name" {
  description = "IAM execution role name (output from base/)"
  type        = string
}

variable "runtime_name" {
  description = "Name for the AgentCore runtime. Must match ^[a-zA-Z][a-zA-Z0-9_]{0,46}$"
  type        = string
  default     = null

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9_]{0,46}$", var.runtime_name))
    error_message = "runtime_name must start with a letter, contain only letters, numbers, or underscores, and be at most 47 characters."
  }
}
