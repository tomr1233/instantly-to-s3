import boto3
import pytest
from moto import mock_aws

from src.activities.s3 import upload_to_s3


BUCKET = "expressnext-workspace"


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    monkeypatch.setenv("S3_BUCKET_NAME", BUCKET)
    monkeypatch.setenv("INSTANTLY_API_KEY", "unused-for-these-tests")


async def test_upload_to_s3_puts_object(aws_env):
    with mock_aws():
        s3 = boto3.client("s3", region_name="ap-southeast-2")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-southeast-2"},
        )

        await upload_to_s3("# hello", "campaigns/instantly-campaigns/test 2026-04-20.md")

        obj = s3.get_object(
            Bucket=BUCKET, Key="campaigns/instantly-campaigns/test 2026-04-20.md"
        )
        assert obj["Body"].read().decode("utf-8") == "# hello"
        assert obj["ContentType"] == "text/markdown"


async def test_upload_to_s3_overwrites_existing_object(aws_env):
    with mock_aws():
        s3 = boto3.client("s3", region_name="ap-southeast-2")
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-southeast-2"},
        )
        key = "campaigns/instantly-campaigns/overwrite 2026-04-20.md"

        await upload_to_s3("first", key)
        await upload_to_s3("second", key)

        obj = s3.get_object(Bucket=BUCKET, Key=key)
        assert obj["Body"].read().decode("utf-8") == "second"
