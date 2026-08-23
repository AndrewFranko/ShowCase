// Case Spine — AWS Free-Tier deployment.
//
// One t3.micro running the same docker-compose stack verified locally and in
// CI, fronted by Caddy for TLS + basic-auth. Deliberately tiny: free tier is
// mostly about what you DON'T create. Contrast with ../main.tf, which is the
// enterprise (EKS + Redshift) module kept as target-architecture collateral for
// the Heartflow pitch — that one is ~$73/month before nodes and is NOT applied
// on a free-tier account.
//
// Security posture (synthetic data, but we practice like it isn't):
//   * no SSH port at all — administration via SSM Session Manager (free,
//     IAM-scoped, audited);
//   * HTTP/HTTPS restricted to `allowed_cidr` (default: your IP only);
//   * Caddy supplies basic-auth — the portal's own OIDC seam is unbound, so the
//     proxy is the minimum credible gate before anything faces the internet;
//   * a $1 budget alarm for legacy free-tier accounts (the post-2025-07 Free
//     Plan cannot bill you at all — the ceiling is enforced by AWS).
//
// Free-tier arithmetic (legacy 12-month tier):
//   EC2 t3.micro 750 h/mo ✅ (24×7 = ~730 h)   EBS 20 of 30 GB ✅
//   EIP attached ✅   S3 backups ≤5 GB ✅   egress ≤100 GB/mo ✅
//   Expected bill: $0.00. New Free Plan: ~$8–9/mo of the $100+ credits.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
  // Local state, gitignored. Small enough that remote state is ceremony;
  // documented trade-off — move to an S3 backend if a second operator appears.
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Application = "case-spine"
      Tier        = "free-tier-demo"
      DataClass   = "synthetic-no-phi"
      ManagedBy   = "terraform"
    }
  }
}

// ---------------------------------------------------------------- networking
// Use the default VPC — creating a VPC/NAT would be cost and complexity for a
// single public instance serving a demo.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "portal" {
  name        = "case-spine-portal"
  description = "Case Spine: HTTPS from allowed CIDR only; no SSH (SSM instead)"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }

  ingress {
    description = "HTTP (Caddy redirect + ACME HTTP-01 when a domain is used)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    // ACME challenges arrive from Let's Encrypt, not from your IP: keep 80 open
    // to the world ONLY when a domain is set, otherwise restrict like 443.
    cidr_blocks = [var.domain == "" ? var.allowed_cidr : "0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

// ---------------------------------------------------------------- IAM (SSM + backups)
resource "aws_iam_role" "instance" {
  name = "case-spine-instance"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "backup" {
  name = "state-backup"
  role = aws_iam_role.instance.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
      Resource = [aws_s3_bucket.backup.arn, "${aws_s3_bucket.backup.arn}/*"]
    }]
  })
}

resource "aws_iam_instance_profile" "instance" {
  name = "case-spine-instance"
  role = aws_iam_role.instance.name
}

// ---------------------------------------------------------------- backups
resource "aws_s3_bucket" "backup" {
  bucket_prefix = "case-spine-state-"
  force_destroy = true // demo stakes; a real deployment would not set this
}

resource "aws_s3_bucket_versioning" "backup" {
  bucket = aws_s3_bucket.backup.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "backup" {
  bucket                  = aws_s3_bucket.backup.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

// ---------------------------------------------------------------- instance
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-2023*-${var.arch == "arm64" ? "arm64" : "x86_64"}"]
  }
}

resource "aws_instance" "portal" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.portal.id]
  iam_instance_profile   = aws_iam_instance_profile.instance.name

  root_block_device {
    volume_size = 20 // of the 30 GB free allowance
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    http_tokens = "required" // IMDSv2 only
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    image           = var.image
    domain          = var.domain
    basic_auth_user = var.basic_auth_user
    basic_auth_hash = var.basic_auth_hash
    backup_bucket   = aws_s3_bucket.backup.bucket
    region          = var.region
  })
  user_data_replace_on_change = true

  tags = { Name = "case-spine" }
}

resource "aws_eip" "portal" {
  instance = aws_instance.portal.id
  // free while attached to a running instance
}

// ---------------------------------------------------------------- budget guardrail
// Legacy free-tier accounts CAN incur charges; alarm at one dollar. The
// post-2025-07 Free Plan cannot bill and makes this belt-and-braces.
resource "aws_budgets_budget" "guardrail" {
  count        = var.budget_alert_email == "" ? 0 : 1
  name         = "case-spine-free-tier-guardrail"
  budget_type  = "COST"
  limit_amount = "1.0"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}
