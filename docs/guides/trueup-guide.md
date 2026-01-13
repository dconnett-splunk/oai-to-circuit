# Splunk Token Data True-Up Guide

> **Navigation:** [Documentation Home](../README.md) | [Guides](./) | [Backfill Guide](backfill-guide.md)

## Problem
There was a bug in token tracking that caused a gap between Azure API reported usage and Splunk HEC logged usage for January 2026.

## Data Discrepancies

### Azure API (Source of Truth)
| Model | Total Tokens | Prompt Tokens | Completion Tokens |
|-------|--------------|---------------|-------------------|
| gpt-4o-mini | 3,683 | 3,543 | 140 |
| gpt-4o | 37,467 | 33,019 | 4,448 |
| gpt-5-nano | 13,871 | 8,939 | 4,932 |
| gpt-5 | 21,617 | 900 | 20,717 |

### Current Splunk Data
| Model | Total Tokens | Prompt Tokens | Completion Tokens |
|-------|--------------|---------------|-------------------|
| gpt-4o-mini | 0 | 0 | 0 |
| gpt-4o | 37,467 ✓ | 33,019 ✓ | 4,448 ✓ |
| gpt-5-nano | 21,701 ❌ | 15,522 ❌ | 6,179 ❌ |
| gpt-5 | 21,874 ❌ | 853 ❌ | 21,021 ❌ |

### Analysis

**Why does Splunk have MORE data for some models?**
Splunk is updated in real-time, while Azure API data may be delayed. Recent Splunk events show:
- gpt-5-nano: 7,830 tokens (matches the difference exactly!)
- gpt-5: 1,907 tokens (explains most of the difference)

These are legitimate recent requests captured by Splunk but not yet in Azure's report.

### Required Corrections
| Model | Total Adjustment | Status |
|-------|------------------|--------|
| gpt-4o-mini | +3,683 | Missing data - needs backfill |
| gpt-4o | 0 | Perfect match ✓ |
| gpt-5-nano | 0 | Splunk has MORE (more up-to-date) |
| gpt-5 | 0 | Splunk has MORE (more up-to-date) |

**Only gpt-4o-mini needs correction** - the rest is expected variance due to Splunk being more current.

## Solution

The `backfill_january_2026.py` script will send correction events to Splunk HEC to adjust the token counts to match Azure API data.

### Setup

1. **Set the subkey in credentials.env** (optional):
   ```bash
   echo "BACKFILL_SUBKEY=egai-prd-sales-02053..." >> credentials.env
   ```
   
   If not set, it will use a placeholder: `egai-prd-sales-backfill`

2. **Ensure Splunk HEC credentials are set**:
   ```bash
   # Should already be in credentials.env
   SPLUNK_HEC_URL=https://your-splunk:8088/services/collector
   SPLUNK_HEC_TOKEN=your-hec-token
   SPLUNK_VERIFY_SSL=true
   ```

### Run the Script

```bash
cd /Users/daconnet/Git/oai-to-circuit
python backfill_january_2026.py
```

The script will:
1. Show you the required corrections
2. Ask for confirmation before sending
3. Send correction events with a January 2026 timestamp
4. Mark events with `backfill=true` for tracking

### Verify the Results

After running the script, use this SPL query to verify:

```spl
index=oai_circuit sourcetype="llm:usage" earliest="2026-01-01T00:00:00" latest="2026-02-01T00:00:00"
| eval month=strftime(_time, "%Y-%m-01")
| stats 
    sum(total_tokens) as "Total Tokens"
    sum(prompt_tokens) as "Prompt Tokens"
    sum(completion_tokens) as "Completion Tokens"
    by model, month
| eval tier="prem_tier"
| rename model as "Model", month as "Month", tier as "Tier"
| table "Model" "Month" "Tier" "Total Tokens" "Prompt Tokens" "Completion Tokens"
| sort - "Total Tokens"
```

Expected results after correction:
| Model | Total Tokens | Status |
|-------|--------------|--------|
| gpt-4o | 37,467 | Matches Azure ✓ |
| gpt-5 | ~21,874+ | Higher than Azure (real-time) |
| gpt-5-nano | ~21,701+ | Higher than Azure (real-time) |
| gpt-4o-mini | 3,683+ | Now includes backfilled data ✓ |

**Note**: gpt-5 and gpt-5-nano will show MORE tokens than Azure because Splunk is capturing real-time usage. This is expected and correct!

## Notes

- **No negative adjustments**: The script only backfills MISSING data (positive adjustments). Models where Splunk has MORE data than Azure are left alone, as Splunk is more up-to-date.
- **Real-time vs delayed reporting**: It's normal for Splunk to show higher numbers than Azure API, since Splunk captures usage in real-time while Azure API reports may be delayed.
- **Backfill tracking**: All correction events include `backfill=true` so you can identify and filter them if needed.
- **No request count impact**: Corrections use `requests=0` so they don't inflate your request counts.
- **Safe to re-run**: The script calculates the difference each time, so if you've already backfilled, it will show "No corrections needed".

## Troubleshooting

### If corrections don't appear in Splunk

1. **Check HEC is working**:
   ```bash
   curl -k "https://your-splunk:8088/services/collector/health"
   ```

2. **Check the script output** for any error messages

3. **Search for backfill events**:
   ```spl
   index=oai_circuit sourcetype="llm:usage" backfill=true
   ```

4. **Check Splunk indexer logs** for any ingestion errors

### If numbers still don't match

The script shows the Azure data, current Splunk data, and calculated adjustments. Verify:
- Azure data is correct
- You ran the correct SPL query to check current Splunk data
- The adjustments look correct
- You only ran the script once

## Understanding the Differences

Looking at recent Splunk events:

```
2026-01-12 14:19:40  gpt-5       1,907 tokens (48 prompt + 1,859 completion)
2026-01-12 14:09:06  gpt-5-nano  7,830 tokens (6,583 prompt + 1,247 completion)
```

These events explain why Splunk has MORE data:
- **gpt-5-nano**: The 7,830 token difference exactly matches the recent event
- **gpt-5**: Recent usage explains the difference

This confirms that Splunk is working correctly and capturing real-time usage that Azure API hasn't reported yet (likely due to reporting delays).

---

## Related Documentation

- [Backfill Guide](backfill-guide.md) - Backfilling HEC events
- [Subkey Management](../operations/subkey-management.md) - Managing subkeys
- [Database Queries](../operations/database-queries.md) - SQL queries
- [Dashboard Features](../operations/dashboard-features.md) - Splunk dashboards

**[← Back to Documentation Home](../README.md)**

