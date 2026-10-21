terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    # time_rotating: the edge access key's rotation schedule (edge.tf).
    time = {
      source  = "hashicorp/time"
      version = "~> 0.13"
    }
  }

  # Remote state in S3 with native S3 locking (`use_lockfile`, GA since
  # Terraform 1.11 — no DynamoDB table needed). The concrete bucket/key are
  # supplied at init time via `-backend-config=backend.hcl` (see README), so no
  # account-specific values are hard-coded here and `init -backend=false` works
  # in CI. The bucket is managed by deploy/terraform/bootstrap.
  backend "s3" {}
}
