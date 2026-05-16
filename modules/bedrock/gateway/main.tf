# ── AgentCore Gateway ─────────────────────────────────────────────────────────
resource "aws_bedrockagentcore_gateway" "agentcore" {
  name        = "${var.name}-gateway"
  description = "MCP gateway for ${var.name} — Jira tool integration"
  role_arn    = aws_iam_role.gateway.arn

  authorizer_type = "AWS_IAM"

  protocol_type = "MCP"
  protocol_configuration {
    mcp {
      supported_versions = ["2025-03-26", "2025-06-18", "2025-11-25"]
      search_type        = "SEMANTIC"
      instructions       = var.instructions
    }
  }

  tags = var.tags
}

# ── Jira Tool Lambda ──────────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "jira_tool" {
  name              = "/aws/lambda/${var.name}-jira-tool"
  retention_in_days = 7
  kms_key_id        = var.kms_key_arn
  tags              = var.tags
}

data "archive_file" "jira_tool" {
  type        = "zip"
  source_file = "${path.module}/function/jira_tool.py"
  output_path = "${path.module}/jira_tool.zip"
}

resource "aws_lambda_function" "jira_tool" {
  function_name    = "${var.name}-jira-tool"
  role             = aws_iam_role.jira_lambda.arn
  runtime          = "python3.12"
  handler          = "jira_tool.lambda_handler"
  timeout          = 30
  filename         = data.archive_file.jira_tool.output_path
  source_code_hash = data.archive_file.jira_tool.output_base64sha256

  environment {
    variables = {
      JIRA_BASE_URL    = var.jira_base_url
      JIRA_SECRET_NAME = var.jira_secret_name
      LOG_LEVEL        = "INFO"
    }
  }

  tracing_config {
    mode = "Active"
  }

  tags       = var.tags
  depends_on = [aws_cloudwatch_log_group.jira_tool]
}

# ── Gateway Target: Jira Lambda ───────────────────────────────────────────────
resource "aws_bedrockagentcore_gateway_target" "jira" {
  gateway_identifier = aws_bedrockagentcore_gateway.agentcore.gateway_id
  name               = "jira"
  description        = "Jira ticket management tools via Lambda"

  target_configuration {
    mcp {
      lambda {
        lambda_arn = aws_lambda_function.jira_tool.arn

        tool_schema {

          # ── create_jira_ticket ──────────────────────────────────────────────
          inline_payload {
            name        = "create_jira_ticket"
            description = "Create a new Jira issue/ticket in a given project."

            input_schema {
              type = "object"

              property {
                name        = "project_key"
                type        = "string"
                description = "The Jira project key (e.g. DEVOPS)"
                required    = true
              }

              property {
                name        = "summary"
                type        = "string"
                description = "Short title / summary for the ticket"
                required    = true
              }

              property {
                name        = "description"
                type        = "string"
                description = "Detailed description of the issue"
                required    = false
              }

              property {
                name        = "issue_type"
                type        = "string"
                description = "Issue type: Task, Bug, Story, or Epic"
                required    = false
              }

              property {
                name        = "priority"
                type        = "string"
                description = "Priority: Highest, High, Medium, Low, or Lowest"
                required    = false
              }
            }
          }

          # ── get_jira_ticket ─────────────────────────────────────────────────
          inline_payload {
            name        = "get_jira_ticket"
            description = "Get details of an existing Jira ticket by its key."

            input_schema {
              type = "object"

              property {
                name        = "ticket_key"
                type        = "string"
                description = "The Jira ticket key (e.g. DEVOPS-42)"
                required    = true
              }
            }
          }

          # ── update_jira_ticket ──────────────────────────────────────────────
          inline_payload {
            name        = "update_jira_ticket"
            description = "Update an existing Jira ticket's status, priority, or assignee."

            input_schema {
              type = "object"

              property {
                name        = "ticket_key"
                type        = "string"
                description = "The Jira ticket key (e.g. DEVOPS-42)"
                required    = true
              }

              property {
                name        = "status"
                type        = "string"
                description = "New status to transition the ticket to (e.g. To Do, Blocked, On Hold, In Progress, Validation, Done)"
                required    = false
              }

              property {
                name        = "priority"
                type        = "string"
                description = "New priority: Highest, High, Medium, Low, or Lowest"
                required    = false
              }

              property {
                name        = "assignee_account_id"
                type        = "string"
                description = "Jira account ID of the user to assign the ticket to. Use list_jira_users to find account IDs."
                required    = false
              }

              property {
                name        = "assignee_name"
                type        = "string"
                description = "Full display name of the Jira user to assign the ticket to (e.g. John Franks). The user must exist in Jira."
                required    = false
              }

            }
          }

          # ── list_jira_tickets ───────────────────────────────────────────────
          inline_payload {
            name        = "list_jira_tickets"
            description = "List open Jira tickets in a project, optionally filtered by status."

            input_schema {
              type = "object"

              property {
                name        = "project_key"
                type        = "string"
                description = "The Jira project key (e.g. DEVOPS)"
                required    = true
              }

              property {
                name        = "status"
                type        = "string"
                description = "Filter by status (e.g. To Do, Blocked, On Hold, In Progress, Validation, Done). Defaults to all open tickets."
                required    = false
              }

              property {
                name        = "max_results"
                type        = "string"
                description = "Maximum number of tickets to return (default: 10, max: 50)"
                required    = false
              }
            }
          }

          # ── add_jira_comment ────────────────────────────────────────────────
          inline_payload {
            name        = "add_jira_comment"
            description = "Add a comment to an existing Jira ticket."

            input_schema {
              type = "object"

              property {
                name        = "ticket_key"
                type        = "string"
                description = "The Jira ticket key (e.g. DEVOPS-42)"
                required    = true
              }

              property {
                name        = "comment"
                type        = "string"
                description = "The comment text to add to the ticket"
                required    = true
              }
            }
          }

          # ── list_jira_users ─────────────────────────────────────────────────
          inline_payload {
            name        = "list_jira_users"
            description = "List active human users in the Jira instance. Returns display names, email addresses, and account IDs. Use account IDs with update_jira_ticket to assign tickets."

            input_schema {
              type = "object"

              property {
                name        = "max_results"
                type        = "number"
                description = "Maximum number of users to return (default: 50, max: 200)"
                required    = false
              }
            }
          }

        }

      }
    }
  }

  credential_provider_configuration {
    gateway_iam_role {}
  }
}


## ADD ONS: GitLab Lambda and tools

# ── GitLab Tool Lambda ────────────────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "gitlab_tool" {
  name              = "/aws/lambda/${var.name}-gitlab-tool"
  retention_in_days = 7
  kms_key_id        = var.kms_key_arn
  tags              = var.tags
}

data "archive_file" "gitlab_tool" {
  type        = "zip"
  source_file = "${path.module}/function/gitlab_tool.py"
  output_path = "${path.module}/gitlab_tool.zip"
}

resource "aws_lambda_function" "gitlab_tool" {
  function_name    = "${var.name}-gitlab-tool"
  role             = aws_iam_role.gitlab_lambda.arn
  runtime          = "python3.12"
  handler          = "gitlab_tool.lambda_handler"
  timeout          = 30
  filename         = data.archive_file.gitlab_tool.output_path
  source_code_hash = data.archive_file.gitlab_tool.output_base64sha256

  environment {
    variables = {
      GITLAB_BASE_URL           = var.gitlab_base_url
      GITLAB_SECRET_NAME        = var.gitlab_secret_name
      GITLAB_GROUP_PATH         = var.gitlab_group_path
      GITLAB_TERRAFORM_SUBGROUP = var.gitlab_terraform_subgroup
      GITLAB_GITOPS_SUBGROUP    = var.gitlab_gitops_subgroup
      LOG_LEVEL                 = "INFO"
    }
  }

  tracing_config {
    mode = "Active"
  }

  tags       = var.tags
  depends_on = [aws_cloudwatch_log_group.gitlab_tool]
}

# ── Gateway Target: GitLab Lambda ─────────────────────────────────────────────
resource "aws_bedrockagentcore_gateway_target" "gitlab" {
  gateway_identifier = aws_bedrockagentcore_gateway.agentcore.gateway_id
  name               = "gitlab"
  description        = "GitLab repository and MR management tools via Lambda"

  target_configuration {
    mcp {
      lambda {
        lambda_arn = aws_lambda_function.gitlab_tool.arn

        tool_schema {

          # ── resolve_gitlab_project ──────────────────────────────────────────
          inline_payload {
            name        = "resolve_gitlab_project"
            description = <<-DESC
              Search for a GitLab project by name within the parent group, scoped
              by repo_type. Returns the full project path, project ID, default
              branch, and the resolved repo_type.
              Call this ONCE per task. Cache project_id, default_branch, and
              repo_type — reuse them for every subsequent tool call. Do NOT call
              this tool again within the same task; re-resolution is a workflow
              violation.
              repo_type is REQUIRED:
                - "terraform" for Terragrunt/HCL/AWS infrastructure (S3, RDS, IAM,
                  *.tf, terragrunt.hcl)
                - "gitops" for Kubernetes/Flux/Helm/ArgoCD application manifests
                  (*.yaml, kustomization, HelmRelease)
              Carry the DEFAULT BRANCH forward — use it as ref for all read
              operations and as the base for new branches. Never assume main or
              master.
            DESC

            input_schema {
              type = "object"

              property {
                name        = "project_name"
                type        = "string"
                description = "The short name or partial name of the GitLab project (e.g. 'networking', 'rds-module')"
                required    = true
              }

              property {
                name        = "repo_type"
                type        = "string"
                description = "Either 'terraform' (Terragrunt/HCL infra) or 'gitops' (Kubernetes/Flux/Helm manifests). Required so the tool routes to the correct subgroup."
                required    = true
              }
            }
          }

          # ── read_gitlab_tree ────────────────────────────────────────────────
          inline_payload {
            name        = "read_gitlab_tree"
            description = <<-DESC
              List the directory tree of a GitLab project at a given path and ref.
              ALWAYS pass the DEFAULT BRANCH returned by resolve_gitlab_project as ref.
              Read each path AT MOST ONCE per task. The tool will refuse a second
              read of the same path and instruct you to advance the workflow.
              Maximum two tree reads per task: one on root, one on the target
              env/app directory.
              If this tool returns a 404 or 'does not exist' for a path, STOP trying
              that path entirely. Do NOT retry it. Do NOT try variations of it.
              Move on immediately to read_gitlab_file (the exemplar).
            DESC

            input_schema {
              type = "object"

              property {
                name        = "project_id"
                type        = "number"
                description = "The GitLab numeric project ID (from resolve_gitlab_project)"
                required    = true
              }

              property {
                name        = "path"
                type        = "string"
                description = "Directory path within the repo to list (empty string for root)"
                required    = false
              }

              property {
                name        = "ref"
                type        = "string"
                description = "Branch or commit ref to read from (default: main)"
                required    = false
              }
            }
          }

          # ── read_gitlab_file ────────────────────────────────────────────────
          inline_payload {
            name        = "read_gitlab_file"
            description = <<-DESC
              Read the raw content of a file in a GitLab repository. ALWAYS pass
              the DEFAULT BRANCH returned by resolve_gitlab_project as ref when
              reading exemplar files — never the feature branch, which has no
              commits yet.
              Read each file AT MOST ONCE per task. The tool will refuse a second
              read of the same file and instruct you to advance the workflow.
              You only need ONE exemplar — do not browse for more.
            DESC

            input_schema {
              type = "object"

              property {
                name        = "project_id"
                type        = "number"
                description = "The GitLab numeric project ID (from resolve_gitlab_project)"
                required    = true
              }

              property {
                name        = "file_path"
                type        = "string"
                description = "The full file path within the repo (e.g. 'environments/prod/s3/main-bucket/terragrunt.hcl')"
                required    = true
              }

              property {
                name        = "ref"
                type        = "string"
                description = "Branch or commit ref to read from (default: main)"
                required    = false
              }
            }
          }

          # ── create_gitlab_branch ────────────────────────────────────────────
          inline_payload {
            name        = "create_gitlab_branch"
            description = "Create a new branch in a GitLab project. Branch name must follow the convention: feat/JIRA-KEY, fix/JIRA-KEY, or chore/JIRA-KEY. Pass the DEFAULT BRANCH from resolve_gitlab_project as ref — never assume main or master."

            input_schema {
              type = "object"

              property {
                name        = "project_id"
                type        = "number"
                description = "The GitLab numeric project ID (from resolve_gitlab_project)"
                required    = true
              }

              property {
                name        = "branch_name"
                type        = "string"
                description = "The branch name to create (e.g. feat/DEVOPS-42, fix/DEVOPS-15)"
                required    = true
              }

              property {
                name        = "ref"
                type        = "string"
                description = "The branch or commit to branch from (default: main)"
                required    = false
              }
            }
          }

          # ── commit_gitlab_file ──────────────────────────────────────────────
          inline_payload {
            name        = "commit_gitlab_file"
            description = <<-DESC
              Commit a file to a GitLab repository branch. Use action 'auto' to
              automatically detect whether to create or update the file.
              Content validation is repo-type-aware:
                - terraform repos require a complete, valid terragrunt.hcl modelled
                  on the sibling exemplar (locals, generate "provider", remote_state,
                  inputs). Raw `resource "aws_..."` or `terraform { backend ... }`
                  blocks are rejected.
                - gitops repos require valid Kubernetes/Flux YAML containing
                  apiVersion: and kind: fields, modelled on a sibling manifest.
              Pass the SAME repo_type returned by resolve_gitlab_project. If this
              tool returns an error, surface it to the user immediately — do not
              retry.
            DESC

            input_schema {
              type = "object"

              property {
                name        = "project_id"
                type        = "number"
                description = "The GitLab numeric project ID"
                required    = true
              }

              property {
                name        = "branch_name"
                type        = "string"
                description = "The branch to commit to (should be the feat/fix/chore branch, not main)"
                required    = true
              }

              property {
                name        = "file_path"
                type        = "string"
                description = "The full path of the file to create or update within the repo"
                required    = true
              }

              property {
                name        = "content"
                type        = "string"
                description = "The full content of the file to commit (terragrunt.hcl for terraform, K8s/Flux YAML for gitops)"
                required    = true
              }

              property {
                name        = "commit_message"
                type        = "string"
                description = "Git commit message (e.g. 'feat(DEVOPS-42): add S3 bucket for data lake')"
                required    = true
              }

              property {
                name        = "repo_type"
                type        = "string"
                description = "Either 'terraform' or 'gitops' — must match the value returned by resolve_gitlab_project. Drives content validation."
                required    = true
              }

              property {
                name        = "action"
                type        = "string"
                description = "File action: 'create', 'update', or 'auto' (default: auto)"
                required    = false
              }
            }
          }

          # ── create_gitlab_mr ────────────────────────────────────────────────
          inline_payload {
            name        = "create_gitlab_mr"
            description = "Open a Draft Merge Request in GitLab from a feature branch into the default branch. ONLY call this AFTER commit_gitlab_file has succeeded and returned a commit SHA. Never create an MR before the file is committed — an MR with no commits is invalid. Always creates as Draft. Include the Jira key so the MR is traceable. If this tool returns a FATAL ERROR, do not retry from any earlier step — proceed directly to commenting on the Jira ticket and replying to the user."

            input_schema {
              type = "object"

              property {
                name        = "project_id"
                type        = "number"
                description = "The GitLab numeric project ID"
                required    = true
              }

              property {
                name        = "branch_name"
                type        = "string"
                description = "The source branch for the MR (e.g. feat/DEVOPS-42)"
                required    = true
              }

              property {
                name        = "target_branch"
                type        = "string"
                description = "The target branch to merge into (typically main or master)"
                required    = true
              }

              property {
                name        = "title"
                type        = "string"
                description = "MR title summarising the infrastructure change"
                required    = true
              }

              property {
                name        = "description"
                type        = "string"
                description = "MR description with context about the change"
                required    = false
              }

              property {
                name        = "jira_key"
                type        = "string"
                description = "The Jira ticket key to include in the MR description for traceability (e.g. DEVOPS-42)"
                required    = false
              }
            }
          }

        }
      }
    }
  }

  credential_provider_configuration {
    gateway_iam_role {}
  }
}
