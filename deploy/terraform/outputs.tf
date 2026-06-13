output "function_url" {
  description = "Public HTTPS endpoint. Paste into Discord's Interactions Endpoint URL (#31)."
  value       = aws_lambda_function_url.this.function_url
}

output "ecr_repository_url" {
  description = "Push the Lambda image here before the main apply."
  value       = aws_ecr_repository.this.repository_url
}

output "lambda_function_name" {
  description = "Name of the deployed interactions function."
  value       = aws_lambda_function.this.function_name
}
