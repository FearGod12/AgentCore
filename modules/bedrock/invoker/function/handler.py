import boto3
import hashlib
import json
import os
import re
import urllib.request

from aws_lambda_powertools import Logger

logger = Logger()

agentcore = boto3.client("bedrock-agentcore", region_name=os.environ["BEDROCK_REGION"])
sm = boto3.client("secretsmanager")

r = sm.get_secret_value(SecretId=os.environ["SLACK_BOT_TOKEN_SECRET_ID"])
BOT_TOKEN = json.loads(r["SecretString"])["value"]


def _clean_output(raw: str) -> str:
    # Strip <thinking> blocks
    cleaned = re.sub(r"<thinking>.*?</thinking>\s*", "", raw, flags=re.DOTALL)
    # Unwrap any XML wrapper tags the model uses (<response>, <answer>, etc.)
    match = re.search(r"<(?:response|answer)>(.*?)</(?:response|answer)>", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(1)
    return cleaned.strip()


def _post_to_slack(channel, thread_ts, text, request_id):
    payload = json.dumps({
        "channel":   channel,
        "thread_ts": thread_ts,
        "text":      text,
    }).encode()

    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={
            "Content-Type":  "application/json; charset=utf-8",
            "Authorization": f"Bearer {BOT_TOKEN}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
        if not result.get("ok"):
            logger.error("slack_post_failed", extra={
                "request_id": request_id,
                "error":      result.get("error"),
            })
        else:
            logger.info("slack_post_ok", extra={"request_id": request_id})


def _invoke_agentcore(prompt, session_id, request_id):
    logger.info("agentcore_invoke", extra={
        "request_id":    request_id,
        "session_id":    session_id,
        "prompt_length": len(prompt),
    })

    try:
        response = agentcore.invoke_agent_runtime(
            agentRuntimeArn=os.environ["AGENT_RUNTIME_ARN"],
            runtimeSessionId=session_id,
            qualifier="DEFAULT",
            payload=json.dumps({"prompt": prompt}),
        )
    except Exception as e:
        logger.error("agentcore_invoke_failed", extra={
            "request_id": request_id,
            "error_type": type(e).__name__,
            "error_msg":  str(e),
            "response":   getattr(e, "response", None),
        })
        raise

    try:
        raw = b""
        for chunk in response["response"].iter_chunks():
            raw += chunk
        logger.info("agentcore_raw_response", extra={
            "request_id": request_id,
            "raw":        raw.decode("utf-8", errors="replace"),
        })
        result = json.loads(raw.decode("utf-8"))
    except Exception:
        logger.exception("agentcore_stream_error", extra={
            "request_id": request_id,
            "session_id": session_id,
        })
        raise

    logger.info("agentcore_result", extra={
        "request_id":      request_id,
        "response_length": len(str(result)),
    })

    return _clean_output(result.get("output", "No response generated."))


@logger.inject_lambda_context
def lambda_handler(event, context):
    if "Records" in event:
        for record in event["Records"]:
            job = json.loads(record["body"])

            request_id = job.get("request_id", record["messageId"])
            raw_text   = job["text"]
            channel    = job["channel"]
            thread_ts  = job["thread_ts"]

            prompt = re.sub(r"<@[A-Z0-9]+>\s*", "", raw_text).strip()

            if not prompt:
                _post_to_slack(channel, thread_ts, "Please provide a message.", request_id)
                continue

            session_id = hashlib.sha256(f"{channel}:{thread_ts}".encode()).hexdigest()

            logger.info("processing", extra={
                "request_id": request_id,
                "channel":    channel,
                "session_id": session_id,
            })

            try:
                reply = _invoke_agentcore(prompt, session_id, request_id)
            except Exception:
                logger.exception("agentcore_error", extra={"request_id": request_id})
                reply = "Sorry, something went wrong. Please try again."

            try:
                _post_to_slack(channel, thread_ts, reply, request_id)
            except Exception:
                logger.exception("slack_post_error", extra={"request_id": request_id})

        return {"statusCode": 200}

    # Direct invocation for testing
    prompt = event.get("prompt", "")
    if not prompt:
        return {"statusCode": 400, "body": "Missing prompt"}

    request_id = context.aws_request_id

    try:
        reply = _invoke_agentcore(prompt, "test-session", request_id)
        return {"statusCode": 200, "body": reply}
    except Exception:
        logger.exception("agentcore_error", extra={"request_id": request_id})
        return {"statusCode": 500, "body": "Internal error"}