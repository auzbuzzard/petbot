provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "petbot"
      Component = "edge-and-core-worker"
      ManagedBy = "terraform"
    }
  }
}
