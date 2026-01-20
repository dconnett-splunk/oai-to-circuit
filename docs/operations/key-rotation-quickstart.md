# Key Rotation Quick Start

> **Navigation:** [Documentation Home](../README.md) | [Operations](../operations/) | [Full Guide](key-rotation.md)

> **📖 For complete documentation, see the [Key Rotation Guide](key-rotation.md)**

## TL;DR

```bash
# Revoke a compromised key
python3 rotate_key.py --revoke OLD_KEY --reason "Compromised"

# Rotate a key (generate replacement)
python3 rotate_key.py --rotate OLD_KEY --prefix fie_alice --reason "Regular rotation"

# Check key status
python3 rotate_key.py --status KEY
```

## How It Works

1. **Historical data is preserved** - All usage remains in database and Splunk
2. **Revoked keys stop immediately** - Quotas set to 0, `status != 'active'` 
3. **Reporting continuity** - Link keys by email or user_id
4. **Full audit trail** - All rotations tracked with timestamp and reason

## Database Changes

New table: `key_lifecycle`
- Tracks key status (`active`, `revoked`, `replaced`)
- Links old and new keys (`replaced_by`, `replaces`)
- Groups keys by user (`user_id`)

## Integration Points

### 1. Quota Manager (`quota.py`)

Updated `is_subkey_authorized()`:
```python
# Now checks:
1. Is key in quotas.json? ✓
2. Is key in database? ✓
3. Is key status = 'active'? ✓  # NEW
```

Revoked keys return `False` → Request rejected with 403

### 2. Splunk Reporting

Group by email (automatic):
```spl
index=oai_circuit sourcetype="llm:usage"
| stats sum(total_tokens) by email, model
```

All keys with same email aggregate automatically!

### 3. quotas.json

Revoked keys:
- Set to `{"requests": 0, "total_tokens": 0}`
- Kept in file (not deleted)
- Metadata added: `_REVOKED_keyname`

## Common Scenarios

### Key Compromise
```bash
# Immediate revocation + replacement
python3 rotate_key.py --rotate COMPROMISED_KEY --prefix fie_alice --reason "Key exposed"
# Give new key to user
```

### Employee Departure  
```bash
# Revoke only (no replacement)
python3 rotate_key.py --revoke DEPARTED_KEY --reason "Employee departed"
# Historical data preserved for cost allocation
```

### Regular Rotation (Policy)
```bash
# Every 90 days
python3 rotate_key.py --rotate OLD_KEY --prefix fie_alice --reason "90-day policy"
# Same name/email, new key
```

## Reporting Examples

### User's Total Usage (All Keys)
```spl
index=oai_circuit email="alice@example.com"
| stats sum(total_tokens) as tokens by model
```

### Usage Before/After Rotation
```spl
index=oai_circuit email="alice@example.com"  
| eval period=if(_time < 1737331200, "Old Key", "New Key")
| stats sum(tokens) by period
```

### Find All Rotations
```sql
SELECT subkey, status, revoked_at, revoke_reason, replaced_by
FROM key_lifecycle
WHERE status != 'active'
ORDER BY revoked_at DESC;
```

## Safety Features

✅ **Immediate effect** - Revoked keys stop working instantly  
✅ **No data loss** - All historical usage preserved  
✅ **Audit trail** - Every rotation logged with reason  
✅ **Confirmation prompt** - Prevents accidents (use `--yes` to skip)  
✅ **Status check** - See key state before making changes  

## Migration

Existing systems work unchanged:
- Keys without lifecycle records default to `active`
- Historical data remains accessible
- No breaking changes to APIs or Splunk queries

Add lifecycle tracking gradually:
```bash
# Initialize lifecycle for all existing keys
sqlite3 quota.db <<EOF
INSERT OR IGNORE INTO key_lifecycle (subkey, user_id, status)
SELECT subkey, email, 'active' FROM subkey_names;
EOF
```

## What Happens When You Rotate?

```
Before Rotation:
┌─────────────────────┐
│ fie_alice_old123    │ Status: active ✅
│ Email: alice@co.com │ Quotas: normal
│ Usage: 1M tokens    │ Can make requests: YES
└─────────────────────┘

python3 rotate_key.py --rotate fie_alice_old123 --prefix fie_alice --reason "Policy"

After Rotation:
┌─────────────────────┐  ┌─────────────────────┐
│ fie_alice_old123    │  │ fie_alice_new456    │
│ Status: replaced ❌ │  │ Status: active ✅   │
│ Email: alice@co.com │  │ Email: alice@co.com │
│ Quotas: 0           │  │ Quotas: normal      │
│ Usage: 1M (kept!)   │  │ Usage: 0 (new)      │
│ Replaced by: new456 │←─┤ Replaces: old123    │
└─────────────────────┘  └─────────────────────┘
                          New key distributed→
```

Both keys link to same email → Splunk aggregates automatically

## Files

- `rotate_key.py` - Main rotation tool
- `KEY_ROTATION_GUIDE.md` - Comprehensive documentation
- `quota.py` - Updated to check lifecycle status
- Database schema updated with `key_lifecycle` table

## Full Documentation

See **[Key Rotation Guide](key-rotation.md)** for:
- Complete examples
- Automation scripts
- Security best practices
- Splunk query library
- Troubleshooting guide

---

## Related Documentation

- **[Key Rotation Guide](key-rotation.md)** - Complete documentation
- **[Subkey Management](subkey-management.md)** - Full subkey lifecycle
- **[Database Queries](database-queries.md)** - SQL queries for key tracking

---

**[← Back to Documentation Home](../README.md)**

