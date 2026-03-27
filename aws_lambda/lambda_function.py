import gzip
import urllib.parse

import boto3
from PIL import Image

s3 = boto3.client("s3")


def lambda_handler(event, context):
    try:
        bucket = event["Records"][0]["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(event["Records"][0]["s3"]["object"]["key"])

        if key.startswith("processed-") or "-processed" in key or key.endswith(".gz"):
            print(f"File {key} has been already processed. Skipping....")
            return {"statusCode": 200, "body": "Skipped"}

        print(f"Downloading file: {key} from bucket: {bucket}")
        download_path = "/tmp/input_file"
        s3.download_file(bucket, key, download_path)

        filename = key.split("/")[-1]
        prefix_path = "/".join(key.split("/")[:-1]) + "/" if "/" in key else ""
        ext = filename.lower().split(".")[-1]

        if ext in ["jpg", "jpeg", "png"]:
            print("Image detected. Starting scaling (Image Resize)...")
            output_path = f"/tmp/processed_{filename}"
            new_key = f"{prefix_path}processed-{filename}"

            with Image.open(download_path) as img:
                img.thumbnail((800, 800))
                img.save(output_path)

            s3.upload_file(output_path, bucket, new_key)
            print(f"Success! Scaled image saved as: {new_key}")

        else:
            print("Document detected. Starting GZIP conversion...")
            output_path = "/tmp/compressed_file.gz"
            new_key = key + ".gz"

            with open(download_path, "rb") as f_in:
                with gzip.open(output_path, "wb") as f_out:
                    f_out.writelines(f_in)

            s3.upload_file(output_path, bucket, new_key)
            print(f"Success! Compressed document saved as: {new_key}")

        return {"statusCode": 200, "body": f"Successfully processed {key}"}

    except Exception as e:
        print(f"Processing error: {e}")
        return {"statusCode": 500, "body": "Error processing file"}
