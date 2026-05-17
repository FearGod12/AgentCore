"""
Jira Tool Lambda — AgentCore Gateway MCP Target

When using inline_payload in the gateway target configuration, AgentCore
handles the MCP protocol layer itself and invokes Lambda with the raw tool
arguments directly as the event — no jsonrpc/method/params wrapper.

The gateway injects a `tool` field with the namespaced tool name,
e.g. "jira___create_jira_ticket". We strip the namespace and route.

If the `tool` field is absent (observed in some gateway versions), we fall
back to inferring the tool from the shape of the payload keys.

Supported tools:
  - create_jira_ticket  — create a new ticket (optionally assign by name)
  - get_jira_ticket     — fetch ticket details by key
  - update_jira_ticket  — update status, priority, or assignee by name
  - list_jira_tickets   — list open tickets in a project
  - add_jira_comment    — add a comment to a ticket
  - list_jira_users     — list assignable human users

Idempotency:
  - create_jira_ticket checks for an existing open ticket with the same
    summary in the same project before creating. If one exists it returns
    the existing ticket instead of creating a duplicate. This prevents
    double-creation when the model retries after a partial failure.

Sprint behaviour:
  - Looks up the board for the project. If it is not a Scrum board,
    sprint lookup is skipped (simple/kanban boards have no sprints).
  - If a Scrum board has an active sprint, new tickets are assigned to it.
  - Falls back to backlog silently if no active sprint exists.
  - Board type and sprint ID are cached per project key.
"""
import json
import logging
import os
import re
import time
import urllib.request
import urllib.error
import urllib.parse
import boto3
import base64

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

JIRA_BASE_URL    = os.environ["JIRA_BASE_URL"].rstrip("/")
JIRA_SECRET_NAME = os.environ["JIRA_SECRET_NAME"]

_sm = boto3.client("secretsmanager")

# ── TTL cache for Jira auth ───────────────────────────────────────────────────
_jira_auth_cache = {"value": None, "timestamp": 0}
AUTH_CACHE_TTL_SECONDS = 300

# ── TTL cache for sprint IDs keyed by project_key ────────────────────────────
_sprint_cache: dict = {}
SPRINT_CACHE_TTL_SECONDS = 300


# ── Auth ──────────────────────────────────────────────────────────────────────

def _get_secret():
    try:
        return _sm.get_secret_value(SecretId=JIRA_SECRET_NAME)["SecretString"].strip()
    except Exception as e:
        logger.error("secret_fetch_failed", extra={"error": str(e)})
        return None


def _get_jira_auth() -> str:
    now = time.time()

    if (
        _jira_auth_cache["value"] is None
        or now - _jira_auth_cache["timestamp"] > AUTH_CACHE_TTL_SECONDS
    ):
        secret = _get_secret()

        if not secret:
            return None

        encoded = base64.b64encode(secret.encode("utf-8")).decode("utf-8")

        _jira_auth_cache["value"] = f"Basic {encoded}"
        _jira_auth_cache["timestamp"] = now

    return _jira_auth_cache["value"]


def _invalidate_jira_auth_cache(reason: str) -> None:
    """
    Force the next _get_jira_auth() call to refetch the secret. Called when
    Jira returns 401/403 so a rotated email:token doesn't cause a 5-minute
    cached-auth outage.
    """
    if _jira_auth_cache["value"] is not None:
        logger.warning("jira_auth_cache_invalidated", extra={"reason": reason})
    _jira_auth_cache["value"]     = None
    _jira_auth_cache["timestamp"] = 0


# ── Generic HTTP helpers ──────────────────────────────────────────────────────

def _jira_get(path: str) -> dict:
    url = f"{JIRA_BASE_URL}{path}"
    req = urllib.request.Request(
        url,
        headers={"Content-Type": "application/json", "Authorization": _get_jira_auth()},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw  = resp.read()
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise RuntimeError(f"Expected dict from Jira API, got {type(data).__name__}: {path}")
            return data
    except urllib.error.HTTPError as e:
        body_str = e.read().decode()
        if e.code in (401, 403):
            _invalidate_jira_auth_cache(f"http_{e.code}")
        logger.error("jira_http_error", extra={
            "status": e.code, "method": "GET", "path": path, "body": body_str,
        })
        raise RuntimeError(f"Jira API error {e.code}: {body_str}")
    except urllib.error.URLError as e:
        logger.error("jira_url_error", extra={
            "reason": str(e.reason), "method": "GET", "path": path,
        })
        raise RuntimeError(f"Jira connection error: {e.reason}")
    except json.JSONDecodeError as e:
        logger.error("jira_json_error", extra={
            "error": str(e), "method": "GET", "path": path,
        })
        raise RuntimeError(f"Jira returned invalid JSON: {e}")
    except Exception as e:
        logger.error("jira_unexpected_error", extra={
            "error": str(e), "type": type(e).__name__, "method": "GET", "path": path,
        })
        raise


def _jira_get_list(path: str) -> list:
    url = f"{JIRA_BASE_URL}{path}"
    req = urllib.request.Request(
        url,
        headers={"Content-Type": "application/json", "Authorization": _get_jira_auth()},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw  = resp.read()
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, list):
                raise RuntimeError(f"Expected list from Jira API, got {type(data).__name__}: {path}")
            return data
    except urllib.error.HTTPError as e:
        body_str = e.read().decode()
        if e.code in (401, 403):
            _invalidate_jira_auth_cache(f"http_{e.code}")
        logger.error("jira_http_error", extra={
            "status": e.code, "method": "GET_LIST", "path": path, "body": body_str,
        })
        raise RuntimeError(f"Jira API error {e.code}: {body_str}")
    except urllib.error.URLError as e:
        logger.error("jira_url_error", extra={
            "reason": str(e.reason), "method": "GET_LIST", "path": path,
        })
        raise RuntimeError(f"Jira connection error: {e.reason}")
    except json.JSONDecodeError as e:
        logger.error("jira_json_error", extra={
            "error": str(e), "method": "GET_LIST", "path": path,
        })
        raise RuntimeError(f"Jira returned invalid JSON: {e}")
    except Exception as e:
        logger.error("jira_unexpected_error", extra={
            "error": str(e), "type": type(e).__name__, "method": "GET_LIST", "path": path,
        })
        raise


def _jira_post(path: str, body: dict) -> dict:
    url     = f"{JIRA_BASE_URL}{path}"
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data    = payload,
        headers = {"Content-Type": "application/json", "Authorization": _get_jira_auth()},
        method  = "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as e:
        body_str = e.read().decode()
        if e.code in (401, 403):
            _invalidate_jira_auth_cache(f"http_{e.code}")
        logger.error("jira_http_error", extra={
            "status": e.code, "method": "POST", "path": path, "body": body_str,
        })
        raise RuntimeError(f"Jira API error {e.code}: {body_str}")


def _jira_put(path: str, body: dict) -> dict:
    url     = f"{JIRA_BASE_URL}{path}"
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data    = payload,
        headers = {"Content-Type": "application/json", "Authorization": _get_jira_auth()},
        method  = "PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as e:
        body_str = e.read().decode()
        if e.code in (401, 403):
            _invalidate_jira_auth_cache(f"http_{e.code}")
        logger.error("jira_http_error", extra={
            "status": e.code, "method": "PUT", "path": path, "body": body_str,
        })
        raise RuntimeError(f"Jira API error {e.code}: {body_str}")


# ── Idempotency check ─────────────────────────────────────────────────────────
#
# A simple case-insensitive exact-match on summary is too easy for the model to
# bypass by rephrasing (observed in production: "Create S3 bucket X" vs "Add
# S3 bucket X"). We use three signals, in order of precedence:
#
#   1. fingerprint match — a kebab/snake-case identifier (e.g. bucket name,
#      service name) extracted from summary+description; if any open ticket in
#      the project mentions the same identifier in summary or description,
#      that's the same piece of work.
#   2. token-set Jaccard ≥ 0.7 after normalising/stopword-stripping —
#      catches rephrasings that share most content words.
#   3. exact case-insensitive match — preserved as a final fallback.

_IDEMPOTENCY_STOPWORDS = {
    "a", "an", "the", "for", "in", "on", "to", "of", "and", "or", "with", "via",
    "add", "create", "new", "make", "set", "up", "deploy", "configure",
    "please", "kindly", "this", "that",
}

_IDENTIFIER_RE = re.compile(r"\b[a-z0-9]+(?:[-_][a-z0-9]+)+\b", re.IGNORECASE)


def _normalize_tokens(text: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9\s\-_]", " ", (text or "").lower())
    return {t for t in cleaned.split() if t and t not in _IDEMPOTENCY_STOPWORDS}


def _extract_fingerprint(text: str) -> str | None:
    """Pick the first kebab/snake-case identifier (e.g. 'vrzn-use1-platform')."""
    matches = _IDENTIFIER_RE.findall(text or "")
    return matches[0].lower() if matches else None


def _find_existing_ticket(
    project_key: str,
    summary: str,
    description: str = "",
) -> dict | None:
    """
    Search for an existing open ticket that represents the same piece of work.
    Returns the issue dict if found, None otherwise. Non-fatal — if the search
    fails we proceed with creation.
    """
    target_tokens     = _normalize_tokens(summary)
    target_fingerprint = _extract_fingerprint(f"{summary} {description}")

    # Pick the most specific search term we have for the JQL query
    search_term = target_fingerprint
    if not search_term and target_tokens:
        search_term = max(target_tokens, key=len)

    if not search_term:
        return None

    try:
        escaped = search_term.replace('"', '\\"')
        jql     = (
            f'project = "{project_key}" AND '
            f'(summary ~ "{escaped}" OR description ~ "{escaped}") AND '
            f'statusCategory != Done ORDER BY created DESC'
        )
        raw = _jira_get(
            f"/rest/api/3/search/jql?jql={urllib.parse.quote(jql)}"
            f"&maxResults=10&fields=summary,status,description"
        )

        target_summary_lower = summary.lower()

        for issue in raw.get("issues", []):
            fields            = issue.get("fields") or {}
            existing_summary  = fields.get("summary", "")
            existing_desc     = json.dumps(fields.get("description") or "")
            existing_haystack = f"{existing_summary} {existing_desc}".lower()

            # 1. fingerprint match
            if target_fingerprint and target_fingerprint in existing_haystack:
                logger.info("idempotency_match_fingerprint", extra={
                    "fingerprint": target_fingerprint,
                    "match_key":   issue.get("key"),
                })
                return issue

            # 2. token-set similarity
            existing_tokens = _normalize_tokens(existing_summary)
            if target_tokens and existing_tokens:
                intersection = target_tokens & existing_tokens
                union        = target_tokens | existing_tokens
                if union and len(intersection) / len(union) >= 0.7:
                    logger.info("idempotency_match_jaccard", extra={
                        "ratio":     round(len(intersection) / len(union), 2),
                        "match_key": issue.get("key"),
                    })
                    return issue

            # 3. exact summary match (preserved fallback)
            if existing_summary.lower() == target_summary_lower:
                logger.info("idempotency_match_exact", extra={
                    "match_key": issue.get("key"),
                })
                return issue
    except Exception as exc:
        logger.warning("idempotency_check_failed", extra={"error": str(exc)})
    return None


# ── User lookup by display name ───────────────────────────────────────────────

def _resolve_account_id(display_name: str) -> str | None:
    """
    Search Jira for a user by display name and return their accountId.
    Returns None if no match is found.
    Uses case-insensitive exact match first, then partial match fallback.
    """
    results = _jira_get_list(
        f"/rest/api/3/user/search?query={urllib.parse.quote(display_name)}&maxResults=10"
    )

    active     = [u for u in results if u.get("active") and u.get("accountType") == "atlassian"]
    name_lower = display_name.lower()

    for user in active:
        if user.get("displayName", "").lower() == name_lower:
            logger.info("user_resolved", extra={"display_name": display_name})
            return user["accountId"]

    for user in active:
        if name_lower in user.get("displayName", "").lower():
            logger.info("user_resolved_partial", extra={"display_name": display_name, "matched": user["displayName"]})
            return user["accountId"]

    return None


# ── Sprint lookup ─────────────────────────────────────────────────────────────

def _get_active_sprint_id(project_key: str) -> int | None:
    now    = time.time()
    cached = _sprint_cache.get(project_key)

    if cached and now - cached["timestamp"] < SPRINT_CACHE_TTL_SECONDS:
        return cached["sprint_id"]

    try:
        boards_resp = _jira_get(f"/rest/agile/1.0/board?projectKeyOrId={project_key}")
        boards      = boards_resp.get("values", [])

        if not boards:
            logger.info("sprint_lookup_skipped", extra={"reason": "no_board", "project_key": project_key})
            _sprint_cache[project_key] = {"sprint_id": None, "timestamp": now}
            return None

        board      = boards[0]
        board_id   = board["id"]
        board_type = board.get("type", "")

        if board_type != "scrum":
            logger.info("sprint_lookup_skipped", extra={"reason": "non_scrum_board", "board_type": board_type})
            _sprint_cache[project_key] = {"sprint_id": None, "timestamp": now}
            return None

        sprints_resp = _jira_get(f"/rest/agile/1.0/board/{board_id}/sprint?state=active")
        sprints      = sprints_resp.get("values", [])

        if not sprints:
            logger.info("sprint_lookup_skipped", extra={"reason": "no_active_sprint", "board_id": board_id})
            _sprint_cache[project_key] = {"sprint_id": None, "timestamp": now}
            return None

        sprint_id = sprints[0]["id"]
        logger.info("active_sprint_found", extra={"sprint_id": sprint_id})
        _sprint_cache[project_key] = {"sprint_id": sprint_id, "timestamp": now}
        return sprint_id

    except Exception as exc:
        logger.warning("sprint_lookup_failed", extra={"project_key": project_key, "error": str(exc)})
        return None


# ── Response helpers ──────────────────────────────────────────────────────────

def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _error(text: str) -> dict:
    """
    Return a terminal error response. The message instructs the model not to
    retry so it surfaces the error to the user instead of looping.
    """
    return {
        "content": [{"type": "text", "text": f"Error: {text} Do not retry this operation."}],
        "isError": True,
    }


def _adf(text: str) -> dict:
    return {
        "type": "doc", "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


# ── Tool inference fallback ───────────────────────────────────────────────────

def _infer_tool(event: dict) -> str:
    keys = set(event.keys())

    if "project_key" in keys and "summary" in keys:
        return "create_jira_ticket"

    if "ticket_key" in keys and "comment" in keys:
        return "add_jira_comment"

    if "ticket_key" in keys and keys & {"status", "priority", "assignee_name"}:
        return "update_jira_ticket"

    if "ticket_key" in keys:
        return "get_jira_ticket"

    if "project_key" in keys:
        return "list_jira_tickets"

    if not keys or keys <= {"max_results"}:
        return "list_jira_users"

    return ""


def _resolve_tool_call(event: dict) -> tuple[str, dict, str]:
    """
    Normalise the AgentCore Gateway → Lambda payload into (tool_name, args, source).

    Handles three observed shapes:
      - {"tool": "jira___create_jira_ticket", ...args}      (legacy)
      - {"name": "create_jira_ticket", "arguments": {...}}   (MCP envelope)
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


# ── Tool handlers ─────────────────────────────────────────────────────────────

def _create_jira_ticket(args: dict) -> dict:
    project_key   = args.get("project_key")
    summary       = args.get("summary")
    description   = args.get("description", "")
    issue_type    = args.get("issue_type", "Task")
    priority      = args.get("priority")
    assignee_name = (args.get("assignee_name") or "").strip()

    if not project_key or not summary:
        return _error("project_key and summary are required.")

    # ── Idempotency: return existing ticket if summary already exists ─────────
    existing = _find_existing_ticket(project_key, summary, description)
    if existing:
        ticket_key = existing.get("key", "unknown")
        ticket_url = f"{JIRA_BASE_URL}/browse/{ticket_key}"
        status     = (existing.get("fields") or {}).get("status", {}).get("name", "Unknown")
        logger.info("ticket_already_exists", extra={"key": ticket_key})
        return _ok(
            f"A ticket with this summary already exists — returning existing ticket.\n"
            f"Key: {ticket_key}\n"
            f"URL: {ticket_url}\n"
            f"Status: {status}\n"
            f"Summary: {summary}"
        )

    fields: dict = {
        "project":   {"key": project_key},
        "summary":   summary,
        "issuetype": {"name": issue_type},
    }

    if description:
        fields["description"] = _adf(description)

    if priority:
        fields["priority"] = {"name": priority}

    # ── Resolve assignee by display name ──────────────────────────────────────
    resolved_name = None
    if assignee_name:
        account_id = _resolve_account_id(assignee_name)
        if not account_id:
            return _error(f"User '{assignee_name}' not found in Jira. Check the name and try again.")
        fields["assignee"] = {"accountId": account_id}
        resolved_name      = assignee_name

    sprint_id = _get_active_sprint_id(project_key)
    if sprint_id is not None:
        fields["customfield_10020"] = sprint_id

    result     = _jira_post("/rest/api/3/issue", {"fields": fields})
    ticket_key = result.get("key", "unknown")
    ticket_url = f"{JIRA_BASE_URL}/browse/{ticket_key}"

    logger.info("ticket_created", extra={
        "key":        ticket_key,
        "sprint_id":  sprint_id,
        "assignee":   resolved_name,
    })

    assignee_str = f"\nAssignee: {resolved_name}" if resolved_name else ""

    return _ok(
        f"Jira ticket created successfully!\n"
        f"Key: {ticket_key}\n"
        f"URL: {ticket_url}\n"
        f"Summary: {summary}"
        f"{assignee_str}"
    )


def _get_jira_ticket(args: dict) -> dict:
    ticket_key = args.get("ticket_key")
    if not ticket_key:
        return _error("ticket_key is required.")

    try:
        result = _jira_get(f"/rest/api/3/issue/{ticket_key}")
    except RuntimeError as e:
        if "404" in str(e):
            return _error(f"Ticket {ticket_key} not found.")
        raise

    fields   = result.get("fields", {})
    summary  = fields.get("summary", "")
    status   = fields.get("status", {}).get("name", "Unknown")
    priority = fields.get("priority", {}).get("name", "None")
    assignee = (fields.get("assignee") or {}).get("displayName", "Unassigned")
    created  = fields.get("created", "")[:10]

    logger.info("ticket_fetched", extra={"key": ticket_key})

    return _ok(
        f"Ticket: {ticket_key}\n"
        f"Summary: {summary}\n"
        f"Status: {status}\n"
        f"Priority: {priority}\n"
        f"Assignee: {assignee}\n"
        f"Created: {created}\n"
        f"URL: {JIRA_BASE_URL}/browse/{ticket_key}"
    )


def _update_jira_ticket(args: dict) -> dict:
    ticket_key    = args.get("ticket_key")
    new_status    = args.get("status")
    new_priority  = args.get("priority")
    assignee_name = (args.get("assignee_name") or "").strip()

    if not ticket_key:
        return _error("ticket_key is required.")

    updates = []
    fields: dict = {}

    if new_priority:
        fields["priority"] = {"name": new_priority}

    if assignee_name:
        account_id = _resolve_account_id(assignee_name)
        if not account_id:
            return _error(f"User '{assignee_name}' not found in Jira. Check the name and try again.")
        fields["assignee"] = {"accountId": account_id}
        logger.info("assignee_resolved", extra={"assignee_name": assignee_name})

    if fields:
        _jira_put(f"/rest/api/3/issue/{ticket_key}", {"fields": fields})
        if new_priority:
            updates.append(f"priority → {new_priority}")
        if assignee_name:
            updates.append(f"assignee → {assignee_name}")

    if new_status:
        transitions_resp = _jira_get(f"/rest/api/3/issue/{ticket_key}/transitions")
        transitions      = transitions_resp.get("transitions", [])
        match = next(
            (t for t in transitions if t["name"].lower() == new_status.lower()),
            None,
        )
        if not match:
            available = ", ".join(t["name"] for t in transitions)
            return _error(f"Status '{new_status}' not available. Available transitions: {available}")

        _jira_post(
            f"/rest/api/3/issue/{ticket_key}/transitions",
            {"transition": {"id": match["id"]}},
        )
        updates.append(f"status → {new_status}")

    if not updates:
        return _error("No updates provided. Supply at least one of: status, priority, assignee_name.")

    logger.info("ticket_updated", extra={"key": ticket_key, "updates": updates})

    return _ok(
        f"Ticket {ticket_key} updated successfully!\n"
        f"Changes: {', '.join(updates)}\n"
        f"URL: {JIRA_BASE_URL}/browse/{ticket_key}"
    )


def _list_jira_tickets(args: dict) -> dict:
    project_key = args.get("project_key")
    status      = args.get("status")
    max_results = min(int(args.get("max_results") or 10), 50)

    if not project_key:
        return _error("project_key is required.")

    if status:
        jql = f'project = "{project_key}" AND status = "{status}" ORDER BY created DESC'
    else:
        jql = f'project = "{project_key}" AND statusCategory != Done ORDER BY created DESC'

    raw = _jira_get(
        f"/rest/api/3/search/jql?jql={urllib.parse.quote(jql)}"
        f"&maxResults={max_results}"
        f"&fields=summary,status,priority,assignee"
    )

    issues  = raw.get("issues", [])
    is_last = raw.get("isLast", True)

    if not issues:
        suffix = f" with status '{status}'" if status else ""
        return _ok(f"No tickets found in {project_key}{suffix}.")

    more  = "" if is_last else " (more available)"
    lines = [f"Found {len(issues)} ticket(s) in {project_key}{more}:\n"]

    for issue in issues:
        f        = issue.get("fields", {}) or {}
        key      = issue.get("key")
        summary  = f.get("summary", "")
        istatus  = (f.get("status") or {}).get("name", "")
        priority = (f.get("priority") or {}).get("name", "")
        assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
        lines.append(f"• {key} [{istatus}] [{priority}] — {summary} (Assignee: {assignee})")

    logger.info("tickets_listed", extra={"project_key": project_key, "count": len(issues), "is_last": is_last})
    return _ok("\n".join(lines))


def _add_jira_comment(args: dict) -> dict:
    ticket_key = args.get("ticket_key")
    comment    = args.get("comment")

    if not ticket_key or not comment:
        return _error("ticket_key and comment are required.")

    _jira_post(
        f"/rest/api/3/issue/{ticket_key}/comment",
        {"body": _adf(comment)},
    )

    logger.info("comment_added", extra={"key": ticket_key})

    return _ok(
        f"Comment added to {ticket_key} successfully!\n"
        f"URL: {JIRA_BASE_URL}/browse/{ticket_key}"
    )


def _list_jira_users(args: dict) -> dict:
    max_results = min(int(args.get("max_results") or 50), 200)

    users = _jira_get_list(
        f"/rest/api/3/users/search?maxResults={max_results}"
    )

    human_users = [u for u in users if u.get("accountType") == "atlassian" and u.get("active")]

    if not human_users:
        return _ok("No active users found.")

    lines = [f"Found {len(human_users)} active user(s):\n"]
    for user in human_users:
        display_name = user.get("displayName", "Unknown")
        email        = user.get("emailAddress", "")
        email_str    = f" <{email}>" if email else ""
        lines.append(f"• {display_name}{email_str}")

    logger.info("users_listed", extra={"count": len(human_users)})
    return _ok("\n".join(lines))


# ── Router ────────────────────────────────────────────────────────────────────

TOOL_HANDLERS = {
    "create_jira_ticket": _create_jira_ticket,
    "get_jira_ticket":    _get_jira_ticket,
    "update_jira_ticket": _update_jira_ticket,
    "list_jira_tickets":  _list_jira_tickets,
    "add_jira_comment":   _add_jira_comment,
    "list_jira_users":    _list_jira_users,
}


def lambda_handler(event, context):
    """
    AgentCore Gateway → Lambda dispatch.

    See _resolve_tool_call for the supported event shapes. AgentCore Gateway
    with inline_payload currently delivers raw arguments without tool metadata;
    we infer the tool from payload shape in that case.
    """
    logger.debug("raw_event", extra={"event": event})

    tool_name, args, source = _resolve_tool_call(event)

    if not tool_name:
        logger.error("tool_unresolvable", extra={"keys": sorted(args.keys())})
        return _error("Could not determine which tool to invoke.")

    logger.info("tool_invoked", extra={"tool": tool_name, "dispatch": source})

    handler = TOOL_HANDLERS.get(tool_name)

    if not handler:
        logger.warning("unknown_tool", extra={"tool_name": tool_name, "dispatch": source})
        return _error(f"Unknown tool: {tool_name or '(none)'}")

    try:
        return handler(args)
    except Exception as exc:
        logger.exception("tool_failed", extra={"tool": tool_name, "error": str(exc)})
        return _error(f"Tool '{tool_name}' failed: {exc}")