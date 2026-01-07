#!/usr/bin/env python3
"""
Generate usage reports with friendly names instead of raw subkeys.

Reads from the quota database and uses the subkey_names table to display
human-readable names in reports.
"""

import argparse
import sqlite3
import sys
from datetime import datetime
from typing import List, Tuple


def get_usage_by_name(db_path: str) -> List[Tuple]:
    """Get usage statistics with friendly names."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    query = """
        SELECT 
            COALESCE(n.friendly_name, u.subkey) as name,
            u.model,
            u.requests,
            u.prompt_tokens,
            u.completion_tokens,
            u.total_tokens,
            n.description
        FROM usage u
        LEFT JOIN subkey_names n ON u.subkey = n.subkey
        ORDER BY u.requests DESC
    """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    
    return rows


def get_summary_by_name(db_path: str) -> List[Tuple]:
    """Get summary statistics grouped by friendly name."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    query = """
        SELECT 
            COALESCE(n.friendly_name, u.subkey) as name,
            SUM(u.requests) as total_requests,
            SUM(u.total_tokens) as total_tokens,
            COUNT(DISTINCT u.model) as models_used,
            n.description
        FROM usage u
        LEFT JOIN subkey_names n ON u.subkey = n.subkey
        GROUP BY COALESCE(n.friendly_name, u.subkey), n.description
        ORDER BY total_requests DESC
    """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    
    return rows


def get_model_summary(db_path: str) -> List[Tuple]:
    """Get usage by model across all users."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    query = """
        SELECT 
            model,
            SUM(requests) as total_requests,
            SUM(total_tokens) as total_tokens,
            COUNT(DISTINCT subkey) as unique_users
        FROM usage
        GROUP BY model
        ORDER BY total_requests DESC
    """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    
    return rows


def print_detailed_report(db_path: str) -> None:
    """Print detailed usage report with friendly names."""
    print("=" * 120)
    print(f"{'OpenAI Bridge Usage Report - Detailed':^120}")
    print(f"{'Generated: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'):^120}")
    print("=" * 120)
    print()
    
    rows = get_usage_by_name(db_path)
    
    if not rows:
        print("No usage data found.")
        return
    
    print(f"{'User/Team':<30} {'Model':<20} {'Requests':>10} {'Tokens':>12} {'Description':<30}")
    print("-" * 120)
    
    for name, model, requests, prompt_tokens, completion_tokens, total_tokens, description in rows:
        name_short = (name[:27] + "...") if len(name) > 30 else name
        desc_short = (description[:27] + "...") if description and len(description) > 30 else (description or "")
        print(f"{name_short:<30} {model:<20} {requests:>10} {total_tokens:>12,} {desc_short:<30}")
    
    print()


def print_summary_report(db_path: str) -> None:
    """Print summary usage report grouped by user."""
    print("=" * 100)
    print(f"{'OpenAI Bridge Usage Report - Summary':^100}")
    print(f"{'Generated: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'):^100}")
    print("=" * 100)
    print()
    
    rows = get_summary_by_name(db_path)
    
    if not rows:
        print("No usage data found.")
        return
    
    print(f"{'User/Team':<30} {'Total Requests':>15} {'Total Tokens':>15} {'Models Used':>12} {'Description':<25}")
    print("-" * 100)
    
    total_requests = 0
    total_tokens = 0
    
    for name, requests, tokens, models, description in rows:
        name_short = (name[:27] + "...") if len(name) > 30 else name
        desc_short = (description[:22] + "...") if description and len(description) > 25 else (description or "")
        print(f"{name_short:<30} {requests:>15,} {tokens:>15,} {models:>12} {desc_short:<25}")
        total_requests += requests
        total_tokens += tokens
    
    print("-" * 100)
    print(f"{'TOTAL':<30} {total_requests:>15,} {total_tokens:>15,}")
    print()


def print_model_report(db_path: str) -> None:
    """Print usage by model."""
    print("=" * 80)
    print(f"{'Usage by Model':^80}")
    print("=" * 80)
    print()
    
    rows = get_model_summary(db_path)
    
    if not rows:
        print("No usage data found.")
        return
    
    print(f"{'Model':<25} {'Total Requests':>15} {'Total Tokens':>15} {'Unique Users':>12}")
    print("-" * 80)
    
    for model, requests, tokens, users in rows:
        print(f"{model:<25} {requests:>15,} {tokens:>15,} {users:>12}")
    
    print()


def export_csv(db_path: str, output_file: str) -> None:
    """Export detailed report to CSV."""
    import csv
    
    rows = get_usage_by_name(db_path)
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['User/Team', 'Model', 'Requests', 'Prompt Tokens', 'Completion Tokens', 'Total Tokens', 'Description'])
        
        for row in rows:
            writer.writerow(row)
    
    print(f"✓ Exported to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate usage reports with friendly names",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Summary report
  python generate_usage_report.py --summary

  # Detailed report
  python generate_usage_report.py --detailed

  # Model usage report
  python generate_usage_report.py --by-model

  # All reports
  python generate_usage_report.py --all

  # Export to CSV
  python generate_usage_report.py --detailed --csv report.csv
        """
    )
    
    parser.add_argument(
        "--db",
        default="/var/lib/oai-to-circuit/quota.db",
        help="Path to quota database"
    )
    
    parser.add_argument("--summary", action="store_true", help="Show summary by user")
    parser.add_argument("--detailed", action="store_true", help="Show detailed usage")
    parser.add_argument("--by-model", action="store_true", help="Show usage by model")
    parser.add_argument("--all", action="store_true", help="Show all reports")
    parser.add_argument("--csv", help="Export detailed report to CSV file")
    
    args = parser.parse_args()
    
    # Default to summary if no flags specified
    if not (args.summary or args.detailed or args.by_model or args.all or args.csv):
        args.summary = True
    
    try:
        if args.all:
            print_summary_report(args.db)
            print()
            print_detailed_report(args.db)
            print()
            print_model_report(args.db)
        else:
            if args.summary:
                print_summary_report(args.db)
            
            if args.detailed:
                print_detailed_report(args.db)
            
            if args.by_model:
                print_model_report(args.db)
        
        if args.csv:
            export_csv(args.db, args.csv)
    
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

