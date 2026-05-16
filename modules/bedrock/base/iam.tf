resource "aws_iam_role" "agentcore_execution" {
  name        = "${var.name}-execution-role"
  description = "IAM execution role assumed by Bedrock AgentCore Runtime"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AgentCoreRuntimeAssumeRole"
        Effect = "Allow"
        Principal = {
          Service = [
            "bedrock-agentcore.amazonaws.com",
            "lambda.amazonaws.com"
          ]
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })

  tags = var.tags
}

# ── Bedrock invoke ──────────────────────────────────
resource "aws_iam_policy" "bedrock_invoke" {
  name        = "${var.name}-bedrock-invoke"
  description = "Allow AgentCore to invoke Bedrock foundation models"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockInvokeModel"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:Converse",
          "bedrock:ConverseStream",
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/*",
          "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/*",
        ]
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "bedrock_invoke" {
  role       = aws_iam_role.agentcore_execution.name
  policy_arn = aws_iam_policy.bedrock_invoke.arn
}

# ── ECR pull ──────────────────────────────────────────────────────────────────
resource "aws_iam_policy" "ecr_pull" {
  name        = "${var.name}-ecr-pull"
  description = "Allow AgentCore to pull container images from ECR"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ECRAuthToken"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = ["*"]
      },
      {
        Sid    = "ECRPullImage"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:DescribeRepositories",
          "ecr:DescribeImages",
        ]
        Resource = [
          "arn:aws:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/*"
        ]
      },
      {
        Sid    = "KMSDecrypt"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey",
          "kms:GenerateDataKey",
        ]
        Resource = [aws_kms_key.agentcore.arn]
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ecr_pull" {
  role       = aws_iam_role.agentcore_execution.name
  policy_arn = aws_iam_policy.ecr_pull.arn
}

# ── CloudWatch Logs ───────────────────────────────────────────────────────────
resource "aws_iam_policy" "cloudwatch_logs" {
  name        = "${var.name}-cloudwatch-logs"
  description = "Allow AgentCore container to write logs to CloudWatch"

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
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
        ]
        Resource = [
          "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock/${var.name}/*",
          "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock/${var.name}/*:*",
        ]
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "cloudwatch_logs" {
  role       = aws_iam_role.agentcore_execution.name
  policy_arn = aws_iam_policy.cloudwatch_logs.arn
}

# ── Secrets Manager ─────────────────────────────────────────────────────
resource "aws_iam_policy" "secrets_read" {
  name        = "${var.name}-secrets-read"
  description = "Allow AgentCore to read Secrets Manager and SSM parameters"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SecretsManagerRead"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
        ]
        Resource = [
          "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.name}/*"
        ]
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "secrets_read" {
  role       = aws_iam_role.agentcore_execution.name
  policy_arn = aws_iam_policy.secrets_read.arn
}
