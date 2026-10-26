# Plans the stack offline for each kind of environment: production runs the edge; a dev core
# runs alone, on the mantle endpoint with its own IAM role and no key. The AWS provider has
# fake credentials and makes no calls (the account ID and the image digest are overridden);
# the IAM documents render from this code.

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

variables {
  chat_llm_model    = "google.gemma-4-31b"
  chat_llm_base_url = "https://bedrock-mantle.us-east-1.api.aws/openai/v1"
}

run "production_runs_the_edge_on_a_keyed_model" {
  command = plan

  variables {
    chat_llm_kind                  = "openai_compatible"
    chat_llm_api_key_ssm_parameter = "/petbot-prod/core/bedrock_api_key"
    edge_image_tag                 = "abc123"
  }

  assert {
    condition = alltrue([
      length(aws_lightsail_container_service.edge) == 1,
      length(aws_lightsail_container_service_deployment_version.edge) == 1,
      length(aws_iam_user.edge) == 1,
      length(aws_iam_access_key.edge) == 1,
      length(aws_dynamodb_table.claims) == 1,
      length(aws_ecr_repository.edge) == 1,
    ])
    error_message = "Production must run the edge."
  }

  assert {
    condition     = length(aws_iam_role_policy.bedrock_mantle) == 0
    error_message = "A keyed provider gets no mantle grant."
  }

  assert {
    condition     = jsondecode(aws_lambda_function.this.environment[0].variables.SSM_SECRETS).CHAT_LLM__API_KEY == "/petbot-prod/core/bedrock_api_key"
    error_message = "A keyed provider reads its key from SSM."
  }

  assert {
    condition = alltrue([
      aws_lambda_function.this.function_name == "petbot-prod-core",
      aws_lightsail_container_service.edge[0].name == "petbot-prod-edge",
      aws_dynamodb_table.claims[0].name == "petbot-prod-edge-claims",
      aws_iam_role.lambda.permissions_boundary == "arn:aws:iam::123456789012:policy/petbot-prod-workload-boundary",
    ])
    error_message = "Production's resources are petbot-prod-*, under its own boundary."
  }

  assert {
    condition     = local.edge_secret_parameters.DISCORD_TOKEN == "/petbot-prod/edge/discord_token"
    error_message = "The edge reads its Discord token from under its own prefix."
  }

  assert {
    condition = alltrue([
      aws_iam_role.lambda.name == "petbot-prod-core-role",
      aws_iam_user.edge[0].name == "petbot-prod-edge",
    ])
    error_message = "The stack's IAM principals keep the exact names its deploy role may create (bootstrap's stack_role_names and stack_user_names)."
  }

  assert {
    condition     = aws_lightsail_container_service.edge[0].tags.Stack == "petbot-prod"
    error_message = "The edge's container service is tagged with its stack."
  }
}

run "a_dev_core_runs_alone_with_no_key" {
  command = plan

  variables {
    name_prefix        = "petbot-dev"
    lambda_environment = "dev"
    chat_llm_kind      = "bedrock_mantle"
    edge_enabled       = false
    edge_image_tag     = "abc123"
  }

  assert {
    condition = alltrue([
      length(aws_lightsail_container_service.edge) == 0,
      length(aws_lightsail_container_service_deployment_version.edge) == 0,
      length(aws_iam_user.edge) == 0,
      length(aws_iam_access_key.edge) == 0,
      length(aws_dynamodb_table.claims) == 0,
      length(aws_ecr_repository.edge) == 0,
      output.edge_container_service_name == null,
    ])
    error_message = "A stack without the edge must create none of it."
  }

  assert {
    condition     = aws_lambda_function.this.function_name == "petbot-dev-core" && aws_iam_role.lambda.name == "petbot-dev-core-role"
    error_message = "The dev core and its role are named after its prefix."
  }

  assert {
    condition     = jsondecode(aws_iam_role_policy.bedrock_mantle[0].policy).Statement[0].Action == "bedrock-mantle:CreateInference"
    error_message = "The dev core's role may call the mantle endpoint."
  }

  assert {
    condition     = !contains(keys(aws_lambda_function.this.environment[0].variables), "SSM_SECRETS")
    error_message = "A dev core with no optional keys reads no secrets."
  }

  assert {
    condition     = aws_lambda_function.this.environment[0].variables.CHAT_LLM__KIND == "bedrock_mantle"
    error_message = "The dev core signs its model calls."
  }
}

run "mantle_needs_its_endpoint" {
  command = plan

  variables {
    chat_llm_kind     = "bedrock_mantle"
    chat_llm_base_url = ""
    edge_enabled      = false
  }

  expect_failures = [aws_lambda_function.this]
}

run "a_parameter_outside_the_prefix_is_rejected" {
  command = plan

  variables {
    chat_llm_kind  = "bedrock_mantle"
    edge_enabled   = false
    ssm_parameters = { "/petbot-dev/edge/discord_token" = "" }
  }

  expect_failures = [var.ssm_parameters]
}

run "the_edge_can_be_paused_in_place" {
  command = plan

  variables {
    chat_llm_kind = "bedrock_mantle"
    edge_paused   = true
  }

  assert {
    condition     = aws_lightsail_container_service.edge[0].is_disabled
    error_message = "Pausing disables the edge's service."
  }
}
