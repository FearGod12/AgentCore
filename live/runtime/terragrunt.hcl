terraform {
  source = "../../modules/bedrock/runtime"
}

dependency "base" {
  config_path = "../base"
}

dependency "security_groups" {
  config_path = "../security_groups"
}

dependency "gateway" {
  config_path = "../gateway"
}

dependency "vpc" {
  config_path = "../vpc"
}

inputs = {
  name                = "agentcore"
  runtime_name        = "agentcore_runtime"
  aws_region          = "us-east-1"
  kms_key_arn         = dependency.base.outputs.kms_key_arn
  execution_role_arn  = dependency.base.outputs.execution_role_arn
  execution_role_name = dependency.base.outputs.execution_role_name
  ecr_repository_url  = dependency.base.outputs.ecr_repository_url
  image_tag           = "v1.0.0"
  subnet_ids          = dependency.vpc.outputs.private_subnets
  security_group_ids  = [dependency.security_groups.outputs.agentcore_security_group_id]
  # MODEL_ID = "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0"]
  model_id         = "us.anthropic.claude-opus-4-6-v1"
  gateway_endpoint = dependency.gateway.outputs.gateway_endpoint

  tags = {
    Project     = "agentcore-initiative"
    Environment = "dev"
    ManagedBy   = "terragrunt"
  }
}
