"""
api/schemas.py
Pydantic models for request / response validation.
"""

from pydantic import BaseModel, Field
from typing import Optional, List


# ── Request Models ───────────────────────────────────────────────────────────


class ScanRequest(BaseModel):
    """Payload to kick off a new S3 SWAT scan."""

    bucket: str = Field(..., description="S3 bucket name to scan")
    region: str = Field(default="us-east-1", description="AWS region")
    aws_access_key_id: Optional[str] = Field(
        None, description="AWS access key (overrides env)"
    )
    aws_secret_access_key: Optional[str] = Field(
        None, description="AWS secret key (overrides env)"
    )
    aws_session_token: Optional[str] = Field(
        None, description="AWS session token for assumed roles"
    )
    max_objects: int = Field(
        default=10000, description="Max objects to sample for efficiency scan"
    )


# ── Scanner Result Models ────────────────────────────────────────────────────


class GhostUpload(BaseModel):
    key: str
    upload_id: str
    age_days: int
    size_bytes: int
    monthly_cost: float


class NetworkFinding(BaseModel):
    vpc_id: str
    has_nat: bool
    has_endpoint: bool
    potential_saving: str


class EfficiencyResult(BaseModel):
    total_objects: int = 0
    small_objects: int = 0
    small_file_pct: float = 0.0
    total_actual_bytes: int = 0
    total_billed_bytes: int = 0
    waste_ratio_pct: float = 0.0
    recommendation: str = "N/A"


# ── Response Models ──────────────────────────────────────────────────────────


class ScanResponse(BaseModel):
    """Full scan result returned by the API."""

    id: str
    user_id: str
    bucket: str
    region: str
    health_score: int
    ghost_results: List[GhostUpload] = []
    network_results: List[NetworkFinding] = []
    efficiency_results: Optional[EfficiencyResult] = None
    created_at: str


class ScanSummary(BaseModel):
    """Lightweight model for listing past scans."""

    id: str
    bucket: str
    region: str
    health_score: int
    ghost_count: int = 0
    network_leak_count: int = 0
    efficiency_waste_pct: float = 0.0
    created_at: str


class HealthCheck(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    timestamp: str
