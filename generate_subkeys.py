#!/usr/bin/env python3
"""
Generate secure subkeys for API access control.

Subkeys are used to identify callers and enforce per-user quotas.
"""

import argparse
import secrets
import string
import sys
from typing import List


def generate_subkey(prefix: str = "", length: int = 32) -> str:
    """Generate a cryptographically secure random subkey.
    
    Args:
        prefix: Optional prefix for the key (e.g., "team_", "user_")
        length: Length of the random portion (default: 32)
    
    Returns:
        A secure random subkey string
    """
    # Use URL-safe characters (alphanumeric + hyphen + underscore)
    alphabet = string.ascii_letters + string.digits + "-_"
    random_part = ''.join(secrets.choice(alphabet) for _ in range(length))
    
    if prefix:
        # Ensure prefix ends with underscore for readability
        if not prefix.endswith("_"):
            prefix += "_"
        return f"{prefix}{random_part}"
    
    return random_part


def generate_batch(count: int, prefix: str = "", length: int = 32) -> List[str]:
    """Generate multiple subkeys at once.
    
    Args:
        count: Number of keys to generate
        prefix: Optional prefix for all keys
        length: Length of random portion per key
    
    Returns:
        List of generated subkeys
    """
    return [generate_subkey(prefix=prefix, length=length) for _ in range(count)]


def main():
    parser = argparse.ArgumentParser(
        description="Generate secure subkeys for oai-to-circuit API access control",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate a single key
  python generate_subkeys.py

  # Generate 5 keys
  python generate_subkeys.py --count 5

  # Generate keys with a team prefix
  python generate_subkeys.py --count 3 --prefix "team_alpha"

  # Generate shorter keys (16 chars)
  python generate_subkeys.py --length 16

  # Generate keys and save to file
  python generate_subkeys.py --count 10 --output subkeys.txt

Usage:
  1. Generate subkeys using this script
  2. Add subkeys to quotas.json with desired limits:
     {
       "team_alpha_xyz123": {
         "gpt-4o-mini": {"requests": 1000},
         "*": {"requests": 100}
       }
     }
  3. Distribute subkeys to users
  4. Users include subkey in requests via:
     - Header: X-Bridge-Subkey: <subkey>
     - Or: Authorization: Bearer <subkey>
        """
    )
    
    parser.add_argument(
        "--count", "-c",
        type=int,
        default=1,
        help="Number of subkeys to generate (default: 1)"
    )
    parser.add_argument(
        "--prefix", "-p",
        type=str,
        default="",
        help="Prefix for generated keys (e.g., 'team_alpha', 'user')"
    )
    parser.add_argument(
        "--length", "-l",
        type=int,
        default=32,
        help="Length of random portion (default: 32)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output file path (if not specified, prints to stdout)"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.count < 1:
        print("Error: count must be at least 1", file=sys.stderr)
        sys.exit(1)
    
    if args.length < 8:
        print("Error: length must be at least 8 for security", file=sys.stderr)
        sys.exit(1)
    
    # Generate keys
    keys = generate_batch(count=args.count, prefix=args.prefix, length=args.length)
    
    # Output
    if args.output:
        try:
            with open(args.output, "w") as f:
                for key in keys:
                    f.write(f"{key}\n")
            print(f"Generated {len(keys)} subkey(s) and saved to {args.output}", file=sys.stderr)
        except IOError as e:
            print(f"Error writing to {args.output}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Print to stdout (one per line)
        for key in keys:
            print(key)
        
        if args.count == 1:
            print("\nExample usage:", file=sys.stderr)
            print(f"  curl -H 'X-Bridge-Subkey: {keys[0]}' http://localhost:12000/v1/chat/completions ...", file=sys.stderr)


if __name__ == "__main__":
    main()

