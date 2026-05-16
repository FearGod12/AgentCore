output "gateway_id" {
  description = "AgentCore Gateway identifier"
  value       = aws_bedrockagentcore_gateway.agentcore.gateway_id
}

output "gateway_arn" {
  description = "AgentCore Gateway ARN"
  value       = aws_bedrockagentcore_gateway.agentcore.gateway_arn
}

output "gateway_endpoint" {
  description = "AgentCore Gateway MCP endpoint URL (pass to Runtime as GATEWAY_ENDPOINT)"
  value       = aws_bedrockagentcore_gateway.agentcore.gateway_url
}
