output "kms_key_arn" {
  description = "KMS key ARN for AgentCore ECR and CloudWatch logs"
  value       = aws_kms_key.agentcore.arn
}

output "kms_key_id" {
  description = "KMS key ID for AgentCore ECR and CloudWatch logs"
  value       = aws_kms_key.agentcore.id
}

output "execution_role_arn" {
  description = "IAM execution role ARN for AgentCore runtime"
  value       = aws_iam_role.agentcore_execution.arn
}

output "execution_role_name" {
  description = "IAM execution role name for AgentCore runtime (for use in Bedrock agent definition)"
  value       = aws_iam_role.agentcore_execution.name
}

output "ecr_repository_url" {
  description = "ECR repository URL for the AgentCore runtime image"
  value       = aws_ecr_repository.runtime.repository_url
}
