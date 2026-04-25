"""
scanners/ghost_hunter.py
Scenario 01 — Finds incomplete (abandoned) multipart uploads that are
still consuming storage and costing money.

Uses: s3.list_multipart_uploads(), s3.list_parts()
"""

import boto3
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# S3 Standard storage: $0.023 per GB-month (us-east-1)
S3_STANDARD_COST_PER_GB = 0.023


def scan(
    bucket: str,
    region: str = "us-east-1",
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
    aws_session_token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Lists all incomplete multipart uploads in the given bucket.
    Returns a list of ghost uploads with key, age, size, and cost.
    """
    session_kwargs = {"region_name": region}
    if aws_access_key_id and aws_secret_access_key:
        session_kwargs["aws_access_key_id"] = aws_access_key_id
        session_kwargs["aws_secret_access_key"] = aws_secret_access_key
    if aws_session_token:
        session_kwargs["aws_session_token"] = aws_session_token

    session = boto3.Session(**session_kwargs)
    s3 = session.client("s3")

    results = []
    now = datetime.now(timezone.utc)

    # Paginate through all incomplete multipart uploads
    paginator = s3.get_paginator("list_multipart_uploads")
    for page in paginator.paginate(Bucket=bucket):
        uploads = page.get("Uploads", [])
        for upload in uploads:
            key = upload["Key"]
            upload_id = upload["UploadId"]
            initiated = upload["Initiated"]

            # Calculate age
            if isinstance(initiated, str):
                initiated = datetime.fromisoformat(initiated.replace("Z", "+00:00"))
            age_days = (now - initiated).days

            # Sum up all parts to get total size
            total_bytes = _get_upload_size(s3, bucket, key, upload_id)

            # Calculate monthly cost
            size_gb = total_bytes / (1024**3)
            monthly_cost = round(size_gb * S3_STANDARD_COST_PER_GB, 4)

            results.append(
                {
                    "key": key,
                    "upload_id": upload_id,
                    "age_days": age_days,
                    "size_bytes": total_bytes,
                    "monthly_cost": monthly_cost,
                }
            )

    # Sort by cost descending (biggest waste first)
    results.sort(key=lambda r: r["monthly_cost"], reverse=True)
    return results


def _get_upload_size(s3_client, bucket: str, key: str, upload_id: str) -> int:
    """Sum all part sizes for a multipart upload."""
    total = 0
    paginator = s3_client.get_paginator("list_parts")
    try:
        for page in paginator.paginate(Bucket=bucket, Key=key, UploadId=upload_id):
            for part in page.get("Parts", []):
                total += part.get("Size", 0)
    except Exception:
        # If we can't list parts (permissions etc.), report 0
        pass
    return total
