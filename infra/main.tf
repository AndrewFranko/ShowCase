// Case Spine infrastructure.
//
// Deploys into an EXISTING landing zone. Every resource here attaches to
// infrastructure Heartflow already runs: their VPC, their EKS cluster, their
// Redshift cluster, their IdP. Nothing new is introduced at the vendor level.
//
// That constraint is deliberate and it is the difference between a security review
// measured in weeks and one measured in quarters. An outsourced team that reaches
// for a hosted BI SaaS triggers vendor qualification, a DPA, and a HITRUST scope
// change. This triggers none of them.
//
// Subnet note: node placement uses the existing node groups and relies on VPC CNI
// prefix delegation rather than requesting new subnets. Heartflow's public GitHub
// org carries a fork of aws-subnet-ip-address-utilization-monitor, which suggests
// address exhaustion on the cluster is a live constraint - so asking the platform
// team for a /24 is a good way to not get deployed.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws        = { source = "hashicorp/aws", version = "~> 5.0" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.30" }
  }
  backend "s3" {
    // bucket / key / dynamodb_table supplied per environment via -backend-config
    encrypt = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Application = "case-spine"
      Owner       = var.owner
      // Production/QMS software under FDA Computer Software Assurance.
      // NOT device software. See validation/csa-validation-plan.md.
      Regulated = "csa-production-quality-system"
      DataClass = "no-phi"
    }
  }
}

// ---------------------------------------------------------------- existing infra
data "aws_vpc" "main" {
  id = var.vpc_id
}

data "aws_eks_cluster" "main" {
  name = var.eks_cluster_name
}

data "aws_redshift_cluster" "warehouse" {
  cluster_identifier = var.redshift_cluster_identifier
}

// ---------------------------------------------------------------- app identity
// IRSA: the pod assumes this role. No long-lived keys anywhere.
data "aws_iam_openid_connect_provider" "eks" {
  url = data.aws_eks_cluster.main.identity[0].oidc[0].issuer
}

resource "aws_iam_role" "app" {
  name = "case-spine-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = data.aws_iam_openid_connect_provider.eks.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${replace(data.aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub" = "system:serviceaccount:${var.namespace}:case-spine"
        }
      }
    }]
  })
}

// Read-only against the warehouse. The service has no write path to the case
// pipeline and must not acquire one - a write path, or any endpoint that
// dispositions a case, changes the regulatory regime.
resource "aws_iam_role_policy" "warehouse_read" {
  name = "warehouse-read"
  role = aws_iam_role.app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["redshift-data:ExecuteStatement", "redshift-data:GetStatementResult",
        "redshift-data:DescribeStatement"]
        Resource = data.aws_redshift_cluster.warehouse.arn
      },
      {
        Effect   = "Allow"
        Action   = ["redshift:GetClusterCredentialsWithIAM"]
        Resource = data.aws_redshift_cluster.warehouse.arn
        Condition = {
          StringEquals = { "redshift:DbUser" = "case_spine_ro" }
        }
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = aws_secretsmanager_secret.oidc.arn
      }
    ]
  })
}

// OIDC client secret for the existing identity provider. Role-scoped lenses map to
// IdP groups: Operations sees difficulty, Quality sees hazards and complaints,
// Engineering sees release effects, Field sees sites. Nobody gets the union.
resource "aws_secretsmanager_secret" "oidc" {
  name                    = "case-spine/${var.environment}/oidc"
  recovery_window_in_days = 7
}

// ---------------------------------------------------------------- workload
resource "kubernetes_service_account" "app" {
  metadata {
    name      = "case-spine"
    namespace = var.namespace
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.app.arn
    }
  }
}

resource "kubernetes_deployment" "app" {
  metadata {
    name      = "case-spine"
    namespace = var.namespace
    labels    = { app = "case-spine" }
  }

  spec {
    replicas = var.replicas

    selector { match_labels = { app = "case-spine" } }

    template {
      metadata { labels = { app = "case-spine" } }

      spec {
        service_account_name = kubernetes_service_account.app.metadata[0].name

        // Schedule onto existing node groups. Do not request new subnets.
        node_selector = var.node_selector

        security_context {
          run_as_non_root = true
          run_as_user     = 10001
          fs_group        = 10001
        }

        container {
          name  = "api"
          image = "${var.ecr_repository}:${var.image_tag}"

          port { container_port = 8000 }

          env {
            name  = "REDSHIFT_CLUSTER"
            value = data.aws_redshift_cluster.warehouse.cluster_identifier
          }
          env {
            name  = "OIDC_SECRET_ARN"
            value = aws_secretsmanager_secret.oidc.arn
          }

          security_context {
            allow_privilege_escalation = false
            read_only_root_filesystem  = true
            capabilities { drop = ["ALL"] }
          }

          resources {
            requests = { cpu = "250m", memory = "512Mi" }
            limits   = { cpu = "1000m", memory = "1Gi" }
          }

          liveness_probe {
            http_get {
              path = "/api/overview"
              port = 8000
            }
            initial_delay_seconds = 10
            period_seconds        = 30
          }
          readiness_probe {
            http_get {
              path = "/api/overview"
              port = 8000
            }
            initial_delay_seconds = 5
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "app" {
  metadata {
    name      = "case-spine"
    namespace = var.namespace
  }
  spec {
    selector = { app = "case-spine" }
    port {
      port        = 80
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

// Ingress attaches to the existing internal ALB. Internal only - this service is
// never internet-facing.
resource "kubernetes_ingress_v1" "app" {
  metadata {
    name      = "case-spine"
    namespace = var.namespace
    annotations = {
      "kubernetes.io/ingress.class"               = "alb"
      "alb.ingress.kubernetes.io/scheme"          = "internal"
      "alb.ingress.kubernetes.io/target-type"     = "ip"
      "alb.ingress.kubernetes.io/group.name"      = var.alb_group_name
      "alb.ingress.kubernetes.io/certificate-arn" = var.acm_certificate_arn
      "alb.ingress.kubernetes.io/ssl-redirect"    = "443"
    }
  }
  spec {
    rule {
      host = var.hostname
      http {
        path {
          path      = "/"
          path_type = "Prefix"
          backend {
            service {
              name = kubernetes_service.app.metadata[0].name
              port { number = 80 }
            }
          }
        }
      }
    }
  }
}
