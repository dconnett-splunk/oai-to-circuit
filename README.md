# OpenAI to Circuit Bridge

A minimal local webserver that translates standard OpenAI-style requests into Circuit’s deployment-based API.

## Features

- OpenAI-compatible endpoint: `POST /v1/chat/completions`
- Accepts `model` parameter, forwards to Circuit using deployment path
- Fetches/caches OAuth2 tokens; clients can use any static API key
- Optional HTTPS (self-signed) and dual-mode HTTP/HTTPS
- Health endpoint: `GET /health`
- Verbose, colorized logging (with process tags in dual mode)

## Documentation

📚 **[Complete Documentation](docs/README.md)** - Browse all documentation

### Quick Links

- 🚀 **[Quick Start Guide](docs/getting-started/quickstart.md)** - Get up and running in minutes
- 📦 **[Installation Guide](docs/getting-started/installation.md)** - Complete systemd setup
- 🚢 **[Deployment Guide](docs/deployment/deployment-guide.md)** - Deploy updates and manage releases
- 🏗️ **[Architecture Overview](docs/architecture/architecture.md)** - How the system works
- 🔑 **[Subkey Management](docs/operations/subkey-management.md)** - Manage API keys and quotas
- 🔄 **[Key Rotation](docs/operations/key-rotation.md)** - Secure key rotation and lifecycle
- 📊 **[Operations Guides](docs/operations/)** - Day-to-day operations

**Production Deployment:** See the [Deployment Guide](docs/deployment/deployment-guide.md) for complete deployment procedures.

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

Optional quotas and subkeys:
- `REQUIRE_SUBKEY` (default: `true`) – require a caller subkey per request
- `QUOTA_DB_PATH` (default: `quota.db`) – SQLite file for usage tracking
- `QUOTAS_JSON` – inline JSON mapping subkey→model→limits
- `QUOTAS_JSON_PATH` (default: `quotas.json`) – file to load quotas from if `QUOTAS_JSON` not set

Optional Splunk HEC integration (for usage analytics):
- `SPLUNK_HEC_URL` – Splunk HTTP Event Collector URL (e.g., `https://splunk.example.com:8088/services/collector/event`)
- `SPLUNK_HEC_TOKEN` – Splunk HEC authentication token
- `SPLUNK_SOURCE` (default: `oai-to-circuit`) – Event source name
- `SPLUNK_SOURCETYPE` (default: `llm:usage`) – Event sourcetype
- `SPLUNK_INDEX` (default: `main`) – Splunk index name

Optional admin interface:
- `ADMIN_USERNAME` (default: `admin`) – username for the admin UI when auth is enabled
- `ADMIN_PASSWORD` – if set, `/admin` is protected with HTTP Basic auth
- `ADMIN_TITLE` (default: `Circuit Bridge Admin`) – heading shown in the admin UI

Caller subkey is read from either header `X-Bridge-Subkey: <subkey>` or `Authorization: Bearer <subkey>`. The subkey is NOT forwarded to Circuit; it is only used locally for per-model quotas and usage tracking.

Example `quotas.json` (with model blacklisting):
```json
{
  "team-alpha": {
    "claude-3-opus": { "requests": 0 },      // Blacklisted - too expensive
    "claude-opus-4": { "requests": 0 },      // Blacklisted - too expensive
    "claude-3.5-sonnet": { "requests": 0 },  // Blacklisted - too expensive
    "gpt-4o-mini": { "requests": 1000, "total_tokens": 500000 },
    "*": { "requests": 100 }
  },
  "power-user-123": {
    "gpt-4o": { "requests": 50, "total_tokens": 100000 },
    "gpt-4o-mini": { "requests": 5000 },
    "*": { "requests": 1000 }
  }
}
```

See `quotas.json.example` for more examples including full model blacklisting scenarios.

Optional: generate a development certificate:
```bash
python generate_cert.py
```

Start the server:
- HTTP only: `python rewriter.py`
- HTTPS only: `python rewriter.py --ssl-only`
- Dual: `python rewriter.py --ssl`

## Admin Interface

The bridge now includes an embedded admin console at [`/admin`](http://localhost:12000/admin).

It includes:
- Overview stats for total requests, tokens, top users, and model mix
- A user directory with generated subkeys, owner metadata, lifecycle status, and usage
- A Policies screen for global defaults and reusable template rule sets
- Per-user quota editing with template assignment plus local wildcard/per-model overrides

If `QUOTAS_JSON_PATH` is file-backed, quota edits are written back to that file. If `QUOTAS_JSON` is set inline, the UI warns that quota edits are runtime-only and will be lost on restart.

Rule precedence is:
1. Global defaults
2. Optional template rules
3. User-local overrides

Advanced quota files can now use a structured format:

```json
{
  "_global": {
    "*": { "requests": 100 }
  },
  "_templates": {
    "team-standard": {
      "description": "Shared team defaults",
      "rules": {
        "*": { "requests": 50, "total_tokens": 100000 },
        "gpt-4o": { "requests": 10 }
      }
    }
  },
  "_users": {
    "alice_key": {
      "template": "team-standard",
      "rules": {
        "gpt-4o": { "requests": 5 }
      }
    }
  }
}
```

The legacy flat `subkey -> rules` format still works and is treated as user-local rules without templates or global defaults.

For any non-local deployment, set `ADMIN_PASSWORD` so the admin routes require HTTP Basic auth.

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

## Subkey Quotas and Model Blacklisting

- Provide a subkey per request via `Authorization: Bearer <subkey>` or `X-Bridge-Subkey: <subkey>`.
- Limits are enforced **per subkey and per model**. Supported limits:
  - `requests`: total number of requests allowed (set to `0` to **blacklist a model**)
  - `total_tokens`: sum of returned usage.total_tokens (if present)
- **Blacklist expensive models** by setting their `requests` quota to `0`:
  ```json
  {
    "team_member": {
      "claude-3-opus": {"requests": 0},      // Completely blocked
      "claude-opus-4": {"requests": 0},      // Completely blocked
      "claude-3.5-sonnet": {"requests": 0},  // Completely blocked
      "gpt-4o-mini": {"requests": 1000},     // Allowed
      "*": {"requests": 100}                 // Default for other models
    }
  }
  ```
- Model-specific limits **override** wildcard `"*"` limits
- When a request exceeds a quota or uses a blacklisted model, the bridge returns `429 Too Many Requests`.
- See `quotas.json.example` for a complete configuration template.

## Splunk HEC Integration

When Splunk HEC is configured, the bridge automatically sends usage metrics to Splunk for analytics and monitoring:

**Event Types:**
- **Usage Events**: Sent after each successful API request with token counts
- **Error Events**: Sent when quotas are exceeded or errors occur

**Example Splunk query** to analyze usage:

```spl
index=main sourcetype=llm:usage
| stats sum(requests) as total_requests, sum(total_tokens) as total_tokens by subkey, model
| sort -total_tokens
```

See `INSTALLATION.md` for detailed Splunk HEC setup instructions.

## Systemd Service

For production deployment, use the included systemd unit file:

```bash
sudo cp oai-to-circuit.service /etc/systemd/system/
sudo systemctl enable oai-to-circuit
sudo systemctl start oai-to-circuit
```

See `INSTALLATION.md` for complete installation instructions.

## Debugging

- Common: "Invalid HTTP request received" usually means HTTPS was sent to the HTTP port.
- Run diagnostics:
```bash
python debug_invalid_http.py
```

## Tests & Examples

Run the full test suite:
```bash
pytest
```

Individual test modules in `tests/`:
- `test_quota.py` – quota enforcement and usage tracking
- `test_requests.py` – endpoint behavior and error scenarios
- `test_subkey_extraction.py` – header parsing
- `test_oauth.py` – token caching and authentication
- `test_config.py` – configuration loading
- `test_https.py` – SSL configuration validation

Usage examples:
- `examples.py` – curl and SDK examples
- `python_openai_demo.py` – Python OpenAI SDK integration
- `debug_invalid_http.py` – connection diagnostics

## References

- [Cisco CIRCUIT Chat API](https://ai-chat.cisco.com/bridgeit-platform/api/home)
- See `circuit_api.org` for API details.

---

## Documentation Structure

All comprehensive documentation has been moved to the [`docs/`](docs/) folder for better organization:

- **[docs/getting-started/](docs/getting-started/)** - Installation and quick start guides
- **[docs/deployment/](docs/deployment/)** - Deployment procedures
- **[docs/architecture/](docs/architecture/)** - System design and architecture
- **[docs/operations/](docs/operations/)** - Operations and management
- **[docs/guides/](docs/guides/)** - Specialized guides
- **[docs/migrations/](docs/migrations/)** - Database migrations and changelogs
- **[docs/reference/](docs/reference/)** - Reference documentation
- **[docs/archive/](docs/archive/)** - Historical documents

**[Browse Complete Documentation →](docs/README.md)**
