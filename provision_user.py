#!/usr/bin/env python3
"""
One-shot user provisioning - generates subkey and adds friendly name.

This combines:
1. Subkey generation (like generate_subkeys.py)
2. Name assignment (like add_subkey_names_table.py)
3. Optional quota assignment

Usage:
    python3 provision_user.py \\
      --prefix fie_gurkan \\
      --name "Gurkan Gokdemir" \\
      --email "ggokdemi@cisco.com" \\
      --description "Field Innovation Engineering" \\
      --quota-requests 1000 \\
      --quota-tokens 1000000
"""

import argparse
import json
import os
import secrets
import sqlite3
import sys
from pathlib import Path


def generate_subkey(prefix: str) -> str:
    """Generate a secure subkey with the given prefix."""
    # Generate 32 random bytes (256 bits), encode as base64-like string
    random_part = secrets.token_urlsafe(32)
    # Remove padding and make URL-safe
    random_part = random_part.replace('-', '').replace('_', '')[:32]
    return f"{prefix}_{random_part}"


def add_to_database(db_path: str, subkey: str, name: str, email: str, description: str) -> None:
    """Add the subkey and name to the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Ensure the table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subkey_names (
            subkey TEXT PRIMARY KEY,
            friendly_name TEXT NOT NULL,
            email TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Insert the name
    cursor.execute("""
        INSERT INTO subkey_names (subkey, friendly_name, email, description)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(subkey) DO UPDATE SET
            friendly_name = excluded.friendly_name,
            email = excluded.email,
            description = excluded.description,
            updated_at = CURRENT_TIMESTAMP
    """, (subkey, name, email, description))
    
    conn.commit()
    conn.close()


def add_to_quotas_file(quotas_path: str, subkey: str, requests: int, tokens: int) -> None:
    """Add quota limits to quotas.json file."""
    # Read existing quotas
    if os.path.exists(quotas_path):
        with open(quotas_path, 'r') as f:
            quotas = json.load(f)
    else:
        quotas = {}
    
    # Add new user quota
    quotas[subkey] = {
        "*": {
            "requests": requests,
            "total_tokens": tokens
        }
    }
    
    # Write back
    with open(quotas_path, 'w') as f:
        json.dump(quotas, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Provision a new user with subkey and friendly name",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Provision Gurkan
  python3 provision_user.py \\
    --prefix fie_gurkan \\
    --name "Gurkan Gokdemir" \\
    --email "ggokdemi@cisco.com" \\
    --description "Field Innovation Engineering" \\
    --quota-requests 1000 \\
    --quota-tokens 1000000

  # Provision Hutch
  python3 provision_user.py \\
    --prefix fie_hutch \\
    --name "Hutch Hutchinson" \\
    --email "huhutchi@cisco.com" \\
    --description "Field Innovation Engineering"

  # Provision without quotas (unlimited)
  python3 provision_user.py \\
    --prefix team_ml \\
    --name "ML Team" \\
    --email "ml-team@example.com"
        """
    )
    
    # Required arguments
    parser.add_argument(
        "--prefix",
        required=True,
        help="Prefix for the subkey (e.g., fie_gurkan, fie_dave)"
    )
    
    parser.add_argument(
        "--name",
        required=True,
        help="Friendly name (e.g., 'Gurkan Gokdemir')"
    )
    
    # Optional arguments
    parser.add_argument(
        "--email",
        default="",
        help="Email address"
    )
    
    parser.add_argument(
        "--description",
        default="",
        help="Description (e.g., 'Field Innovation Engineering')"
    )
    
    parser.add_argument(
        "--db",
        default="/var/lib/oai-to-circuit/quota.db",
        help="Path to quota database (default: /var/lib/oai-to-circuit/quota.db)"
    )
    
    parser.add_argument(
        "--quotas-file",
        default="quotas.json",
        help="Path to quotas.json file (default: quotas.json)"
    )
    
    parser.add_argument(
        "--quota-requests",
        type=int,
        help="Request limit (omit for unlimited)"
    )
    
    parser.add_argument(
        "--quota-tokens",
        type=int,
        help="Token limit (omit for unlimited)"
    )
    
    parser.add_argument(
        "--no-quotas",
        action="store_true",
        help="Don't add to quotas.json (unlimited access)"
    )
    
    parser.add_argument(
        "--output-format",
        choices=["text", "json", "env"],
        default="text",
        help="Output format (default: text)"
    )
    
    args = parser.parse_args()
    
    try:
        # Generate subkey
        subkey = generate_subkey(args.prefix)
        
        # Add to database
        add_to_database(
            args.db,
            subkey,
            args.name,
            args.email,
            args.description
        )
        
        # Add to quotas file if requested
        quota_added = False
        if not args.no_quotas and (args.quota_requests or args.quota_tokens):
            add_to_quotas_file(
                args.quotas_file,
                subkey,
                args.quota_requests or 999999,
                args.quota_tokens or 999999999
            )
            quota_added = True
        
        # Output based on format
        if args.output_format == "json":
            output = {
                "subkey": subkey,
                "name": args.name,
                "email": args.email,
                "description": args.description,
                "quota_added": quota_added
            }
            if quota_added:
                output["quota_requests"] = args.quota_requests
                output["quota_tokens"] = args.quota_tokens
            print(json.dumps(output, indent=2))
        
        elif args.output_format == "env":
            print(f"export SUBKEY_{args.prefix.upper().replace('-', '_')}='{subkey}'")
        
        else:  # text
            print("=" * 70)
            print("✓ User Provisioned Successfully!")
            print("=" * 70)
            print()
            print(f"Name:        {args.name}")
            if args.email:
                print(f"Email:       {args.email}")
            if args.description:
                print(f"Description: {args.description}")
            print()
            print("Subkey:")
            print(f"  {subkey}")
            print()
            
            if quota_added:
                print("Quotas:")
                if args.quota_requests:
                    print(f"  Requests:    {args.quota_requests:,}")
                if args.quota_tokens:
                    print(f"  Tokens:      {args.quota_tokens:,}")
                print(f"  File:        {args.quotas_file}")
                print()
            else:
                print("Quotas:      Unlimited (not added to quotas.json)")
                print()
            
            print("Next Steps:")
            print("  1. Send the subkey to the user securely")
            print("  2. Restart the service if quotas were updated:")
            print("     sudo systemctl restart oai-to-circuit")
            print("  3. User can now make requests with their subkey")
            print()
            print("User's code example:")
            print("  from openai import OpenAI")
            print("  client = OpenAI(")
            print(f"      api_key='{subkey}',")
            print("      base_url='https://your-server/v1'")
            print("  )")
            print()
            print("=" * 70)
    
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

