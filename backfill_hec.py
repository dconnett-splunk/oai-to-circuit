#!/usr/bin/env python3
"""
Backfill HEC data from log entries.

This script parses log lines containing "Sending usage event to Splunk HEC"
and sends them to Splunk HEC, optionally excluding already-sent events.

Usage:
    python backfill_hec.py < logfile.txt
    python backfill_hec.py --exclude-timestamp "2026-01-07T21:08:16.953866+00:00" < logfile.txt
"""

import sys
import json
import re
import time
import argparse
from datetime import datetime

# Add parent directory to path for imports
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from oai_to_circuit.config import load_config
from oai_to_circuit.splunk_hec import SplunkHEC


def parse_log_line(line: str):
    """
    Parse a log line and extract the JSON event data.
    
    Expected format:
    Jan 07 20:25:56 ... - Sending usage event to Splunk HEC: {"subkey": "...", ...}
    """
    # Look for JSON data after "Sending usage event to Splunk HEC:"
    match = re.search(r'Sending usage event to Splunk HEC: ({.*})$', line)
    if not match:
        return None
    
    try:
        event_data = json.loads(match.group(1))
        return event_data
    except json.JSONDecodeError:
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Backfill Splunk HEC data from log entries'
    )
    parser.add_argument(
        '--exclude-timestamp',
        action='append',
        dest='exclude_timestamps',
        help='Exclude events with this timestamp (can be specified multiple times)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Parse and show events but do not send to HEC'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=0.1,
        help='Delay in seconds between HEC requests (default: 0.1)'
    )
    
    args = parser.parse_args()
    
    # Load config
    config = load_config()
    
    if not config.splunk_hec_url or not config.splunk_hec_token:
        print("❌ Error: SPLUNK_HEC_URL and SPLUNK_HEC_TOKEN must be configured")
        print("\nSet them in credentials.env or environment variables:")
        print("  SPLUNK_HEC_URL=https://your-splunk:8088/services/collector/event")
        print("  SPLUNK_HEC_TOKEN=your-token-here")
        return 1
    
    # Initialize Splunk HEC
    hec = SplunkHEC(
        hec_url=config.splunk_hec_url,
        hec_token=config.splunk_hec_token,
        source=config.splunk_source,
        sourcetype=config.splunk_sourcetype,
        index=config.splunk_index,
        verify_ssl=config.splunk_verify_ssl,
        hash_subkeys=True,  # Enable hashing to match production
    )
    
    print(f"\n{'='*70}")
    print("SPLUNK HEC BACKFILL TOOL")
    print(f"{'='*70}")
    print(f"HEC URL: {config.splunk_hec_url}")
    print(f"Index: {config.splunk_index}")
    print(f"SSL Verification: {config.splunk_verify_ssl}")
    print(f"Dry Run: {args.dry_run}")
    print(f"Delay: {args.delay}s")
    
    if args.exclude_timestamps:
        print(f"\nExcluding timestamps:")
        for ts in args.exclude_timestamps:
            print(f"  - {ts}")
    
    print(f"\n{'='*70}")
    print("Reading log lines from stdin...")
    print(f"{'='*70}\n")
    
    # Process log lines from stdin
    events_parsed = 0
    events_excluded = 0
    events_sent = 0
    events_failed = 0
    
    exclude_set = set(args.exclude_timestamps or [])
    
    for line_num, line in enumerate(sys.stdin, 1):
        event_data = parse_log_line(line.strip())
        
        if not event_data:
            continue
        
        events_parsed += 1
        
        # Check if this event should be excluded
        timestamp = event_data.get('timestamp', '')
        if timestamp in exclude_set:
            print(f"⏭️  Skipping excluded event: timestamp={timestamp}")
            events_excluded += 1
            continue
        
        # Extract fields
        subkey = event_data.get('subkey', 'unknown')
        model = event_data.get('model', 'unknown')
        prompt_tokens = event_data.get('prompt_tokens', 0)
        completion_tokens = event_data.get('completion_tokens', 0)
        total_tokens = event_data.get('total_tokens', 0)
        requests = event_data.get('requests', 1)
        
        # Additional fields
        additional_fields = {}
        if 'status_code' in event_data:
            additional_fields['status_code'] = event_data['status_code']
        if 'success' in event_data:
            additional_fields['success'] = event_data['success']
        
        print(
            f"📝 Event {events_parsed}: {timestamp} - "
            f"subkey={subkey[:20]}..., model={model}, tokens={total_tokens}"
        )
        
        if args.dry_run:
            print(f"   [DRY RUN] Would send to HEC")
            events_sent += 1
        else:
            # Send to HEC
            success = hec.send_usage_event(
                subkey=subkey,
                model=model,
                requests=requests,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                additional_fields=additional_fields,
            )
            
            if success:
                print(f"   ✅ Sent successfully")
                events_sent += 1
            else:
                print(f"   ❌ Failed to send")
                events_failed += 1
            
            # Add delay to avoid overwhelming HEC
            if args.delay > 0:
                time.sleep(args.delay)
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"Events parsed:   {events_parsed}")
    print(f"Events excluded: {events_excluded}")
    print(f"Events sent:     {events_sent}")
    print(f"Events failed:   {events_failed}")
    print(f"{'='*70}\n")
    
    if events_failed > 0:
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

