# Splunk Dashboard Features

## Overview

The updated Splunk dashboard (`splunk_dashboard_token_usage.xml`) now includes intelligent handling of friendly names and subkey hashing.

## New Features

### 1. Automatic Friendly Name Display

All panels now use the `friendly_name` field when available, falling back to the subkey if no name is set.

**SPL Pattern:**
```spl
| eval display_name=coalesce(friendly_name, subkey)
```

### 2. Hashed vs Non-Hashed Detection

The dashboard can detect whether a subkey is hashed (starts with `sha256:`) or not.

**SPL Pattern:**
```spl
| eval is_hashed=if(match(subkey, "^sha256:"), "Yes", "No")
```

### 3. Enhanced Top Users Panel

The "Top 10 Users by Token Usage" panel now shows:
- User's friendly name (or subkey if no name)
- Whether the subkey is hashed
- All usage statistics

### 4. User Summary with Names

New panel showing:
- All users with their friendly names
- Which users have names assigned
- Models used by each user
- Average tokens per request

### 5. Name Assignment Tracking

New pie chart showing token distribution between:
- Users with friendly names assigned
- Users without friendly names (need to be set up)

### 6. Recent Requests with Names

The recent requests table now shows:
- Friendly names instead of hashed subkeys
- Type indicator (hashed vs plain)
- All standard request details

## Useful Queries

### Find Users Without Names

```spl
index=oai_circuit sourcetype="llm:usage"
| eval has_name=if(isnotnull(friendly_name), "Has Name", "Needs Name")
| stats sum(total_tokens) as tokens, sum(requests) as requests by subkey, has_name
| where has_name="Needs Name"
| sort -tokens
```

This shows which subkeys are actively using the service but don't have friendly names yet.

### Usage by Named Users

```spl
index=oai_circuit sourcetype="llm:usage"
| where isnotnull(friendly_name)
| stats sum(total_tokens) as total_tokens, sum(requests) as requests by friendly_name
| sort -total_tokens
```

### Compare Hashed vs Non-Hashed Subkeys

```spl
index=oai_circuit sourcetype="llm:usage"
| eval key_type=if(match(subkey, "^sha256:"), "Hashed", "Non-Hashed")
| stats sum(total_tokens) as total_tokens by key_type
```

This helps verify that your subkeys are being hashed properly for privacy.

### Usage by Email Domain (if emails are set)

```spl
index=oai_circuit sourcetype="llm:usage"
| where isnotnull(friendly_name)
| rex field=email ".*@(?<domain>.*)"
| stats sum(total_tokens) as tokens by domain, friendly_name
| sort -tokens
```

**Note:** Emails are not currently exported to HEC events (only stored in the database). If you want this, you'd need to modify the `splunk_hec.py` to include email in additional_fields.

## Dashboard Sections

### Row 1: Summary Statistics
- Total tokens, requests, avg tokens/request, unique users
- Now uses friendly names for unique user count

### Row 2: Token Usage Trend
- Predictive analytics for next 24 hours
- Unchanged from original

### Row 3: Token Breakdown
- Prompt vs completion tokens
- Unchanged from original

### Row 4: Usage by Model
- Token usage and request rate by model
- Unchanged from original

### Row 5: Top Users and Model Distribution
- **UPDATED:** Now shows friendly names and hash status
- Model distribution pie chart unchanged

### Row 6: Hourly and Daily Patterns
- Unchanged from original

### Row 7: Success Rate and Errors
- Unchanged from original

### Row 8: Recent API Requests
- **UPDATED:** Shows friendly names and key type

### Row 9: User Summary (NEW)
- Table showing all users with names and usage stats
- Pie chart showing % of traffic from named vs unnamed users

## Smart Fallback Logic

All queries use `coalesce(friendly_name, subkey)` which means:

1. **If friendly_name exists:** Show the friendly name
2. **If friendly_name is NULL:** Show the raw/hashed subkey

This ensures the dashboard works correctly whether or not you've assigned names to your subkeys.

## Privacy Considerations

The dashboard queries work with:
- **Hashed subkeys** (format: `sha256:abc123...`) - Exported by default for privacy
- **Friendly names** (format: `"Dave (FIE Team)"`) - Human-readable, exported alongside hashed keys
- **Raw subkeys** - Only present in your database, never exported to Splunk

## Installation

1. Copy the XML to your Splunk dashboard:
   ```bash
   cp splunk_dashboard_token_usage.xml /path/to/splunk/dashboards/
   ```

2. Or paste the contents into Splunk Web:
   - Go to Dashboards → Create New Dashboard
   - Click "Source" and paste the XML
   - Save

3. Adjust time ranges and index names if needed

## Customization

To modify the dashboard:

1. **Change time range:** Update `<earliest>` and `<latest>` tags
2. **Change index:** Update `index=oai_circuit` to your index name
3. **Add fields:** Extend queries with additional fields from your HEC events
4. **Add panels:** Copy existing panel structure and modify queries

## Troubleshooting

### Names not showing up

**Check if names are in HEC events:**
```spl
index=oai_circuit sourcetype="llm:usage"
| head 10
| table _raw
```

Look for `"friendly_name"` in the raw events.

### All users showing as "Unnamed"

This means friendly_name is NULL in your HEC events. Check:

1. Are names in the database?
   ```bash
   sudo sqlite3 /var/lib/oai-to-circuit/quota.db "SELECT * FROM subkey_names;"
   ```

2. Did you restart the service after adding the QuotaManager changes?
   ```bash
   sudo systemctl restart oai-to-circuit
   ```

3. Check the service logs:
   ```bash
   sudo journalctl -u oai-to-circuit -n 50 | grep friendly_name
   ```

### Dashboard shows "No results"

- Check your index name matches (`index=oai_circuit`)
- Check your sourcetype matches (`sourcetype="llm:usage"`)
- Check time range includes data
- Verify HEC is sending events successfully

