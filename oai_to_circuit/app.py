import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, AsyncIterator

import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import StreamingResponse

from oai_to_circuit.config import BridgeConfig
from oai_to_circuit.oauth import TokenCache, get_access_token
from oai_to_circuit.quota import QuotaManager, load_quotas_from_env_or_file
from oai_to_circuit.splunk_hec import SplunkHEC
from oai_to_circuit.pricing import calculate_cost


def extract_subkey(request: Request) -> Optional[str]:
    """Extract a caller subkey from headers."""
    subkey = request.headers.get("X-Bridge-Subkey")
    if subkey:
        return subkey.strip()
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None


async def parse_sse_stream(
    response: httpx.Response,
    logger: logging.Logger
) -> AsyncIterator[tuple[bytes, Optional[Dict[str, int]]]]:
    """
    Parse SSE (Server-Sent Events) stream and extract usage data.
    
    Yields chunks to forward to client, and extracts usage from final chunk.
    
    Args:
        response: httpx Response object with streaming content
        logger: Logger instance
        
    Yields:
        Tuple of (chunk_bytes, usage_dict)
        - chunk_bytes: Raw bytes to forward to client
        - usage_dict: Token usage if found in this chunk, else None
    """
    usage_data: Optional[Dict[str, int]] = None
    
    async for line in response.aiter_lines():
        chunk_bytes = (line + "\n").encode('utf-8')
        
        # Parse SSE data lines
        if line.startswith("data: "):
            data_content = line[6:]  # Remove "data: " prefix
            
            # Check for [DONE] marker
            if data_content.strip() == "[DONE]":
                logger.debug("[SSE PARSER] Reached [DONE] marker")
                yield (chunk_bytes, usage_data)
                continue
            
            # Try to parse JSON from data line
            try:
                data_json = json.loads(data_content)
                
                # Check for usage field (typically in final chunk before [DONE])
                if isinstance(data_json, dict) and "usage" in data_json:
                    usage = data_json.get("usage")
                    if isinstance(usage, dict):
                        usage_data = {
                            "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                            "completion_tokens": int(usage.get("completion_tokens", 0)),
                            "total_tokens": int(usage.get("total_tokens", 0)),
                        }
                        logger.debug(f"[SSE PARSER] Extracted usage from stream: {usage_data}")
            except json.JSONDecodeError:
                # Not JSON or malformed, just pass through
                logger.debug(f"[SSE PARSER] Non-JSON data line: {data_content[:100]}")
            except Exception as e:
                logger.debug(f"[SSE PARSER] Error parsing SSE chunk: {e}")
        
        # Forward all chunks to client (including non-data lines)
        yield (chunk_bytes, None)
    
    # If we collected usage data during the stream, yield it at the end
    if usage_data:
        logger.info(f"[SSE PARSER] Final usage extracted from stream: {usage_data}")
        yield (b"", usage_data)


def create_app(*, config: BridgeConfig) -> FastAPI:
    logger = logging.getLogger("oai_to_circuit")
    token_cache = TokenCache()
    quota_manager: Optional[QuotaManager] = None
    splunk_hec: Optional[SplunkHEC] = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal quota_manager, splunk_hec
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

        # Initialize Splunk HEC
        splunk_hec = SplunkHEC(
            hec_url=config.splunk_hec_url,
            hec_token=config.splunk_hec_token,
            source=config.splunk_source,
            sourcetype=config.splunk_sourcetype,
            index=config.splunk_index,
            verify_ssl=config.splunk_verify_ssl,
            hash_subkeys=True,  # Always hash subkeys for privacy
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
        # Extract client IP and X-Forwarded-For for proper source tracking
        client_ip = request.client.host if request.client else 'unknown'
        x_forwarded_for = request.headers.get("X-Forwarded-For", "")
        
        if x_forwarded_for:
            logger.info(f"Received request from {client_ip} (X-Forwarded-For: {x_forwarded_for})")
        else:
            logger.info(f"Received request from {client_ip}")
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

        # Verify subkey is authorized (exists in quotas config or database)
        if caller_subkey and quota_manager:
            if not quota_manager.is_subkey_authorized(caller_subkey):
                logger.warning(f"Unauthorized subkey attempted access: {caller_subkey[:20]}...")
                
                # Send unauthorized access event to Splunk
                if splunk_hec:
                    splunk_hec.send_error_event(
                        error_type="unauthorized_subkey",
                        error_message="Subkey not found in authorized list",
                        subkey=caller_subkey,
                        model=model,
                        additional_fields={
                            "client_ip": client_ip,
                            "x_forwarded_for": x_forwarded_for,
                        },
                    )
                
                raise HTTPException(
                    status_code=403,
                    detail="Unauthorized: Subkey not recognized. Please contact administrator.",
                )

        if caller_subkey and quota_manager:
            if not quota_manager.is_request_allowed(caller_subkey, model):
                logger.warning(f"Quota exceeded (requests) for subkey={caller_subkey} model={model}")
                
                # Send quota exceeded event to Splunk
                if splunk_hec:
                    friendly_name = quota_manager.get_friendly_name(caller_subkey)
                    splunk_hec.send_error_event(
                        error_type="quota_exceeded",
                        error_message=f"Request quota exceeded for model {model}",
                        subkey=caller_subkey,
                        model=model,
                        friendly_name=friendly_name,
                        additional_fields={
                            "client_ip": client_ip,
                            "x_forwarded_for": x_forwarded_for,
                        },
                    )
                
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

        # Log streaming parameter for diagnostic purposes
        is_streaming_request = req_data.get("stream", False)
        logger.info(f"Forwarding to Circuit API: {target_url}")
        logger.debug(f"Circuit request body: {json.dumps(req_data, indent=2)}")
        logger.debug(f"[REQUEST TYPE] Streaming request: {is_streaming_request}")

        try:
            async with httpx.AsyncClient(timeout=90) as client:
                r = await client.post(target_url, json=req_data, headers=headers)
            
            # Diagnostic logging for Circuit API response
            logger.debug(f"[CIRCUIT RESPONSE] Status: {r.status_code}")
            logger.debug(f"[CIRCUIT RESPONSE] Content-Type: {r.headers.get('content-type')}")
            logger.debug(f"[CIRCUIT RESPONSE] All headers: {dict(r.headers)}")
            
            # Look for rate limit headers specifically
            rate_limit_headers = {k: v for k, v in r.headers.items() if 'ratelimit' in k.lower() or 'rate-limit' in k.lower()}
            if rate_limit_headers:
                logger.info(f"[CIRCUIT RATE LIMITS] {rate_limit_headers}")
            else:
                logger.debug("[CIRCUIT RATE LIMITS] No rate limit headers found")
            
            # Check if response is streaming
            ct = (r.headers.get("content-type") or "").lower()
            is_streaming_response = "text/event-stream" in ct or "stream" in ct
            
            if is_streaming_response:
                # Handle streaming response
                logger.info(f"[STREAMING RESPONSE] Detected streaming response, will parse SSE")
                
                # Create async generator that parses SSE and forwards chunks
                async def stream_with_usage_tracking():
                    collected_usage: Optional[Dict[str, int]] = None
                    
                    # Re-open the stream
                    async with httpx.AsyncClient(timeout=90) as stream_client:
                        async with stream_client.stream("POST", target_url, json=req_data, headers=headers) as stream_response:
                            async for chunk_bytes, usage in parse_sse_stream(stream_response, logger):
                                if usage:
                                    collected_usage = usage
                                if chunk_bytes:
                                    yield chunk_bytes
                    
                    # After stream completes, record usage
                    if caller_subkey and quota_manager and collected_usage:
                        prompt_tokens = collected_usage.get("prompt_tokens", 0)
                        completion_tokens = collected_usage.get("completion_tokens", 0)
                        total_tokens = collected_usage.get("total_tokens", 0)
                        
                        logger.info(f"[STREAMING] Recording usage: prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}")
                        
                        # Calculate cost
                        estimated_cost, cost_known = calculate_cost(model, prompt_tokens, completion_tokens)
                        if cost_known:
                            logger.debug(f"[COST] Estimated cost for streaming request: ${estimated_cost:.6f}")
                        
                        quota_manager.record_usage(
                            subkey=caller_subkey,
                            model=model,
                            request_inc=1,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            total_tokens=total_tokens,
                        )
                        
                        # Send usage event to Splunk HEC
                        if splunk_hec:
                            friendly_name, email = quota_manager.get_name_and_email(caller_subkey)
                            
                            # Prepare additional fields with cost and rate limits
                            additional_fields = {
                                "status_code": r.status_code,
                                "success": r.status_code < 400,
                                "client_ip": client_ip,
                                "x_forwarded_for": x_forwarded_for,
                                "is_streaming": True,
                                "cost_known": cost_known,
                            }
                            
                            if cost_known:
                                additional_fields["estimated_cost_usd"] = estimated_cost
                            
                            # Add rate limit info if available
                            if rate_limit_headers:
                                additional_fields["circuit_rate_limits"] = rate_limit_headers
                            
                            splunk_hec.send_usage_event(
                                subkey=caller_subkey,
                                model=model,
                                requests=1,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                total_tokens=total_tokens,
                                additional_fields=additional_fields,
                                friendly_name=friendly_name,
                                email=email,
                            )
                    elif caller_subkey and quota_manager:
                        logger.warning("[STREAMING] No usage data collected from stream")
                
                return StreamingResponse(
                    stream_with_usage_tracking(),
                    status_code=r.status_code,
                    headers={"Content-Type": r.headers.get("content-type", "text/event-stream")},
                    media_type=r.headers.get("content-type", "text/event-stream")
                )
            
            else:
                # Handle non-streaming response
                logger.debug(f"[NON-STREAMING RESPONSE] Processing JSON response")
                if "application/json" in ct and r.content:
                    logger.debug(f"[NON-STREAMING RESPONSE] Full JSON response: {r.text}")
                
                if caller_subkey and quota_manager:
                    prompt_tokens = 0
                    completion_tokens = 0
                    total_tokens = 0
                    try:
                        if "application/json" in ct and r.content:
                            payload = r.json()
                            usage = payload.get("usage") if isinstance(payload, dict) else None
                            if isinstance(usage, dict):
                                prompt_tokens = int(usage.get("prompt_tokens") or 0)
                                completion_tokens = int(usage.get("completion_tokens") or 0)
                                total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
                                logger.debug(f"[TOKEN EXTRACTION] Successfully extracted tokens: prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}")
                            else:
                                logger.debug(f"[TOKEN EXTRACTION] No usage dict found in response payload")
                        else:
                            logger.debug(f"[TOKEN EXTRACTION] Skipped - Content-Type: {ct}, has_content: {bool(r.content)}")
                    except Exception as e:
                        logger.warning(
                            f"[TOKEN EXTRACTION] Failed to extract token usage from response: {type(e).__name__}: {e}. "
                            f"Content-Type: {ct}, Status: {r.status_code}, "
                            f"Has content: {bool(r.content)}"
                        )
                        logger.debug(f"[TOKEN EXTRACTION] Response body that failed to parse: {r.text[:500] if r.text else 'empty'}")
                    
                    # Calculate cost
                    estimated_cost, cost_known = calculate_cost(model, prompt_tokens, completion_tokens)
                    if cost_known:
                        logger.debug(f"[COST] Estimated cost for non-streaming request: ${estimated_cost:.6f}")
                    
                    quota_manager.record_usage(
                        subkey=caller_subkey,
                        model=model,
                        request_inc=1,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                    )
                    
                    # Send usage event to Splunk HEC
                    if splunk_hec:
                        friendly_name, email = quota_manager.get_name_and_email(caller_subkey)
                        
                        # Prepare additional fields with cost and rate limits
                        additional_fields = {
                            "status_code": r.status_code,
                            "success": r.status_code < 400,
                            "client_ip": client_ip,
                            "x_forwarded_for": x_forwarded_for,
                            "is_streaming": False,
                            "cost_known": cost_known,
                        }
                        
                        if cost_known:
                            additional_fields["estimated_cost_usd"] = estimated_cost
                        
                        # Add rate limit info if available
                        if rate_limit_headers:
                            additional_fields["circuit_rate_limits"] = rate_limit_headers
                        
                        splunk_hec.send_usage_event(
                            subkey=caller_subkey,
                            model=model,
                            requests=1,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            total_tokens=total_tokens,
                            additional_fields=additional_fields,
                            friendly_name=friendly_name,
                            email=email,
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


