import boto3
import hashlib
import hmac
import json
import os
import time

from aws_lambda_powertools import Logger

logger = Logger()

sqs = boto3.client("sqs")
sm  = boto3.client("secretsmanager")

r = sm.get_secret_value(SecretId=os.environ["SLACK_SIGNING_SECRET_ID"])
SIGNING_SECRET = json.loads(r["SecretString"])["value"]


def _verify(headers, raw_body):
    ts  = headers.get("x-slack-request-timestamp", "")
    sig = headers.get("x-slack-signature", "")

    try:
        if abs(time.time() - int(ts)) > 300:
            logger.warning("signature_check_failed", extra={"reason": "timestamp_too_old"})
            return False
    except (ValueError, TypeError):
        logger.warning("signature_check_failed", extra={"reason": "invalid_timestamp"})
        return False

    base   = f"v0:{ts}:{raw_body}"
    expect = "v0=" + hmac.new(
        SIGNING_SECRET.encode(), base.encode(), hashlib.sha256
    ).hexdigest()
    match = hmac.compare_digest(expect, sig)
    if not match:
        logger.warning("signature_check_failed", extra={"reason": "signature_mismatch"})
    return match


@logger.inject_lambda_context
def lambda_handler(event, context):
    headers  = {k.lower(): v for k, v in event.get("headers", {}).items()}
    raw_body = event.get("body", "")

    if not _verify(headers, raw_body):
        return {"statusCode": 403, "body": "Forbidden"}

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("bad_request", extra={"reason": "invalid_json"})
        return {"statusCode": 400, "body": "Bad Request"}

    if body.get("type") == "url_verification":
        return {"statusCode": 200, "body": json.dumps({"challenge": body["challenge"]})}

    event_data = body.get("event", {})
    request_id = body.get("event_id", context.aws_request_id)

    # Drop bot messages silently — no log needed, just noise
    if event_data.get("bot_id"):
        return {"statusCode": 200, "body": "ok"}

    logger.info("event_received", extra={
        "request_id": request_id,
        "type":       event_data.get("type"),
        "retry":      headers.get("x-slack-retry-num"),
        "user":       event_data.get("user"),
        "channel":    event_data.get("channel"),
    })

    text = event_data.get("text", "").strip()
    if not text:
        logger.info("dropped", extra={"request_id": request_id, "reason": "empty_text"})
        return {"statusCode": 200, "body": "ok"}

    # Enqueue — FIFO deduplication on ts handles Slack retries,
    # so we don't drop retries here and risk losing a message
    try:
        sqs.send_message(
            QueueUrl=os.environ["SQS_QUEUE_URL"],
            MessageBody=json.dumps({
                "request_id": request_id,
                "text":       text,
                "channel":    event_data.get("channel"),
                "thread_ts":  event_data.get("thread_ts") or event_data.get("ts"),
                "user":       event_data.get("user"),
            }),
            MessageGroupId=event_data.get("channel"),
            MessageDeduplicationId=event_data.get("ts"),
        )
        logger.info("enqueued", extra={"request_id": request_id})
    except Exception:
        logger.exception("sqs_send_failed", extra={"request_id": request_id})
        return {"statusCode": 500, "body": "Internal error"}

    return {"statusCode": 200, "body": "ok"}