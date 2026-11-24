output "api_endpoint" {
  description = "HTTP API Gateway URL endpoint"
  value       = aws_apigatewayv2_stage.default_stage.invoke_url
}

output "dynamodb_table_arn" {
  description = "DynamoDB Orders Table ARN"
  value       = aws_dynamodb_table.orders_table.arn
}

output "sqs_queue_url" {
  description = "SQS Queue URL"
  value       = aws_sqs_queue.orders_queue.id
}

output "sns_topic_arn" {
  description = "SNS Notifications Topic ARN"
  value       = aws_sns_topic.notifications_topic.arn
}

