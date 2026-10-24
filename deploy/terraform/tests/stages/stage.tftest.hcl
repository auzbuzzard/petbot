# Plans one stage file offline. .github/scripts/check-stage-files.sh runs it per stage, with
# -var-file=stages/<stage>.tfvars and that stage's name_prefix, so the real file is checked
# against the stack's variable types, validations and preconditions (its copied
# parameters aside, below). The AWS provider has
# fake credentials and makes no calls (the account ID and the image digest are overridden).

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "mock"
  secret_key                  = "mock"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

mock_provider "time" {}

override_data {
  target = data.aws_caller_identity.current
  values = { account_id = "123456789012" }
}

override_data {
  target = data.aws_ecr_image.this
  values = { image_digest = "sha256:0000000000000000000000000000000000000000000000000000000000000000" }
}

# The whole stack plans with the file's settings, its preconditions included, except its
# copied parameters (ssm_parameters): their source reads are ephemeral, which call AWS even
# in a plan and which mocks don't support. Those names are checked by their variable's
# validation when the stage deploys.
run "plans" {
  command = plan

  variables {
    ssm_parameters = {}
  }
}
