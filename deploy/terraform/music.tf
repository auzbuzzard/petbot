# Future blocks, intentionally commented so they don't provision anything yet.
# Uncomment when the corresponding issue lands; both reuse the role/function
# defined in main.tf.

# --- Deferred-response self-invoke (#35) --------------------------------------
# The deferred-response path returns a type-5 ACK and then self-invokes the same
# function asynchronously to finish the work. That needs a scoped permission to
# invoke itself:
#
# resource "aws_iam_role_policy" "self_invoke" {
#   name = "${var.name_prefix}-self-invoke"
#   role = aws_iam_role.lambda.id
#
#   policy = jsonencode({
#     Version = "2012-10-17"
#     Statement = [{
#       Effect   = "Allow"
#       Action   = "lambda:InvokeFunction"
#       Resource = aws_lambda_function.this.arn
#     }]
#   })
# }

# --- Music remote-skill bus (#33) ---------------------------------------------
# Music runs as a cluster worker fed by an SQS queue; the Lambda enqueues jobs,
# the worker pulls them (no inbound to home). Activated by #33.
#
# resource "aws_sqs_queue" "music_jobs" {
#   name                       = "${var.name_prefix}-music-jobs"
#   message_retention_seconds  = 3600
#   visibility_timeout_seconds = 300
# }
#
# resource "aws_iam_role_policy" "music_enqueue" {
#   name = "${var.name_prefix}-music-enqueue"
#   role = aws_iam_role.lambda.id
#
#   policy = jsonencode({
#     Version = "2012-10-17"
#     Statement = [{
#       Effect   = "Allow"
#       Action   = "sqs:SendMessage"
#       Resource = aws_sqs_queue.music_jobs.arn
#     }]
#   })
# }
