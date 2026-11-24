import json
import pytest
import boto3
from moto import mock_aws
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR / "src"))

from handlers.order_ingest import lambda_handler as ingest_handler
from handlers.order_processor import lambda_handler as processor_handler
from handlers.notification_dispatcher import lambda_handler as notification_handler

@pytest.fixture
def aws_credentials():
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["ORDERS_QUEUE_URL"] = "http://localhost:4566/mock-queue"
    os.environ["ORDERS_TABLE_NAME"] = "OrdersTable"

def test_order_ingest_success(aws_credentials):
    with mock_aws():
        sqs = boto3.client("sqs", region_name="us-east-1")
        queue = sqs.create_queue(QueueName="test-orders-queue")
        os.environ["ORDERS_QUEUE_URL"] = queue["QueueUrl"]

        event = {
            "body": json.dumps({
                "customer_id": "CUST-994",
                "items": [{"item_id": "prod-1", "quantity": 2, "unit_price": 50.0}]
            })
        }
        response = ingest_handler(event, None)
        assert response["statusCode"] == 202
        body = json.loads(response["body"])
        assert "order_id" in body

def test_order_ingest_missing_fields(aws_credentials):
    event = {"body": json.dumps({})}
    response = ingest_handler(event, None)
    assert response["statusCode"] == 400

def test_order_processor(aws_credentials):
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="OrdersTable",
            KeySchema=[
                {"AttributeName": "order_id", "KeyType": "HASH"},
                {"AttributeName": "customer_id", "KeyType": "RANGE"}
            ],
            AttributeDefinitions=[
                {"AttributeName": "order_id", "AttributeType": "S"},
                {"AttributeName": "customer_id", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST"
        )

        sqs_event = {
            "Records": [{
                "messageId": "msg-001",
                "body": json.dumps({
                    "order_id": "ORDER-XYZ",
                    "customer_id": "CUST-100",
                    "items": [{"item_id": "p1", "quantity": 2, "unit_price": 30.0}]
                })
            }]
        }

        result = processor_handler(sqs_event, None)
        assert result["status"] == "COMPLETED"
        assert result["processed_records"] == 1

        # Check item in DynamoDB
        item = table.get_item(Key={"order_id": "ORDER-XYZ", "customer_id": "CUST-100"}).get("Item")
        assert item is not None
        assert float(item["total_amount"]) == 60.0

