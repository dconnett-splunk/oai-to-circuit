#!/usr/bin/env python3
"""
Simple demo using the OpenAI Python SDK against the local OpenAI-to-Circuit bridge.

Usage:
  # HTTP (default)
  python python_openai_demo.py --prompt "Say hello from the bridge"

  # HTTPS with self-signed cert (server started with --ssl or --ssl-only)
  python python_openai_demo.py --https --prompt "Say hello over HTTPS"

  # Streaming
  python python_openai_demo.py --stream --prompt "Count to 5"

Requires:
  pip install openai httpx
"""

import argparse
import os
import sys
import httpx
from typing import List, Dict

try:
    from openai import OpenAI
except Exception:
    print("This demo requires the 'openai' package. Install with: pip install openai httpx", file=sys.stderr)
    raise


def build_client(use_https: bool, insecure_skip_verify: bool) -> OpenAI:
    if use_https:
        base_url = "https://localhost:12443/v1"
        http_client = httpx.Client(verify=not insecure_skip_verify)
        return OpenAI(base_url=base_url, api_key="demo_key", http_client=http_client)
    else:
        base_url = "http://localhost:12000/v1"
        return OpenAI(base_url=base_url, api_key="demo_key")


def run_chat_completion(client: OpenAI, model: str, prompt: str, stream: bool) -> None:
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": prompt},
    ]

    if stream:
        response_stream = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )
        print("Streaming response:\n")
        for chunk in response_stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print()
    else:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
        )
        print(response.choices[0].message.content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenAI SDK demo against local bridge")
    parser.add_argument("--prompt", required=True, help="User prompt to send")
    parser.add_argument("--model", default=os.environ.get("DEMO_MODEL", "gpt-4o-mini"), help="Model/deployment name")
    parser.add_argument("--https", action="store_true", help="Use https://localhost:12443/v1")
    parser.add_argument(
        "--insecure-skip-verify",
        action="store_true",
        help="Skip TLS verification for self-signed certs (HTTPS only)",
    )
    parser.add_argument("--stream", action="store_true", help="Stream tokens as they arrive")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = build_client(use_https=args.https, insecure_skip_verify=args.insecure_skip_verify)
    run_chat_completion(client=client, model=args.model, prompt=args.prompt, stream=args.stream)


if __name__ == "__main__":
    main()


