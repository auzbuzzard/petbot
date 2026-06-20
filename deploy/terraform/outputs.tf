output "core_function_name" {
  description = "Name of the core worker Lambda (the edge's WORKER__FUNCTION_NAME)."
  value       = aws_lambda_function.this.function_name
}

output "core_function_arn" {
  description = "ARN of the core worker Lambda; the edge's IAM user is granted lambda:InvokeFunction on it."
  value       = aws_lambda_function.this.arn
}

output "ecr_repository_url" {
  description = "Push the core worker Lambda image here before the main apply."
  value       = aws_ecr_repository.this.repository_url
}

output "edge_ecr_repository_url" {
  description = "Push the edge image here; the host (Lightsail or Fargate) pulls it from this repo."
  value       = aws_ecr_repository.edge.repository_url
}

output "edge_host" {
  description = "Where the edge runs: lightsail or fargate."
  value       = var.edge_host
}

output "edge_service_name" {
  description = "Name of the edge service on whichever host is active (empty until an image is deployed)."
  value = (
    var.edge_host == "lightsail"
    ? try(aws_lightsail_container_service.edge[0].name, "")
    : try(aws_ecs_service.edge[0].name, "")
  )
}
