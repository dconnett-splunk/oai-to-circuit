# /usr/bin/env python3


import os
import base64
import json
import time
import logging
from typing import Dict, Any
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
import httpx
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Config (edit these or use env vars as needed) ---
# Get from env or config securely in real code!
CIRCUIT_CLIENT_ID = os.environ.get("CIRCUIT_CLIENT_ID", "")
CIRCUIT_CLIENT_SECRET = os.environ.get("CIRCUIT_CLIENT_SECRET", "")
CIRCUIT_APPKEY = os.environ.get("CIRCUIT_APPKEY", "")
TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"
CIRCUIT_BASE = "https://chat-ai.cisco.com"
API_VERSION = "2025-04-01-preview"  # Or dynamically
# --------------------------------------------------------

app = FastAPI(title="OpenAI to Circuit Bridge", version="1.0.0")

_token_cache = {"access_token": None, "expires_at": 0}


async def get_access_token() -> str:
    """Get or refresh OAuth2 access token."""
    # Simple in-memory cache.
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        logger.debug("Using cached access token")
        return _token_cache["access_token"]
    # Get new token
    logger.info("Fetching new access token")
    if not CIRCUIT_CLIENT_ID or not CIRCUIT_CLIENT_SECRET:
        logger.error("Missing CIRCUIT_CLIENT_ID or CIRCUIT_CLIENT_SECRET")
        raise HTTPException(
            status_code=500, detail="Server misconfigured: missing credentials"
        )

    creds = f"{CIRCUIT_CLIENT_ID}:{CIRCUIT_CLIENT_SECRET}"
    b64 = base64.b64encode(creds.encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {b64}",
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = "grant_type=client_credentials"

    try:
        async with httpx.AsyncClient() as client:
            logger.debug(f"Requesting token from {TOKEN_URL}")
            r = await client.post(TOKEN_URL, headers=headers, data=data)

        if r.status_code != 200:
            logger.error(f"Token request failed: {r.status_code} - {r.text}")
            raise HTTPException(status_code=502, detail=f"Token err: {r.text}")

        j = r.json()
        _token_cache["access_token"] = j["access_token"]
        _token_cache["expires_at"] = now + int(j.get("expires_in", 3600))
        logger.info("Successfully obtained new access token")
        return j["access_token"]
    except Exception as e:
        logger.exception("Error getting access token")
        raise


@app.get("/health")
async def health_check():
    """Health check endpoint for debugging connectivity."""
    return {
        "status": "healthy",
        "service": "OpenAI to Circuit Bridge",
        "credentials_configured": bool(CIRCUIT_CLIENT_ID and CIRCUIT_CLIENT_SECRET),
        "appkey_configured": bool(CIRCUIT_APPKEY),
    }


@app.post("/v1/chat/completions")
async def chat_completion(request: Request):
    """Main endpoint that bridges OpenAI format to Circuit API."""
    logger.info(
        f"Received request from {request.client.host if request.client else 'unknown'}"
    )

    # Log request headers for debugging
    logger.debug(f"Request headers: {dict(request.headers)}")

    try:
        req_data: Dict[str, Any] = await request.json()
        logger.debug(f"Request body: {json.dumps(req_data, indent=2)}")
    except Exception as e:
        logger.error(f"Failed to parse request JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON in request body")

    model = req_data.pop("model", None)
    if not model:
        logger.error("Missing model parameter")
        raise HTTPException(status_code=400, detail="Model parameter required")

    logger.info(f"Processing request for model: {model}")

    # Insert appkey if not present
    user_field = req_data.get("user")
    if not user_field:
        if not CIRCUIT_APPKEY:
            logger.warning("No CIRCUIT_APPKEY configured")
        req_data["user"] = json.dumps({"appkey": CIRCUIT_APPKEY})
        logger.debug(f"Added user field with appkey")
    elif CIRCUIT_APPKEY and CIRCUIT_APPKEY not in user_field:
        # Inject in-place if user provided, but no appkey
        try:
            d = json.loads(user_field)
            d["appkey"] = CIRCUIT_APPKEY
            req_data["user"] = json.dumps(d)
            logger.debug(f"Injected appkey into existing user field")
        except Exception as e:
            logger.warning(f"Failed to inject appkey into user field: {e}")
            pass  # If malformed, just pass through

    # Compose proxy request
    target_url = f"{CIRCUIT_BASE}/openai/deployments/{model}/chat/completions?api-version={API_VERSION}"

    try:
        access_token = await get_access_token()
    except Exception as e:
        logger.error(f"Failed to get access token: {e}")
        raise HTTPException(
            status_code=502, detail="Failed to authenticate with Circuit API"
        )

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "api-key": access_token,
    }

    logger.info(f"Forwarding to Circuit API: {target_url}")
    logger.debug(f"Circuit request body: {json.dumps(req_data, indent=2)}")

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(target_url, json=req_data, headers=headers)

        logger.info(f"Circuit API response: {r.status_code}")
        if r.status_code >= 400:
            logger.error(f"Circuit API error response: {r.text}")

        return Response(
            content=r.content,
            status_code=r.status_code,
            headers={"Content-Type": r.headers.get("content-type", "application/json")},
        )
    except httpx.TimeoutException:
        logger.error("Circuit API request timed out")
        raise HTTPException(
            status_code=504,
            detail="Gateway timeout - Circuit API took too long to respond",
        )
    except Exception as e:
        logger.exception(f"Unexpected error calling Circuit API")
        raise HTTPException(status_code=502, detail=f"Gateway error: {str(e)}")


@app.on_event("startup")
async def startup_event():
    """Log configuration on startup."""
    logger.info("Starting OpenAI to Circuit Bridge server")
    logger.info(f"Circuit base URL: {CIRCUIT_BASE}")
    logger.info(f"API version: {API_VERSION}")
    logger.info(
        f"Credentials configured: {bool(CIRCUIT_CLIENT_ID and CIRCUIT_CLIENT_SECRET)}"
    )
    logger.info(f"App key configured: {bool(CIRCUIT_APPKEY)}")
    if not CIRCUIT_CLIENT_ID or not CIRCUIT_CLIENT_SECRET:
        logger.warning(
            "⚠️  Missing CIRCUIT_CLIENT_ID or CIRCUIT_CLIENT_SECRET - authentication will fail!"
        )
    if not CIRCUIT_APPKEY:
        logger.warning(
            "⚠️  Missing CIRCUIT_APPKEY - requests may be rejected by Circuit API!"
        )


if __name__ == "__main__":
    # Run with more verbose logging
    uvicorn.run(
        "rewriter:app",
        host="0.0.0.0",
        port=12000,
        reload=True,
        log_level="debug",
        access_log=True,
    )
