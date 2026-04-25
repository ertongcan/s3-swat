"""
scanners/network_scout.py
Scenario 02 — Audits VPCs in the region for missing S3 Gateway Endpoints.
Traffic routed through NAT Gateways costs $0.045/GB unnecessarily.

Uses: ec2.describe_vpcs(), ec2.describe_vpc_endpoints(), ec2.describe_nat_gateways()
"""

import boto3
from typing import List, Dict, Any, Optional


def scan(
    region: str = "us-east-1",
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
    aws_session_token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Checks every VPC in the region for:
    - Whether a Gateway VPC Endpoint for S3 exists
    - Whether a NAT Gateway is present (potential cost leak)

    Returns a list of per-VPC findings.
    """
    session_kwargs = {"region_name": region}
    if aws_access_key_id and aws_secret_access_key:
        session_kwargs["aws_access_key_id"] = aws_access_key_id
        session_kwargs["aws_secret_access_key"] = aws_secret_access_key
    if aws_session_token:
        session_kwargs["aws_session_token"] = aws_session_token

    session = boto3.Session(**session_kwargs)
    ec2 = session.client("ec2")

    # ── Fetch all VPCs ───────────────────────────────────────────────────────
    vpcs = []
    paginator = ec2.get_paginator("describe_vpcs")
    for page in paginator.paginate():
        vpcs.extend(page.get("Vpcs", []))

    if not vpcs:
        return []

    vpc_ids = [v["VpcId"] for v in vpcs]

    # ── Check for S3 Gateway Endpoints ───────────────────────────────────────
    s3_service_name = f"com.amazonaws.{region}.s3"
    endpoints_resp = ec2.describe_vpc_endpoints(
        Filters=[
            {"Name": "service-name", "Values": [s3_service_name]},
            {"Name": "vpc-endpoint-type", "Values": ["Gateway"]},
        ]
    )
    vpcs_with_endpoint = {ep["VpcId"] for ep in endpoints_resp.get("VpcEndpoints", [])}

    # ── Check for NAT Gateways ───────────────────────────────────────────────
    nat_resp = ec2.describe_nat_gateways(
        Filter=[{"Name": "state", "Values": ["available"]}]
    )
    vpcs_with_nat = {nat["VpcId"] for nat in nat_resp.get("NatGateways", [])}

    # ── Build results ────────────────────────────────────────────────────────
    results = []
    for vpc_id in vpc_ids:
        has_endpoint = vpc_id in vpcs_with_endpoint
        has_nat = vpc_id in vpcs_with_nat

        # Potential saving exists when there's a NAT but no S3 endpoint
        if has_nat and not has_endpoint:
            saving = "$0.045/GB"
        else:
            saving = "$0.00"

        results.append(
            {
                "vpc_id": vpc_id,
                "has_nat": has_nat,
                "has_endpoint": has_endpoint,
                "potential_saving": saving,
            }
        )

    # Sort: problematic VPCs first (has NAT, no endpoint)
    results.sort(key=lambda r: (r["has_endpoint"], not r["has_nat"]))
    return results
