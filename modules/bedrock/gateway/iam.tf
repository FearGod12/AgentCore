# ── Gateway Execution Role ────────────────────────────────────────────────────
resource "aws_iam_role" "gateway" {
  name        = "${var.name}-gateway-execution-role"
  description = "IAM execution role assumed by AgentCore Gateway"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "GatewayAssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "bedrock-agentcore.amazonaws.com"
      }
      Action = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
        ArnLike = {
          "aws:SourceArn" = "arn:aws:bedrock-agentcore:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:*"
        }
      }
    }]
  })

  tags = var.tags
}

# ── Grant the AgentCore Runtime execution role access to invoke this gateway ──
resource "aws_iam_policy" "gateway_invoke" {
  name        = "${var.name}-gateway-invoke"
  description = "Allow AgentCore Runtime to invoke the Gateway and call tools"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "InvokeAgentCoreGateway"
      Effect = "Allow"
      Action = [
        "bedrock-agentcore:InvokeGateway",
        "bedrock-agentcore:CallTool",
      ]
      Resource = [
        aws_bedrockagentcore_gateway.agentcore.gateway_arn
      ]
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "gateway_invoke" {
  role       = var.execution_role_name
  policy_arn = aws_iam_policy.gateway_invoke.arn
}

# ── Jira Lambda execution role ────────────────────────────────────────────────
resource "aws_iam_role" "jira_lambda" {
  name        = "${var.name}-jira-lambda-role"
  description = "IAM role for the Jira tool Lambda function"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

# ── Gateway: Lambda invoke permission ─────────────────────────────────────────
resource "aws_iam_role_policy" "gateway_jira_lambda_invoke" {
  name = "${var.name}-gateway-jira-lambda-invoke"
  role = aws_iam_role.gateway.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "InvokeJiraToolLambda"
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = [aws_lambda_function.jira_tool.arn]
    }]
  })
}

resource "aws_iam_role_policy" "jira_lambda_logs" {
  name = "${var.name}-jira-lambda-logs"
  role = aws_iam_role.jira_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = [
          "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.name}-jira-tool:*"
        ]
      },
      {
        Sid    = "KMSLogsEncryption"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey",
        ]
        Resource = [var.kms_key_arn]
      }
    ]
  })
}

resource "aws_iam_role_policy" "jira_lambda_secrets" {
  name = "${var.name}-jira-lambda-secrets"
  role = aws_iam_role.jira_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ReadJiraApiToken"
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        "arn:aws:secretsmanager:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:secret:${var.name}/jira-api-token*"
      ]
    }]
  })
}

# ── Allow Gateway to invoke the Lambda ───────────────────────────────────────
resource "aws_lambda_permission" "gateway_invoke_jira" {
  statement_id   = "AllowGatewayInvoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.jira_tool.function_name
  principal      = "bedrock-agentcore.amazonaws.com"
  source_account = data.aws_caller_identity.current.account_id
  source_arn     = aws_bedrockagentcore_gateway.agentcore.gateway_arn
}

resource "aws_kms_grant" "jira_lambda_logs" {
  name              = "${var.name}-jira-lambda-logs"
  key_id            = var.kms_key_arn
  grantee_principal = aws_iam_role.jira_lambda.arn

  operations = [
    "Decrypt",
    "GenerateDataKey",
    "DescribeKey",
  ]
}

resource "aws_iam_role_policy" "jira_lambda_xray" {
  name = "${var.name}-jira-lambda-xray"
  role = aws_iam_role.jira_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "XRayTracing"
      Effect = "Allow"
      Action = [
        "xray:PutTraceSegments",
        "xray:PutTelemetryRecords",
      ]
      Resource = ["*"]
    }]
  })
}



### GITLAB ADD ON


# ── GitLab Lambda execution role ──────────────────────────────────────────────
resource "aws_iam_role" "gitlab_lambda" {
  name        = "${var.name}-gitlab-lambda-role"
  description = "IAM role for the GitLab tool Lambda function"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

# ── Allow Gateway to invoke the GitLab Lambda ─────────────────────────────────
resource "aws_iam_role_policy" "gateway_gitlab_lambda_invoke" {
  name = "${var.name}-gateway-gitlab-lambda-invoke"
  role = aws_iam_role.gateway.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "InvokeGitlabToolLambda"
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = [aws_lambda_function.gitlab_tool.arn]
    }]
  })
}

resource "aws_iam_role_policy" "gitlab_lambda_logs" {
  name = "${var.name}-gitlab-lambda-logs"
  role = aws_iam_role.gitlab_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = [
          "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.name}-gitlab-tool:*"
        ]
      },
      {
        Sid    = "KMSLogsEncryption"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey",
        ]
        Resource = [var.kms_key_arn]
      }
    ]
  })
}

resource "aws_iam_role_policy" "gitlab_lambda_secrets" {
  name = "${var.name}-gitlab-lambda-secrets"
  role = aws_iam_role.gitlab_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ReadGitlabApiToken"
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        "arn:aws:secretsmanager:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:secret:${var.name}/gitlab-api-token*"
      ]
    }]
  })
}

resource "aws_lambda_permission" "gateway_invoke_gitlab" {
  statement_id   = "AllowGatewayInvokeGitlab"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.gitlab_tool.function_name
  principal      = "bedrock-agentcore.amazonaws.com"
  source_account = data.aws_caller_identity.current.account_id
  source_arn     = aws_bedrockagentcore_gateway.agentcore.gateway_arn
}

resource "aws_kms_grant" "gitlab_lambda_logs" {
  name              = "${var.name}-gitlab-lambda-logs"
  key_id            = var.kms_key_arn
  grantee_principal = aws_iam_role.gitlab_lambda.arn

  operations = [
    "Decrypt",
    "GenerateDataKey",
    "DescribeKey",
  ]
}

resource "aws_iam_role_policy" "gitlab_lambda_xray" {
  name = "${var.name}-gitlab-lambda-xray"
  role = aws_iam_role.gitlab_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "XRayTracing"
      Effect = "Allow"
      Action = [
        "xray:PutTraceSegments",
        "xray:PutTelemetryRecords",
      ]
      Resource = ["*"]
    }]
  })
}
