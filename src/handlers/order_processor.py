import json
import os
import datetime
import boto3
from decimal import Decimal

TABLE_NAME = os.getenv("ORDERS_TABLE_NAME", "OrdersTable")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
ENDPOINT_URL = os.getenv("LOCALSTACK_ENDPOINT", None)

def get_dynamo_resource():
    if ENDPOINT_URL:
        return boto3.resource("dynamodb", region_name=AWS_REGION, endpoint_url=ENDPOINT_URL)
    return boto3.resource("dynamodb", region_name=AWS_REGION)

def lambda_handler(event, context):
    """
    SQS Event Trigger:
    Pulls batch of records from SQS queue, calculates pricing, and persists to DynamoDB.
    """
    dynamodb = get_dynamo_resource()
    table = dynamodb.Table(TABLE_NAME)
    processed_count = 0

    records = event.get("Records", [])
    for record in records:
        try:
            body = json.loads(record["body"])
            order_id = body["order_id"]
            customer_id = body["customer_id"]
            items = body.get("items", [])

            # Compute order total
            total_amount = Decimal("0.0")
            for item in items:
                price = Decimal(str(item.get("unit_price", 10.0)))
                qty = Decimal(str(item.get("quantity", 1)))
                total_amount += price * qty

            item_record = {
                "order_id": order_id,
                "customer_id": customer_id,
                "items": items,
                "total_amount": total_amount,
                "status": "PROCESSED",
                "processed_at": datetime.datetime.utcnow().isoformat(),
                "sqs_message_id": record.get("messageId", "mock-msg-id")
            }

            table.put_item(Item=item_record)
            processed_count += 1
            print(f"[SUCCESS] Processed order {order_id} for customer {customer_id} (Total: ${total_amount})")

        except Exception as e:
            print(f"[ERROR] Failed to process SQS record: {str(e)}")
            raise e

    return {
        "status": "COMPLETED",
        "processed_records": processed_count
    }

