variable "region" {
  description = "AWS region. Free tier is region-agnostic; pick one near you."
  type        = string
  default     = "eu-central-1"
}

variable "instance_type" {
  description = <<-EOT
    t3.micro is the legacy-free-tier instance (750 h/mo, 12 months).
    On a post-2025-07 Free Plan account t4g.micro (arm64) burns credits slower —
    set arch = "arm64" with it. 1 GB RAM is verified sufficient: the container
    runs healthy under a 768 MB compose limit.
  EOT
  type        = string
  default     = "t3.micro"
}

variable "arch" {
  description = "Instance architecture matching instance_type: x86_64 or arm64."
  type        = string
  default     = "x86_64"
  validation {
    condition     = contains(["x86_64", "arm64"], var.arch)
    error_message = "arch must be x86_64 or arm64."
  }
}

variable "image" {
  description = <<-EOT
    Container image reference, e.g. ghcr.io/<github-user>/case-spine:latest.
    Built and pushed by .github/workflows/release.yml; the in-image spine build
    runs `--check`, so a bad warehouse fails the image, never the deploy.
  EOT
  type        = string
}

variable "allowed_cidr" {
  description = <<-EOT
    CIDR allowed to reach the portal, e.g. "203.0.113.7/32" (your IP).
    Widen deliberately if you decide to share the link.
  EOT
  type        = string
  validation {
    condition     = can(cidrnetmask(var.allowed_cidr))
    error_message = "allowed_cidr must be a valid CIDR, e.g. 1.2.3.4/32."
  }
}

variable "domain" {
  description = <<-EOT
    Optional domain pointed at the EIP (A record). With a domain Caddy gets a
    real Let's Encrypt certificate; without one it serves its self-signed
    'internal' TLS on the bare IP — browsers warn once, Playwright is told to
    ignore it via --ignore-certificate-errors when targeting the raw IP.
  EOT
  type        = string
  default     = ""
}

variable "basic_auth_user" {
  description = "Username Caddy requires before anything is served."
  type        = string
  default     = "spine"
}

variable "basic_auth_hash" {
  description = <<-EOT
    Bcrypt hash of the basic-auth password. Generate locally, never commit the
    plaintext:  docker run --rm caddy caddy hash-password --plaintext 'your-pw'
  EOT
  type        = string
  sensitive   = true
}

variable "budget_alert_email" {
  description = <<-EOT
    Email for the $1 budget alarm (legacy free-tier accounts). Leave empty on a
    post-2025-07 Free Plan account — those cannot bill beyond credits and the
    Budgets API itself may be restricted there.
  EOT
  type        = string
  default     = ""
}
