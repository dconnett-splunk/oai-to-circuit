# Key Rotation Guide

> **Navigation:** [Documentation Home](../README.md) | [Operations](../operations/) | [Subkey Management](subkey-management.md)

## Overview

This guide explains how to securely rotate API keys while preserving historical data and maintaining reporting continuity.

**Key Principles:**
- ✅ **Historical data is never deleted** - All usage remains queryable
- ✅ **Revoked keys stop working immediately** - No grace period needed
- ✅ **Reporting continuity** - Usage can be aggregated across key rotations
- ✅ **Audit trail** - All rotations are tracked with timestamps and reasons

## Key Lifecycle States

| State | Description | Can Make Requests? | In Quotas? | Historical Data? |
|-------|-------------|-------------------|------------|------------------|
| `active` | Normal operational state | ✅ Yes | ✅ Yes | ✅ Yes |
| `revoked` | Disabled, no replacement | ❌ No | ❌ No (zeroed) | ✅ Yes |
| `replaced` | Disabled, replaced by new key | ❌ No | ❌ No (zeroed) | ✅ Yes |

## Quick Reference

```bash
# Check key status
python3 rotate_key.py --status KEY

# Revoke a key (compromise, termination)
python3 rotate_key.py --revoke KEY --reason "Key compromised"

# Rotate a key (generate replacement)
python3 rotate_key.py --rotate KEY --prefix fie_alice --reason "Regular rotation"

# Replace with existing key
python3 rotate_key.py --replace OLD_KEY NEW_KEY --reason "Team restructure"
```

## Use Cases

### 1. Key Compromise

**Scenario**: A key was accidentally committed to GitHub

```bash
cd /opt/oai-to-circuit

# Immediate revocation
sudo -u oai-bridge python3 rotate_key.py \
    --revoke fie_alice_abc123 \
    --reason "Key exposed in GitHub commit 7a3f21" \
    --yes

# Generate replacement
sudo -u oai-bridge python3 rotate_key.py \
    --rotate fie_alice_abc123 \
    --prefix fie_alice \
    --reason "Replacement for exposed key"
```

**What happens:**
1. Old key immediately stops working (quotas set to 0)
2. New key generated with same user identity
3. All historical data preserved
4. Replacement tracked in database

### 2. Regular Key Rotation (Security Policy)

**Scenario**: 90-day rotation policy

```bash
# Rotate all keys reaching 90 days
for key in $(python3 list_expiring_keys.py --days 90); do
    python3 rotate_key.py \
        --rotate "$key" \
        --prefix "$(echo $key | cut -d_ -f1-2)" \
        --reason "90-day rotation policy" \
        --yes
done
```

### 3. Employee Departure

**Scenario**: Team member leaving company

```bash
# Revoke without replacement
python3 rotate_key.py \
    --revoke fie_departing_user_xyz \
    --reason "Employee departed 2026-01-20"
```

**Historical data remains for:**
- Cost allocation
- Project tracking
- Compliance audits

### 4. Team Reorganization

**Scenario**: User moving between teams, need new key prefix

```bash
# Generate new key for different team
python3 provision_user.py \
    --prefix sales_alice \
    --name "Alice Smith" \
    --email "alice@example.com" \
    --quota-requests 1000 \
    --quota-tokens 1000000

# Replace old key
python3 rotate_key.py \
    --replace fie_alice_old123 sales_alice_new456 \
    --reason "Transferred to Sales team"
```

## Database Schema

### New Table: `key_lifecycle`

```sql
CREATE TABLE key_lifecycle (
    subkey TEXT PRIMARY KEY,
    user_id TEXT,                  -- Links keys to the same user
    status TEXT DEFAULT 'active',   -- 'active', 'revoked', 'replaced'
    revoked_at TIMESTAMP,
    revoke_reason TEXT,
    replaced_by TEXT,               -- Points to replacement key
    replaces TEXT                   -- Points to old key
);
```

**Example Data:**
```
subkey                  | user_id      | status   | replaced_by          | replaces
------------------------|--------------|----------|----------------------|----------------------
fie_alice_old123        | alice@co.com | replaced | fie_alice_new456     | NULL
fie_alice_new456        | alice@co.com | active   | NULL                 | fie_alice_old123
```

## Splunk Queries for Rotated Keys

### Show Usage Across All Keys for a User

```spl
index=oai_circuit sourcetype="llm:usage" email="alice@example.com"
| stats 
    sum(total_tokens) as total_tokens 
    sum(requests) as requests 
    by model, subkey
| sort - total_tokens
```

### Usage Before and After Rotation

```spl
index=oai_circuit sourcetype="llm:usage" email="alice@example.com"
| eval period=if(_time < strptime("2026-01-20", "%Y-%m-%d"), "Before Rotation", "After Rotation")
| stats sum(total_tokens) as tokens by period, subkey
| sort - tokens
```

### Find All Replaced Keys

```sql
SELECT 
    old.subkey as old_key,
    old.revoked_at,
    old.revoke_reason,
    new.subkey as new_key,
    old.user_id
FROM key_lifecycle old
JOIN key_lifecycle new ON old.replaced_by = new.subkey
WHERE old.status = 'replaced'
ORDER BY old.revoked_at DESC;
```

### Aggregate Usage by User (Across All Keys)

```spl
index=oai_circuit sourcetype="llm:usage"
| lookup key_lifecycle subkey OUTPUT user_id
| stats 
    sum(total_tokens) as total_tokens 
    sum(requests) as requests 
    dc(subkey) as key_count
    by user_id, friendly_name
| sort - total_tokens
```

## Reporting Continuity

### Method 1: Email-Based Aggregation

Since all keys for a user share the same email, use `email` field:

```spl
index=oai_circuit sourcetype="llm:usage"
| stats sum(total_tokens) by email, model
```

**Pros:** Works immediately, no database join needed  
**Cons:** Email must be consistent across rotations

### Method 2: user_id-Based Aggregation

Link keys using the `user_id` from `key_lifecycle` table:

```spl
index=oai_circuit sourcetype="llm:usage"
| lookup key_lifecycle subkey OUTPUT user_id
| stats sum(total_tokens) by user_id, model
```

**Pros:** Explicit relationship, survives email changes  
**Cons:** Requires database lookup

## Best Practices

### 1. Always Provide a Reason

```bash
# Good
--reason "Key compromised in phishing attack"
--reason "90-day rotation policy"
--reason "Employee departed"

# Bad
--reason "revoked"
--reason "old"
```

### 2. Rotate Regularly

Implement a rotation policy:
- **High-privilege keys**: 30-60 days
- **Standard keys**: 90 days
- **Limited-scope keys**: 180 days

### 3. Maintain Consistent User Identity

When rotating, keep the same:
- Friendly name
- Email address
- Quota limits

### 4. Document in Version Control

Keep a log of rotations:
```bash
# Add to CHANGELOG
echo "2026-01-20: Rotated fie_alice_old123 -> fie_alice_new456 (90-day policy)" >> KEY_ROTATION_LOG.md
```

### 5. Test New Keys Before Revoking Old

```bash
# 1. Generate new key
python3 provision_user.py --prefix fie_alice ...

# 2. Test new key
curl -H "Authorization: Bearer fie_alice_new456" ...

# 3. Once confirmed working, rotate
python3 rotate_key.py --replace fie_alice_old123 fie_alice_new456 ...
```

## Automation

### Automated Rotation Script

```bash
#!/bin/bash
# rotate_expiring_keys.sh

DAYS_THRESHOLD=90

# Find keys older than threshold
psql quota.db <<EOF
SELECT subkey, friendly_name, email, 
       julianday('now') - julianday(created_at) as age
FROM subkey_names 
WHERE age > $DAYS_THRESHOLD
AND subkey NOT IN (
    SELECT subkey FROM key_lifecycle WHERE status != 'active'
);
EOF | while read key name email age; do
    echo "Rotating $key (age: $age days)"
    
    prefix=$(echo $key | cut -d_ -f1-2)
    
    python3 rotate_key.py \
        --rotate "$key" \
        --prefix "$prefix" \
        --reason "Automated 90-day rotation" \
        --yes
    
    # Email new key to user
    echo "New key: [generated key]" | mail -s "API Key Rotation" "$email"
done
```

## Troubleshooting

### Q: Can I un-revoke a key?

**A:** No, for security reasons. Generate a new key instead.

```bash
# Don't try to un-revoke
# Instead, generate a new key for the same user
python3 provision_user.py --prefix fie_alice --name "Alice" --email "alice@co.com"
```

### Q: What if I lose track of which keys belong to whom?

**A:** Check the database:

```sql
SELECT subkey, friendly_name, email, status, replaced_by, replaces
FROM subkey_names 
LEFT JOIN key_lifecycle USING (subkey)
WHERE email = 'alice@example.com'
ORDER BY created_at;
```

### Q: Can historical data show usage across rotated keys?

**A:** Yes! Use email or user_id to aggregate:

```spl
index=oai_circuit email="alice@example.com"
| timechart sum(total_tokens) by subkey
```

This shows all keys used by Alice over time.

### Q: How do I rotate the backfill key?

**A:** The backfill key (`system-backfill-trueup`) is static and doesn't need rotation. It's not used for real API requests, only for data corrections.

## Migration from Old System

If you have existing keys without lifecycle tracking:

```bash
# Initialize lifecycle table
sqlite3 /opt/oai-to-circuit/quota.db <<EOF
-- Ensure lifecycle table exists
CREATE TABLE IF NOT EXISTS key_lifecycle (
    subkey TEXT PRIMARY KEY,
    user_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    revoked_at TIMESTAMP,
    revoke_reason TEXT,
    replaced_by TEXT,
    replaces TEXT
);

-- Populate with existing keys (all marked as active)
INSERT OR IGNORE INTO key_lifecycle (subkey, user_id, status)
SELECT subkey, email, 'active'
FROM subkey_names;
EOF
```

## Security Considerations

1. **Immediate Revocation**: Revoked keys stop working within seconds (next quota check)
2. **No Grace Period**: Don't rely on delayed revocation
3. **Audit Trail**: All rotations logged with timestamp and reason
4. **Historical Preservation**: Old data never deleted (compliance, cost allocation)
5. **Key Strength**: All generated keys use 256-bit entropy

## Summary

- **Revoke keys immediately** when compromised
- **Rotate keys regularly** per security policy
- **Preserve all historical data** for reporting and compliance
- **Link keys by user_id or email** for reporting continuity
- **Document every rotation** with a clear reason

The system ensures that revoking a key doesn't lose any historical data while preventing future use of compromised credentials.

---

## Related Documentation

- **[Key Rotation Quick Start](key-rotation-quickstart.md)** - TL;DR version for quick reference
- **[Subkey Management Guide](subkey-management.md)** - Complete subkey lifecycle
- **[Database Queries](database-queries.md)** - Useful SQL queries for key tracking
- **[Dashboard Features](dashboard-features.md)** - Splunk dashboard usage reporting

---

**[← Back to Documentation Home](../README.md)**

