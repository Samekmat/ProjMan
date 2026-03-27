import aioboto3

from src.core.config import settings


async def generate_presigned_upload_url(
    object_name: str, content_type: str, expiration: int = 3600
) -> str:
    """
    Generate a one-time link to direct s3 upload.
    object_name: path and file name in S3 (np. 'project_123/documents/raport.pdf')
    content_type: Typ MIME (np. 'application/pdf')
    """
    session = aioboto3.Session()

    async with session.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        aws_session_token=settings.AWS_SESSION_TOKEN,
    ) as s3_client:
        response = await s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": settings.S3_BUCKET_NAME,
                "Key": object_name,
                "ContentType": content_type,
            },
            ExpiresIn=expiration,
        )

    return response


async def generate_presigned_download_url(
    object_name: str, expiration: int = 3600
) -> str:
    """
    Generate a one-time link to download a private file from a S3 bucket.
    """
    session = aioboto3.Session()

    async with session.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        aws_session_token=settings.AWS_SESSION_TOKEN,
    ) as s3_client:
        response = await s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": settings.S3_BUCKET_NAME, "Key": object_name},
            ExpiresIn=expiration,
        )

    return response


async def delete_file_from_s3(object_name: str) -> None:
    """
    Delete file from S3 bucket.
    """
    session = aioboto3.Session()

    async with session.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        aws_session_token=settings.AWS_SESSION_TOKEN,
    ) as s3_client:
        await s3_client.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=object_name)
