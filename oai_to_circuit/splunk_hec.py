import json
import logging
import time
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime, timezone

import httpx


class SplunkHEC:
    """
    Splunk HTTP Event Collector (HEC) client for streaming usage metrics.
    
    Sends usage events to Splunk HEC endpoint for analytics and monitoring.
    """

    def __init__(
        self,
        hec_url: Optional[str] = None,
        hec_token: Optional[str] = None,
        source: str = "oai-to-circuit",
        sourcetype: str = "llm:usage",
        index: str = "oai_circuit",
        timeout: float = 5.0,
        hash_subkeys: bool = True,
        verify_ssl: bool = True,
    ):
        self.hec_url = hec_url
        self.hec_token = hec_token
        self.source = source
        self.sourcetype = sourcetype
        self.index = index
        self.timeout = timeout
        self.hash_subkeys = hash_subkeys
        self.verify_ssl = verify_ssl
        self.enabled = bool(hec_url and hec_token)
        self.logger = logging.getLogger("oai_to_circuit.splunk_hec")

        if self.enabled:
            ssl_status = "enabled" if verify_ssl else "DISABLED (insecure)"
            self.logger.info(
                f"Splunk HEC enabled: {self.hec_url} "
                f"(subkey hashing: {'enabled' if hash_subkeys else 'disabled'}, "
                f"SSL verification: {ssl_status})"
            )
        else:
            self.logger.info("Splunk HEC disabled (no URL or token configured)")

    def _hash_subkey(self, subkey: str) -> str:
        """
        Hash a subkey for privacy while maintaining consistent identification.
        Uses SHA-256 and returns first 16 chars for readability.
        
        Args:
            subkey: The subkey to hash
            
        Returns:
            Hashed subkey (or original if hashing is disabled)
        """
        if not self.hash_subkeys:
            return subkey
        
        # Use SHA-256 for consistent, secure hashing
        hash_obj = hashlib.sha256(subkey.encode('utf-8'))
        # Return first 16 chars of hex digest for readability
        return f"sha256:{hash_obj.hexdigest()[:16]}"

    def send_usage_event(
        self,
        subkey: str,
        model: str,
        requests: int = 1,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        additional_fields: Optional[Dict[str, Any]] = None,
        preserve_timestamp: bool = False,
        friendly_name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> bool:
        """
        Send a usage event to Splunk HEC.
        
        Args:
            subkey: User/team identifier
            model: Model name used
            requests: Number of requests (usually 1)
            prompt_tokens: Tokens in the prompt
            completion_tokens: Tokens in the completion
            total_tokens: Total tokens used
            additional_fields: Extra fields to include in the event
            preserve_timestamp: Whether to preserve timestamp from additional_fields
            friendly_name: Optional friendly name for the subkey
            email: Optional email for the subkey
            
        Returns:
            True if event was sent successfully, False otherwise
        """
        if not self.enabled:
            self.logger.debug("Splunk HEC is disabled, skipping usage event")
            return False

        # Hash subkey for privacy in exports
        hashed_subkey = self._hash_subkey(subkey)
        
        # Use existing timestamp from additional_fields if preserve_timestamp is True
        if preserve_timestamp and additional_fields and 'timestamp' in additional_fields:
            timestamp_iso = additional_fields['timestamp']
        else:
            timestamp_iso = datetime.now(timezone.utc).isoformat()
        
        event_data = {
            "subkey": hashed_subkey,
            "model": model,
            "requests": requests,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "timestamp": timestamp_iso,
        }
        
        # Add friendly name and email if provided
        if friendly_name:
            event_data["friendly_name"] = friendly_name
        if email:
            event_data["email"] = email
        
        if additional_fields:
            # Don't duplicate timestamp if we already used it
            for key, value in additional_fields.items():
                if key != 'timestamp' or not preserve_timestamp:
                    event_data[key] = value

        hec_event = {
            "time": time.time(),
            "event": event_data,
            "source": self.source,
            "sourcetype": self.sourcetype,
            "index": self.index,
        }

        try:
            self.logger.info(
                f"[HEC EXPORT] Starting Splunk HEC export - "
                f"subkey={hashed_subkey}, model={model}, "
                f"tokens={total_tokens} (prompt={prompt_tokens}, completion={completion_tokens}), "
                f"url={self.hec_url}"
            )
            self.logger.debug(f"[HEC EXPORT] Full HEC payload: {json.dumps(hec_event, indent=2)}")
            
            headers = {
                "Authorization": f"Splunk {self.hec_token}",
                "Content-Type": "application/json",
            }
            
            self.logger.debug(
                f"[HEC EXPORT] Sending POST to {self.hec_url} with timeout={self.timeout}s, "
                f"verify_ssl={self.verify_ssl}, "
                f"token={self.hec_token[:10] if self.hec_token else 'None'}..."
            )
            
            with httpx.Client(timeout=self.timeout, verify=self.verify_ssl) as client:
                response = client.post(
                    self.hec_url,
                    json=hec_event,
                    headers=headers,
                )
                
                if response.status_code == 200:
                    self.logger.info(
                        f"[HEC EXPORT] ✓ SUCCESS - Event sent successfully for "
                        f"subkey={hashed_subkey}, model={model}, tokens={total_tokens}. "
                        f"Response: {response.text}"
                    )
                    return True
                else:
                    self.logger.error(
                        f"[HEC EXPORT] ✗ FAILED - Non-200 status code {response.status_code} for "
                        f"subkey={hashed_subkey}, model={model}. "
                        f"URL: {self.hec_url}. "
                        f"Response body: {response.text}. "
                        f"Request payload: {json.dumps(hec_event)}"
                    )
                    return False
                    
        except httpx.TimeoutException as e:
            self.logger.error(
                f"[HEC EXPORT] ✗ TIMEOUT - Request timed out after {self.timeout}s for "
                f"subkey={hashed_subkey}, model={model}, tokens={total_tokens}. "
                f"URL: {self.hec_url}. "
                f"Error details: {e}. "
                f"Payload size: {len(json.dumps(hec_event))} bytes"
            )
            return False
        except httpx.ConnectError as e:
            self.logger.error(
                f"[HEC EXPORT] ✗ CONNECTION FAILED - Cannot connect to Splunk HEC for "
                f"subkey={hashed_subkey}, model={model}. "
                f"URL: {self.hec_url}. "
                f"Error: {e}"
            )
            return False
        except httpx.HTTPError as e:
            self.logger.error(
                f"[HEC EXPORT] ✗ HTTP ERROR - HTTP error sending event for "
                f"subkey={hashed_subkey}, model={model}. "
                f"URL: {self.hec_url}. "
                f"Error: {type(e).__name__}: {e}"
            )
            return False
        except Exception as e:
            self.logger.error(
                f"[HEC EXPORT] ✗ UNEXPECTED ERROR - Failed to send event for "
                f"subkey={hashed_subkey}, model={model}. "
                f"URL: {self.hec_url}. "
                f"Error: {type(e).__name__}: {e}",
                exc_info=True
            )
            return False

    def send_error_event(
        self,
        error_type: str,
        error_message: str,
        subkey: Optional[str] = None,
        model: Optional[str] = None,
        additional_fields: Optional[Dict[str, Any]] = None,
        friendly_name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> bool:
        """
        Send an error event to Splunk HEC.
        
        Args:
            error_type: Type of error (e.g., 'quota_exceeded', 'auth_failed')
            error_message: Detailed error message
            subkey: Optional user/team identifier
            model: Optional model name
            additional_fields: Extra fields to include
            friendly_name: Optional friendly name for the subkey
            email: Optional email for the subkey
            
        Returns:
            True if event was sent successfully, False otherwise
        """
        if not self.enabled:
            self.logger.debug("Splunk HEC is disabled, skipping error event")
            return False

        # Hash subkey for privacy in exports
        hashed_subkey = self._hash_subkey(subkey) if subkey else None
        
        timestamp_iso = datetime.now(timezone.utc).isoformat()
        
        event_data = {
            "event_type": "error",
            "error_type": error_type,
            "error_message": error_message,
            "timestamp": timestamp_iso,
        }
        
        if hashed_subkey:
            event_data["subkey"] = hashed_subkey
        if model:
            event_data["model"] = model
        if friendly_name:
            event_data["friendly_name"] = friendly_name
        if email:
            event_data["email"] = email
        if additional_fields:
            event_data.update(additional_fields)

        hec_event = {
            "time": time.time(),
            "event": event_data,
            "source": self.source,
            "sourcetype": f"{self.sourcetype}:error",
            "index": self.index,
        }

        try:
            self.logger.info(
                f"[HEC ERROR EXPORT] Starting Splunk HEC error export - "
                f"error_type={error_type}, subkey={hashed_subkey}, model={model}, "
                f"url={self.hec_url}"
            )
            self.logger.debug(f"[HEC ERROR EXPORT] Full HEC error payload: {json.dumps(hec_event, indent=2)}")
            
            headers = {
                "Authorization": f"Splunk {self.hec_token}",
                "Content-Type": "application/json",
            }
            
            with httpx.Client(timeout=self.timeout, verify=self.verify_ssl) as client:
                response = client.post(
                    self.hec_url,
                    json=hec_event,
                    headers=headers,
                )
                
                if response.status_code == 200:
                    self.logger.info(
                        f"[HEC ERROR EXPORT] ✓ SUCCESS - Error event sent successfully: "
                        f"error_type={error_type}, subkey={hashed_subkey}. "
                        f"Response: {response.text}"
                    )
                    return True
                else:
                    self.logger.error(
                        f"[HEC ERROR EXPORT] ✗ FAILED - Status {response.status_code}: "
                        f"error_type={error_type}, subkey={hashed_subkey}, model={model}. "
                        f"URL: {self.hec_url}. "
                        f"Response: {response.text}"
                    )
                    return False
                    
        except httpx.TimeoutException as e:
            self.logger.error(
                f"[HEC ERROR EXPORT] ✗ TIMEOUT - Request timed out after {self.timeout}s: "
                f"error_type={error_type}, subkey={hashed_subkey}. "
                f"URL: {self.hec_url}. Error: {e}"
            )
            return False
        except httpx.ConnectError as e:
            self.logger.error(
                f"[HEC ERROR EXPORT] ✗ CONNECTION FAILED - Cannot connect to Splunk HEC: "
                f"error_type={error_type}, subkey={hashed_subkey}. "
                f"URL: {self.hec_url}. Error: {e}"
            )
            return False
        except httpx.HTTPError as e:
            self.logger.error(
                f"[HEC ERROR EXPORT] ✗ HTTP ERROR - Failed sending error event: "
                f"error_type={error_type}, subkey={hashed_subkey}. "
                f"URL: {self.hec_url}. Error: {type(e).__name__}: {e}"
            )
            return False
        except Exception as e:
            self.logger.error(
                f"[HEC ERROR EXPORT] ✗ UNEXPECTED ERROR - Failed to send error event: "
                f"error_type={error_type}, subkey={hashed_subkey}. "
                f"URL: {self.hec_url}. Error: {type(e).__name__}: {e}",
                exc_info=True
            )
            return False

