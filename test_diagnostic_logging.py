#!/usr/bin/env python3
"""
Test script to verify diagnostic logging for Circuit API responses.
This script tests both streaming and non-streaming requests.

Usage:
    LOG_LEVEL=DEBUG python test_diagnostic_logging.py
"""
import os
import sys
import asyncio
import json
from pathlib import Path

# Add the package to path
sys.path.insert(0, str(Path(__file__).parent))

# Set DEBUG logging before importing
os.environ["LOG_LEVEL"] = "DEBUG"

from oai_to_circuit.config import load_config
from oai_to_circuit.app import create_app
from fastapi.testclient import TestClient


def test_non_streaming_request():
    """Test non-streaming request with diagnostic logging."""
    print("\n" + "=" * 80)
    print("TEST 1: Non-Streaming Request")
    print("=" * 80)
    
    # Load config from environment
    config = load_config()
    
    # Check if credentials are configured
    if not config.circuit_client_id or not config.circuit_client_secret:
        print("⚠️  WARNING: Circuit credentials not configured")
        print("   Set CIRCUIT_CLIENT_ID, CIRCUIT_CLIENT_SECRET, and CIRCUIT_APPKEY")
        print("   This test will fail but you can still see the diagnostic logging structure")
        print()
    
    app = create_app(config=config)
    client = TestClient(app)
    
    # Make a non-streaming request
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "Say 'Hello' (this is a test)"}
        ],
        "stream": False
    }
    
    try:
        response = client.post(
            "/v1/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer test-diagnostic-key"}
        )
        
        print(f"\n✓ Response Status: {response.status_code}")
        if response.status_code == 200:
            print(f"✓ Response received successfully")
            # Don't print full response in production
            print(f"✓ Content length: {len(response.content)} bytes")
        else:
            print(f"✗ Error response: {response.text[:200]}")
    except Exception as e:
        print(f"✗ Request failed: {e}")
    
    print("\n" + "=" * 80)


def test_streaming_request():
    """Test streaming request with diagnostic logging."""
    print("\n" + "=" * 80)
    print("TEST 2: Streaming Request")
    print("=" * 80)
    
    config = load_config()
    
    if not config.circuit_client_id or not config.circuit_client_secret:
        print("⚠️  WARNING: Circuit credentials not configured")
        print("   This test will fail but you can still see the diagnostic logging structure")
        print()
    
    app = create_app(config=config)
    client = TestClient(app)
    
    # Make a streaming request
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "Count to 3 (this is a test)"}
        ],
        "stream": True
    }
    
    try:
        response = client.post(
            "/v1/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer test-diagnostic-key"}
        )
        
        print(f"\n✓ Response Status: {response.status_code}")
        if response.status_code == 200:
            print(f"✓ Streaming response received")
            # For streaming, we get chunks
            print(f"✓ Content length: {len(response.content)} bytes")
            print(f"✓ Content-Type: {response.headers.get('content-type')}")
        else:
            print(f"✗ Error response: {response.text[:200]}")
    except Exception as e:
        print(f"✗ Request failed: {e}")
    
    print("\n" + "=" * 80)


def main():
    """Run diagnostic logging tests."""
    print("\n" + "=" * 80)
    print("DIAGNOSTIC LOGGING TEST SUITE")
    print("=" * 80)
    print("\nThis script tests the diagnostic logging added to app.py")
    print("Look for log lines marked with:")
    print("  [REQUEST TYPE]")
    print("  [CIRCUIT RESPONSE]")
    print("  [CIRCUIT RATE LIMITS]")
    print("  [STREAMING RESPONSE] or [NON-STREAMING RESPONSE]")
    print("  [TOKEN EXTRACTION]")
    print("\n" + "=" * 80)
    
    # Test non-streaming
    test_non_streaming_request()
    
    # Test streaming
    test_streaming_request()
    
    print("\n" + "=" * 80)
    print("TESTS COMPLETE")
    print("=" * 80)
    print("\nCheck the logs above for diagnostic information about Circuit API responses.")
    print("Next steps:")
    print("  1. Review the diagnostic logs")
    print("  2. Deploy to production with LOG_LEVEL=DEBUG")
    print("  3. Analyze real Circuit API responses")
    print("  4. Proceed to Phase 2 implementation")
    print()


if __name__ == "__main__":
    main()

