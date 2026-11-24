terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# 1. DynamoDB Table for Order Storage
resource "aws_dynamodb_table" "orders_table" {
  name             = var.table_name
  billing_mode     = "PAY_PER_REQUEST"
  hash_key         = "order_id"
  range_key        = "customer_id"
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  attribute {
    name = "order_id"
    type = "S"
  }

  attribute {
    name = "customer_id"
    type = "S"
  }

  tags = {
    Environment = var.environment
    Architecture = "Serverless"
  }
}

# 2. SQS Dead-Letter Queue & Main Queue
resource "aws_sqs_queue" "orders_dlq" {
  name                      = "${var.queue_name}-dlq"
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_sqs_queue" "orders_queue" {
  name                       = var.queue_name
  visibility_timeout_seconds = 60
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.orders_dlq.arn
    maxReceiveCount     = 3
  })
}

# 3. SNS Topic for Notifications
resource "aws_sns_topic" "notifications_topic" {
  name = "order-notifications-topic"
}

# 4. IAM Role for Lambda Functions
resource "aws_iam_role" "lambda_exec_role" {
  name = "serverless_lambda_execution_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "serverless_lambda_permissions"
  role = aws_iam_role.lambda_exec_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Effect   = "Allow"
        Resource = aws_sqs_queue.orders_queue.arn
      },
      {
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:DescribeStream",
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:ListStreams"
        ]
        Effect   = "Allow"
        Resource = [aws_dynamodb_table.orders_table.arn, "${aws_dynamodb_table.orders_table.arn}/*"]
      },
      {
        Action = [
          "sns:Publish"
        ]
        Effect   = "Allow"
        Resource = aws_sns_topic.notifications_topic.arn
      },
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# Zip packaging for Lambdas
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/lambda_payload.zip"
}

# Lambda 1: Order Ingest
resource "aws_lambda_function" "order_ingest" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "order-ingest-function"
  role             = aws_iam_role.lambda_exec_role.arn
  handler          = "handlers.order_ingest.lambda_handler"
  runtime          = "python3.11"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      ORDERS_QUEUE_URL = aws_sqs_queue.orders_queue.id
    }
  }
}

# Lambda 2: Order Processor (SQS Triggered)
resource "aws_lambda_function" "order_processor" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "order-processor-function"
  role             = aws_iam_role.lambda_exec_role.arn
  handler          = "handlers.order_processor.lambda_handler"
  runtime          = "python3.11"
  timeout          = 30
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      ORDERS_TABLE_NAME = aws_dynamodb_table.orders_table.name
    }
  }
}

resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.orders_queue.arn
  function_name    = aws_lambda_function.order_processor.arn
  batch_size       = 10
}

# Lambda 3: Notification Dispatcher (DynamoDB Stream Triggered)
resource "aws_lambda_function" "notification_dispatcher" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "notification-dispatcher-function"
  role             = aws_iam_role.lambda_exec_role.arn
  handler          = "handlers.notification_dispatcher.lambda_handler"
  runtime          = "python3.11"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      NOTIFICATIONS_TOPIC_ARN = aws_sns_topic.notifications_topic.arn
    }
  }
}

resource "aws_lambda_event_source_mapping" "dynamo_stream_trigger" {
  event_source_arn  = aws_dynamodb_table.orders_table.stream_arn
  function_name     = aws_lambda_function.notification_dispatcher.arn
  starting_position = "LATEST"
}

# API Gateway HTTP API
resource "aws_apigatewayv2_api" "http_api" {
  name          = "serverless-order-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda_integration" {
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.order_ingest.invoke_arn
}

resource "aws_apigatewayv2_route" "order_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /orders"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

resource "aws_apigatewayv2_stage" "default_stage" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = "$default"
  auto_deploy = true
}

