#!/usr/bin/env python3
"""Download Project Gutenberg books and stage them in a public S3 bucket."""

import sys
import os
import time
import json
import logging

import boto3
import requests
from botocore.exceptions import ClientError


# Set up logger
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)
log = logging.getLogger(__name__)

# Create one shared S3 client
s3 = boto3.client("s3", region_name="us-east-1")


def parse_args():
    """Read command-line arguments"""
    if len(sys.argv) < 4:
        log.error(
            "Usage: python stage_books.py "
            "book_urls.txt index.html BUCKET"
        )
        sys.exit(1)

    return sys.argv[1], sys.argv[2], sys.argv[3]


def download_books(list_file, dest_dir):
    """Download books and return their local file paths"""
    os.makedirs(dest_dir, exist_ok=True)
    file_paths = []

    try:
        with open(list_file, "r") as f:
            urls = [line.strip() for line in f if line.strip()]
    except OSError as e:
        log.error(f"Cannot read book list: {e}")
        return file_paths

    for url in urls:
        filename = url.split("/")[-1]
        path = os.path.join(dest_dir, filename)

        if os.path.exists(path):
            log.info(f"Skipping existing file: {path}")
            file_paths.append(path)
            continue

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status() # raise an error for 404 etc.
            # save response.content to the file
            with open(path, "wb") as f:
                f.write(response.content)

            file_paths.append(path)
            log.info(f"Downloaded: {filename}")

            time.sleep(1)

        except requests.RequestException as e:
            log.error(f"Error downloading {url}: {e}")
        except OSError as e:
            log.error(f"Error saving {path}: {e}")

    return file_paths


def create_bucket(bucket):
    """Create the bucket if it does not already exist"""
    try:
        s3.head_bucket(Bucket=bucket)
        log.info(f"Bucket already exists: {bucket}")
        return True

    except ClientError as e:
        code = e.response["Error"]["Code"]

        if code not in ("404", "NoSuchBucket", "NotFound"):
            log.error(f"Cannot access bucket {bucket}: {e}")
            return False

    try:
        s3.create_bucket(Bucket=bucket)
        log.info(f"Created bucket: {bucket}")
        return True

    except ClientError as e:
        log.error(f"Error creating bucket: {e}")
        return False


def make_public(bucket):
    """Disable public access blocking and attach a read-only policy."""
    try:
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": False,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False,
            },
        )

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket}/*",
                }
            ],
        }

        s3.put_bucket_policy(
            Bucket=bucket,
            Policy=json.dumps(policy)
        )

        log.info(f"Bucket is publicly readable: {bucket}")
        return True

    except ClientError as e:
        log.error(f"Error making bucket public: {e}")
        return False


def upload_files(bucket, file_paths):
    """Upload book files to the top level of the bucket."""
    count = 0

    for path in file_paths:
        filename = os.path.basename(path)

        try:
            s3.upload_file(
                path,
                bucket,
                filename,
                ExtraArgs={
                    "ContentType": "text/plain; charset=utf-8"
                },
            )

            count += 1
            log.info(f"Uploaded: {filename}")

        except (ClientError, OSError) as e:
            log.error(f"Error uploading {filename}: {e}")

    return count


def upload_index(bucket, index_path):
    """Upload the HTML index page."""
    try:
        s3.upload_file(
            index_path,
            bucket,
            "index.html",
            ExtraArgs={"ContentType": "text/html"},
        )

        log.info("Uploaded index.html")
        return True

    except (ClientError, OSError) as e:
        log.error(f"Error uploading index.html: {e}")
        return False


def main():
    """Run the complete book staging workflow."""
    list_file, index_path, bucket = parse_args()

    file_paths = download_books(list_file, "books")

    if not file_paths:
        log.error("No books downloaded.")
        sys.exit(1)

    if not create_bucket(bucket):
        sys.exit(1)

    if not make_public(bucket):
        sys.exit(1)

    count = upload_files(bucket, file_paths)
    index_success = upload_index(bucket, index_path)

    url = f"https://{bucket}.s3.amazonaws.com/index.html"

    if count == len(file_paths) and index_success:
        log.info(f"Success! Uploaded {count} books.")
        log.info(f"Public index: {url}")
    else:
        log.error("Some files failed to upload.")
        log.info(f"Index URL: {url}")
        sys.exit(1)


if __name__ == "__main__":
    main()