import json
import os
import boto3

TOPIC_ARN = os.getenv("NOTIFICATIONS_TOPIC_ARN", "")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
ENDPOINT_URL = os.getenv("LOCALSTACK_ENDPOINT", None)

def get_sns_client():
    if ENDPOINT_URL:
        return boto3.client("sns", region_name=AWS_REGION, endpoint_url=ENDPOINT_URL)
    return boto3.client("sns", region_name=AWS_REGION)

def lambda_handler(event, context):
    """
    DynamoDB Stream or Direct Notification Handler:
    Sends real-time email / push notification via Amazon SNS upon order persistence.
    """
    sns = get_sns_client()
    dispatched = 0

    records = event.get("Records", [])
    for record in records:
        event_name = record.get("eventName", "INSERT")
        if event_name in ["INSERT", "MODIFY"]:
            new_image = record.get("dynamodb", {}).get("NewImage", {})
            order_id = new_image.get("order_id", {}).get("S", "UNKNOWN")
            customer_id = new_image.get("customer_id", {}).get("S", "UNKNOWN")
            status = new_image.get("status", {}).get("S", "CONFIRMED")

            message_payload = {
                "event": "OrderNotification",
                "order_id": order_id,
                "customer_id": customer_id,
                "order_status": status,
                "message": f"Hello {customer_id}, your order {order_id} has been successfully processed!"
            }

            if TOPIC_ARN:
                sns.publish(
                    TopicArn=TOPIC_ARN,
                    Message=json.dumps(message_payload),
                    Subject=f"Order Update: {order_id}"
                )

            print(f"[NOTIFICATION DISPATCHED] Order: {order_id} to Customer: {customer_id}")
            dispatched += 1

    return {"dispatched_notifications": dispatched}

