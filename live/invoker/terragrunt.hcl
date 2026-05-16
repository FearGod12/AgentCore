terraform {
  source = "../../modules/bedrock/invoker"
}

dependency "runtime" {
  config_path = "../runtime"
}

dependency "slack_handler" {
  config_path = "../slack_handler"
}

dependency "security_groups" {
  config_path = "../security_groups"
}

dependency "base" {
  config_path = "../base"
}

dependency "vpc" {
  config_path = "../vpc"
}

inputs = {
  name                      = "agentcore"
  aws_region                = "us-east-1"
  subnet_ids                = dependency.vpc.outputs.private_subnets
  security_group_ids        = [dependency.security_groups.outputs.lambda_security_group_id]
  runtime_arn         = dependency.runtime.outputs.runtime_arn
  sqs_queue_arn             = dependency.slack_handler.outputs.sqs_queue_arn
  slack_bot_token_secret_id = "agentcore/slack-bot-token"
  kms_key_arn               = dependency.base.outputs.kms_key_arn

  tags = {
    Project     = "agentcore"
    Environment = "prod"
    ManagedBy   = "terragrunt"
  }
}