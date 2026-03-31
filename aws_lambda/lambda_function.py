import gzip
import urllib.parse
import boto3
import os
import asyncpg
import asyncio
from PIL import Image

s3 = boto3.client("s3")

DB_DSN = os.environ.get("DATABASE_URL")


async def update_db(original_key, new_key, size_bytes):
    if not DB_DSN:
        print("DATABASE_URL not set, skipping DB update")
        return

    conn = await asyncpg.connect(DB_DSN)
    try:
        project_id = await conn.fetchval(
            """
            UPDATE documents 
            SET s3_key = $1, size_bytes = $2 
            WHERE s3_key = $3
            RETURNING project_id
            """,
            new_key,
            size_bytes,
            original_key,
        )

        if project_id:
            await conn.execute(
                """
                UPDATE projects 
                SET total_storage_bytes = (
                    SELECT COALESCE(SUM(size_bytes), 0) 
                    FROM documents 
                    WHERE project_id = $1
                )
                WHERE id = $1
                """,
                project_id,
            )
            print(f"Updated DB for {original_key} -> {new_key}: {size_bytes} bytes")
    finally:
        await conn.close()


def lambda_handler(event, context):
    try:
        bucket = event["Records"][0]["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(event["Records"][0]["s3"]["object"]["key"])

        filename = os.path.basename(key)
        prefix_path = os.path.dirname(key)

        if filename.startswith("processed-") or "-processed" in key or key.lower().endswith(".gz"):
            print(f"Skipping already processed file: {key}")
            return {"statusCode": 200, "body": "Skipped"}

        print(f"Downloading file: {key} from bucket: {bucket}")
        download_path = f"/tmp/{filename}"
        s3.download_file(bucket, key, download_path)

        _, ext = os.path.splitext(filename)
        ext = ext.lower().replace(".", "")

        if ext in ["jpg", "jpeg", "png"]:
            print(f"Image detected ({ext}). Resizing...")

            new_filename = f"processed-{filename}"
            new_key = os.path.join(prefix_path, new_filename) if prefix_path else new_filename
            output_path = f"/tmp/{new_filename}"

            with Image.open(download_path) as img:
                img.thumbnail((800, 800))
                img.save(output_path)

            s3.upload_file(output_path, bucket, new_key)
            print(f"Success! Resized image saved as: {new_key}")

            processed_size = os.path.getsize(output_path)
            asyncio.run(update_db(key, new_key, processed_size))
            s3.delete_object(Bucket=bucket, Key=key)
            print(f"Original file {key} deleted from S3.")

        else:
            print(f"Document detected ({ext}). Converting to GZIP...")

            new_key = f"{key}.gz"
            output_path = f"/tmp/{filename}.gz"

            with open(download_path, "rb") as f_in:
                with gzip.open(output_path, "wb") as f_out:
                    for line in f_in:
                        f_out.write(line)

            s3.upload_file(output_path, bucket, new_key)
            print(f"Success! Compressed document saved as: {new_key}")

            processed_size = os.path.getsize(output_path)
            asyncio.run(update_db(key, new_key, processed_size))
            s3.delete_object(Bucket=bucket, Key=key)
            print(f"Original file {key} deleted from S3.")

        if os.path.exists(download_path):
            os.remove(download_path)
        if os.path.exists(output_path):
            os.remove(output_path)

        return {"statusCode": 200, "body": f"Successfully processed {key}"}

    except Exception as e:
        print(f"Processing error: {e}")
        return {"statusCode": 500, "body": "Error processing file"}
