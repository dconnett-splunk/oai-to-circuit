import json
import logging
import time
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
        index: str = "main",
        timeout: float = 5.0,
    ):
        self.hec_url = hec_url
        self.hec_token = hec_token
        self.source = source
        self.sourcetype = sourcetype
        self.index = index
        self.timeout = timeout
        self.enabled = bool(hec_url and hec_token)
        self.logger = logging.getLogger("oai_to_circuit.splunk_hec")

        if self.enabled:
            self.logger.info(f"Splunk HEC enabled: {self.hec_url}")
        else:
            self.logger.info("Splunk HEC disabled (no URL or token configured)")

    def send_usage_event(
        self,
        subkey: str,
        model: str,
        requests: int = 1,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        additional_fields: Optional[Dict[str, Any]] = None,
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
            
        Returns:
            True if event was sent successfully, False otherwise
        """
        if not self.enabled:
            return False

        timestamp_iso = datetime.now(timezone.utc).isoformat()
        
        event_data = {
            "subkey": subkey,
            "model": model,
            "requests": requests,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "timestamp": timestamp_iso,
        }
        
        if additional_fields:
            event_data.update(additional_fields)

        hec_event = {
            "time": time.time(),
            "event": event_data,
            "source": self.source,
            "sourcetype": self.sourcetype,
            "index": self.index,
        }

        try:
            self.logger.debug(f"Sending usage event to Splunk HEC: {json.dumps(event_data)}")
            
            headers = {
                "Authorization": f"Splunk {self.hec_token}",
                "Content-Type": "application/json",
            }
            
            with httpx.Client(timeout=self.timeout, verify=True) as client:
                response = client.post(
                    self.hec_url,
                    json=hec_event,
                    headers=headers,
                )
                
                if response.status_code == 200:
                    self.logger.debug(f"Splunk HEC event sent successfully: {response.text}")
                    return True
                else:
                    self.logger.warning(
                        f"Splunk HEC returned non-200 status: {response.status_code} - {response.text}"
                    )
                    return False
                    
        except httpx.TimeoutException:
            self.logger.warning(f"Splunk HEC request timed out after {self.timeout}s")
            return False
        except Exception as e:
            self.logger.error(f"Failed to send event to Splunk HEC: {e}")
            return False

    def send_error_event(
        self,
        error_type: str,
        error_message: str,
        subkey: Optional[str] = None,
        model: Optional[str] = None,
        additional_fields: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Send an error event to Splunk HEC.
        
        Args:
            error_type: Type of error (e.g., 'quota_exceeded', 'auth_failed')
            error_message: Detailed error message
            subkey: Optional user/team identifier
            model: Optional model name
            additional_fields: Extra fields to include
            
        Returns:
            True if event was sent successfully, False otherwise
        """
        if not self.enabled:
            return False

        timestamp_iso = datetime.now(timezone.utc).isoformat()
        
        event_data = {
            "event_type": "error",
            "error_type": error_type,
            "error_message": error_message,
            "timestamp": timestamp_iso,
        }
        
        if subkey:
            event_data["subkey"] = subkey
        if model:
            event_data["model"] = model
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
            headers = {
                "Authorization": f"Splunk {self.hec_token}",
                "Content-Type": "application/json",
            }
            
            with httpx.Client(timeout=self.timeout, verify=True) as client:
                response = client.post(
                    self.hec_url,
                    json=hec_event,
                    headers=headers,
                )
                
                if response.status_code == 200:
                    return True
                else:
                    self.logger.warning(
                        f"Splunk HEC error event failed: {response.status_code} - {response.text}"
                    )
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to send error event to Splunk HEC: {e}")
            return False

