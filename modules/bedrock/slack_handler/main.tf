data "aws_caller_identity" "current" {}

locals {
  powertools_layer_arn = "arn:aws:lambda:${var.aws_region}:017000801446:layer:AWSLambdaPowertoolsPythonV3-python312-x86_64:7"
}

resource "aws_apigatewayv2_api" "slack" {
  name          = "${var.name}-slack-api"
  protocol_type = "HTTP"
  tags          = var.tags
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.slack.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_apigatewayv2_integration" "slack" {
  api_id                 = aws_apigatewayv2_api.slack.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.slack_handler.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "slack_events" {
  api_id    = aws_apigatewayv2_api.slack.id
  route_key = "POST /slack/events"
  target    = "integrations/${aws_apigatewayv2_integration.slack.id}"
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGWInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.slack_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.slack.execution_arn}/*/*"
}

resource "aws_sqs_queue" "slack_jobs" {
  name                        = "${var.name}-slack-jobs.fifo"
  fifo_queue                  = true
  content_based_deduplication = true
  visibility_timeout_seconds  = 900
  message_retention_seconds   = 3600
  kms_master_key_id           = var.kms_key_id
  tags                        = var.tags
}

resource "aws_iam_role" "slack_handler" {
  name = "${var.name}-slack-handler-role"
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

resource "aws_iam_policy" "slack_handler" {
  name = "${var.name}-slack-handler-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "SQSSend"
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = [aws_sqs_queue.slack_jobs.arn]
      },
      {
        Sid    = "SecretsRead"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = [
          "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.name}/slack-*"
        ]
      },
      {
        Sid      = "KMSDecrypt"
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:GenerateDataKey"]
        Resource = [var.kms_key_arn]
      },
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.name}-slack-handler:*"]
      },
      {
        Sid    = "XRayTracing"
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
        ]
        Resource = ["*"]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "slack_handler" {
  role       = aws_iam_role.slack_handler.name
  policy_arn = aws_iam_policy.slack_handler.arn
}

data "archive_file" "slack_handler" {
  type        = "zip"
  source_file = "${path.module}/function/slack_handler.py"
  output_path = "${path.module}/slack_handler.zip"
}

resource "aws_lambda_function" "slack_handler" {
  function_name    = "${var.name}-slack-handler"
  role             = aws_iam_role.slack_handler.arn
  runtime          = "python3.12"
  handler          = "slack_handler.lambda_handler"
  timeout          = 5
  filename         = data.archive_file.slack_handler.output_path
  source_code_hash = data.archive_file.slack_handler.output_base64sha256
  layers           = [local.powertools_layer_arn]

  environment {
    variables = {
      SQS_QUEUE_URL           = aws_sqs_queue.slack_jobs.url
      SLACK_SIGNING_SECRET_ID = "${var.name}/slack-signing-secret"
      AWS_REGION_NAME         = var.aws_region
      POWERTOOLS_SERVICE_NAME = "slack-handler"
      LOG_LEVEL               = "INFO"
    }
  }

  tracing_config {
    mode = "Active"
  }

  tags       = var.tags
  depends_on = [aws_cloudwatch_log_group.slack_handler]
}

resource "aws_cloudwatch_log_group" "slack_handler" {
  name              = "/aws/lambda/${var.name}-slack-handler"
  retention_in_days = 7
  kms_key_id        = var.kms_key_arn
  tags              = var.tags
}
