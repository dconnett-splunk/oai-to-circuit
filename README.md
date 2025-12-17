# OpenAI to Circuit Bridge

A minimal local webserver that translates standard OpenAI-style requests into Circuit’s deployment-based API.

## Features

- OpenAI-compatible endpoint: `POST /v1/chat/completions`
- Accepts `model` parameter, forwards to Circuit using deployment path
- Fetches/caches OAuth2 tokens; clients can use any static API key
- Optional HTTPS (self-signed) and dual-mode HTTP/HTTPS
- Health endpoint: `GET /health`
- Verbose, colorized logging (with process tags in dual mode)

## Quick Start

See `QUICKSTART.md` or `QUICKSTART.org` for step-by-step setup, including cert generation and examples.

## Usage

HTTP example:
```bash
curl http://localhost:12000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

HTTPS with self-signed cert:
```bash
curl -k https://localhost:12443/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

The server rewrites to `https://chat-ai.cisco.com/openai/deployments/<model>/chat/completions` and injects the OAuth2 token.

## Configuration

Set the following environment variables (see `circuit_api.org`):
- `CIRCUIT_CLIENT_ID`
- `CIRCUIT_CLIENT_SECRET`
- `CIRCUIT_APPKEY`

Optional: generate a development certificate:
```bash
python generate_cert.py
```

Start the server:
- HTTP only: `python rewriter.py`
- HTTPS only: `python rewriter.py --ssl-only`
- Dual: `python rewriter.py --ssl`

## ChatGPT CLI (demo)

- Project: [kardolus/chatgpt-cli](https://github.com/kardolus/chatgpt-cli)
- Use the provided config file:
```bash
chatgpt --config /Users/daconnet/Git/oai-to-circuit/chatgpt-cli.openai.yaml "Say hello from the bridge"
```
- Or env vars (override config):
```bash
export OPENAI_URL=http://localhost:12000
export OPENAI_COMPLETIONS_PATH=/v1/chat/completions
export OPENAI_API_KEY=demo_key # This is ignored, and is arbitrary.
export OPENAI_MODEL=gpt-4o-mini
chatgpt "Say hello from the bridge"
```

## Python SDK Demo

A runnable example is included:
```bash
python python_openai_demo.py --prompt "Say hello from the bridge"
```
HTTPS with self-signed cert:
```bash
python python_openai_demo.py --https --insecure-skip-verify --prompt "Say hello over HTTPS"
```
Streaming tokens:
```bash
python python_openai_demo.py --stream --prompt "Count to 5"
```

## Health Check

`GET /health` returns service status and configuration flags.

## Debugging

- Common: “Invalid HTTP request received” usually means HTTPS was sent to the HTTP port.
- Run diagnostics:
```bash
python debug_invalid_http.py
```

## Tests & Examples

- `test_requests.py` – typical and error scenarios
- `test_https.py` – HTTPS verification
- `examples.py` – curl and SDK examples

## References

- [Cisco CIRCUIT Chat API](https://ai-chat.cisco.com/bridgeit-platform/api/home)
- See `circuit_api.org` for API details.
