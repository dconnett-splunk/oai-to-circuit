# Subkey Management Guide

> **Navigation:** [Documentation Home](../README.md) | [Operations](../operations/) | [Getting Started](../getting-started/)

Complete guide to generating, managing, and tracking API subkeys for the OpenAI to Circuit Bridge.

---

## Table of Contents

- [Overview](#overview)
- [Quick Reference](#quick-reference)
- [Generating Subkeys](#generating-subkeys)
- [Configuring Quotas](#configuring-quotas)
- [Distributing Subkeys](#distributing-subkeys)
- [Friendly Names System](#friendly-names-system)
- [Monitoring Usage](#monitoring-usage)
- [Revoking Access](#revoking-access)
- [Security Best Practices](#security-best-practices)
- [Troubleshooting](#troubleshooting)

---

## Overview

### What are Subkeys?

Subkeys are unique identifiers used to:
- **Identify individual users or teams** accessing the bridge
- **Enforce per-user quotas** (requests and token limits per model)
- **Track usage** in SQLite database and optionally Splunk
- **Control access** to expensive or restricted models

**Important:** Subkeys are **not** forwarded to Circuit - they're only used locally by the bridge for access control and tracking.

### System Components

| Component | Purpose |
|-----------|---------|
| **Database** | `subkey_names` table auto-created on startup |
| **QuotaManager** | `get_friendly_name()` method for name lookup |
| **SplunkHEC** | Events include `friendly_name` field |
| **App** | Automatically looks up and passes names |
| **Backfill** | Includes names when re-sending data |

---

## Quick Reference

### Common Commands

**Check what needs names:**
```bash
python check_and_setup_names.py
```

**Generate a new subkey:**
```bash
python generate_subkeys.py
```

**Add a friendly name:**
```bash
python add_subkey_names_table.py --add \
  --subkey "your_key_here" \
  --name "Your Name (Team)" \
  --email "your.email@example.com"
```

**List all names:**
```bash
python add_subkey_names_table.py --list
```

**Generate usage report:**
```bash
python generate_usage_report.py --summary
```

**Restart service:**
```bash
sudo systemctl restart oai-to-circuit
```

---

## Generating Subkeys

### Single Subkey

Generate a single subkey:

```bash
python generate_subkeys.py
```

Output:
```
xK9mP2nR7vL4tQ8wY1zN5jH3fD6sA0uB
```

### Multiple Subkeys

Generate multiple keys for a team:

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

### Generation Options

| Flag | Description | Default |
|------|-------------|---------|
| `--count`, `-c` | Number of keys to generate | 1 |
| `--prefix`, `-p` | Prefix for keys (e.g., "team_", "user_") | None |
| `--length`, `-l` | Length of random portion | 32 |
| `--output`, `-o` | Save to file instead of stdout | None |

### Example: Complete New User Setup

```bash
# 1. Generate key for new user
SUBKEY=$(python3 generate_subkeys.py --prefix "john" | head -1)
echo "Generated subkey: $SUBKEY"

# 2. Add to quotas.json
# (edit quotas.json manually to add the key with limits)

# 3. Add name mapping
python3 add_subkey_names_table.py --add \
  --subkey "$SUBKEY" \
  --name "John Doe" \
  --email "john.doe@example.com" \
  --description "Marketing Team"

# 4. Share key with user securely
# (send via encrypted channel)

# 5. Generate report after usage
python3 generate_usage_report.py --summary
# Output shows "John Doe" instead of raw key!
```

---

## Configuring Quotas

### Quota Configuration File

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

### Loading Quotas

Set quotas via environment variable or file:

```bash
# Option 1: File path (recommended)
export QUOTAS_JSON_PATH="/path/to/quotas.json"

# Option 2: Inline JSON
export QUOTAS_JSON='{"subkey1": {"gpt-4o-mini": {"requests": 1000}}}'
```

If neither is set, the bridge looks for `quotas.json` in the current directory.

---

## Distributing Subkeys

### Step 1: Generate Keys for Each User/Team

```bash
# Generate keys for each user/team
python generate_subkeys.py --count 1 --prefix "alice" > alice_key.txt
python generate_subkeys.py --count 1 --prefix "bob" > bob_key.txt
python generate_subkeys.py --count 1 --prefix "team_data" > team_data_key.txt
```

### Step 2: Configure Quotas

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

### Step 3: Share Keys Securely

**Option A: Direct Communication**
- Send via encrypted email or secure messaging (Signal, etc.)
- Don't send via Slack/Teams unless they support E2E encryption

**Option B: Password Manager**
- Store in shared password vault (1Password, LastPass, etc.)
- Share vault access with team members

**Option C: Secrets Management**
- Use enterprise secrets manager (HashiCorp Vault, AWS Secrets Manager)
- Grant programmatic access to authorized systems

### Step 4: Provide Usage Instructions

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

---

## Friendly Names System

The friendly names system allows you to generate reports with human-readable names instead of raw subkeys, keeping actual subkeys private in reports and logs.

### Quick Setup

#### Step 1: Check Current State

Run the check script to see which subkeys are active and which need names:

```bash
# For local development
python check_and_setup_names.py --local

# For production (default path: /var/lib/oai-to-circuit/quota.db)
python check_and_setup_names.py

# Or specify a custom database path
python check_and_setup_names.py --db /path/to/quota.db
```

This shows:
- ✓ Whether the `subkey_names` table exists (auto-created on startup)
- All active subkeys from the usage table
- Which ones have names and which don't
- Commands to add names to unnamed keys

#### Step 2: Add Names to Active Keys

For each active subkey without a name:

```bash
python add_subkey_names_table.py --add \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "your_actual_subkey_here" \
  --name "Friendly Name (Team)" \
  --email "user@example.com" \
  --description "Optional description"
```

**Examples:**

```bash
# Dave from FIE team
python add_subkey_names_table.py --add \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "fie_dave_jhKaCh88CgkSfl_p7RN01jv82dkOL90g" \
  --name "Dave (FIE Team)" \
  --email "dave@example.com" \
  --description "Field Innovation Engineering"

# ML Team
python add_subkey_names_table.py --add \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "team_ml_xK9pLm3nQr8sT2vW5yZ1aB4cD7eF0gH6" \
  --name "ML Team" \
  --email "ml-team@example.com" \
  --description "Machine Learning Research"
```

#### Step 3: Verify Names Were Added

List all name mappings:

```bash
python add_subkey_names_table.py --list --db /var/lib/oai-to-circuit/quota.db
```

Output:
```
Friendly Name                  Subkey Prefix             Description                    Created
========================================================================================================================
Alice Johnson                  alice_xK9mP2nR7vL4t...    Senior Engineer                2024-01-15 10:30:00
Dave (FIE Team)                fie_dave_jhKaCh88Cg...    Field Innovation Engineering   2024-01-15 11:00:00
Team Alpha                     team_alpha_kL9pX2mN...    Development Team               2024-01-15 09:45:00
```

#### Step 4: Restart Service (if needed)

```bash
sudo systemctl restart oai-to-circuit
```

Check the logs:

```bash
sudo journalctl -u oai-to-circuit -f
```

#### Step 5: Verify HEC Events Include Names

Example HEC event with friendly name:

```json
{
  "subkey": "sha256:1a2b3c4d5e6f7890",
  "friendly_name": "Dave (FIE Team)",
  "model": "gpt-4o-mini",
  "requests": 1,
  "prompt_tokens": 150,
  "completion_tokens": 50,
  "total_tokens": 200,
  "timestamp": "2026-01-08T12:34:56.789Z"
}
```

### Managing Name Mappings

**Update an existing mapping:**

```bash
python add_subkey_names_table.py --add \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "fie_dave_jhKaCh88CgkSfl_p7RN01jv82dkOL90g" \
  --name "Dave Smith (FIE)" \
  --email "dave.smith@example.com" \
  --description "Updated description"
```

**Remove a mapping:**

```bash
python add_subkey_names_table.py --remove \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "fie_dave_jhKaCh88CgkSfl_p7RN01jv82dkOL90g"
```

### Database Schema

The `subkey_names` table:

```sql
CREATE TABLE subkey_names (
    subkey TEXT PRIMARY KEY,
    friendly_name TEXT NOT NULL,
    email TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Monitoring Usage

### Usage Reports

**Summary report:**
```bash
python3 generate_usage_report.py --summary
```

Output:
```
==================================================================================
                     OpenAI Bridge Usage Report - Summary
                       Generated: 2024-01-15 14:30:00
==================================================================================

User/Team                      Total Requests   Total Tokens   Models Used   Description
--------------------------------------------------------------------------------------------------
Dave (FIE Team)                           450        125,430             2   Field Innovation...
Team Alpha                                320         89,120             3   Development Team
Alice Johnson                             180         45,200             1   Senior Engineer
--------------------------------------------------------------------------------------------------
TOTAL                                     950        259,750
```

**Detailed report:**
```bash
python3 generate_usage_report.py --detailed
```

**Usage by model:**
```bash
python3 generate_usage_report.py --by-model
```

**All reports:**
```bash
python3 generate_usage_report.py --all
```

**Export to CSV:**
```bash
python3 generate_usage_report.py --detailed --csv monthly_report.csv
```

### SQLite Database Queries

**Check usage directly:**

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

### Splunk Queries

**Total usage by user and model:**
```spl
index=main sourcetype=llm:usage
| stats sum(requests) as total_requests, sum(total_tokens) as total_tokens by friendly_name, model
| sort -total_tokens
```

**Usage with friendly names:**
```spl
index=oai_circuit sourcetype="llm:usage"
| eval display_name=coalesce(friendly_name, subkey)
| stats sum(total_tokens) as total_tokens, sum(requests) as requests by display_name, model
| sort -total_tokens
```

**Find users that need names:**
```spl
index=oai_circuit sourcetype="llm:usage"
| eval has_name=if(isnotnull(friendly_name), "Has Name", "Needs Name")
| stats sum(total_tokens) as tokens, sum(requests) as requests by subkey, has_name
| where has_name="Needs Name"
| sort -tokens
```

**Quota exceeded events:**
```spl
index=main sourcetype=llm:usage:error error_type=quota_exceeded
| stats count by friendly_name, model
```

**Token usage over time:**
```spl
index=main sourcetype=llm:usage
| timechart span=1h sum(total_tokens) by model
```

---

## Revoking Access

To revoke a subkey:

### Step 1: Blacklist in quotas.json

```json
{
  "alice_xK9mP2nR7vL4tQ8wY1zN5jH3": {
    "*": {"requests": 0}  // Blacklist all models
  }
}
```

### Step 2: Restart the Bridge

```bash
sudo systemctl restart oai-to-circuit
```

### Step 3: Verify

User will receive: `HTTP 429 Quota exceeded`

**Note:** You can keep the name mapping for historical reports even after revoking access. The mapping will remain in `subkey_names` even after the key is removed from `quotas.json`.

---

## Security Best Practices

### Key Generation
1. **Generate strong keys**: Use at least 32 characters (default)
2. **Use prefixes**: Makes keys easier to manage (`team_`, `user_`, etc.)
3. **Rotate regularly**: Generate new keys periodically and update quotas

### Key Distribution
4. **Encrypt in transit**: Use HTTPS for production deployments
5. **Secure storage**: Never commit keys to git or share via insecure channels
6. **Use secure channels**: Encrypted email, secure messaging, or password managers

### Monitoring & Access Control
7. **Monitor usage**: Check for anomalous patterns in Splunk or SQLite
8. **Revoke compromised keys**: Set quota to 0 immediately
9. **Don't log keys**: Keys should never appear in application logs
10. **Audit regularly**: Verify mappings and quotas are up-to-date

### Database Security
11. **Restrict DB access**: Only root and oai-bridge user
12. **Proper file permissions**: quota.db should be 640, owned by oai-bridge
13. **Regular backups**: Backup quota database regularly
14. **Secure friendly names**: Don't include sensitive information in names

### What's Protected
- ✅ **Subkeys are never shown in reports** (only friendly names)
- ✅ **Subkeys are hashed in Splunk** (using SHA-256)
- ✅ **Mappings are stored only on the server** (not in git)
- ✅ **Database permissions** protect the mappings

### What to Remember
- ⚠️ **The database still contains raw subkeys** in the `usage` table
- ⚠️ **Anyone with DB access can see the mappings**
- ⚠️ **Friendly names are NOT hashed** - they're meant to be human-readable
- ⚠️ **Don't include sensitive information** in friendly names

---

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

### "No such table: subkey_names"
The table is now automatically created when the service starts. If using an old database:

```bash
python add_subkey_names_table.py --init --db /var/lib/oai-to-circuit/quota.db
```

### "Database is locked"
The service might be writing to it. Stop briefly:

```bash
sudo systemctl stop oai-to-circuit
python3 add_subkey_names_table.py --add ...
sudo systemctl start oai-to-circuit
```

### Reports show raw subkeys instead of names
You haven't added a mapping for that subkey yet:

```bash
python3 add_subkey_names_table.py --list  # Check existing mappings
python3 add_subkey_names_table.py --add --subkey "..." --name "..."
```

### Names not showing up in HEC events

1. Check that names are in the database:
   ```bash
   sqlite3 /var/lib/oai-to-circuit/quota.db "SELECT * FROM subkey_names;"
   ```

2. Restart the service:
   ```bash
   sudo systemctl restart oai-to-circuit
   ```

3. Check logs for errors:
   ```bash
   sudo journalctl -u oai-to-circuit -n 100
   ```

### Permission denied on database

```bash
sudo chown oai-bridge:oai-bridge /var/lib/oai-to-circuit/quota.db
sudo chmod 640 /var/lib/oai-to-circuit/quota.db
```

---

## Testing

### Test Key Generation

```bash
pytest tests/test_subkey_generation.py -v
```

### Test Subkey Extraction

```bash
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

---

## Related Documentation

- [Installation Guide](../getting-started/installation.md) - Initial setup
- [Deployment Guide](../deployment/deployment-guide.md) - Deploying updates
- [Database Queries](database-queries.md) - SQL query examples
- [Diagnostic Logging](diagnostic-logging.md) - Troubleshooting with logs
- [True-Up Guide](../guides/trueup-guide.md) - Reconciling usage data

---

**For quota configuration details**, see the [Architecture Guide](../architecture/architecture.md).

**For production deployment**, see the [Production Setup Guide](../getting-started/production-setup.md).

