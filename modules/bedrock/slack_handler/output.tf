output "api_endpoint" {
  description = "API Gateway invoke URL — paste into Slack Event Subscriptions"
  value       = "${aws_apigatewayv2_stage.default.invoke_url}/slack/events"
}

output "sqs_queue_arn" {
  description = "ARN of the SQS queue — wired into lambda_invoker"
  value       = aws_sqs_queue.slack_jobs.arn
}

output "sqs_queue_url" {
  description = "URL of the SQS queue"
  value       = aws_sqs_queue.slack_jobs.url
}
