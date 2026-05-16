variable "name" {
  description = "The name for the security groups"
  type        = string
}

variable "vpc_id" {
  description = "The VPC ID"
  type        = string
}

variable "aws_region" {
  description = "AWS region to deploy resources in"
  type        = string
  default     = "us-east-1"
}

variable "tags" {
  type    = map(string)
  default = {}
}
