# Quick Start Guide

> **Navigation:** [Documentation Home](../README.md) | [Getting Started](./) | [Installation](installation.md)

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables:**
   ```bash
   export CIRCUIT_CLIENT_ID="your_client_id"
   export CIRCUIT_CLIENT_SECRET="your_client_secret"
   export CIRCUIT_APPKEY="your_appkey"
   ```

   Or create a `.env` file:
   ```env
   CIRCUIT_CLIENT_ID=your_client_id
   CIRCUIT_CLIENT_SECRET=your_client_secret
   CIRCUIT_APPKEY=your_appkey
   ```

3. **Generate SSL certificate (for HTTPS):**
   ```bash
   python generate_cert.py
   ```

4. **Start the server:**
   
   HTTP only (default):
   ```bash
   python rewriter.py
   ```

   HTTPS only:
   ```bash
   python rewriter.py --ssl-only
   ```

   Both HTTP and HTTPS:
   ```bash
   python rewriter.py --ssl
   ```

   The server will start on:
   - HTTP: http://localhost:12000
   - HTTPS: https://localhost:12443

## Testing

1. **Check if server is running:**
   ```bash
   curl http://localhost:12000/health
   ```

2. **Test chat completion:**
   ```bash
   curl -X POST http://localhost:12000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "gpt-4o-mini",
       "messages": [{"role": "user", "content": "Hello!"}]
     }'
   ```

## Debugging "Invalid HTTP request received"

This error usually means:
- You're using `https://` instead of `http://` (most common!)
- Something else is running on port 12000
- Malformed HTTP requests

**To debug:**
```bash
python debug_invalid_http.py
```

## Using with OpenAI SDK

```python
from openai import OpenAI

# For HTTP:
client = OpenAI(
    base_url="http://localhost:12000/v1",
    api_key="any-key-here"
)

# For HTTPS (with self-signed cert):
import httpx
client = OpenAI(
    base_url="https://localhost:12443/v1",
    api_key="any-key-here",
    http_client=httpx.Client(verify=False)  # Accept self-signed cert
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

## Common Issues

1. **"Invalid HTTP request received"**
   - If running HTTP-only mode: client is using HTTPS on HTTP port
   - Solution: Run with `--ssl` or `--ssl-only` to enable HTTPS
   - Or ensure client uses correct protocol for the mode

2. **502 Bad Gateway**
   - Check environment variables are set
   - Verify Circuit credentials are valid

3. **Connection refused**
   - Ensure server is running
   - Check firewall settings

## More Examples

Run `python examples.py` to see detailed request/response examples.

---

## Related Documentation

- [Installation Guide](installation.md) - Complete systemd installation
- [Production Setup](production-setup.md) - Production configuration
- [Architecture Overview](../architecture/architecture.md) - How the system works
- [Deployment Guide](../deployment/deployment-guide.md) - Deploying updates

**[← Back to Documentation Home](../README.md)**
