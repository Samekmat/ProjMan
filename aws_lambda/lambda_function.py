import gzip
import os
import urllib.parse

import boto3
from PIL import Image

s3 = boto3.client("s3")


def lambda_handler(event, context):
    try:
        bucket = event["Records"][0]["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(event["Records"][0]["s3"]["object"]["key"])

        filename = os.path.basename(key)
        prefix_path = os.path.dirname(key)

        if (
            filename.startswith("processed-")
            or "-processed" in key
            or key.lower().endswith(".gz")
        ):
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
            new_key = (
                os.path.join(prefix_path, new_filename) if prefix_path else new_filename
            )
            output_path = f"/tmp/{new_filename}"

            with Image.open(download_path) as img:
                img.thumbnail((800, 800))
                img.save(output_path)

            s3.upload_file(output_path, bucket, new_key)
            print(f"Success! Resized image saved as: {new_key}")

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
