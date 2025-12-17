import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Request, Response, HTTPException

from oai_to_circuit.config import BridgeConfig
from oai_to_circuit.oauth import TokenCache, get_access_token
from oai_to_circuit.quota import QuotaManager, load_quotas_from_env_or_file


def extract_subkey(request: Request) -> Optional[str]:
    """Extract a caller subkey from headers."""
    subkey = request.headers.get("X-Bridge-Subkey")
    if subkey:
        return subkey.strip()
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None


def create_app(*, config: BridgeConfig) -> FastAPI:
    logger = logging.getLogger("oai_to_circuit")
    token_cache = TokenCache()
    quota_manager: Optional[QuotaManager] = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal quota_manager
        logger.info("Starting OpenAI to Circuit Bridge server")
        logger.info(f"Circuit base URL: {config.circuit_base}")
        logger.info(f"API version: {config.api_version}")
        logger.info(f"Credentials configured: {bool(config.circuit_client_id and config.circuit_client_secret)}")
        logger.info(f"App key configured: {bool(config.circuit_appkey)}")

        quotas_cfg = load_quotas_from_env_or_file()
        quota_manager = QuotaManager(db_path=config.quota_db_path, quotas=quotas_cfg)
        logger.info(
            f"Quotas enabled: {bool(quotas_cfg)} (db={config.quota_db_path}, require_subkey={config.require_subkey})"
        )

        if not config.circuit_client_id:
            logger.warning("⚠️  Missing CIRCUIT_CLIENT_ID - authentication will fail!")
        if not config.circuit_client_secret:
            logger.warning("⚠️  Missing CIRCUIT_CLIENT_SECRET - authentication will fail!")
        if not config.circuit_appkey:
            logger.warning("⚠️  Missing CIRCUIT_APPKEY - requests may be rejected by Circuit API!")

        yield
        logger.info("Shutting down OpenAI to Circuit Bridge server")

    app = FastAPI(title="OpenAI to Circuit Bridge", version="1.0.0", lifespan=lifespan)

    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "service": "OpenAI to Circuit Bridge",
            "credentials_configured": bool(config.circuit_client_id and config.circuit_client_secret),
            "appkey_configured": bool(config.circuit_appkey),
        }

    @app.post("/v1/chat/completions")
    async def chat_completion(request: Request):
        logger.info(f"Received request from {request.client.host if request.client else 'unknown'}")
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

        caller_subkey = extract_subkey(request)
        if config.require_subkey and not caller_subkey:
            raise HTTPException(
                status_code=401,
                detail="Subkey required. Provide 'Authorization: Bearer <subkey>' or 'X-Bridge-Subkey' header.",
            )

        if caller_subkey and quota_manager:
            if not quota_manager.is_request_allowed(caller_subkey, model):
                logger.warning(f"Quota exceeded (requests) for subkey={caller_subkey} model={model}")
                raise HTTPException(status_code=429, detail="Quota exceeded for this subkey and model (requests)")

        # Insert appkey if not present
        user_field = req_data.get("user")
        if not user_field:
            if not config.circuit_appkey:
                logger.warning("No CIRCUIT_APPKEY configured")
            req_data["user"] = json.dumps({"appkey": config.circuit_appkey})
            logger.debug("Added user field with appkey")
        elif config.circuit_appkey and config.circuit_appkey not in user_field:
            try:
                d = json.loads(user_field)
                d["appkey"] = config.circuit_appkey
                req_data["user"] = json.dumps(d)
                logger.debug("Injected appkey into existing user field")
            except Exception as e:
                logger.warning(f"Failed to inject appkey into user field: {e}")

        target_url = (
            f"{config.circuit_base}/openai/deployments/{model}/chat/completions?api-version={config.api_version}"
        )

        try:
            access_token = await get_access_token(
                token_url=config.token_url,
                client_id=config.circuit_client_id,
                client_secret=config.circuit_client_secret,
                logger=logger,
                cache=token_cache,
            )
        except Exception as e:
            logger.error(f"Failed to get access token: {e}")
            raise HTTPException(status_code=502, detail="Failed to authenticate with Circuit API")

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

            if caller_subkey and quota_manager:
                prompt_tokens = 0
                completion_tokens = 0
                total_tokens = 0
                try:
                    ct = (r.headers.get("content-type") or "").lower()
                    if "application/json" in ct and r.content:
                        payload = r.json()
                        usage = payload.get("usage") if isinstance(payload, dict) else None
                        if isinstance(usage, dict):
                            prompt_tokens = int(usage.get("prompt_tokens") or 0)
                            completion_tokens = int(usage.get("completion_tokens") or 0)
                            total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
                except Exception:
                    pass
                quota_manager.record_usage(
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
            logger.exception("Unexpected error calling Circuit API")
            raise HTTPException(status_code=502, detail=f"Gateway error: {str(e)}")

    return app


