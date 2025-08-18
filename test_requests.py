#!/usr/bin/env python3
"""
Test script demonstrating expected requests and common issues.
This helps debug "Invalid HTTP request received" warnings.
"""

import httpx
import json
import asyncio
import base64
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:12000"  # Your server URL
STATIC_API_KEY = "your_static_api_key_here"  # This is ignored by the bridge

# Color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_test_header(test_name: str):
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}TEST: {test_name}{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}")


def print_result(success: bool, message: str):
    color = GREEN if success else RED
    status = "✓ PASS" if success else "✗ FAIL"
    print(f"{color}{status}: {message}{RESET}")


async def test_health_check():
    """Test the health check endpoint."""
    print_test_header("Health Check")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BASE_URL}/health")
            print(f"Status: {response.status_code}")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            
            print_result(
                response.status_code == 200,
                "Health check endpoint is accessible"
            )
            
            data = response.json()
            if not data.get("credentials_configured"):
                print(f"{YELLOW}⚠️  WARNING: Circuit credentials not configured!{RESET}")
            if not data.get("appkey_configured"):
                print(f"{YELLOW}⚠️  WARNING: Circuit appkey not configured!{RESET}")
                
        except httpx.ConnectError:
            print_result(False, "Cannot connect to server - is it running?")
        except Exception as e:
            print_result(False, f"Unexpected error: {e}")


async def test_valid_request():
    """Test a valid OpenAI-style request."""
    print_test_header("Valid OpenAI-style Request")
    
    request_body = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, how are you?"}
        ],
        "temperature": 0.7,
        "max_tokens": 150
    }
    
    print(f"Request body:\n{json.dumps(request_body, indent=2)}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{BASE_URL}/v1/chat/completions",
                json=request_body,
                headers={
                    "Authorization": f"Bearer {STATIC_API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            
            print(f"\nStatus: {response.status_code}")
            
            if response.status_code == 200:
                print_result(True, "Request successful")
                print(f"Response preview: {response.text[:200]}...")
            else:
                print_result(False, f"Request failed with status {response.status_code}")
                print(f"Error: {response.text}")
                
        except Exception as e:
            print_result(False, f"Request failed: {e}")


async def test_missing_model():
    """Test request without model parameter."""
    print_test_header("Missing Model Parameter")
    
    request_body = {
        "messages": [
            {"role": "user", "content": "Hello"}
        ]
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BASE_URL}/v1/chat/completions",
                json=request_body
            )
            
            print_result(
                response.status_code == 400,
                f"Server correctly rejected request (status: {response.status_code})"
            )
            print(f"Error message: {response.text}")
            
        except Exception as e:
            print_result(False, f"Unexpected error: {e}")


async def test_malformed_json():
    """Test request with malformed JSON."""
    print_test_header("Malformed JSON Request")
    
    # Send invalid JSON
    malformed_json = '{"model": "gpt-4o-mini", "messages": [{"role": "user"'  # Missing closing brackets
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BASE_URL}/v1/chat/completions",
                content=malformed_json,
                headers={"Content-Type": "application/json"}
            )
            
            print_result(
                response.status_code == 400,
                f"Server correctly rejected malformed JSON (status: {response.status_code})"
            )
            
        except Exception as e:
            print(f"Client-side error (expected): {e}")


async def test_wrong_endpoint():
    """Test request to wrong endpoint."""
    print_test_header("Wrong Endpoint")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BASE_URL}/v1/engines")
            print_result(
                response.status_code == 404,
                f"Server correctly returned 404 for unknown endpoint"
            )
            
        except Exception as e:
            print_result(False, f"Unexpected error: {e}")


async def test_direct_connection_issue():
    """Test potential causes of 'Invalid HTTP request received'."""
    print_test_header("Direct Connection Issues")
    
    # Test 1: Try connecting with wrong protocol (common cause)
    print(f"\n{YELLOW}Testing common causes of 'Invalid HTTP request received':{RESET}")
    
    # Check if something else is running on the port
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', 12000))
    sock.close()
    
    if result != 0:
        print(f"{RED}✗ Port 12000 is not accessible. Is the server running?{RESET}")
    else:
        print(f"{GREEN}✓ Port 12000 is accessible{RESET}")
    
    # Test raw HTTP request
    print(f"\n{YELLOW}Sending raw HTTP request to test basic connectivity:{RESET}")
    reader, writer = await asyncio.open_connection('localhost', 12000)
    
    try:
        # Send a minimal HTTP request
        writer.write(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        
        # Read response
        data = await reader.read(1000)
        if b"HTTP/1.1" in data:
            print(f"{GREEN}✓ Server responds to raw HTTP requests{RESET}")
        else:
            print(f"{RED}✗ Server not responding properly to HTTP{RESET}")
            
    except Exception as e:
        print(f"{RED}✗ Raw connection failed: {e}{RESET}")
    finally:
        writer.close()
        await writer.wait_closed()


def print_debugging_tips():
    """Print debugging tips for common issues."""
    print(f"\n{YELLOW}{'=' * 60}{RESET}")
    print(f"{YELLOW}DEBUGGING TIPS for 'Invalid HTTP request received':{RESET}")
    print(f"{YELLOW}{'=' * 60}{RESET}")
    
    tips = [
        "1. Check if you're using HTTP vs HTTPS correctly (server expects HTTP on port 12000)",
        "2. Ensure no other process is using port 12000: `lsof -i :12000` or `netstat -an | grep 12000`",
        "3. Check if a proxy or VPN is interfering with connections",
        "4. Try using curl directly: `curl -v http://localhost:12000/health`",
        "5. Check server logs for more details about rejected requests",
        "6. Ensure you're not accidentally sending HTTPS requests to HTTP endpoint",
        "7. Check if firewall is blocking local connections",
        "8. Try connecting with telnet: `telnet localhost 12000`"
    ]
    
    for tip in tips:
        print(f"  • {tip}")
    
    print(f"\n{YELLOW}Example curl commands:{RESET}")
    print("  # Test health endpoint:")
    print("  curl -v http://localhost:12000/health")
    print()
    print("  # Test chat completion:")
    print("""  curl -X POST http://localhost:12000/v1/chat/completions \\
    -H "Content-Type: application/json" \\
    -d '{
      "model": "gpt-4o-mini",
      "messages": [{"role": "user", "content": "Hello"}]
    }'""")


async def main():
    """Run all tests."""
    print(f"{BLUE}OpenAI to Circuit Bridge - Test Suite{RESET}")
    print(f"{BLUE}Testing server at: {BASE_URL}{RESET}")
    
    # Run tests
    await test_health_check()
    await test_valid_request()
    await test_missing_model()
    await test_malformed_json()
    await test_wrong_endpoint()
    await test_direct_connection_issue()
    
    # Print debugging tips
    print_debugging_tips()


if __name__ == "__main__":
    asyncio.run(main())
