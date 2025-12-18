import json
from unittest.mock import Mock, patch

import pytest

from oai_to_circuit.splunk_hec import SplunkHEC


def test_splunk_hec_disabled_when_no_config():
    """Test that Splunk HEC is disabled when URL or token is missing."""
    hec = SplunkHEC(hec_url=None, hec_token=None)
    assert hec.enabled is False

    hec = SplunkHEC(hec_url="http://example.com", hec_token=None)
    assert hec.enabled is False

    hec = SplunkHEC(hec_url=None, hec_token="token123")
    assert hec.enabled is False


def test_splunk_hec_enabled_with_config():
    """Test that Splunk HEC is enabled when both URL and token are provided."""
    hec = SplunkHEC(hec_url="http://splunk.example.com:8088/services/collector/event", hec_token="token123")
    assert hec.enabled is True


def test_send_usage_event_returns_false_when_disabled():
    """Test that send_usage_event returns False when HEC is disabled."""
    hec = SplunkHEC(hec_url=None, hec_token=None)
    result = hec.send_usage_event(subkey="test", model="gpt-4o-mini", requests=1)
    assert result is False


@patch("oai_to_circuit.splunk_hec.httpx.Client")
def test_send_usage_event_success(mock_client_class):
    """Test successful usage event submission to Splunk HEC."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = '{"text":"Success","code":0}'

    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client.post = Mock(return_value=mock_response)
    mock_client_class.return_value = mock_client

    hec = SplunkHEC(
        hec_url="http://splunk.example.com:8088/services/collector/event",
        hec_token="test-token-123",
        source="oai-test",
        sourcetype="llm:test",
        index="test",
    )

    result = hec.send_usage_event(
        subkey="test-user",
        model="gpt-4o-mini",
        requests=1,
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )

    assert result is True
    mock_client.post.assert_called_once()

    # Verify the call arguments
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "http://splunk.example.com:8088/services/collector/event"

    # Check headers
    headers = call_args[1]["headers"]
    assert headers["Authorization"] == "Splunk test-token-123"
    assert headers["Content-Type"] == "application/json"

    # Check event payload
    event_payload = call_args[1]["json"]
    assert "time" in event_payload
    assert event_payload["source"] == "oai-test"
    assert event_payload["sourcetype"] == "llm:test"
    assert event_payload["index"] == "test"

    event_data = event_payload["event"]
    assert event_data["subkey"] == "test-user"
    assert event_data["model"] == "gpt-4o-mini"
    assert event_data["requests"] == 1
    assert event_data["prompt_tokens"] == 100
    assert event_data["completion_tokens"] == 50
    assert event_data["total_tokens"] == 150
    assert "timestamp" in event_data


@patch("oai_to_circuit.splunk_hec.httpx.Client")
def test_send_usage_event_with_additional_fields(mock_client_class):
    """Test that additional fields are included in the event."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = '{"text":"Success","code":0}'

    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client.post = Mock(return_value=mock_response)
    mock_client_class.return_value = mock_client

    hec = SplunkHEC(hec_url="http://splunk.example.com:8088", hec_token="token")

    result = hec.send_usage_event(
        subkey="test-user",
        model="gpt-4o",
        requests=1,
        additional_fields={"status_code": 200, "success": True, "custom_field": "value"},
    )

    assert result is True

    call_args = mock_client.post.call_args
    event_data = call_args[1]["json"]["event"]
    assert event_data["status_code"] == 200
    assert event_data["success"] is True
    assert event_data["custom_field"] == "value"


@patch("oai_to_circuit.splunk_hec.httpx.Client")
def test_send_usage_event_handles_non_200_response(mock_client_class):
    """Test that non-200 responses are handled gracefully."""
    mock_response = Mock()
    mock_response.status_code = 400
    mock_response.text = '{"text":"Invalid token","code":4}'

    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client.post = Mock(return_value=mock_response)
    mock_client_class.return_value = mock_client

    hec = SplunkHEC(hec_url="http://splunk.example.com:8088", hec_token="bad-token")

    result = hec.send_usage_event(subkey="test", model="gpt-4o-mini", requests=1)

    assert result is False


@patch("oai_to_circuit.splunk_hec.httpx.Client")
def test_send_usage_event_handles_timeout(mock_client_class):
    """Test that timeout exceptions are handled gracefully."""
    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client.post = Mock(side_effect=Exception("Timeout"))
    mock_client_class.return_value = mock_client

    hec = SplunkHEC(hec_url="http://splunk.example.com:8088", hec_token="token", timeout=1.0)

    result = hec.send_usage_event(subkey="test", model="gpt-4o-mini", requests=1)

    assert result is False


@patch("oai_to_circuit.splunk_hec.httpx.Client")
def test_send_error_event_success(mock_client_class):
    """Test successful error event submission to Splunk HEC."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = '{"text":"Success","code":0}'

    mock_client = Mock()
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client.post = Mock(return_value=mock_response)
    mock_client_class.return_value = mock_client

    hec = SplunkHEC(hec_url="http://splunk.example.com:8088", hec_token="token")

    result = hec.send_error_event(
        error_type="quota_exceeded",
        error_message="User exceeded quota",
        subkey="test-user",
        model="gpt-4o",
    )

    assert result is True

    call_args = mock_client.post.call_args
    event_payload = call_args[1]["json"]
    assert event_payload["sourcetype"] == "llm:usage:error"

    event_data = event_payload["event"]
    assert event_data["event_type"] == "error"
    assert event_data["error_type"] == "quota_exceeded"
    assert event_data["error_message"] == "User exceeded quota"
    assert event_data["subkey"] == "test-user"
    assert event_data["model"] == "gpt-4o"


def test_send_error_event_returns_false_when_disabled():
    """Test that send_error_event returns False when HEC is disabled."""
    hec = SplunkHEC(hec_url=None, hec_token=None)
    result = hec.send_error_event(error_type="test", error_message="test message")
    assert result is False

