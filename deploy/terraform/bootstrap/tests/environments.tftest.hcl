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
      aws_iam_policy.workload_boundary["prod"].name == "petbot-prod-workload-boundary",
      aws_iam_policy.workload_boundary["dev"].name == "petbot-dev-workload-boundary",
    ])
    error_message = "Each stage's role and boundary are named after it."
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
      strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions["prod"].statement), "function:petbot-prod-*"),
      !strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions["prod"].statement), "parameter/petbot/"),
      !strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions["dev"].statement), "parameter/petbot/"),
      !strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions["dev"].statement), "petbot-prod"),
      !strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions["prod"].statement), "petbot-dev"),
      !strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions["dev"].statement), "lightsail"),
    ])
    error_message = "Each stage's deploy role covers its own prefix and never reaches the other's."
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

run "deploy_roles_are_pinned_to_their_workflow" {
  command = plan

  assert {
    condition = alltrue([
      strcontains(jsonencode(data.aws_iam_policy_document.github_trust["deploy-dev"].statement), "auzbuzzard/petbot/.github/workflows/deploy.yml@*"),
      strcontains(jsonencode(data.aws_iam_policy_document.github_trust["deploy-prod"].statement), "auzbuzzard/petbot/.github/workflows/deploy.yml@*"),
      strcontains(jsonencode(data.aws_iam_policy_document.github_trust["deploy-dev"].statement), "StringLikeIfExists"),
      !strcontains(jsonencode(data.aws_iam_policy_document.github_trust["bootstrap-apply"].statement), "job_workflow_ref"),
    ])
    error_message = "Each deploy role trusts only its workflow file; the bootstrap pipeline roles are unchanged."
  }
}

run "a_stack_with_an_edge_may_delete_its_edge_user" {
  command = plan

  assert {
    condition = alltrue([
      for env in ["prod"] :
      strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions[env].statement), "iam:ListGroupsForUser")
    ])
    error_message = "Deleting the edge's IAM user needs iam:ListGroupsForUser: the provider removes its group memberships first."
  }
}
