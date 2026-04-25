"""
api/auth.py
Simple read-only authentication via X-User-ID header.
All S3 operations are read-only — no data is ever modified.
"""

from fastapi import Request


async def get_current_user(request: Request) -> str:
    """
    Extracts the user ID from the X-User-ID header.
    Returns 'anonymous' if no header is provided (for demo mode).
    """
    user_id = request.headers.get("X-User-ID", "").strip()
    if not user_id:
        user_id = "anonymous"
    return user_id
