terraform {
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-vpc.git?ref=v6.6.1"
}

inputs = {
  name = "acore"
  cidr = "10.0.0.0/16"

  azs             = ["us-east-1a", "us-east-1b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true
  enable_vpn_gateway = true

  tags = {
    Project     = "agentcore"
    Environment = "prod"
    ManagedBy   = "terragrunt"
  }
}
