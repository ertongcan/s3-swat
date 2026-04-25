"""
scanners/efficiency.py
Scenario 03 — Analyzes the small-file tax problem.

S3 Intelligent-Tiering bills a minimum of 128 KB per object.
If most objects are < 128 KB, switching TO Intelligent-Tiering
actually *increases* costs because you're billed for 128 KB
per tiny file instead of the actual size.

Uses: s3.list_objects_v2() (paginated, sampled)
"""

import boto3
from typing import Dict, Any, Optional

MIN_BILLED_SIZE = 128 * 1024  # 128 KB in bytes


def scan(
    bucket: str,
    region: str = "us-east-1",
    max_objects: int = 10000,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
    aws_session_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Samples up to `max_objects` objects in the bucket and calculates:
    - % of objects smaller than 128 KB
    - Billed-vs-actual bloat ratio
    - Recommendation: STAY IN STANDARD or ELIGIBLE FOR TIERING
    """
    session_kwargs = {"region_name": region}
    if aws_access_key_id and aws_secret_access_key:
        session_kwargs["aws_access_key_id"] = aws_access_key_id
        session_kwargs["aws_secret_access_key"] = aws_secret_access_key
    if aws_session_token:
        session_kwargs["aws_session_token"] = aws_session_token

    session = boto3.Session(**session_kwargs)
    s3 = session.client("s3")

    total_objects = 0
    small_objects = 0
    total_actual_bytes = 0
    total_billed_bytes = 0
    active_tiering_waste_bytes = 0
    storage_classes = {}

    paginator = s3.get_paginator("list_objects_v2")
    scanned = 0

    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            size = obj.get("Size", 0)
            storage_class = obj.get("StorageClass", "STANDARD")
            storage_classes[storage_class] = storage_classes.get(storage_class, 0) + 1

            # Skip zero-byte objects (folders / markers)
            if size == 0:
                continue

            total_objects += 1
            total_actual_bytes += size

            if size < MIN_BILLED_SIZE:
                small_objects += 1
                # Under Intelligent-Tiering, this is billed as 128 KB
                total_billed_bytes += MIN_BILLED_SIZE

                # Check if it's ACTUALLY currently bleeding money
                if storage_class == "INTELLIGENT_TIERING":
                    active_tiering_waste_bytes += MIN_BILLED_SIZE - size
            else:
                total_billed_bytes += size

            scanned += 1
            if scanned >= max_objects:
                break

        if scanned >= max_objects:
            break

    # ── Calculate metrics ────────────────────────────────────────────────────
    if total_objects == 0:
        return {
            "total_objects": 0,
            "small_objects": 0,
            "small_file_pct": 0.0,
            "total_actual_bytes": 0,
            "total_billed_bytes": 0,
            "waste_ratio_pct": 0.0,
            "recommendation": "N/A",
        }
    small_file_pct = round((small_objects / total_objects) * 100, 1)

    # Waste ratio: how much extra you'd pay under tiering
    if total_actual_bytes > 0:
        waste_ratio = (
            (total_billed_bytes - total_actual_bytes) / total_actual_bytes
        ) * 100
        waste_ratio_pct = round(max(0, waste_ratio), 1)
    else:
        waste_ratio_pct = 0.0

    # Decision: if >50% of objects are small, tiering will hurt
    if small_file_pct > 50:
        recommendation = "STAY IN STANDARD"
    elif small_file_pct > 20:
        recommendation = "MIXED — REVIEW PREFIXES"
    else:
        recommendation = "ELIGIBLE FOR TIERING"

    return {
        "total_objects": total_objects,
        "small_objects": small_objects,
        "small_file_pct": small_file_pct,
        "total_actual_bytes": total_actual_bytes,
        "total_billed_bytes": total_billed_bytes,
        "active_tiering_waste_bytes": active_tiering_waste_bytes,
        "waste_ratio_pct": waste_ratio_pct,
        "recommendation": recommendation,
        "storage_classes": storage_classes,
    }
