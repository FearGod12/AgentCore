output "endpoints_security_group_id" {
  value = aws_security_group.endpoints.id
}

output "agentcore_security_group_id" {
  value = aws_security_group.agentcore.id
}

output "lambda_security_group_id" {
  value = aws_security_group.lambda.id
}
