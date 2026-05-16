# terragrunt.hcl

terraform {
  source = "tfr:///terraform-aws-modules/vpc/aws//modules/vpc-endpoints?version=6.6.1"
}

dependency "security_groups" {
  config_path = "../security_groups"
}

dependency "vpc" {
  config_path = "../vpc"
}

inputs = {

  vpc_id             = dependency.vpc.outputs.vpc_id
  security_group_ids = [dependency.security_groups.outputs.endpoints_security_group_id]
  subnet_ids         = dependency.vpc.outputs.private_subnets

  endpoints = {
    ecr_api = {
      service             = "ecr.api"
      private_dns_enabled = true
      tags                = { Name = "ecr-api-endpoint" }
    }
    ecr_dkr = {
      service             = "ecr.dkr"
      private_dns_enabled = true
      tags                = { Name = "ecr-dkr-endpoint" }
    }
    bedrock_runtime = {
      service             = "bedrock-runtime"
      private_dns_enabled = true
      tags                = { Name = "bedrock-runtime-endpoint" }
    }
    bedrock_agentcore = {
      service             = "bedrock-agentcore"
      private_dns_enabled = true
      tags                = { Name = "bedrock-agentcore-endpoint" }
    }
    bedrock_agentcore_gateway = {
      service_name        = "com.amazonaws.us-east-1.bedrock-agentcore.gateway"
      private_dns_enabled = true
      tags                = { Name = "bedrock-agentcore-gateway-endpoint" }
    }
    secretsmanager = {
      service             = "secretsmanager"
      private_dns_enabled = true
      tags                = { Name = "secretsmanager-endpoint" }
    }
    logs = {
      service             = "logs"
      private_dns_enabled = true
      tags                = { Name = "logs-endpoint" }
    }
    sqs = {
      service             = "sqs"
      private_dns_enabled = true
      tags                = { Name = "sqs-endpoint" }
    }
  }

  tags = {
    Project     = "agentcore"
    Environment = "prod"
    ManagedBy   = "terragrunt"
  }
}
