import asyncio

import boto3
from temporalio import activity

from src.config import get_settings


def _put_object(content: str, key: str) -> None:
    settings = get_settings()
    client = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    client.put_object(
        Bucket=settings.s3_bucket_name,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType="text/markdown",
    )


@activity.defn
async def upload_to_s3(content: str, key: str) -> None:
    await asyncio.to_thread(_put_object, content, key)
