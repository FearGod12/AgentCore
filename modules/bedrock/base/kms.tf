resource "aws_kms_key" "agentcore" {
  description             = "KMS key for ${var.name} AgentCore ECR and CloudWatch logs"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  tags                    = var.tags
}

resource "aws_kms_alias" "agentcore" {
  name          = "alias/${var.name}-agentcore"
  target_key_id = aws_kms_key.agentcore.key_id
}

resource "aws_kms_key_policy" "agentcore" {
  key_id = aws_kms_key.agentcore.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnableRootAccess"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowBedrockService"
        Effect = "Allow"
        Principal = {
          Service = [
            "bedrock.amazonaws.com",
            "bedrock-agentcore.amazonaws.com",
          ]
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      },
      {
        Sid    = "AllowCloudWatchLogs"
        Effect = "Allow"
        Principal = {
          Service = "logs.${var.aws_region}.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey",
          "kms:ReEncrypt*",
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:*${var.name}*"
          }
        }
      },
      {
        Sid    = "AllowExecutionRoleDecrypt"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.agentcore_execution.arn
        }
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey",
          "kms:GenerateDataKey",
        ]
        Resource = "*"
      }
    ]
  })
}
