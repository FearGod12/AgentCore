#!/usr/bin/env bash

set -euo pipefail

AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="072496344726"
ECR_REPOSITORY_URL="072496344726.dkr.ecr.us-east-1.amazonaws.com/agentcore-runtime"
IMAGE_TAG="v1.0.0"
FULL_IMAGE_URI="${ECR_REPOSITORY_URL}:${IMAGE_TAG}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Validate placeholders have been filled in
for VAR_NAME in AWS_REGION AWS_ACCOUNT_ID ECR_REPOSITORY_URL; do
  VAR_VALUE="${!VAR_NAME}"
  if [[ "$VAR_VALUE" == "<INSERT_HERE>" || -z "$VAR_VALUE" ]]; then
    echo "  Please set ${VAR_NAME} at the top of push_image.sh before running."
    exit 1
  fi
done

# ── Authenticate Docker to ECR ────────────────────────────────────────────────
echo "  Authenticating Docker to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin \
    "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# ── Build image ───────────────────────────────────────────────────────────────
echo ""
echo "  Building Docker image..."
docker build \
  --platform linux/arm64 \
  -t "${FULL_IMAGE_URI}" \
  -t "${ECR_REPOSITORY_URL}:latest" \
  "${SCRIPT_DIR}"

# ── Push image ────────────────────────────────────────────────────────────────
echo ""
echo "   Pushing ${FULL_IMAGE_URI}..."
docker push "${FULL_IMAGE_URI}"

# ── Done ──────────────────────────────────────────────────────────────────────

echo "  Done! Image pushed successfully."
