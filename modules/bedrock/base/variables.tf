variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
}

variable "name" {
  description = "Name used as a prefix for all resource names"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
}
