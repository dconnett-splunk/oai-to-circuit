#!/usr/bin/env python3
"""
Unified Backfill Script for Splunk HEC Token Data

This script can backfill token usage data to Splunk HEC for true-up purposes.
All backfill events use a static subkey for easy correlation and have backfill=true flag.

Usage Examples:
    # Interactive mode - edit the data in the script and run
    python3 backfill.py
    
    # From command line with inline data
    python3 backfill.py --model gpt-4o-mini --total 3683 --prompt 3543 --completion 140
    
    # Multiple models at once
    python3 backfill.py \
        --entry gpt-4o-mini,3683,3543,140 \
        --entry gpt-4o,1000,800,200
    
    # Specify a custom date
    python3 backfill.py --date 2026-01-15 --model gpt-4o --total 1000 --prompt 800 --completion 200
"""

import os
import sys
import argparse
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional

# Add the oai_to_circuit directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'oai_to_circuit'))

from oai_to_circuit.splunk_hec import SplunkHEC

# Load environment variables
def load_env_file():
    """Load environment variables from credentials.env if it exists."""
    env_paths = [
        '/etc/oai-to-circuit/credentials.env',
        'credentials.env',
        '/opt/oai-to-circuit/credentials.env',
    ]
    
    for env_path in env_paths:
        if os.path.exists(env_path):
            print(f"✓ Loading credentials from: {env_path}")
            try:
                from dotenv import load_dotenv
                load_dotenv(env_path)
                return env_path
            except ImportError:
                # Manual parsing if dotenv not available
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip().strip('"').strip("'")
                            if key not in os.environ:
                                os.environ[key] = value
                return env_path
    
    print("⚠️  WARNING: Could not find credentials.env in standard locations")
    print("   Tried: /etc/oai-to-circuit/credentials.env, ./credentials.env, /opt/oai-to-circuit/credentials.env")
    return None


# Static backfill subkey - consistent across all backfill operations
BACKFILL_SUBKEY = "system-backfill-trueup"
BACKFILL_FRIENDLY_NAME = "System Backfill"
BACKFILL_EMAIL = "backfill@system"


def parse_entry_string(entry: str) -> Dict:
    """Parse an entry string like 'gpt-4o,1000,800,200' into a dict."""
    parts = entry.split(',')
    if len(parts) != 4:
        raise ValueError(f"Invalid entry format: {entry}. Expected: model,total,prompt,completion")
    
    return {
        "model": parts[0].strip(),
        "total_tokens": int(parts[1].strip()),
        "prompt_tokens": int(parts[2].strip()),
        "completion_tokens": int(parts[3].strip()),
    }


def get_backfill_data_from_args(args) -> List[Dict]:
    """Get backfill data from command line arguments."""
    entries = []
    
    # Single entry from --model/--total/--prompt/--completion
    if args.model:
        if not all([args.total is not None, args.prompt is not None, args.completion is not None]):
            raise ValueError("When using --model, must also specify --total, --prompt, and --completion")
        
        entries.append({
            "model": args.model,
            "total_tokens": args.total,
            "prompt_tokens": args.prompt,
            "completion_tokens": args.completion,
        })
    
    # Multiple entries from --entry
    if args.entry:
        for entry_str in args.entry:
            entries.append(parse_entry_string(entry_str))
    
    return entries


def get_backfill_data_interactive() -> List[Dict]:
    """
    Define backfill data here for interactive mode.
    Edit this section when you need to backfill data.
    """
    return [
        # Example entries - replace with your actual data
        # {
        #     "model": "gpt-4o-mini",
        #     "total_tokens": 3683,
        #     "prompt_tokens": 3543,
        #     "completion_tokens": 140,
        #     "reason": "Missing data from 2026-01-01 due to tracking bug",
        # },
    ]


def main():
    parser = argparse.ArgumentParser(
        description='Backfill token usage data to Splunk HEC',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single model backfill
  %(prog)s --model gpt-4o-mini --total 3683 --prompt 3543 --completion 140
  
  # Multiple models
  %(prog)s --entry "gpt-4o-mini,3683,3543,140" --entry "gpt-4o,1000,800,200"
  
  # With custom date and reason
  %(prog)s --date 2026-01-15 --reason "Bug fix true-up" --model gpt-4o --total 1000 --prompt 800 --completion 200
  
  # Interactive mode (edit data in script)
  %(prog)s
        """
    )
    
    # Single entry arguments
    parser.add_argument('--model', help='Model name (e.g., gpt-4o-mini)')
    parser.add_argument('--total', type=int, help='Total tokens')
    parser.add_argument('--prompt', type=int, help='Prompt tokens')
    parser.add_argument('--completion', type=int, help='Completion tokens')
    
    # Multiple entry argument
    parser.add_argument('--entry', action='append',
                        help='Entry in format: model,total,prompt,completion (can specify multiple times)')
    
    # Common arguments
    parser.add_argument('--date', help='Date for backfill (YYYY-MM-DD, default: today)')
    parser.add_argument('--reason', default='Data true-up',
                        help='Reason for backfill (default: "Data true-up")')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be sent without actually sending')
    parser.add_argument('--yes', action='store_true',
                        help='Skip confirmation prompt')
    
    args = parser.parse_args()
    
    print("="*80)
    print("SPLUNK HEC BACKFILL TOOL")
    print("="*80)
    
    # Load credentials
    env_file = load_env_file()
    
    # Get backfill data
    try:
        backfill_data = get_backfill_data_from_args(args)
        if not backfill_data:
            print("\nNo command line arguments provided, using interactive mode...")
            backfill_data = get_backfill_data_interactive()
    except ValueError as e:
        print(f"\n✗ ERROR: {e}")
        return 1
    
    if not backfill_data:
        print("\n✗ ERROR: No backfill data specified")
        print("\nPlease either:")
        print("  1. Edit the get_backfill_data_interactive() function in this script")
        print("  2. Use command line arguments: --model, --total, --prompt, --completion")
        print("  3. Use --entry 'model,total,prompt,completion'")
        print("\nRun with --help for examples")
        return 1
    
    # Determine timestamp
    if args.date:
        try:
            date_obj = datetime.strptime(args.date, "%Y-%m-%d")
            timestamp = date_obj.replace(hour=12, minute=0, second=0, tzinfo=timezone.utc).isoformat()
        except ValueError:
            print(f"\n✗ ERROR: Invalid date format: {args.date}. Use YYYY-MM-DD")
            return 1
    else:
        timestamp = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0).isoformat()
    
    # Display configuration
    print(f"\nBackfill Configuration:")
    print(f"  Subkey:        {BACKFILL_SUBKEY}")
    print(f"  Friendly Name: {BACKFILL_FRIENDLY_NAME}")
    print(f"  Email:         {BACKFILL_EMAIL}")
    print(f"  Timestamp:     {timestamp}")
    print(f"  Reason:        {args.reason}")
    print(f"  Dry Run:       {args.dry_run}")
    
    # Display data to backfill
    print(f"\nData to Backfill:")
    print("-"*80)
    for i, entry in enumerate(backfill_data, 1):
        reason_note = f" ({entry.get('reason', '')})" if 'reason' in entry else ""
        print(f"{i}. {entry['model']:15} "
              f"Total: {entry['total_tokens']:>6}, "
              f"Prompt: {entry['prompt_tokens']:>6}, "
              f"Completion: {entry['completion_tokens']:>6}"
              f"{reason_note}")
    print("-"*80)
    
    # Initialize Splunk HEC
    hec_url = os.getenv('SPLUNK_HEC_URL')
    hec_token = os.getenv('SPLUNK_HEC_TOKEN')
    verify_ssl = os.getenv('SPLUNK_VERIFY_SSL', 'true').lower() == 'true'
    
    if not hec_url or not hec_token:
        print("\n✗ ERROR: SPLUNK_HEC_URL and SPLUNK_HEC_TOKEN must be set")
        print("\nSet them in credentials.env:")
        print("  SPLUNK_HEC_URL=https://your-splunk:8088/services/collector")
        print("  SPLUNK_HEC_TOKEN=your-hec-token")
        return 1
    
    print(f"\nSplunk HEC Configuration:")
    print(f"  URL:        {hec_url}")
    print(f"  Token:      {hec_token[:10]}...")
    print(f"  Verify SSL: {verify_ssl}")
    
    # Confirm before sending
    if not args.yes and not args.dry_run:
        print("\n" + "="*80)
        response = input(f"\nSend {len(backfill_data)} backfill event(s) to Splunk HEC? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return 0
    
    # Initialize HEC client
    splunk_hec = SplunkHEC(
        hec_url=hec_url,
        hec_token=hec_token,
        hash_subkeys=True,
        verify_ssl=verify_ssl,
    )
    
    # Send backfill events
    print("\n" + "="*80)
    print("Sending Backfill Events...")
    print("="*80)
    
    success_count = 0
    
    for i, entry in enumerate(backfill_data, 1):
        model = entry["model"]
        total = entry["total_tokens"]
        prompt = entry["prompt_tokens"]
        completion = entry["completion_tokens"]
        entry_reason = entry.get("reason", args.reason)
        
        print(f"\n[{i}/{len(backfill_data)}] {model}: {total} tokens (prompt={prompt}, completion={completion})")
        
        if args.dry_run:
            print("     [DRY RUN] Would send to Splunk HEC")
            success_count += 1
            continue
        
        additional_fields = {
            "timestamp": timestamp,
            "backfill": True,
            "backfill_reason": entry_reason,
            "backfill_subkey": BACKFILL_SUBKEY,
            "source_system": "backfill_script",
        }
        
        success = splunk_hec.send_usage_event(
            subkey=BACKFILL_SUBKEY,
            model=model,
            requests=0,  # Don't count as a request, just token adjustment
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            additional_fields=additional_fields,
            preserve_timestamp=True,
            friendly_name=BACKFILL_FRIENDLY_NAME,
            email=BACKFILL_EMAIL,
        )
        
        if success:
            print("     ✓ SUCCESS - Event sent to Splunk HEC")
            success_count += 1
        else:
            print("     ✗ FAILED - Could not send event")
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total entries:     {len(backfill_data)}")
    print(f"Successfully sent: {success_count}")
    print(f"Failed:            {len(backfill_data) - success_count}")
    
    if success_count == len(backfill_data):
        print("\n✓ All backfill events sent successfully!")
        
        print("\nVerification Query:")
        print("-"*80)
        print("""
index=oai_circuit sourcetype="llm:usage" backfill=true
| table _time, model, total_tokens, prompt_tokens, completion_tokens, backfill_reason
| sort - _time
""")
        
        print("\nTo see impact on totals:")
        print("-"*80)
        date_str = timestamp.split('T')[0]
        print(f"""
index=oai_circuit sourcetype="llm:usage" earliest="{date_str}T00:00:00" latest="{date_str}T23:59:59"
| stats sum(total_tokens) as total_tokens, sum(prompt_tokens) as prompt_tokens, sum(completion_tokens) as completion_tokens by model
| sort - total_tokens
""")
    
    print("="*80)
    
    return 0 if success_count == len(backfill_data) else 1


if __name__ == "__main__":
    sys.exit(main())

