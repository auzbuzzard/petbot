# Plans the root of trust offline: a provider with fake credentials that makes no calls
# (the account ID and the ARNs of resources not yet created are overridden), so the IAM
# documents render from this code alone.

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "mock"
  secret_key                  = "mock"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

variables {
  state_bucket = "tfstate-test"
}

override_data {
  target = data.aws_caller_identity.current
  values = { account_id = "123456789012" }
}

override_resource {
  target          = aws_s3_bucket.state
  override_during = plan
  values          = { arn = "arn:aws:s3:::tfstate-test", id = "tfstate-test" }
}

override_resource {
  target          = aws_iam_openid_connect_provider.github
  override_during = plan
  values          = { arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" }
}

override_resource {
  target          = aws_iam_role.operator
  override_during = plan
  values          = { arn = "arn:aws:iam::123456789012:role/petbot-operator" }
}

override_resource {
  target          = aws_iam_user.operator
  override_during = plan
  values          = { arn = "arn:aws:iam::123456789012:user/claude" }
}

override_resource {
  target          = aws_iam_policy.workload_boundary
  override_during = plan
  values          = { arn = "arn:aws:iam::123456789012:policy/BOUNDARY" }
}

run "each_stage_gets_its_own_role_and_boundary" {
  command = plan

  assert {
    condition = alltrue([
      aws_iam_role.github_deploy["prod"].name == "petbot-github-deploy-prod",
      aws_iam_role.github_deploy["dev"].name == "petbot-github-deploy-dev",
      aws_iam_role.github_deploy["legacy"].name == "petbot-github-deploy",
      aws_iam_policy.workload_boundary["prod"].name == "petbot-prod-workload-boundary",
      aws_iam_policy.workload_boundary["dev"].name == "petbot-dev-workload-boundary",
      aws_iam_policy.workload_boundary["legacy"].name == "petbot-workload-boundary",
    ])
    error_message = "Each stage's role and boundary are named after it; legacy keeps its names."
  }

  assert {
    condition = alltrue([
      strcontains(aws_iam_policy.workload_boundary["prod"].policy, "parameter/petbot-prod/*"),
      !strcontains(aws_iam_policy.workload_boundary["prod"].policy, "petbot-dev"),
      strcontains(aws_iam_policy.workload_boundary["dev"].policy, "parameter/petbot-dev/*"),
      !strcontains(aws_iam_policy.workload_boundary["dev"].policy, "petbot-prod"),
      strcontains(aws_iam_policy.workload_boundary["dev"].policy, "bedrock-mantle:CreateInference"),
    ])
    error_message = "Each boundary covers its own stage only."
  }

  assert {
    condition = alltrue([
      strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions["prod"].statement), "parameter/petbot/edge/discord_token"),
      !strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions["dev"].statement), "parameter/petbot/"),
      !strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions["dev"].statement), "petbot-prod"),
      !strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions["prod"].statement), "petbot-dev"),
      !strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions["dev"].statement), "lightsail"),
    ])
    error_message = "Prod may read only the legacy token it adopts; neither stage's deploy role reaches the other."
  }

  assert {
    condition     = strcontains(jsonencode(data.aws_iam_policy_document.bootstrap_apply.statement), "user/petbot-bedrock-key")
    error_message = "Bootstrap's pipeline may manage the user it retires."
  }
}

run "a_prefix_containing_another_is_rejected" {
  command = plan

  variables {
    environments = {
      prod = { name_prefix = "petbot", github_environment = "production" }
      dev  = { name_prefix = "petbot-dev", github_environment = "dev" }
    }
  }

  expect_failures = [var.environments]
}

run "legacy_may_contain_the_stages" {
  command = plan

  variables {
    environments = {
      prod   = { name_prefix = "petbot-prod", github_environment = "production" }
      legacy = { name_prefix = "petbot", github_environment = "production", legacy = true }
    }
  }
}
