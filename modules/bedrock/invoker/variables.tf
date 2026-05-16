variable "name" {
  description = "Base name for the Lambda function and related resources"
  type = string
}

variable "aws_region" {
  description = "AWS region to deploy the Lambda function"
  type = string
}

variable "subnet_ids" {
  description = "List of private subnet IDs for the Lambda function"
  type = list(string)
}

variable "security_group_ids" {
  description = "List of security group IDs for the Lambda function"
  type = list(string)
}

variable "runtime_arn" {
  description = "ARN of the Bedrock AgentCore Runtime to invoke"
  type = string
}

variable "tags" {
  description = "Tags to apply to resources"
  type    = map(string)
  default = {}
}

variable "sqs_queue_arn" {
  description = "ARN of the SQS queue that triggers this Lambda"
  type        = string
}

variable "slack_bot_token_secret_id" {
  description = "Secrets Manager secret ID for the Slack bot token"
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN for SQS decryption"
  type        = string
}
