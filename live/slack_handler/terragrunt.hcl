terraform {
  source = "../../modules/bedrock/slack_handler"
}

dependency "base" {
  config_path = "../base"
}

inputs = {
  name        = "agentcore"
  aws_region  = "us-east-1"
  kms_key_arn = dependency.base.outputs.kms_key_arn
  kms_key_id  = dependency.base.outputs.kms_key_id

  tags = {
    Project     = "agentcore-initiative"
    Environment = "dev"
    ManagedBy   = "terragrunt"
  }
}
