"""
api/routes.py
All REST endpoints for the S3 SWAT SaaS API.
"""

import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Request, HTTPException

from api.auth import get_current_user
from api.schemas import (
    ScanRequest,
    ScanResponse,
    ScanSummary,
    HealthCheck,
    GhostUpload,
    NetworkFinding,
    EfficiencyResult,
)
from db import database
from scanners import ghost_hunter, network_scout, efficiency

router = APIRouter(prefix="/api", tags=["s3-swat"])


# ── Health ───────────────────────────────────────────────────────────────────


@router.get("/health", response_model=HealthCheck)
async def health_check():
    return HealthCheck(
        status="ok",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/config")
async def get_config():
    """Return public configuration for the frontend."""
    import os

    return {
        "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID", ""),
        "has_secret_key": bool(os.getenv("AWS_SECRET_ACCESS_KEY")),
        "saas_account_id": os.getenv("SAAS_AWS_ACCOUNT_ID", "123456789012"),
    }


# ── Scan ─────────────────────────────────────────────────────────────────────


@router.post("/scan", response_model=ScanResponse)
async def run_scan(body: ScanRequest, request: Request):
    """
    Run all 3 S3 SWAT scenarios against the given bucket.
    Persists results and returns the full report.
    """
    user_id = await get_current_user(request)
    scan_id = str(uuid.uuid4())[:8]

    creds = {
        "aws_access_key_id": body.aws_access_key_id,
        "aws_secret_access_key": body.aws_secret_access_key,
        "aws_session_token": body.aws_session_token,
    }

    # ── Run scanners ─────────────────────────────────────────────────────
    errors = []

    # Scenario 01: Ghost Hunter
    try:
        ghost_data = ghost_hunter.scan(bucket=body.bucket, region=body.region, **creds)
    except Exception as e:
        ghost_data = []
        errors.append(f"Ghost Hunter: {e}")

    # Scenario 02: Network Scout
    try:
        network_data = network_scout.scan(region=body.region, **creds)
    except Exception as e:
        network_data = []
        errors.append(f"Network Scout: {e}")

    # Scenario 03: Efficiency Audit
    try:
        eff_data = efficiency.scan(
            bucket=body.bucket,
            region=body.region,
            max_objects=body.max_objects,
            **creds,
        )
    except Exception as e:
        eff_data = {
            "total_objects": 0,
            "small_objects": 0,
            "small_file_pct": 0,
            "total_actual_bytes": 0,
            "total_billed_bytes": 0,
            "waste_ratio_pct": 0,
            "recommendation": "SCAN FAILED",
        }
        errors.append(f"Efficiency: {e}")

    # ── Calculate health score ───────────────────────────────────────────
    ghost_count = len(ghost_data)
    network_leak_count = len([r for r in network_data if not r.get("has_endpoint")])
    eff_waste = eff_data.get("waste_ratio_pct", 0)

    health_score = max(
        0,
        100 - (ghost_count * 3) - (network_leak_count * 20) - int(eff_waste / 2),
    )

    # ── Persist ──────────────────────────────────────────────────────────
    created_at = datetime.now(timezone.utc).isoformat()
    await database.save_scan(
        scan_id=scan_id,
        user_id=user_id,
        bucket=body.bucket,
        region=body.region,
        health_score=health_score,
        ghost_data=ghost_data,
        network_data=network_data,
        efficiency_data=eff_data,
    )

    return ScanResponse(
        id=scan_id,
        user_id=user_id,
        bucket=body.bucket,
        region=body.region,
        health_score=health_score,
        ghost_results=[GhostUpload(**g) for g in ghost_data],
        network_results=[NetworkFinding(**n) for n in network_data],
        efficiency_results=EfficiencyResult(**eff_data),
        created_at=created_at,
    )


# ── Retrieve ─────────────────────────────────────────────────────────────────


@router.get("/scan/{scan_id}", response_model=ScanResponse)
async def get_scan(scan_id: str, request: Request):
    """Get full results for a specific scan."""
    user_id = await get_current_user(request)
    row = await database.get_scan(scan_id, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    return ScanResponse(
        id=row["id"],
        user_id=row["user_id"],
        bucket=row["bucket"],
        region=row["region"],
        health_score=row["health_score"],
        ghost_results=[GhostUpload(**g) for g in row["ghost_data"]],
        network_results=[NetworkFinding(**n) for n in row["network_data"]],
        efficiency_results=EfficiencyResult(**row["efficiency_data"]),
        created_at=str(row["created_at"]),
    )


# ── List ─────────────────────────────────────────────────────────────────────


@router.get("/scans", response_model=List[ScanSummary])
async def list_scans(request: Request):
    """List all scans for the authenticated user."""
    user_id = await get_current_user(request)
    rows = await database.list_scans(user_id)

    summaries = []
    for row in rows:
        eff = row.get("efficiency_data", {})
        summaries.append(
            ScanSummary(
                id=row["id"],
                bucket=row["bucket"],
                region=row["region"],
                health_score=row["health_score"],
                ghost_count=len(row.get("ghost_data", [])),
                network_leak_count=len(
                    [
                        r
                        for r in row.get("network_data", [])
                        if not r.get("has_endpoint")
                    ]
                ),
                efficiency_waste_pct=eff.get("waste_ratio_pct", 0),
                created_at=str(row["created_at"]),
            )
        )
    return summaries


# ── Delete ───────────────────────────────────────────────────────────────────


@router.delete("/scan/{scan_id}")
async def delete_scan(scan_id: str, request: Request):
    """Delete a scan from history."""
    user_id = await get_current_user(request)
    deleted = await database.delete_scan(scan_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Scan not found")
    return {"status": "deleted", "id": scan_id}


# ── Report ───────────────────────────────────────────────────────────────────


@router.get("/report/{scan_id}")
async def get_report(scan_id: str, request: Request):
    """Generate and return the HTML report for a scan."""
    from fastapi.responses import HTMLResponse
    import artifact

    user_id = await get_current_user(request)
    row = await database.get_scan(scan_id, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    html_path = artifact.generate(
        ghost_results=row["ghost_data"],
        network_results=row["network_data"],
        efficiency_results=row["efficiency_data"],
        bucket=row["bucket"],
        region=row["region"],
    )

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    return HTMLResponse(content=html_content)
