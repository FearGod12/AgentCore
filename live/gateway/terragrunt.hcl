terraform {
  source = "../../modules/bedrock/gateway"
}

dependency "base" {
  config_path = "../base"
}

inputs = {
  name                = "agentcore"
  aws_region          = "us-east-1"
  execution_role_name = dependency.base.outputs.execution_role_name
  kms_key_arn         = dependency.base.outputs.kms_key_arn
  jira_base_url             = "https://wavlengt.atlassian.net"
  jira_secret_name          = "agentcore/jira-api-token"
  gitlab_base_url           = "https://gitlab.com"
  gitlab_secret_name        = "agentcore/gitlab-api-token"

  # Parent group — must NOT include the trailing /terraform or /gitops segment.
  # The Lambda appends the correct subgroup based on the repo_type passed by
  # the agent at resolve_gitlab_project time.
  gitlab_group_path         = "audasity-inc/devops"
  gitlab_terraform_subgroup = "terraform"
  # TODO: confirm the actual GitOps subgroup name with the team and update.
  gitlab_gitops_subgroup    = "gitops"

  tags = {
    Project     = "agentcore-initiative"
    Environment = "dev"
    ManagedBy   = "terragrunt"
  }
}
