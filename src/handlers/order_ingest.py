import json
import os
import uuid
import datetime
import boto3

# Environment variables
QUEUE_URL = os.getenv("ORDERS_QUEUE_URL", "http://localhost:4566/000000000000/orders-queue")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
ENDPOINT_URL = os.getenv("LOCALSTACK_ENDPOINT", None)

def get_sqs_client():
    if ENDPOINT_URL:
        return boto3.client("sqs", region_name=AWS_REGION, endpoint_url=ENDPOINT_URL)
    return boto3.client("sqs", region_name=AWS_REGION)

def lambda_handler(event, context):
    """
    HTTP API Gateway entrypoint:
    Validates incoming order request and publishes an event message to SQS queue.
    """
    try:
        body = event.get("body")
        if isinstance(body, str):
            payload = json.loads(body)
        elif isinstance(body, dict):
            payload = body
        else:
            payload = event

        # Validation
        customer_id = payload.get("customer_id")
        items = payload.get("items", [])
        
        if not customer_id or not items:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Missing required fields: customer_id or items"})
            }

        order_id = f"ORDER-{uuid.uuid4().hex[:8].upper()}"
        order_event = {
            "order_id": order_id,
            "customer_id": customer_id,
            "items": items,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "status": "QUEUED"
        }

        # Send to SQS
        sqs = get_sqs_client()
        response = sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps(order_event),
            MessageAttributes={
                "EventType": {
                    "DataType": "String",
                    "StringValue": "OrderCreated"
                }
            }
        )

        return {
            "statusCode": 202,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "message": "Order successfully accepted and enqueued for asynchronous processing",
                "order_id": order_id,
                "sqs_message_id": response.get("MessageId")
            })
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)})
        }

