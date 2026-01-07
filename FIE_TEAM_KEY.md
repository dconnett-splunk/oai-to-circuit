# Field Innovation Engineering (FIE) Team - API Access

## Your API Key

```
fie_fzgpoy0pjGqRrPJpebalkEz225pJzgtN
```

**⚠️ IMPORTANT**: Keep this key secure! Do not commit it to git or share it publicly.

## Your Quotas

| Model | Requests | Tokens |
|-------|----------|--------|
| `gpt-4o-mini` | 1,000 | 500,000 |
| `gpt-4o` | 50 | 100,000 |
| `claude-3-opus` | ❌ Blacklisted | - |
| `claude-opus-4` | ❌ Blacklisted | - |
| Other models | 100 | - |

## How to Use

### Option 1: Using curl

```bash
curl -H "X-Bridge-Subkey: fie_fzgpoy0pjGqRrPJpebalkEz225pJzgtN" \
     -H "Content-Type: application/json" \
     https://your-server.example.com:12443/v1/chat/completions \
     -d '{
       "model": "gpt-4o-mini",
       "messages": [
         {"role": "system", "content": "You are a helpful assistant."},
         {"role": "user", "content": "Hello!"}
       ]
     }'
```

### Option 2: Using Python OpenAI SDK

```python
from openai import OpenAI

# HTTP
client = OpenAI(
    base_url="http://your-server.example.com:12000/v1",
    api_key="fie_fzgpoy0pjGqRrPJpebalkEz225pJzgtN"
)

# Or HTTPS (if server uses self-signed cert)
import httpx
client = OpenAI(
    base_url="https://your-server.example.com:12443/v1",
    api_key="fie_fzgpoy0pjGqRrPJpebalkEz225pJzgtN",
    http_client=httpx.Client(verify=False)
)

# Make a request
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the capital of France?"}
    ]
)

print(response.choices[0].message.content)
```

### Option 3: Using Environment Variable

```bash
export OPENAI_API_KEY="fie_fzgpoy0pjGqRrPJpebalkEz225pJzgtN"
export OPENAI_BASE_URL="http://your-server.example.com:12000/v1"

# Then use any OpenAI-compatible tool
python your_script.py
```

## Recommended Models

### For Development/Testing
- **`gpt-4o-mini`**: Fast, cheap, good for most tasks (1000 requests available)

### For Production/Complex Tasks
- **`gpt-4o`**: More capable but expensive (50 requests only)

### ❌ Blocked Models
- `claude-3-opus`: Too expensive
- `claude-opus-4`: Too expensive

## Monitoring Your Usage

Check your usage on the server:

```bash
ssh your-server.example.com
sudo sqlite3 /var/lib/oai-to-circuit/quota.db \
  "SELECT model, requests, total_tokens FROM usage WHERE subkey='fie_fzgpoy0pjGqRrPJpebalkEz225pJzgtN';"
```

## Troubleshooting

### Error: "401 - Subkey required"
Make sure you're including the key in your requests:
- Header: `X-Bridge-Subkey: fie_fzgpoy0pjGqRrPJpebalkEz225pJzgtN`
- Or: `Authorization: Bearer fie_fzgpoy0pjGqRrPJpebalkEz225pJzgtN`

### Error: "429 - Quota exceeded"
You've hit your quota limit. Check usage with the command above. Contact your admin to increase limits if needed.

### Error: Connection refused
- Verify server address and port
- Check if you need HTTP (12000) or HTTPS (12443)
- Ensure firewall allows connections

## Best Practices

1. **Store securely**: Use environment variables, not hardcoded in source
2. **Don't commit**: Add to `.gitignore` or use secrets management
3. **Monitor usage**: Check regularly to avoid surprise quota exhaustion
4. **Use appropriate models**: 
   - `gpt-4o-mini` for 90% of tasks
   - `gpt-4o` only when you need higher quality
5. **Report issues**: Contact your admin if you hit quotas frequently

## Need More Quota?

Contact your administrator with:
- Current usage statistics
- Justification for increase
- Which model(s) you need more of

## Questions?

See full documentation:
- [SUBKEY_MANAGEMENT.md](SUBKEY_MANAGEMENT.md) - Complete subkey guide
- [QUICKSTART.md](QUICKSTART.md) - Getting started
- [README.md](README.md) - Full project documentation

