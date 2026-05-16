output "runtime_id" {
  description = "AgentCore Runtime ID — use this to invoke the runtime"
  value       = aws_bedrockagentcore_agent_runtime.agentcore.agent_runtime_id
}

output "runtime_arn" {
  description = "AgentCore Runtime ARN"
  value       = aws_bedrockagentcore_agent_runtime.agentcore.agent_runtime_arn
}
