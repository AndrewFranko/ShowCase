variable "region" {
  description = "AWS region of the existing landing zone."
  type        = string
  default     = "us-west-2"
}

variable "environment" {
  description = "Deployment environment (dev | staging | prod)."
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "owner" {
  description = "Owning team, for cost allocation and the CMDB."
  type        = string
  default     = "data-platform"
}

variable "vpc_id" {
  description = "Existing VPC. This project creates no networking."
  type        = string
}

variable "eks_cluster_name" {
  description = "Existing EKS cluster. Workload lands on existing node groups."
  type        = string
}

variable "node_selector" {
  description = <<-EOT
    Node selector for existing node groups. Deliberately does not request new
    subnets - VPC CNI prefix delegation covers pod IPs on the current allocation.
  EOT
  type        = map(string)
  default     = { "workload" = "general" }
}

variable "namespace" {
  description = "Kubernetes namespace."
  type        = string
  default     = "analytics"
}

variable "redshift_cluster_identifier" {
  description = "Existing Redshift cluster holding the spine. Read-only access."
  type        = string
}

variable "ecr_repository" {
  description = "ECR repository URI for the API image."
  type        = string
}

variable "image_tag" {
  description = "Immutable image tag. Set by CI from the commit SHA - never 'latest'."
  type        = string
  validation {
    condition     = var.image_tag != "latest"
    error_message = "image_tag must be immutable; 'latest' breaks release traceability, which IEC 62304 configuration management requires."
  }
}

variable "replicas" {
  description = "Replica count."
  type        = number
  default     = 2
}

variable "alb_group_name" {
  description = "Existing internal ALB ingress group to attach to."
  type        = string
}

variable "acm_certificate_arn" {
  description = "Existing ACM certificate for the internal hostname."
  type        = string
}

variable "hostname" {
  description = "Internal hostname, e.g. case-spine.internal.example.com."
  type        = string
}
