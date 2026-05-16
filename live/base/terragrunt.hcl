terraform {
  source = "../../modules/bedrock/base"
}

inputs = {
  name       = "agentcore"
  aws_region = "us-east-1"
  tags = {
    Project     = "agentcore-initiative"
    Environment = "dev"
    ManagedBy   = "terragrunt"
  }
}
