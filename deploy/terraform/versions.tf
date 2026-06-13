terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state in S3 with a DynamoDB lock table. The concrete bucket/table are
  # supplied at init time via `-backend-config=backend.hcl` (see README), so no
  # account-specific values are hard-coded here and `init -backend=false` works
  # in CI. Bootstrap the bucket/table once with deploy/terraform/bootstrap.
  backend "s3" {}
}
