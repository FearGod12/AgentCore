terraform {
  source = "../../modules/bedrock/security_groups"
}

dependency "vpc" {
  config_path = "../vpc"
}

inputs = {
  name   = "agentcore"
  vpc_id = dependency.vpc.outputs.vpc_id

  tags = {
    Project     = "agentcore"
    Environment = "prod"
    ManagedBy   = "terragrunt"
  }
}