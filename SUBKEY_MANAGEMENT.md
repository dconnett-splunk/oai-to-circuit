# Subkey Management Guide

## What are Subkeys?

Subkeys are unique identifiers used to:
- **Identify individual users or teams** accessing the bridge
- **Enforce per-user quotas** (requests and token limits per model)
- **Track usage** in SQLite database and optionally Splunk
- **Control access** to expensive or restricted models

Subkeys are **not** forwarded to Circuit - they're only used locally by the bridge for access control.

## Generating Subkeys

### Quick Start

Generate a single subkey:
```bash
python generate_subkeys.py
```

Output:
```
xK9mP2nR7vL4tQ8wY1zN5jH3fD6sA0uB
```

### Generate Multiple Keys

For a team:
```bash
python generate_subkeys.py --count 5 --prefix "team_alpha"
```

Output:
```
team_alpha_kL9pX2mN7vR4tQ8wY1zJ5hF3
team_alpha_aB8cD1eF6gH3iJ0kL5mN2oP7
team_alpha_qR4sT9uV2wX7yZ1aB6cD3eF8
team_alpha_gH2iJ7kL4mN9oP1qR6sT3uV8
team_alpha_wX5yZ0aB3cD8eF1gH6iJ2kL7
```

### Save to File

```bash
python generate_subkeys.py --count 10 --output keys.txt
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--count`, `-c` | Number of keys to generate | 1 |
| `--prefix`, `-p` | Prefix for keys (e.g., "team_", "user_") | None |
| `--length`, `-l` | Length of random portion | 32 |
| `--output`, `-o` | Save to file instead of stdout | None |

## Configuring Quotas for Subkeys

After generating subkeys, add them to `quotas.json`:

```json
{
  "team_alpha_kL9pX2mN7vR4tQ8wY1zJ5hF3": {
    "gpt-4o-mini": {
      "requests": 1000,
      "total_tokens": 500000
    },
    "gpt-4o": {
      "requests": 50,
      "total_tokens": 100000
    },
    "*": {
      "requests": 100
    }
  },
  "team_beta_aB8cD1eF6gH3iJ0kL5mN2oP7": {
    "claude-3-opus": {"requests": 0},  // Blacklisted
    "gpt-4o-mini": {"requests": 5000},
    "*": {"requests": 200}
  }
}
```

### Quota Configuration

Set quotas via environment variable or file:

```bash
# Option 1: File path (recommended)
export QUOTAS_JSON_PATH="/path/to/quotas.json"

# Option 2: Inline JSON
export QUOTAS_JSON='{"subkey1": {"gpt-4o-mini": {"requests": 1000}}}'
```

If neither is set, the bridge looks for `quotas.json` in the current directory.

## Distributing Subkeys to Users

### 1. Generate Keys

```bash
# Generate keys for each user/team
python generate_subkeys.py --count 1 --prefix "alice" > alice_key.txt
python generate_subkeys.py --count 1 --prefix "bob" > bob_key.txt
python generate_subkeys.py --count 1 --prefix "team_data" > team_data_key.txt
```

### 2. Configure Quotas

Add to `quotas.json`:
```json
{
  "alice_xK9mP2nR7vL4tQ8wY1zN5jH3": {
    "gpt-4o-mini": {"requests": 500},
    "*": {"requests": 50}
  },
  "bob_aB8cD1eF6gH3iJ0kL5mN2oP7": {
    "gpt-4o-mini": {"requests": 1000},
    "gpt-4o": {"requests": 10}
  },
  "team_data_qR4sT9uV2wX7yZ1aB6cD3": {
    "gpt-4o-mini": {"requests": 10000},
    "*": {"requests": 1000}
  }
}
```

### 3. Share Keys Securely

**Option A: Direct Communication**
- Send via encrypted email or secure messaging (Signal, etc.)
- Don't send via Slack/Teams unless they support E2E encryption

**Option B: Password Manager**
- Store in shared password vault (1Password, LastPass, etc.)
- Share vault access with team members

**Option C: Secrets Management**
- Use enterprise secrets manager (HashiCorp Vault, AWS Secrets Manager)
- Grant programmatic access to authorized systems

### 4. Provide Usage Instructions

Send users this template:

```
Your Bridge API Access Key
===========================

Subkey: alice_xK9mP2nR7vL4tQ8wY1zN5jH3

Usage:
------

Option 1: Header (recommended)
curl -H "X-Bridge-Subkey: alice_xK9mP2nR7vL4tQ8wY1zN5jH3" \
     -H "Content-Type: application/json" \
     http://localhost:12000/v1/chat/completions \
     -d '{"model": "gpt-4o-mini", "messages": [...]}'

Option 2: Authorization Bearer
curl -H "Authorization: Bearer alice_xK9mP2nR7vL4tQ8wY1zN5jH3" \
     -H "Content-Type: application/json" \
     http://localhost:12000/v1/chat/completions \
     -d '{"model": "gpt-4o-mini", "messages": [...]}'

Python (OpenAI SDK):
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:12000/v1",
    api_key="alice_xK9mP2nR7vL4tQ8wY1zN5jH3"
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello!"}]
)

Your Quotas:
------------
- gpt-4o-mini: 500 requests
- Other models: 50 requests (default)

Keep your key secure - do not share or commit to git!
```

## Testing Subkey Access

### Test Key Generation

```bash
# Run generation tests
pytest tests/test_subkey_generation.py -v
```

### Test Subkey Extraction

```bash
# Run subkey extraction tests
pytest tests/test_subkey_extraction.py -v
```

### Test with Real Server

Start the server:
```bash
export REQUIRE_SUBKEY=true
export QUOTAS_JSON='{"test_key_123": {"gpt-4o-mini": {"requests": 10}}}'
python rewriter.py
```

Test with curl:
```bash
# Should succeed
curl -H "X-Bridge-Subkey: test_key_123" \
     -H "Content-Type: application/json" \
     http://localhost:12000/v1/chat/completions \
     -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "test"}]}'

# Should fail (401 - no subkey)
curl -H "Content-Type: application/json" \
     http://localhost:12000/v1/chat/completions \
     -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "test"}]}'

# Should fail (429 - quota exceeded after 10 requests)
for i in {1..11}; do
  curl -H "X-Bridge-Subkey: test_key_123" \
       -H "Content-Type: application/json" \
       http://localhost:12000/v1/chat/completions \
       -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "test '$i'"}]}'
done
```

## Monitoring Usage

### Check SQLite Database

```bash
sqlite3 quota.db "SELECT * FROM usage;"
```

Output:
```
subkey                              | model        | requests | prompt_tokens | completion_tokens | total_tokens
------------------------------------|--------------|----------|---------------|-------------------|-------------
alice_xK9mP2nR7vL4tQ8wY1zN5jH3    | gpt-4o-mini  | 45       | 2340          | 3120              | 5460
bob_aB8cD1eF6gH3iJ0kL5mN2oP7      | gpt-4o-mini  | 103      | 8920          | 11240             | 20160
```

### Splunk Queries (if configured)

```spl
# Usage by subkey
index=main sourcetype=llm:usage
| stats sum(requests) as total_requests, sum(total_tokens) as total_tokens by subkey
| sort -total_tokens

# Quota exceeded events
index=main sourcetype=llm:usage:error error_type=quota_exceeded
| stats count by subkey, model
```

## Revoking Access

To revoke a subkey:

1. **Remove from quotas.json**:
   ```json
   {
     "alice_xK9mP2nR7vL4tQ8wY1zN5jH3": {
       "*": {"requests": 0}  // Blacklist all models
     }
   }
   ```

2. **Restart the bridge** (or wait for quota reload if implemented)

3. **User will receive**: `HTTP 429 Quota exceeded`

## Security Best Practices

1. **Generate strong keys**: Use at least 32 characters (default)
2. **Use prefixes**: Makes keys easier to manage (`team_`, `user_`, etc.)
3. **Rotate regularly**: Generate new keys periodically and update quotas
4. **Monitor usage**: Check for anomalous patterns in Splunk or SQLite
5. **Revoke compromised keys**: Set quota to 0 immediately
6. **Don't log keys**: Keys should never appear in application logs
7. **Encrypt in transit**: Use HTTPS for production deployments
8. **Secure storage**: Never commit keys to git or share via insecure channels

## Example: Onboarding a New Team

```bash
# 1. Generate team keys
python generate_subkeys.py --count 5 --prefix "team_ml" --output team_ml_keys.txt

# 2. Add to quotas.json (edit file with generated keys)
cat >> quotas.json << 'EOF'
{
  "team_ml_kL9pX2mN7vR4tQ8wY1zJ5hF3": {
    "gpt-4o-mini": {"requests": 2000, "total_tokens": 1000000},
    "*": {"requests": 100}
  }
}
EOF

# 3. Restart bridge
systemctl restart oai-to-circuit  # or kill and restart manually

# 4. Share keys with team via secure channel
# 5. Monitor usage in first week to adjust quotas
sqlite3 quota.db "SELECT subkey, model, requests, total_tokens FROM usage WHERE subkey LIKE 'team_ml_%';"
```

## Troubleshooting

### "401 - Subkey required"
- User didn't provide subkey
- Check they're using correct header: `X-Bridge-Subkey` or `Authorization: Bearer`

### "429 - Quota exceeded"
- User hit their quota limit
- Check usage: `sqlite3 quota.db "SELECT * FROM usage WHERE subkey='<key>';"`
- Increase quota in `quotas.json` and restart bridge

### Subkey not working after creation
- Ensure subkey is in `quotas.json`
- Restart bridge after modifying quotas
- Check `QUOTAS_JSON_PATH` or `QUOTAS_JSON` environment variable is set correctly

