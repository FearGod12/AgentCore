variable "name" {
  description = "The name of the Slack handler"
  type        = string
}

variable "aws_region" {
  description = "The AWS region where the Slack handler will be deployed"
  type        = string
}

variable "kms_key_arn" {
  description = "The ARN of the KMS key used to encrypt the Slack handler's secrets"
  type        = string
}

variable "kms_key_id" {
  description = "The ID of the KMS key used to encrypt the Slack handler's secrets"
  type        = string
}

variable "tags" {
  description = "A map of tags to assign to the Slack handler"
  type        = map(string)
}
