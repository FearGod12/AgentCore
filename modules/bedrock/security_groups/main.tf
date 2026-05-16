data "aws_vpc" "current" {
  id = var.vpc_id
}

# ── Endpoints SG ─────────────────────────────────────────────────────────────
resource "aws_security_group" "endpoints" {
  name        = "${var.name}-endpoints"
  description = "Allow HTTPS from within VPC to interface endpoints"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name}-endpoints" })
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_https" {
  security_group_id = aws_security_group.endpoints.id
  cidr_ipv4         = data.aws_vpc.current.cidr_block
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "HTTPS from within VPC"
}

resource "aws_vpc_security_group_egress_rule" "endpoints_all" {
  security_group_id = aws_security_group.endpoints.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "Allow all outbound"
}

# ── AgentCore SG ──────────────────────────────────────────────────────────────
resource "aws_security_group" "agentcore" {
  name        = "${var.name}-agentcore"
  description = "Security group for AgentCore runtime ENIs"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name}-agentcore" })
}

resource "aws_vpc_security_group_ingress_rule" "agentcore_from_lambda" {
  security_group_id            = aws_security_group.agentcore.id
  referenced_security_group_id = aws_security_group.lambda.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
  description                  = "Allow inbound from Lambda"
}

resource "aws_vpc_security_group_egress_rule" "agentcore_to_endpoints" {
  security_group_id            = aws_security_group.agentcore.id
  referenced_security_group_id = aws_security_group.endpoints.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
  description                  = "Allow outbbound to VPC endpoints"
}

resource "aws_vpc_security_group_egress_rule" "agentcore_to_internet" {
  security_group_id = aws_security_group.agentcore.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "Allow outbound HTTPS to internet for AgentCore Gateway"
}

# ── Lambda SG ─────────────────────────────────────────────────────────────────
resource "aws_security_group" "lambda" {
  name        = "${var.name}-lambda"
  description = "Security group for Lambda invoker"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name}-lambda" })
}

resource "aws_vpc_security_group_egress_rule" "lambda_to_internet_https" {
  security_group_id = aws_security_group.lambda.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "Allow outbound HTTPS to Slack API"
}
