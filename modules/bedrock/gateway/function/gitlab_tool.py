"""
GitLab Tool Lambda — AgentCore Gateway MCP Target

Dispatch contract (in priority order):
  1. event["tool"]   — legacy direct invoke, e.g. "gitlab___read_gitlab_tree"
  2. event["name"]   — MCP envelope style, e.g. "read_gitlab_tree"
  3. event["arguments"] dict — MCP envelope, args nested
  4. _infer_tool()   — production fallback (AgentCore Gateway with
                        inline_payload currently delivers raw arguments
                        with no tool metadata)

Supported tools:
  - resolve_gitlab_project  — find a project by name within the configured subgroup
                              (terraform or gitops, selected via `repo_type`)
  - read_gitlab_tree        — list a directory in a project's repository
  - read_gitlab_file        — read the raw content of a file
  - create_gitlab_branch    — create a branch (feat/fix/chore + Jira key)
  - commit_gitlab_file      — create or update a file on a branch (content guard
                              is repo-type aware: blocks raw Terraform in
                              terraform repos, requires K8s/Flux shape in
                              gitops repos)
  - create_gitlab_mr        — open a Draft MR (idempotent — returns existing MR if one exists)
"""
import base64
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

GITLAB_BASE_URL          = os.environ["GITLAB_BASE_URL"].rstrip("/")
GITLAB_SECRET_NAME       = os.environ["GITLAB_SECRET_NAME"]
GITLAB_GROUP_PATH        = os.environ["GITLAB_GROUP_PATH"].strip("/")
GITLAB_TERRAFORM_SUBGROUP = os.environ.get("GITLAB_TERRAFORM_SUBGROUP", "terraform").strip("/")
GITLAB_GITOPS_SUBGROUP    = os.environ.get("GITLAB_GITOPS_SUBGROUP", "gitops").strip("/")

VALID_REPO_TYPES = ("terraform", "gitops")

_sm = boto3.client("secretsmanager")

# ── TTL cache for GitLab token ────────────────────────────────────────────────
_token_cache = {"value": None, "timestamp": 0}
TOKEN_CACHE_TTL_SECONDS = 300

# ── Repeat-read guard (within warm container lifetime) ────────────────────────
# Keyed by (kind, project_id, ref, path). Used to detect the agent re-entering
# the exploration phase and respond with a hard stop instead of more data.
_path_read_log: dict = {}
PATH_REPEAT_TTL = 600  # 10 minutes

# ── Per-project repo_type cache ──────────────────────────────────────────────
# Populated by resolve_gitlab_project so commit_gitlab_file can apply the right
# content guard even if the agent forgets to pass repo_type explicitly.
_project_type_cache: dict = {}
PROJECT_TYPE_TTL = 1800  # 30 minutes


# ── Auth ──────────────────────────────────────────────────────────────────────

def _get_gitlab_token() -> str:
    now = time.time()
    if _token_cache["value"] is None or now - _token_cache["timestamp"] > TOKEN_CACHE_TTL_SECONDS:
        secret = _sm.get_secret_value(SecretId=GITLAB_SECRET_NAME)["SecretString"].strip()
        _token_cache["value"]     = secret
        _token_cache["timestamp"] = now
    return _token_cache["value"]


# ── Generic HTTP helper ───────────────────────────────────────────────────────

def _gitlab_request(method: str, path: str, body: dict | None = None) -> dict | list:
    token = _get_gitlab_token()
    url   = f"{GITLAB_BASE_URL}/api/v4{path}"
    data  = json.dumps(body).encode() if body else None
    req   = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "PRIVATE-TOKEN": token,
            "Content-Type":  "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as e:
        body_str = e.read().decode()
        print(f"GITLAB_HTTP_ERROR: status={e.code} path={path} body={body_str}")
        logger.error("gitlab_http_error", extra={"status": e.code, "body": body_str, "path": path})
        raise RuntimeError(f"GitLab API {e.code}: {body_str}")
    except urllib.error.URLError as e:
        print(f"GITLAB_URL_ERROR: reason={e.reason} path={path}")
        logger.error("gitlab_url_error", extra={"reason": str(e.reason), "path": path})
        raise RuntimeError(f"GitLab connection error: {e.reason}")
    except json.JSONDecodeError as e:
        print(f"GITLAB_JSON_ERROR: error={e} path={path}")
        logger.error("gitlab_json_error", extra={"error": str(e), "path": path})
        raise RuntimeError(f"GitLab returned invalid JSON: {e}")


# ── Response helpers ──────────────────────────────────────────────────────────

def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _error(text: str) -> dict:
    """Retriable error — something transient or recoverable."""
    return {
        "content": [{"type": "text", "text": f"Error: {text} Do not retry this operation."}],
        "isError": True,
    }


def _fatal(text: str) -> dict:
    """Non-retriable error — stop immediately and surface to user."""
    return {
        "content": [{"type": "text", "text": (
            f"FATAL ERROR — stop immediately and report to the user: {text}\n"
            "Do not retry. Do not search for more examples. Do not call any further tools."
        )}],
        "isError": True,
    }


# ── Tool inference fallback ───────────────────────────────────────────────────
#
# Order matters: each rule must use a key signature that is unique to that
# tool given the rules above it. With AgentCore Gateway not injecting a `tool`
# field today, this is the primary dispatch path in production — keep it
# deterministic.

def _infer_tool(event: dict) -> str:
    keys = set(event.keys())

    if "project_name" in keys:
        return "resolve_gitlab_project"

    if "target_branch" in keys or "source_branch" in keys:
        return "create_gitlab_mr"

    if "file_path" in keys and "content" in keys:
        return "commit_gitlab_file"

    if "file_path" in keys:
        return "read_gitlab_file"

    if "branch_name" in keys and "project_id" in keys:
        return "create_gitlab_branch"

    if "project_id" in keys:
        return "read_gitlab_tree"

    return ""


def _resolve_tool_call(event: dict) -> tuple[str, dict]:
    """
    Normalise the AgentCore Gateway → Lambda payload into (tool_name, args).

    Handles three observed shapes:
      - {"tool": "gitlab___read_gitlab_tree", ...args}      (legacy)
      - {"name": "read_gitlab_tree", "arguments": {...}}     (MCP envelope)
      - {...args}                                            (no metadata)
    """
    raw = event.pop("tool", "") or event.pop("name", "") or ""
    tool_name = raw.split("___", 1)[-1] if "___" in raw else raw

    inner = event.pop("arguments", None)
    args  = inner if isinstance(inner, dict) else event

    if not tool_name:
        tool_name = _infer_tool(args)
        source    = "inferred"
    else:
        source = "envelope"

    return tool_name, args, source


# ── Repeat-read guard ────────────────────────────────────────────────────────

def _record_read(kind: str, project_id, ref: str, path: str) -> bool:
    """
    Returns True when the same (kind, project_id, ref, path) has already been
    read within PATH_REPEAT_TTL — indicating the agent is re-entering the
    exploration phase. Always records the timestamp.
    """
    key = (kind, str(project_id), ref or "", path or "")
    now = time.time()
    prev = _path_read_log.get(key)
    _path_read_log[key] = now
    return bool(prev and now - prev < PATH_REPEAT_TTL)


# ── Tool handlers ─────────────────────────────────────────────────────────────

def _subgroup_for(repo_type: str) -> str:
    return GITLAB_TERRAFORM_SUBGROUP if repo_type == "terraform" else GITLAB_GITOPS_SUBGROUP


def _format_project_ok(project: dict, repo_type: str) -> dict:
    return _ok(
        f"Project resolved successfully.\n"
        f"Name: {project['name']}\n"
        f"ID: {project['id']}\n"
        f"Repo type: {repo_type}\n"
        f"Full path: {project['path_with_namespace']}\n"
        f"Default branch: {project['default_branch']}\n"
        f"URL: {project['web_url']}\n\n"
        f"Carry project_id, default_branch, and repo_type through every "
        f"subsequent tool call in this task. Do NOT call resolve_gitlab_project "
        f"again — re-resolution is a workflow violation."
    )


def _resolve_gitlab_project(args: dict) -> dict:
    project_name = (args.get("project_name") or "").strip()
    repo_type    = (args.get("repo_type") or "terraform").strip().lower()

    if not project_name:
        return _fatal("project_name is required.")

    if repo_type not in VALID_REPO_TYPES:
        return _fatal(
            f"Invalid repo_type '{repo_type}'. Must be one of: {', '.join(VALID_REPO_TYPES)}. "
            f"Use 'terraform' for Terragrunt/HCL/AWS infra, 'gitops' for "
            f"Kubernetes/Flux/Helm/ArgoCD manifests."
        )

    subgroup = _subgroup_for(repo_type)

    # First try: direct lookup by full path — most reliable, bypasses search
    candidate_path = f"{GITLAB_GROUP_PATH}/{subgroup}/{project_name}"
    encoded_path   = urllib.parse.quote(candidate_path, safe="")

    print(f"RESOLVE_ATTEMPT_DIRECT: path={candidate_path} repo_type={repo_type}")
    try:
        project = _gitlab_request("GET", f"/projects/{encoded_path}")
        _project_type_cache[project["id"]] = {"repo_type": repo_type, "ts": time.time()}
        logger.info("project_resolved_direct", extra={
            "project_name": project["name"],
            "project_id":   project["id"],
            "repo_type":    repo_type,
        })
        return _format_project_ok(project, repo_type)
    except RuntimeError as e:
        print(f"RESOLVE_DIRECT_FAILED: {e}")

    # Second try: group search API scoped to the chosen subgroup
    scoped_group  = f"{GITLAB_GROUP_PATH}/{subgroup}"
    encoded_group = urllib.parse.quote(scoped_group, safe="")
    encoded_name  = urllib.parse.quote(project_name, safe="")

    print(f"RESOLVE_ATTEMPT_SEARCH: group={scoped_group} name={project_name}")
    try:
        results = _gitlab_request(
            "GET",
            f"/groups/{encoded_group}/projects?search={encoded_name}&include_subgroups=true&per_page=10",
        )
    except RuntimeError as e:
        print(f"RESOLVE_SEARCH_FAILED: {e}")
        return _error(str(e))

    print(f"RESOLVE_SEARCH_RESULTS: count={len(results) if isinstance(results, list) else 'non-list'}")

    if not results:
        return _fatal(
            f"No project found matching '{project_name}' in group '{scoped_group}'. "
            f"Tried direct path '{candidate_path}' and group search. "
            f"Check the project name matches exactly what is in GitLab and that "
            f"repo_type='{repo_type}' is correct."
        )

    exact = [p for p in results if
             p["name"].lower() == project_name.lower() or
             p["path"].lower() == project_name.lower()]
    project = exact[0] if exact else results[0]

    _project_type_cache[project["id"]] = {"repo_type": repo_type, "ts": time.time()}
    logger.info("project_resolved_search", extra={
        "project_name": project["name"],
        "project_id":   project["id"],
        "repo_type":    repo_type,
    })

    return _format_project_ok(project, repo_type)


def _cached_repo_type(project_id) -> str | None:
    entry = _project_type_cache.get(project_id)
    if not entry:
        return None
    if time.time() - entry["ts"] > PROJECT_TYPE_TTL:
        return None
    return entry["repo_type"]


def _read_gitlab_tree(args: dict) -> dict:
    project_id = args.get("project_id")
    path       = args.get("path", "")
    ref        = args.get("ref", "main")

    if not project_id:
        return _fatal("project_id is required.")

    if _record_read("tree", project_id, ref, path):
        logger.warning("tree_repeat_blocked", extra={
            "project_id": project_id, "ref": ref, "path": path,
        })
        return _ok(
            f"You already read directory '{path or '/'}' on ref '{ref}' in this task. "
            f"Duplicate exploration calls are forbidden — your previous response "
            f"contained everything you need.\n\n"
            f"Do NOT call read_gitlab_tree again for this path or any prefix of it. "
            f"Do NOT call read_gitlab_file on the exemplar more than once. "
            f"Proceed immediately to the next workflow step "
            f"(generate the file → create_gitlab_branch → commit_gitlab_file)."
        )

    query = f"ref={urllib.parse.quote(ref)}&per_page=50"
    if path:
        query += f"&path={urllib.parse.quote(path, safe='')}"

    try:
        items = _gitlab_request("GET", f"/projects/{project_id}/repository/tree?{query}")
    except RuntimeError as e:
        if "404" in str(e):
            # Return ok with a strong stop instruction — 404 on a path is expected,
            # not an error. Agent should move on, not retry.
            logger.info("tree_path_not_found", extra={"project_id": project_id, "path": path})
            return _ok(
                f"Directory '{path or '/'}' does not exist on ref '{ref}'. "
                f"Do not retry this path or any variation of it. "
                f"Do not try 'environments/{path}' or any other prefix. "
                f"Proceed immediately using the root directory structure already read."
            )
        return _error(str(e))

    if not items:
        logger.info("tree_empty", extra={"project_id": project_id, "path": path})
        return _ok(
            f"Directory '{path or '/'}' is empty on ref '{ref}'. "
            f"Do not retry this path. Proceed with the root terragrunt.hcl pattern already read."
        )

    lines = [f"Contents of '{path or '/'}' on ref '{ref}':\n"]
    for item in items:
        icon = "📁" if item["type"] == "tree" else "📄"
        lines.append(f"{icon} {item['path']}")

    logger.info("tree_read", extra={"project_id": project_id, "path": path, "count": len(items)})
    return _ok("\n".join(lines))


def _read_gitlab_file(args: dict) -> dict:
    project_id = args.get("project_id")
    file_path  = args.get("file_path")
    ref        = args.get("ref", "main")

    if not project_id or not file_path:
        return _fatal("project_id and file_path are required.")

    if _record_read("file", project_id, ref, file_path):
        logger.warning("file_repeat_blocked", extra={
            "project_id": project_id, "ref": ref, "file_path": file_path,
        })
        return _ok(
            f"You already read '{file_path}' on ref '{ref}' in this task. "
            f"You have the exemplar — do not read it again or any other "
            f"exemplar. Generate the new file from what you already have and "
            f"proceed to create_gitlab_branch → commit_gitlab_file."
        )

    encoded_path = urllib.parse.quote(file_path, safe="")

    try:
        data = _gitlab_request(
            "GET",
            f"/projects/{project_id}/repository/files/{encoded_path}?ref={urllib.parse.quote(ref)}",
        )
    except RuntimeError as e:
        if "404" in str(e):
            return _ok(
                f"File '{file_path}' does not exist on ref '{ref}'. "
                f"No sibling example is available at this path. "
                f"Proceed with the commit using the root terragrunt.hcl pattern already read. "
                f"Do not retry this file read."
            )
        return _error(str(e))

    content = base64.b64decode(data["content"]).decode("utf-8")

    logger.info("file_read", extra={"project_id": project_id, "file_path": file_path, "ref": ref})

    return _ok(
        f"File: {file_path}\n"
        f"Ref: {ref}\n"
        f"Last commit: {data.get('last_commit_id', 'unknown')}\n\n"
        f"{content}"
    )


def _create_gitlab_branch(args: dict) -> dict:
    project_id  = args.get("project_id")
    branch_name = (args.get("branch_name") or "").strip()
    ref         = args.get("ref", "main")

    if not project_id or not branch_name:
        return _fatal("project_id and branch_name are required.")

    if "JIRA-KEY" in branch_name or "JIRA_KEY" in branch_name:
        return _fatal(
            f"Branch name '{branch_name}' contains a placeholder. "
            f"Substitute the actual Jira ticket key before calling this tool."
        )

    try:
        result = _gitlab_request(
            "POST",
            f"/projects/{project_id}/repository/branches",
            {"branch": branch_name, "ref": ref},
        )
    except RuntimeError as e:
        if "already exists" in str(e).lower() or "400" in str(e):
            try:
                encoded = urllib.parse.quote(branch_name, safe="")
                existing = _gitlab_request(
                    "GET",
                    f"/projects/{project_id}/repository/branches/{encoded}",
                )
                logger.info("branch_already_exists", extra={"branch": branch_name})
                return _ok(
                    f"Branch already exists.\n"
                    f"Branch: {existing['name']}\n"
                    f"Commit SHA: {existing['commit']['id']}\n"
                    f"Web URL: {existing['web_url']}"
                )
            except RuntimeError:
                pass
            return _fatal(f"Branch '{branch_name}' already exists or is invalid.")
        return _error(str(e))

    logger.info("branch_created", extra={"project_id": project_id, "branch": branch_name, "from_ref": ref})

    return _ok(
        f"Branch created successfully.\n"
        f"Branch: {result['name']}\n"
        f"From: {ref}\n"
        f"Commit SHA: {result['commit']['id']}\n"
        f"URL: {result['web_url']}"
    )


def _commit_gitlab_file(args: dict) -> dict:
    project_id     = args.get("project_id")
    branch_name    = (args.get("branch_name") or "").strip()
    file_path      = (args.get("file_path") or "").strip()
    content        = args.get("content", "")
    commit_message = (args.get("commit_message") or "").strip()
    action         = args.get("action", "auto")
    repo_type      = (args.get("repo_type") or "").strip().lower()

    if not all([project_id, branch_name, file_path, content, commit_message]):
        return _fatal("project_id, branch_name, file_path, content, and commit_message are all required.")

    if "JIRA-KEY" in branch_name or "JIRA_KEY" in branch_name:
        return _fatal(
            f"Branch name '{branch_name}' contains a placeholder. "
            f"Substitute the actual Jira ticket key before calling this tool."
        )

    if not repo_type:
        repo_type = _cached_repo_type(project_id) or "terraform"
        logger.info("repo_type_defaulted", extra={
            "project_id": project_id, "repo_type": repo_type,
        })

    if repo_type not in VALID_REPO_TYPES:
        return _fatal(
            f"Invalid repo_type '{repo_type}'. Must be one of: {', '.join(VALID_REPO_TYPES)}."
        )

    # Repo-type-aware content validation
    if repo_type == "terraform":
        raw_tf_markers = [
            'resource "aws_',
            "resource 'aws_",
            "terraform {\n  backend",
        ]
        for marker in raw_tf_markers:
            if marker in content:
                print(f"CONTENT_GUARD_TRIGGERED: marker={repr(marker)} repo_type=terraform")
                logger.error("content_guard_triggered", extra={
                    "marker": marker, "branch": branch_name, "repo_type": repo_type,
                })
                return _fatal(
                    "The generated content contains raw Terraform resource blocks. "
                    "This repo uses Terragrunt modules. Read a sibling terragrunt.hcl first "
                    "and model the output on that pattern. Do not retry with raw Terraform content."
                )
    elif repo_type == "gitops":
        if "apiVersion:" not in content or "kind:" not in content:
            print("CONTENT_GUARD_TRIGGERED: missing K8s manifest markers repo_type=gitops")
            logger.error("content_guard_triggered", extra={
                "marker": "missing_apiVersion_or_kind",
                "branch": branch_name,
                "repo_type": repo_type,
            })
            return _fatal(
                "GitOps repos require Kubernetes/Flux manifests. The generated content is "
                "missing 'apiVersion:' and/or 'kind:' fields. Read a sibling manifest first "
                "and model the output on that pattern. Do not retry with non-manifest content."
            )

    if action == "auto":
        try:
            encoded = urllib.parse.quote(file_path, safe="")
            _gitlab_request(
                "GET",
                f"/projects/{project_id}/repository/files/{encoded}?ref={urllib.parse.quote(branch_name)}",
            )
            action = "update"
        except RuntimeError:
            action = "create"

    payload = {
        "branch":         branch_name,
        "commit_message": commit_message,
        "actions": [{
            "action":    action,
            "file_path": file_path,
            "content":   content,
        }],
    }

    try:
        result = _gitlab_request("POST", f"/projects/{project_id}/repository/commits", payload)
    except RuntimeError as e:
        return _error(str(e))

    logger.info("file_committed", extra={
        "project_id": project_id,
        "branch":     branch_name,
        "file_path":  file_path,
        "action":     action,
    })

    return _ok(
        f"File committed successfully.\n"
        f"Action: {action}\n"
        f"File: {file_path}\n"
        f"Branch: {branch_name}\n"
        f"Commit SHA: {result['id']}\n"
        f"Message: {result['message'].strip()}"
    )


def _create_gitlab_mr(args: dict) -> dict:
    project_id    = args.get("project_id")
    branch_name   = (args.get("branch_name") or "").strip()
    target_branch = (args.get("target_branch") or "").strip()
    title         = (args.get("title") or "").strip()
    description   = args.get("description", "")
    jira_key      = (args.get("jira_key") or "").strip()

    if not all([project_id, branch_name, target_branch, title]):
        return _fatal("project_id, branch_name, target_branch, and title are all required.")

    if "JIRA-KEY" in branch_name or "JIRA_KEY" in branch_name:
        return _fatal(
            f"Branch name '{branch_name}' contains a placeholder. "
            f"Substitute the actual Jira ticket key before calling this tool."
        )

    draft_title = f"Draft: {title}" if not title.lower().startswith("draft:") else title

    body_desc = description or ""
    if jira_key:
        body_desc = f"Jira: {jira_key}\n\n{body_desc}".strip()
    body_desc = body_desc.replace("\\n", "\n")

    try:
        result = _gitlab_request(
            "POST",
            f"/projects/{project_id}/merge_requests",
            {
                "source_branch": branch_name,
                "target_branch": target_branch,
                "title":         draft_title,
                "description":   body_desc,
                "draft":         True,
            },
        )
    except RuntimeError as e:
        if "409" in str(e):
            try:
                encoded = urllib.parse.quote(branch_name, safe="")
                mrs = _gitlab_request(
                    "GET",
                    f"/projects/{project_id}/merge_requests?source_branch={encoded}&state=opened",
                )
                if mrs and isinstance(mrs, list):
                    existing = mrs[0]
                    logger.info("mr_already_exists", extra={"mr_iid": existing["iid"]})
                    return {
                        "content": [{"type": "text", "text": (
                            f"Draft MR already exists for this branch.\n"
                            f"Title: {existing['title']}\n"
                            f"MR URL: {existing['web_url']}\n"
                            f"Source: {branch_name} → {target_branch}\n"
                            f"State: {existing['state']}\n\n"
                            f"Proceed immediately to step 9: call add_jira_comment with the branch name, "
                            f"commit SHA, and this MR URL. Do not call any GitLab tools."
                        )}],
                        "isError": False,
                    }
            except RuntimeError:
                pass
        return _fatal(str(e))

    logger.info("mr_created", extra={"project_id": project_id, "branch": branch_name, "mr_iid": result["iid"]})

    return {
        "content": [{"type": "text", "text": (
            f"Draft MR opened successfully.\n"
            f"Title: {result['title']}\n"
            f"MR URL: {result['web_url']}\n"
            f"Source: {branch_name} → {target_branch}\n"
            f"State: {result['state']}\n\n"
            f"Proceed immediately to step 9: call add_jira_comment with the branch name, "
            f"commit SHA, and this MR URL. Do not call any GitLab tools."
        )}],
        "isError": False,
    }


# ── Router ────────────────────────────────────────────────────────────────────

TOOL_HANDLERS = {
    "resolve_gitlab_project": _resolve_gitlab_project,
    "read_gitlab_tree":       _read_gitlab_tree,
    "read_gitlab_file":       _read_gitlab_file,
    "create_gitlab_branch":   _create_gitlab_branch,
    "commit_gitlab_file":     _commit_gitlab_file,
    "create_gitlab_mr":       _create_gitlab_mr,
}


def lambda_handler(event, context):
    print("RAW_EVENT:", json.dumps(event))

    tool_name, args, source = _resolve_tool_call(event)

    if not tool_name:
        logger.error("tool_unresolvable", extra={"keys": sorted(args.keys())})
        return _fatal("Could not determine which tool to invoke.")

    logger.info("tool_invoked", extra={"tool": tool_name, "dispatch": source})

    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        logger.warning("unknown_tool", extra={"tool_name": tool_name, "dispatch": source})
        return _fatal(f"Unknown tool: {tool_name or '(none)'}")

    try:
        return handler(args)
    except Exception as exc:
        import traceback
        print("TOOL_FAILED:", tool_name, str(exc))
        print("TRACEBACK:",   traceback.format_exc())
        logger.error("tool_failed", extra={"tool": tool_name, "error": str(exc)})
        return _fatal(f"Tool '{tool_name}' failed: {exc}")