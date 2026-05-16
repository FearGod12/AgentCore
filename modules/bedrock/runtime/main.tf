resource "aws_bedrockagentcore_agent_runtime" "agentcore" {
  agent_runtime_name = var.runtime_name
  role_arn           = var.execution_role_arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = "${var.ecr_repository_url}:${var.image_tag}"
    }
  }

  network_configuration {
    network_mode = "VPC"
    network_mode_config {
      security_groups = var.security_group_ids
      subnets         = var.subnet_ids
    }
  }

  environment_variables = {
    MODEL_ID         = var.model_id
    AWS_REGION       = var.aws_region
    GATEWAY_ENDPOINT = var.gateway_endpoint
  }

  lifecycle_configuration {
    idle_runtime_session_timeout = 900  # 15 mins
    max_lifetime                 = 7200 # 2 hours
  }

}

resource "aws_cloudwatch_log_group" "agentcore" {
  name              = "/aws/bedrock/${var.name}"
  retention_in_days = 30
  kms_key_id        = var.kms_key_arn
  tags              = var.tags
}

resource "aws_iam_policy" "agentcore_control" {
  name = "${var.name}-agentcore-control"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "AgentCoreRuntimeControl"
      Effect   = "Allow"
      Action   = ["bedrock-agentcore:*"]
      Resource = [aws_bedrockagentcore_agent_runtime.agentcore.agent_runtime_arn]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "agentcore_control" {
  role       = var.execution_role_name
  policy_arn = aws_iam_policy.agentcore_control.arn
}
