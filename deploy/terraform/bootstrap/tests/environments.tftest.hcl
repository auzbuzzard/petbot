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

run "each_ci_role_trusts_only_deploy_yml_in_this_repository" {
  command = plan

  assert {
    condition = alltrue([
      for role, expected in {
        "deploy-prod" = [
          "StringEquals token.actions.githubusercontent.com:sub repo:auzbuzzard/petbot:environment:production",
          "StringLike token.actions.githubusercontent.com:job_workflow_ref auzbuzzard/petbot/.github/workflows/deploy.yml@refs/heads/main",
          "StringEquals token.actions.githubusercontent.com:ref refs/heads/main",
        ]
        "deploy-dev" = [
          "StringEquals token.actions.githubusercontent.com:sub repo:auzbuzzard/petbot:environment:dev",
          "StringLike token.actions.githubusercontent.com:job_workflow_ref auzbuzzard/petbot/.github/workflows/deploy.yml@*",
        ]
        "bootstrap-plan" = [
          "StringEquals token.actions.githubusercontent.com:sub repo:auzbuzzard/petbot:environment:bootstrap-plan",
          "StringLike token.actions.githubusercontent.com:job_workflow_ref auzbuzzard/petbot/.github/workflows/deploy.yml@*",
        ]
        "bootstrap-apply" = [
          "StringEquals token.actions.githubusercontent.com:sub repo:auzbuzzard/petbot:environment:bootstrap",
          "StringLike token.actions.githubusercontent.com:job_workflow_ref auzbuzzard/petbot/.github/workflows/deploy.yml@refs/heads/main",
          "StringEquals token.actions.githubusercontent.com:ref refs/heads/main",
        ]
      } :
      toset(flatten([
        for s in data.aws_iam_policy_document.github_trust[role].statement : [
          for c in s.condition : "${c.test} ${c.variable} ${join(",", c.values)}"
        ]
        ])) == toset(concat(expected, [
        "StringEquals token.actions.githubusercontent.com:aud sts.amazonaws.com",
        "StringEquals token.actions.githubusercontent.com:repository_id 129497244",
      ]))
    ])
    error_message = "Each CI role trusts its environment and deploy.yml in this repository (by ID); the prod deploy and bootstrap apply roles only from main."
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


run "deploy_roles_create_only_their_stacks_principals" {
  command = plan

  assert {
    condition = alltrue([
      for env in ["prod", "dev"] :
      join(" ", flatten([for s in data.aws_iam_policy_document.deploy_permissions[env].statement : tolist(s.resources) if s.sid == "ManageStackRoles"])) == "arn:aws:iam::123456789012:role/petbot-${env}-core-role"
    ])
    error_message = "A deploy role may create, and grant permissions to, only its stack's core role."
  }

  assert {
    condition = alltrue([
      join(" ", flatten([for s in data.aws_iam_policy_document.deploy_permissions["prod"].statement : tolist(s.resources) if s.sid == "ManageStackUsers"])) == "arn:aws:iam::123456789012:user/petbot-prod-edge",
      join(" ", flatten([for s in data.aws_iam_policy_document.deploy_permissions["prod"].statement : tolist(s.resources) if s.sid == "CreateStackUserKeys"])) == "arn:aws:iam::123456789012:user/petbot-prod-edge",
      length([for s in data.aws_iam_policy_document.deploy_permissions["prod"].statement : s.sid if s.sid != "CreateStackUserKeys" && contains(s.actions, "iam:CreateAccessKey")]) == 0,
      !strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions["dev"].statement), "iam:CreateUser"),
      !strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions["dev"].statement), "iam:CreateAccessKey"),
    ])
    error_message = "Only a stack with the edge may create a user and its keys, and only the edge's."
  }
}

run "deploy_roles_attach_no_resource_policies" {
  command = plan

  assert {
    condition = alltrue([
      for env in ["prod", "dev"] : length([
        for s in data.aws_iam_policy_document.deploy_permissions[env].statement : s.sid
        if s.sid == "DenyResourcePolicies" && s.effect == "Deny" && s.resources == toset(["*"]) && length(setsubtract([
          "lambda:AddPermission",
          "lambda:CreateFunctionUrlConfig",
          "lambda:UpdateFunctionUrlConfig",
          "lambda:PutResourcePolicy",
          "dynamodb:PutResourcePolicy",
          "logs:PutSubscriptionFilter",
        ], s.actions)) == 0
      ]) == 1
    ])
    error_message = "Each deploy role is denied the resource-policy actions the stack never uses."
  }

  assert {
    condition = alltrue([
      join(" ", flatten([for s in data.aws_iam_policy_document.deploy_permissions["prod"].statement : tolist(s.not_resources) if s.sid == "DenyRepositoryPolicies" && s.effect == "Deny"])) == "arn:aws:ecr:us-east-1:123456789012:repository/petbot-prod-edge",
      join(" ", flatten([for s in data.aws_iam_policy_document.deploy_permissions["dev"].statement : tolist(s.resources) if s.sid == "DenyRepositoryPolicies" && s.effect == "Deny"])) == "*",
    ])
    error_message = "Only the edge's repository may have a policy, and only where the stack runs the edge."
  }
}

run "deploy_roles_manage_only_their_own_budget" {
  command = plan

  assert {
    condition = alltrue([
      join(" ", flatten([for s in data.aws_iam_policy_document.deploy_permissions["prod"].statement : tolist(s.resources) if s.sid == "ManageBudget"])) == "arn:aws:budgets::123456789012:budget/petbot-prod-monthly",
      !strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions["dev"].statement), "budgets:"),
    ])
    error_message = "A deploy role manages its own stack's budget only."
  }
}

run "deploy_roles_list_only_the_workspace_prefix" {
  command = plan

  assert {
    condition = alltrue([
      for env in ["prod", "dev"] :
      join(" ", flatten([
        for s in data.aws_iam_policy_document.deploy_permissions[env].statement : [
          for c in s.condition : "${c.test} ${c.variable} ${join(",", c.values)}"
        ] if s.sid == "ListState"
      ])) == "StringEquals s3:prefix env:/"
    ])
    error_message = "A deploy role lists the state bucket only under the backend's workspace prefix."
  }
}

run "workloads_write_their_own_logs_and_invoke_regional_models" {
  command = plan

  assert {
    condition = alltrue(flatten([
      for env in ["prod", "dev"] : [
        join(" ", flatten([for s in data.aws_iam_policy_document.workload_boundary[env].statement : tolist(s.resources) if s.sid == "WriteLogs"])) == "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/petbot-${env}-*",
        join(" ", sort(flatten([for s in data.aws_iam_policy_document.workload_boundary[env].statement : tolist(s.resources) if s.sid == "InvokeModels"]))) == "arn:aws:bedrock:us-east-1:123456789012:inference-profile/* arn:aws:bedrock:us-east-1::foundation-model/*",
      ]
    ]))
    error_message = "A workload may write only its stack's Lambda logs and invoke only the models the root stack grants."
  }
}

run "the_operator_reads_only_stack_query_results_and_budgets" {
  command = plan

  assert {
    condition = alltrue([
      contains(flatten([for s in data.aws_iam_policy_document.operator_permissions.statement : tolist(s.actions) if s.sid == "ReadStackLogs"]), "logs:GetQueryResults"),
      length([
        for s in data.aws_iam_policy_document.operator_permissions.statement : s.sid
        if contains(s.resources, "*") && length(setintersection(s.actions, ["logs:GetQueryResults", "ecr:DescribeRepositories", "budgets:ViewBudget"])) > 0
      ]) == 0,
      join(" ", flatten([for s in data.aws_iam_policy_document.operator_permissions.statement : tolist(s.resources) if s.sid == "ReadStackBudgets"])) == "arn:aws:budgets::123456789012:budget/petbot-*",
    ])
    error_message = "The operator reads query results, repositories and budgets of the stacks only."
  }
}

run "the_operator_cannot_read_container_environments" {
  command = plan

  assert {
    condition = alltrue([
      strcontains(jsonencode(data.aws_iam_policy_document.operator_permissions.statement), "lightsail:GetContainerLog"),
      !strcontains(jsonencode(data.aws_iam_policy_document.operator_permissions.statement), "lightsail:GetContainerServices"),
      !strcontains(jsonencode(data.aws_iam_policy_document.operator_permissions.statement), "lightsail:GetContainerServiceDeployments"),
    ])
    error_message = "The operator may read the edge's logs but not its container environment, which holds the edge's AWS key."
  }
}

run "deploy_roles_cannot_replace_a_role" {
  command = plan

  assert {
    condition = alltrue([
      for env in ["prod", "dev"] : alltrue([
        for s in data.aws_iam_policy_document.deploy_permissions[env].statement :
        s.effect == "Deny" || length(setintersection(s.actions, ["iam:DeleteRole", "iam:UpdateAssumeRolePolicy", "iam:*"])) == 0
      ])
    ])
    error_message = "No deploy role may delete a role or change its trust: a stack's role keeps the trust it was created with."
  }
}

run "the_edge_deploy_role_changes_only_its_own_tagged_container_service" {
  command = plan

  assert {
    condition = alltrue([
      !strcontains(jsonencode(data.aws_iam_policy_document.deploy_permissions["prod"].statement), "lightsail:*"),
      join(" ", flatten([
        for s in data.aws_iam_policy_document.deploy_permissions["prod"].statement : [
          for c in s.condition : "${c.test} ${c.variable} ${join(",", c.values)}"
        ] if s.sid == "ManageEdgeContainerService"
      ])) == "StringEquals aws:ResourceTag/Stack petbot-prod",
      join(" ", flatten([
        for s in data.aws_iam_policy_document.deploy_permissions["prod"].statement : [
          for c in s.condition : "${c.test} ${c.variable} ${join(",", c.values)}"
        ] if s.sid == "CreateEdgeContainerService"
      ])) == "StringEquals aws:RequestTag/Stack petbot-prod",
      toset(flatten([
        for s in data.aws_iam_policy_document.deploy_permissions["prod"].statement : [
          for c in s.condition : "${c.test} ${c.variable} ${join(",", c.values)}"
        ] if s.sid == "TagUntaggedEdgeContainerService"
        ])) == toset([
        "StringEquals aws:ResourceTag/Project petbot",
        "Null aws:ResourceTag/Stack true",
        "StringEquals aws:RequestTag/Stack petbot-prod",
        "ForAllValues:StringEquals aws:TagKeys Stack",
      ]),
      length([
        for s in data.aws_iam_policy_document.deploy_permissions["prod"].statement : s.sid
        if anytrue([for a in s.actions : startswith(a, "lightsail:")]) && length(s.condition) == 0 && s.sid != "ReadContainerServices"
      ]) == 0,
      toset(flatten([for s in data.aws_iam_policy_document.deploy_permissions["prod"].statement : tolist(s.actions) if s.sid == "ReadContainerServices"])) == toset([
        "lightsail:GetContainerServices",
        "lightsail:GetContainerServiceDeployments",
        "lightsail:GetContainerLog",
      ]),
    ])
    error_message = "The prod deploy role reads container services and changes only the one tagged with its stack."
  }
}

run "workloads_publish_telemetry_only_where_observability_is_on" {
  command = plan

  assert {
    condition = alltrue([
      for env in ["prod", "dev"] :
      !strcontains(aws_iam_policy.workload_boundary[env].policy, "xray:") && !strcontains(aws_iam_policy.workload_boundary[env].policy, "cloudwatch:PutMetricData")
    ])
    error_message = "No stage turns on observability, so no boundary allows telemetry."
  }
}

run "a_stage_with_observability_may_publish_telemetry" {
  command = plan

  variables {
    environments = {
      prod = { name_prefix = "petbot-prod", github_environment = "production", observability = true }
      dev  = { name_prefix = "petbot-dev", github_environment = "dev", edge = false, budget = false, main_only = false }
    }
  }

  assert {
    condition = alltrue([
      strcontains(aws_iam_policy.workload_boundary["prod"].policy, "xray:PutTraceSegments"),
      !strcontains(aws_iam_policy.workload_boundary["dev"].policy, "xray:"),
    ])
    error_message = "Only a stage with observability = true lets its workloads publish telemetry."
  }
}

run "only_a_stages_deploy_role_touches_its_state" {
  command = plan

  assert {
    condition = alltrue([
      for env in ["prod", "dev"] : length([
        for s in data.aws_iam_policy_document.state_bucket.statement : s.sid
        if s.effect == "Deny" && s.actions == toset(["s3:*"])
        && s.resources == toset(["arn:aws:s3:::tfstate-test/petbot-${env}/*"])
        && join(" ", flatten([for c in s.condition : "${c.test} ${c.variable} ${join(",", c.values)}"])) == "ArnNotEquals aws:PrincipalArn arn:aws:iam::123456789012:role/petbot-github-deploy-${env}"
      ]) == 1
    ])
    error_message = "The state bucket denies a stage's state to every principal but that stage's deploy role."
  }
}

run "the_plan_role_only_reads" {
  command = plan

  assert {
    condition = alltrue([
      for s in data.aws_iam_policy_document.bootstrap_read.statement : alltrue([
        for a in s.actions : anytrue([for prefix in ["s3:Get", "s3:List", "iam:Get", "iam:List"] : startswith(a, prefix)])
      ])
    ])
    error_message = "The bootstrap plan role, which pull requests assume, may only read."
  }
}
