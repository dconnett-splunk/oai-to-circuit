import base64
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from fastapi import HTTPException


@dataclass
class TokenCache:
    access_token: Optional[str] = None
    expires_at: float = 0.0


async def get_access_token(
    *,
    token_url: str,
    client_id: str,
    client_secret: str,
    logger,
    cache: TokenCache,
) -> str:
    """Get or refresh OAuth2 access token (client credentials), with simple in-memory caching."""
    now = time.time()
    if cache.access_token and now < cache.expires_at - 60:
        logger.debug("Using cached access token")
        return cache.access_token

    logger.info("Fetching new access token")
    missing: list[str] = []
    if not client_id:
        missing.append("CIRCUIT_CLIENT_ID")
    if not client_secret:
        missing.append("CIRCUIT_CLIENT_SECRET")
    if missing:
        logger.error(f"Missing required env vars: {', '.join(missing)}")
        raise HTTPException(
            status_code=500,
            detail=f"Server misconfigured: missing {', '.join(missing)}",
        )

    creds = f"{client_id}:{client_secret}"
    b64 = base64.b64encode(creds.encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {b64}",
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = "grant_type=client_credentials"

    try:
        async with httpx.AsyncClient() as client:
            logger.debug(f"Requesting token from {token_url}")
            r = await client.post(token_url, headers=headers, data=data)

        if r.status_code != 200:
            logger.error(f"Token request failed: {r.status_code} - {r.text}")
            raise HTTPException(status_code=502, detail=f"Token err: {r.text}")

        j = r.json()
        cache.access_token = j["access_token"]
        cache.expires_at = now + int(j.get("expires_in", 3600))
        logger.info("Successfully obtained new access token")
        return cache.access_token
    except Exception:
        logger.exception("Error getting access token")
        raise


