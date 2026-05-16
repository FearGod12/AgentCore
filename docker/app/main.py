from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os
import time
import logging
import hashlib
import json
import boto3
import httpx

from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from strands import Agent
from strands.models import BedrockModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

MODEL_ID         = os.environ["MODEL_ID"]
AWS_REGION       = os.environ["AWS_REGION"]
GATEWAY_ENDPOINT = os.environ.get("GATEWAY_ENDPOINT", "").strip()

_model = None


def _get_model() -> BedrockModel:
    global _model
    if _model is None:
        logger.info(f"[MODEL] Initializing BedrockModel model_id={MODEL_ID!r} region={AWS_REGION!r}")
        _model = BedrockModel(
            model_id=MODEL_ID,
            region_name=AWS_REGION,
        )
        logger.info("[MODEL] BedrockModel initialized successfully")
    return _model


class SigV4Auth_HTTPX(httpx.Auth):
    def auth_flow(self, request: httpx.Request):
        session   = boto3.session.Session()
        body      = request.content or b""
        body_hash = hashlib.sha256(body).hexdigest()

        creds   = session.get_credentials().get_frozen_credentials()
        aws_req = AWSRequest(
            method  = request.method,
            url     = str(request.url),
            data    = body,
            headers = {
                "Content-Type":         "application/json",
                "x-amz-content-sha256": body_hash,
            },
        )
        SigV4Auth(creds, "bedrock-agentcore", AWS_REGION).add_auth(aws_req)

        for key, value in aws_req.headers.items():
            request.headers[key] = value

        yield request


@app.get("/ping")
def ping():
    return {
        "status": "Healthy",
        "time_of_last_update": int(time.time()),
    }


@app.post("/invocations")
async def invocations(request: Request):
    raw = await request.body()
    logger.info(f"[RAW_BODY] {raw.decode('utf-8', errors='replace')}")

    try:
        body = json.loads(raw)
    except Exception:
        return JSONResponse(status_code=400, content={"output": "Invalid JSON in request body"})

    prompt = (
        body.get("prompt")
        or body.get("inputText")
        or body.get("input")
        or body.get("text")
        or body.get("message")
        or (body.get("messages", [{}])[-1].get("content", "") if body.get("messages") else "")
        or ""
    ).strip()

    session_id = (
        body.get("session_id")
        or body.get("sessionId")
        or body.get("session")
        or body.get("conversationId")
    )

    logger.info(f"[REQUEST] prompt={prompt!r}, session_id={session_id}")

    if not prompt:
        logger.warning(f"[NO_PROMPT] body keys={list(body.keys())}")
        return JSONResponse(
            status_code=200,
            content={"output": f"DEBUG: Could not extract prompt. Raw body: {json.dumps(body)}"},
        )

    try:
        model = _get_model()

        if GATEWAY_ENDPOINT:
            from mcp.client.streamable_http import streamablehttp_client
            from strands.tools.mcp.mcp_client import MCPClient

            def transport_factory():
                return streamablehttp_client(
                    GATEWAY_ENDPOINT,
                    auth=SigV4Auth_HTTPX(),
                )

            gateway_client = MCPClient(transport_factory)
            gateway_client.start()
            gateway_client._tool_provider_started = True

            try:
                logger.info("[GATEWAY] MCP connection established")
                agent = Agent(model=model, tools=[gateway_client])
                response = await agent.invoke_async(prompt)
            finally:
                gateway_client.stop(None, None, None)

        else:
            logger.warning("[GATEWAY] No GATEWAY_ENDPOINT set — invoking model directly")
            agent = Agent(model=model)
            response = await agent.invoke_async(prompt)

        result = str(response)
        logger.info(f"[RESPONSE] {result!r}")
        return {"output": result}

    except Exception as e:
        logger.error(f"Agent execution failed: {type(e).__name__}: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"output": "Error processing request"})