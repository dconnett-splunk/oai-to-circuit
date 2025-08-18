#!/usr/bin/env python3

import os
import base64
import json
import time
from typing import Dict, Any
from fastapi import FastAPI, Request, Response, HTTPException
import httpx

# --- Config (edit these or use env vars as needed) ---
# Get from env or config securely in real code!
CIRCUIT_CLIENT_ID = os.environ.get("CIRCUIT_CLIENT_ID", "")
CIRCUIT_CLIENT_SECRET = os.environ.get("CIRCUIT_CLIENT_SECRET", "")
CIRCUIT_APPKEY = os.environ.get("CIRCUIT_APPKEY", "")
TOKEN_URL = "https://id.cisco.com/oauth2/default/v1/token"
CIRCUIT_BASE = "https://chat-ai.cisco.com"
API_VERSION = "2025-04-01-preview"  # Or dynamically
# --------------------------------------------------------

app = FastAPI()

_token_cache = {"access_token": None, "expires_at": 0}


async def get_access_token() -> str:
    # Simple in-memory cache.
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]
    # Get new
    creds = f"{CIRCUIT_CLIENT_ID}:{CIRCUIT_CLIENT_SECRET}"
    b64 = base64.b64encode(creds.encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {b64}",
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = "grant_type=client_credentials"
    async with httpx.AsyncClient() as client:
        r = await client.post(TOKEN_URL, headers=headers, data=data)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Token err: {r.text}")
    j = r.json()
    _token_cache["access_token"] = j["access_token"]
    _token_cache["expires_at"] = now + int(j.get("expires_in", 3600))
    return j["access_token"]


@app.post("/v1/chat/completions")
async def chat_completion(request: Request):
    req_data: Dict[str, Any] = await request.json()
    model = req_data.pop("model", None)
    if not model:
        raise HTTPException(status_code=400, detail="Model parameter required")
    # Optionally: Validate/model whitelist here.

    # Insert appkey if not present
    user_field = req_data.get("user")
    if not user_field:
        req_data["user"] = json.dumps({"appkey": CIRCUIT_APPKEY})
    elif CIRCUIT_APPKEY and CIRCUIT_APPKEY not in user_field:
        # Inject in-place if user provided, but no appkey
        try:
            d = json.loads(user_field)
            d["appkey"] = CIRCUIT_APPKEY
            req_data["user"] = json.dumps(d)
        except Exception:
            pass  # If malformed, just pass through

    # Compose proxy request
    target_url = f"{CIRCUIT_BASE}/openai/deployments/{model}/chat/completions?api-version={API_VERSION}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "api-key": await get_access_token(),
    }

    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(target_url, json=req_data, headers=headers)
    return Response(
        content=r.content,
        status_code=r.status_code,
        headers={"Content-Type": r.headers.get("content-type", "application/json")},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("rewriter:app", host="0.0.0.0", port=12000, reload=True)
