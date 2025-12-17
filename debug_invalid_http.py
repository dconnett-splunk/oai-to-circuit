#!/usr/bin/env python3
"""
Debug script specifically for "Invalid HTTP request received" warnings.
This tests various scenarios that commonly cause this error.
"""

import socket
import ssl
import asyncio
import httpx
import time

HOST = "localhost"
PORT = 12000


def test_raw_tcp_connection():
    """Test raw TCP connection to see if port is open."""
    print("\n1. Testing raw TCP connection...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((HOST, PORT))
        if result == 0:
            print("   ✓ Port is open and accepting connections")
        else:
            print(f"   ✗ Cannot connect to port {PORT} (error code: {result})")
            print("   → Is the server running? Check with: ps aux | grep rewriter.py")
        sock.close()
    except Exception as e:
        print(f"   ✗ TCP connection failed: {e}")


def test_https_on_http_port():
    """Test if HTTPS request on HTTP port causes the error."""
    print("\n2. Testing HTTPS request on HTTP port (common cause)...")
    try:
        # Try to establish SSL connection on HTTP port
        context = ssl.create_default_context()
        with socket.create_connection((HOST, PORT), timeout=5) as sock:
            try:
                with context.wrap_socket(sock, server_hostname=HOST) as ssock:
                    print("   ✗ SSL handshake succeeded (unexpected)")
            except ssl.SSLError as e:
                print("   ✓ SSL handshake failed as expected (server is HTTP only)")
                print(f"   → This would cause 'Invalid HTTP request received'")
    except Exception as e:
        print(f"   ! Connection failed: {e}")


def test_malformed_http():
    """Send various malformed HTTP requests."""
    print("\n3. Testing malformed HTTP requests...")
    
    test_cases = [
        ("Empty request", b""),
        ("No HTTP version", b"GET /health\r\n\r\n"),
        ("Invalid method", b"INVALID /health HTTP/1.1\r\n\r\n"),
        ("Binary garbage", b"\x00\x01\x02\x03\x04\x05"),
        ("Incomplete headers", b"GET /health HTTP/1.1\r\nHost: "),
    ]
    
    for name, data in test_cases:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((HOST, PORT))
            sock.send(data)
            
            # Try to receive response
            try:
                response = sock.recv(1024)
                if response:
                    print(f"   - {name}: Got response (len={len(response)})")
                else:
                    print(f"   - {name}: Connection closed by server")
            except socket.timeout:
                print(f"   - {name}: No response (timeout)")
            
            sock.close()
        except Exception as e:
            print(f"   - {name}: Error: {e}")


async def test_http_client_requests():
    """Test various HTTP client requests."""
    print("\n4. Testing HTTP client requests...")
    
    # Test 1: Normal HTTP request
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://{HOST}:{PORT}/health")
            print(f"   ✓ HTTP request successful (status: {response.status_code})")
    except Exception as e:
        print(f"   ✗ HTTP request failed: {e}")
    
    # Test 2: HTTPS URL (will fail)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://{HOST}:{PORT}/health")
            print(f"   ✗ HTTPS request succeeded (unexpected)")
    except Exception as e:
        print(f"   ✓ HTTPS request failed as expected: {type(e).__name__}")
        print("   → This is a common cause of 'Invalid HTTP request received'")


def test_connection_close():
    """Test immediate connection close."""
    print("\n5. Testing immediate connection close...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((HOST, PORT))
        sock.close()  # Close immediately without sending anything
        print("   ✓ Immediate close completed")
        print("   → This can also cause 'Invalid HTTP request received'")
    except Exception as e:
        print(f"   ✗ Connection failed: {e}")


def check_server_process():
    """Check if server process is running."""
    print("\n6. Checking server process...")
    import subprocess
    
    try:
        # Check for Python processes running rewriter
        result = subprocess.run(
            ["ps", "aux"], 
            capture_output=True, 
            text=True
        )
        
        rewriter_processes = [
            line for line in result.stdout.split('\n') 
            if 'rewriter' in line and 'python' in line
        ]
        
        if rewriter_processes:
            print("   ✓ Server process found:")
            for proc in rewriter_processes:
                # Truncate long lines
                print(f"     {proc[:100]}...")
        else:
            print("   ✗ No rewriter.py process found")
            
    except Exception as e:
        print(f"   ! Could not check processes: {e}")


def check_port_usage():
    """Check what's using the port."""
    print(f"\n7. Checking what's using port {PORT}...")
    import subprocess
    
    try:
        # Try lsof first
        result = subprocess.run(
            ["lsof", "-i", f":{PORT}"], 
            capture_output=True, 
            text=True
        )
        
        if result.stdout:
            print("   ✓ Port usage (via lsof):")
            print("   " + result.stdout.replace('\n', '\n   '))
        else:
            print(f"   ! No process found on port {PORT}")
            
    except FileNotFoundError:
        # lsof not available, try netstat
        try:
            result = subprocess.run(
                ["netstat", "-an"], 
                capture_output=True, 
                text=True
            )
            port_lines = [
                line for line in result.stdout.split('\n') 
                if f":{PORT}" in line
            ]
            if port_lines:
                print("   ✓ Port usage (via netstat):")
                for line in port_lines:
                    print(f"     {line}")
            else:
                print(f"   ! No connection found on port {PORT}")
        except Exception:
            print("   ! Could not check port usage")


def print_diagnosis():
    """Print diagnosis and recommendations."""
    print("\n" + "="*60)
    print("DIAGNOSIS AND RECOMMENDATIONS")
    print("="*60)
    
    print("""
The "Invalid HTTP request received" warning typically occurs when:

1. **Wrong Protocol**: Client sends HTTPS to HTTP endpoint
   → Solution: Use http:// not https:// in your URLs

2. **Malformed Requests**: Client sends invalid HTTP
   → Solution: Use proper HTTP client libraries

3. **Connection Issues**: Client connects then immediately disconnects
   → Solution: Check client timeout settings

4. **Port Conflicts**: Another service on the same port
   → Solution: Change port or stop conflicting service

To fix:
1. Ensure all clients use: http://localhost:12000 (not https://)
2. Check server logs when the warning appears
3. Use the test scripts to identify the issue
4. Set environment variables if missing:
   export CIRCUIT_CLIENT_ID="your_client_id"
   export CIRCUIT_CLIENT_SECRET="your_secret"
   export CIRCUIT_APPKEY="your_appkey"
""")


async def main():
    """Run all tests."""
    print("Debugging 'Invalid HTTP request received' Warning")
    print("="*60)
    
    # Run synchronous tests
    test_raw_tcp_connection()
    test_https_on_http_port()
    test_malformed_http()
    test_connection_close()
    check_server_process()
    check_port_usage()
    
    # Run async tests
    await test_http_client_requests()
    
    # Print diagnosis
    print_diagnosis()


if __name__ == "__main__":
    asyncio.run(main())
