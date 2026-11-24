variable "aws_region" {
  type        = string
  description = "AWS deployment region"
  default     = "us-east-1"
}

variable "environment" {
  type        = string
  description = "Deployment environment name"
  default     = "production"
}

variable "table_name" {
  type        = string
  description = "DynamoDB Orders Table Name"
  default     = "ServerlessOrders"
}

variable "queue_name" {
  type        = string
  description = "SQS Orders Queue Name"
  default     = "serverless-orders-queue"
}

