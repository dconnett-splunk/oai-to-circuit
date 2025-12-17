#!/usr/bin/env python3


import os
import base64
import json
import time
import logging
from logging.config import dictConfig
import ssl
import argparse
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
import httpx
import uvicorn
from quota import QuotaManager, load_quotas_from_env_or_file

# Configure unified logging for our app, uvicorn, and asyncio
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class RenameLoggerFilter(logging.Filter):
    """Rename a logger's name in emitted records.

    This helps normalize uvicorn's 'uvicorn.error' to simply 'uvicorn'.
    """
    def __init__(self, from_name: str, to_name: str) -> None:
        super().__init__()
        self.from_name = from_name
        self.to_name = to_name

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == self.from_name:
            record.name = self.to_name
        return True

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(levelprefix)s %(asctime)s - %(processName)-13s[%(process)5d] - %(name)-8s - %(message)s",
            "use_colors": True,
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": "%(levelprefix)s %(asctime)s - %(processName)-13s[%(process)5d] - %(name)-10s - %(client_addr)s - \"%(request_line)s\" %(status_code)s",
            "use_colors": True,
        },
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stderr",
            "filters": ["rename_uvicorn"],
        },
        "access": {
            "class": "logging.StreamHandler",
            "formatter": "access",
            "stream": "ext://sys.stdout",
        },
    },
    "filters": {
        "rename_uvicorn": {
            "()": "__main__.RenameLoggerFilter",
            "from_name": "uvicorn.error",
            "to_name": "uvicorn",
        }
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        "asyncio": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "__main__": {"handlers": ["default"], "level": "DEBUG", "propagate": False},
    },
    "root": {"handlers": ["default"], "level": "INFO"},
}

dictConfig(LOGGING_CONFIG)
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

# Quotas / subkey configuration
QUOTA_DB_PATH = os.environ.get("QUOTA_DB_PATH", "quota.db")
REQUIRE_SUBKEY = os.environ.get("REQUIRE_SUBKEY", "true").lower() in ("1", "true", "yes")
_quota_manager: Optional[QuotaManager] = None


def extract_subkey(request: Request) -> Optional[str]:
    """Extract a caller subkey from headers."""
    # Prefer explicit header
    subkey = request.headers.get("X-Bridge-Subkey")
    if subkey:
        return subkey.strip()
    # Fallback to Authorization: Bearer <token>
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("Starting OpenAI to Circuit Bridge server")
    logger.info(f"Circuit base URL: {CIRCUIT_BASE}")
    logger.info(f"API version: {API_VERSION}")
    logger.info(
        f"Credentials configured: {bool(CIRCUIT_CLIENT_ID and CIRCUIT_CLIENT_SECRET)}"
    )
    logger.info(f"App key configured: {bool(CIRCUIT_APPKEY)}")
    
    # Log SSL status (will be set via environment during startup)
    if os.environ.get("SSL_MODE") == "https_only":
        logger.info("🔒 Running in HTTPS-only mode")
    elif os.environ.get("SSL_MODE") == "dual":
        logger.info("🔒 Running in dual HTTP/HTTPS mode")
    else:
        logger.info("🔓 Running in HTTP-only mode (no SSL)")
    
    if not CIRCUIT_CLIENT_ID:
        logger.warning("⚠️  Missing CIRCUIT_CLIENT_ID - authentication will fail!")
    if not CIRCUIT_CLIENT_SECRET:
        logger.warning("⚠️  Missing CIRCUIT_CLIENT_SECRET - authentication will fail!")
    if not CIRCUIT_APPKEY:
        logger.warning("⚠️  Missing CIRCUIT_APPKEY - requests may be rejected by Circuit API!")
    
    # Initialize quotas
    global _quota_manager
    quotas_cfg = load_quotas_from_env_or_file()
    _quota_manager = QuotaManager(db_path=QUOTA_DB_PATH, quotas=quotas_cfg)
    logger.info(f"Quotas enabled: {bool(quotas_cfg)} (db={QUOTA_DB_PATH}, require_subkey={REQUIRE_SUBKEY})")

    yield
    
    # Shutdown
    logger.info("Shutting down OpenAI to Circuit Bridge server")


app = FastAPI(title="OpenAI to Circuit Bridge", version="1.0.0", lifespan=lifespan)

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
    missing: list[str] = []
    if not CIRCUIT_CLIENT_ID:
        missing.append("CIRCUIT_CLIENT_ID")
    if not CIRCUIT_CLIENT_SECRET:
        missing.append("CIRCUIT_CLIENT_SECRET")
    if missing:
        logger.error(f"Missing required env vars: {', '.join(missing)}")
        raise HTTPException(
            status_code=500,
            detail=f"Server misconfigured: missing {', '.join(missing)}",
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

    # Subkey extraction and quota pre-check
    caller_subkey = extract_subkey(request)
    if REQUIRE_SUBKEY and not caller_subkey:
        raise HTTPException(
            status_code=401,
            detail="Subkey required. Provide 'Authorization: Bearer <subkey>' or 'X-Bridge-Subkey' header.",
        )
    # If quotas configured and subkey present, enforce request-count limit before upstream call
    if caller_subkey and _quota_manager:
        if not _quota_manager.is_request_allowed(caller_subkey, model):
            logger.warning(f"Quota exceeded (requests) for subkey={caller_subkey} model={model}")
            raise HTTPException(status_code=429, detail="Quota exceeded for this subkey and model (requests)")

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
        # Record usage after response (if subkey present)
        if caller_subkey and _quota_manager:
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            try:
                # Only parse JSON for usage if content-type indicates JSON
                ct = (r.headers.get("content-type") or "").lower()
                if "application/json" in ct and r.content:
                    payload = r.json()
                    usage = payload.get("usage") if isinstance(payload, dict) else None
                    if isinstance(usage, dict):
                        prompt_tokens = int(usage.get("prompt_tokens") or 0)
                        completion_tokens = int(usage.get("completion_tokens") or 0)
                        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
            except Exception:
                # Swallow parsing issues; still record request count
                pass
            _quota_manager.record_usage(
                subkey=caller_subkey,
                model=model,
                request_inc=1,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
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


# Define multiprocessing functions at module level
def run_http(host: str, port: int):
    """Run HTTP server."""
    uvicorn.run(
        "rewriter:app",
        host=host,
        port=port,
        reload=False,  # Disable reload in dual mode
        log_level="info",
        access_log=True,
    )


def run_https(host: str, port: int, key: str, cert: str):
    """Run HTTPS server."""
    uvicorn.run(
        "rewriter:app",
        host=host,
        port=port,
        ssl_keyfile=key,
        ssl_certfile=cert,
        reload=False,  # Disable reload in dual mode
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenAI to Circuit Bridge Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=12000, help="Port for HTTP (default: 12000)")
    parser.add_argument("--ssl-port", type=int, default=12443, help="Port for HTTPS (default: 12443)")
    parser.add_argument("--ssl", action="store_true", help="Enable HTTPS")
    parser.add_argument("--ssl-only", action="store_true", help="Only run HTTPS (no HTTP)")
    parser.add_argument("--cert", default="cert.pem", help="SSL certificate file")
    parser.add_argument("--key", default="key.pem", help="SSL private key file")
    parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload")
    
    args = parser.parse_args()
    
    # SSL configuration
    ssl_context = None
    if args.ssl or args.ssl_only:
        if not os.path.exists(args.cert) or not os.path.exists(args.key):
            logger.error(f"SSL certificate files not found: {args.cert}, {args.key}")
            logger.error("Run 'python generate_cert.py' to create self-signed certificates")
            exit(1)
        
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(args.cert, args.key)
        logger.info(f"SSL enabled with certificate: {args.cert}")
    
    # Determine which mode to run in
    if args.ssl_only:
        os.environ["SSL_MODE"] = "https_only"
        # HTTPS only
        logger.info(f"Starting HTTPS-only server on https://{args.host}:{args.ssl_port}")
        uvicorn.run(
            "rewriter:app",
            host=args.host,
            port=args.ssl_port,
            ssl_keyfile=args.key,
            ssl_certfile=args.cert,
            reload=not args.no_reload,
            log_level="debug",
            access_log=True,
        )
    elif args.ssl:
        os.environ["SSL_MODE"] = "dual"
        # Both HTTP and HTTPS - we need to run two servers
        logger.info(f"Starting dual-mode server:")
        logger.info(f"  HTTP:  http://{args.host}:{args.port}")
        logger.info(f"  HTTPS: https://{args.host}:{args.ssl_port}")
        
        # For dual mode, we'll use multiprocessing to run both
        import multiprocessing
        import time

        # Set the start method to 'fork' on macOS/Linux for better compatibility
        # On Windows, this will be ignored and 'spawn' will be used
        try:
            multiprocessing.set_start_method('fork')
        except RuntimeError:
            # Already set, ignore
            pass

        processes = []

        http_process = multiprocessing.Process(
            target=run_http,
            args=(args.host, args.port),
            daemon=True,
            name="bridge-http"
        )
        https_process = multiprocessing.Process(
            target=run_https,
            args=(args.host, args.ssl_port, args.key, args.cert),
            daemon=True,
            name="bridge-https"
        )

        processes = [http_process, https_process]

        for p in processes:
            p.start()

        try:
            # Monitor until both processes exit or interrupted
            while any(p.is_alive() for p in processes):
                time.sleep(0.5)
        except KeyboardInterrupt:
            logger.info("Shutting down servers...")
            for p in processes:
                if p.is_alive():
                    p.terminate()
            for p in processes:
                p.join(timeout=5.0)
    else:
        # HTTP only (default)
        logger.info(f"Starting HTTP-only server on http://{args.host}:{args.port}")
        uvicorn.run(
            "rewriter:app",
            host=args.host,
            port=args.port,
            reload=not args.no_reload,
            log_level="debug",
            access_log=True,
        )
