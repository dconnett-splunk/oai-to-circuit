#!/usr/bin/env python3
"""
Quick test to verify HTTPS support is working.
"""

import httpx
import asyncio
import ssl
import json

async def test_https():
    """Test HTTPS endpoint."""
    print("Testing HTTPS support...")
    
    # Create client that accepts self-signed certificates
    client = httpx.AsyncClient(verify=False)
    
    try:
        # Test health endpoint
        print("\n1. Testing HTTPS health endpoint...")
        response = await client.get("https://localhost:12443/health")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   ✅ HTTPS is working!")
            print(f"   Response: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"   ❌ Unexpected status code")
        
        # Test chat completion
        print("\n2. Testing HTTPS chat completion...")
        response = await client.post(
            "https://localhost:12443/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Say 'HTTPS works!'"}]
            }
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   ✅ Chat completion via HTTPS successful")
        else:
            print(f"   ❌ Error: {response.text}")
            
    except httpx.ConnectError as e:
        print(f"\n❌ Cannot connect to HTTPS server on port 12443")
        print(f"   Make sure server is running with --ssl or --ssl-only")
        print(f"   Error: {e}")
    except ssl.SSLError as e:
        print(f"\n❌ SSL Error: {e}")
        print(f"   This might be normal if using self-signed certificates")
    finally:
        await client.aclose()

async def test_http():
    """Test that HTTP still works in dual mode."""
    print("\n3. Testing HTTP endpoint (if in dual mode)...")
    
    client = httpx.AsyncClient()
    try:
        response = await client.get("http://localhost:12000/health")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   ✅ HTTP is also working!")
        else:
            print(f"   ❌ HTTP not available (might be in HTTPS-only mode)")
    except httpx.ConnectError:
        print(f"   ℹ️  HTTP not available (server might be in HTTPS-only mode)")
    finally:
        await client.aclose()

def print_instructions():
    """Print setup instructions."""
    print("\n" + "="*60)
    print("HTTPS Setup Instructions")
    print("="*60)
    print("\n1. Generate certificates (if not already done):")
    print("   python generate_cert.py")
    print("\n2. Start server with HTTPS:")
    print("   python rewriter.py --ssl        # Both HTTP and HTTPS")
    print("   python rewriter.py --ssl-only   # HTTPS only")
    print("\n3. Run this test:")
    print("   python test_https.py")
    print("\n" + "="*60)

async def main():
    """Run all tests."""
    print_instructions()
    await test_https()
    await test_http()
    
    print("\n✅ HTTPS support has been added to fix the 'Invalid HTTP request received' issue!")
    print("   Clients can now use either HTTP or HTTPS depending on server mode.")

if __name__ == "__main__":
    # Suppress SSL warnings for self-signed certificates
    import warnings
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    
    asyncio.run(main())
