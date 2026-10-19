#!/bin/bash
set -euo pipefail

# Check that all three arguments are provided
if [ "$#" -ne 3 ]; then
    echo "Usage: $0 BOOK_URL BUCKET EXPIRATION"
    exit 1
fi

# Read positional arguments
BOOK_URL="$1"
BUCKET="$2"
EXPIRATION="$3"

# Get the book filename from the URL
FILENAME="${BOOK_URL##*/}"

# Create the books folder if needed
mkdir -p books

# Download the book from Project Gutenberg
curl -fL "$BOOK_URL" -o "books/$FILENAME"

# Create the private bucket if it does not exist
if aws s3 ls "s3://$BUCKET" > /dev/null 2>&1; then
    echo "Bucket already exists: $BUCKET"
else
    aws s3 mb "s3://$BUCKET" --region us-east-1
fi

# Upload the book as plain text
aws s3 cp "books/$FILENAME" "s3://$BUCKET/$FILENAME" \
    --content-type "text/plain; charset=utf-8"

# Generate a temporary presigned URL
echo "Presigned URL:"
aws s3 presign "s3://$BUCKET/$FILENAME" \
    --expires-in "$EXPIRATION"