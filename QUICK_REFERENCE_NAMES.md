# Friendly Names - Quick Reference

## TL;DR

✅ **All done!** The system now automatically includes friendly names in Splunk HEC events.

## Quick Commands

### Check what needs names
```bash
python check_and_setup_names.py
```

### Add a name
```bash
python add_subkey_names_table.py --add \
  --subkey "your_key_here" \
  --name "Your Name (Team)"
```

### List all names
```bash
python add_subkey_names_table.py --list
```

### Restart service
```bash
sudo systemctl restart oai-to-circuit
```

## What Changed

| Component | Change |
|-----------|--------|
| **Database** | `subkey_names` table auto-created on startup |
| **QuotaManager** | New `get_friendly_name()` method |
| **SplunkHEC** | Events include `friendly_name` field |
| **App** | Automatically looks up and passes names |
| **Backfill** | Includes names when re-sending data |

## Example HEC Event

```json
{
  "subkey": "sha256:1a2b3c4d5e6f7890",
  "friendly_name": "Dave (FIE Team)",
  "model": "gpt-4o-mini",
  "requests": 1,
  "total_tokens": 200
}
```

## Splunk Query Example

```spl
index=oai_circuit sourcetype="llm:usage"
| stats sum(total_tokens) as tokens by friendly_name, model
| sort -tokens
```

## Files

- `check_and_setup_names.py` - Check current state
- `add_subkey_names_table.py` - Manage names
- `SUBKEY_NAMES_SETUP.md` - Full setup guide
- `CHANGES_SUMMARY.md` - Complete technical details

## SQLite Question

**Q: Does SQLite support stored procedures?**

**A: No**, but we don't need them. We use Python methods in `QuotaManager` for business logic instead.

## Next Steps

1. Run `python check_and_setup_names.py`
2. Add names for active keys
3. Restart service: `sudo systemctl restart oai-to-circuit`
4. Update Splunk dashboards to use `friendly_name`
5. Done! 🎉

