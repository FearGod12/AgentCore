variable "name" {
  description = "Name prefix — must match the value used across modules"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "execution_role_name" {
  description = "AgentCore execution role name (output from base/) — used for policy attachment"
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN for CloudWatch log encryption (from base/ module)"
  type        = string
}

variable "jira_base_url" {
  description = "Jira instance base URL"
  type        = string
}

variable "jira_secret_name" {
  description = "Secrets Manager secret name holding Jira email:token"
  type        = string
}

# ADD ONS

variable "gitlab_base_url" {
  description = "GitLab instance base URL (e.g. https://gitlab.com)"
  type        = string
  default     = "https://gitlab.com"
}

variable "gitlab_secret_name" {
  description = "Secrets Manager secret name holding the GitLab API token"
  type        = string
}

variable "gitlab_group_path" {
  description = "The GitLab parent group path under which terraform and gitops subgroups live (e.g. audasity-inc/devops). Do NOT include the subgroup segment here."
  type        = string
}

variable "gitlab_terraform_subgroup" {
  description = "Subgroup name (under gitlab_group_path) holding Terragrunt/HCL infrastructure projects."
  type        = string
  default     = "terraform"
}

variable "gitlab_gitops_subgroup" {
  description = "Subgroup name (under gitlab_group_path) holding Kubernetes/Flux/Helm GitOps manifests."
  type        = string
  default     = "gitops"
}

# NOTE: keep the rendered instructions ≤ 2000 characters — AgentCore Gateway
# enforces this limit on the protocol_configuration.mcp.instructions field.
variable "instructions" {
  description = "MCP gateway instructions passed to the agent (must stay ≤ 2000 characters)"
  type        = string
  default = <<-EOT
    You are an infrastructure automation agent. Execute the workflow in strict order. Never loop back. Each tool is called the minimum required number of times.

    REPO TYPE — decide before step 2:
    - terraform: Terragrunt/HCL/AWS infra (S3, RDS, IAM, *.tf, terragrunt.hcl)
    - gitops: Kubernetes/Flux/Helm/ArgoCD manifests (*.yaml apps, deployments)
    Pass repo_type to resolve_gitlab_project AND commit_gitlab_file.

    WORKFLOW:
    1. CREATE JIRA TICKET (DEVOPS, Task). Use returned key — never invent one. ticket_already_exists → use existing key, go to 2.
    2. RESOLVE GITLAB PROJECT once with repo_type. Record project_id, default branch, repo_type. Never call this tool again.
    3. DISCOVER: read_gitlab_tree once on root, then once on the target env/app dir. Two calls maximum. Never re-read a path.
    4. READ EXEMPLAR: read_gitlab_file once on a sibling exemplar (terragrunt.hcl or YAML manifest). Do not re-read.
    5. GENERATE the file modelled on the exemplar. terraform → terragrunt.hcl with no raw resource/backend blocks. gitops → valid K8s/Flux YAML with apiVersion and kind.
    6. CREATE BRANCH feat/JIRA-KEY, fix/JIRA-KEY, or chore/JIRA-KEY. branch_already_exists → go to 7.
    7. COMMIT FILE to branch with repo_type set. Use the path discovered from read_gitlab_tree — never assume a path.
    8. OPEN DRAFT MR with jira_key set. On success OR error, go immediately to 9. After this step the only permitted tool call is add_jira_comment.
    9. ADD JIRA COMMENT with branch, commit SHA, and MR URL.
    10. REPLY with Jira URL, branch, file path, commit SHA, MR URL. STOP — no further tool calls.

    RULES:
    - resolve_gitlab_project: step 2 only.
    - create_jira_ticket: step 1 only.
    - read_gitlab_tree / read_gitlab_file: each path/file at most ONCE per task.
    - After step 8, the only permitted tool call is add_jira_comment.
    - FATAL ERROR at any step → skip to 9 then 10.
    - Standalone Jira-only requests (no repo changes) → execute only the relevant Jira tool and reply immediately.
  EOT
}

